"""Recon API — REST endpoints + serves the dashboard and brief."""
import logging
import re
from datetime import date, timedelta, datetime, timezone
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select, func, or_, text
from sqlalchemy.orm import Session
from config import settings
from db import (
    Base, engine, SessionLocal, Company, Role, Application, ApplicationEvent, ResumeFile,
    MailMessage,
    Contact, DailyBrief, ScanRun, PushSubscription, Resume, ResumeExperience,
    Interview, Material, AutofillProfile, DeviceToken, Startup, StartupContact,
)
from seed.companies import seed as seed_companies

logging.basicConfig(level=settings.log_level)
log = logging.getLogger("recon.api")

app = FastAPI(title="Recon", version="1.0.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_schema():
    """Additive, idempotent column adds for existing DBs (create_all only makes
    new *tables*, not new columns). Non-destructive — safe to run every boot."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE roles ADD COLUMN IF NOT EXISTS metro VARCHAR"))
        # provenance: 'ats' (default) | 'jsearch' | 'usajobs' — Postgres backfills existing rows.
        conn.execute(text("ALTER TABLE roles ADD COLUMN IF NOT EXISTS source VARCHAR DEFAULT 'ats'"))
        # full JD text — previously only the hash was kept, so the scorer graded blind to the JD.
        conn.execute(text("ALTER TABLE roles ADD COLUMN IF NOT EXISTS description TEXT"))
        # user feedback (up/down) for feed filtering + scoring calibration.
        conn.execute(text("ALTER TABLE roles ADD COLUMN IF NOT EXISTS interest VARCHAR"))
        conn.execute(text("ALTER TABLE roles ADD COLUMN IF NOT EXISTS interest_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE scan_runs ADD COLUMN IF NOT EXISTS searched BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE roles ADD COLUMN IF NOT EXISTS is_mba BOOLEAN"))
        conn.execute(text("ALTER TABLE roles ADD COLUMN IF NOT EXISTS state VARCHAR"))
        conn.execute(text("ALTER TABLE companies ADD COLUMN IF NOT EXISTS sector VARCHAR"))
        # "never show this employer again" (2026-09-21).
        conn.execute(text("ALTER TABLE companies ADD COLUMN IF NOT EXISTS dismissed_at TIMESTAMPTZ"))
        # Backlog vs. arrival (2026-09-21): a board's first scan is its back
        # catalogue, not today's news.
        conn.execute(text("ALTER TABLE companies ADD COLUMN IF NOT EXISTS first_scanned_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE roles ADD COLUMN IF NOT EXISTS is_backfill BOOLEAN DEFAULT FALSE"))
        # Thread state for mail (2026-09-22).
        for col, typ in (("awaiting", "VARCHAR"), ("last_outbound_at", "TIMESTAMPTZ"),
                         ("last_message_at", "TIMESTAMPTZ"), ("message_count", "INTEGER DEFAULT 1")):
            conn.execute(text(f"ALTER TABLE mail_messages ADD COLUMN IF NOT EXISTS {col} {typ}"))
        # Standard application fields the 2026-09-21 portal survey turned up:
        # Greenhouse asks "Preferred First Name" separately from the legal first
        # name, and its education block is School / Degree / Discipline.
        for col in ("preferred_name", "discipline"):
            conn.execute(text(f"ALTER TABLE autofill_profile ADD COLUMN IF NOT EXISTS {col} VARCHAR"))
        # APNs environment per device token; NULL until send_apns() probes for it.
        conn.execute(text("ALTER TABLE device_tokens ADD COLUMN IF NOT EXISTS environment VARCHAR"))
        # Semantic embeddings: resize column from 1536 → 1024 (mxbai-embed-large).
        # Safe because the column is all-NULL at this point — the USING clause
        # just produces NULL for every row (no data loss).
        conn.execute(text("""
            DO $$ BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_attribute
                    WHERE  attrelid = 'roles'::regclass
                      AND  attname  = 'embedding'
                      AND  atttypmod <> 1024
                ) THEN
                    ALTER TABLE roles
                        ALTER COLUMN embedding
                        TYPE vector(1024)
                        USING NULL::vector(1024);
                END IF;
            END $$;
        """))
        conn.execute(text(
            "ALTER TABLE roles ADD COLUMN IF NOT EXISTS is_duplicate BOOLEAN DEFAULT FALSE"
        ))
        # Partial HNSW index: only covers rows that actually have an embedding,
        # so incremental backfill doesn't force a full index rebuild each scan.
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS roles_emb_hnsw
            ON roles USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            WHERE embedding IS NOT NULL
        """))


def _backfill_sector():
    """One-time backfill of companies.sector for rows that predate the column
    (and any that were auto-created before a name/keyword was added to the
    classifier). Only touches rows where sector IS NULL — no-op after the
    first pass, safe to re-run any time the classifier gains new names."""
    from seed.sectors import sector_for
    db = SessionLocal()
    try:
        rows = db.scalars(select(Company).where(Company.sector.is_(None))).all()
        n = 0
        for c in rows:
            s = sector_for(c.name)
            if s:
                c.sector = s
                n += 1
        if n:
            db.commit()
        log.info("startup: backfilled sector on %d/%d companies", n, len(rows))
    finally:
        db.close()


def _backfill_state():
    """Recompute roles.state for every role with a location, every boot —
    NOT gated on state IS NULL. states_csv() had a real classification bug
    until 2026-08-16 (single-value fallback picked whichever state matched
    earliest in a fixed dict order, not the state actually in the posting —
    e.g. a Denver/CO + LA/CA multi-location posting got mis-tagged CA-only,
    silently hiding it from the Colorado filter), so existing rows can carry
    wrong data, not just missing data. Recomputing all ~54K rows is fast
    enough to just always do it — self-heals if the classifier ever improves
    again, at negligible cost."""
    from scan.geo import states_csv
    db = SessionLocal()
    try:
        rows = db.scalars(select(Role).where(Role.location.isnot(None))).all()
        n = 0
        for r in rows:
            s = states_csv(r.location)
            if s != r.state:
                r.state = s
                n += 1
        if n:
            db.commit()
        log.info("startup: recomputed state on %d/%d roles", n, len(rows))
    finally:
        db.close()


def _backfill_metro():
    """One-time backfill of roles.metro for rows that predate the column.
    Only touches rows where metro IS NULL, so it's a no-op after the first pass."""
    from scan.geo import metro_of
    db = SessionLocal()
    try:
        rows = db.scalars(select(Role).where(Role.metro.is_(None),
                                             Role.location.isnot(None))).all()
        n = 0
        for r in rows:
            m = metro_of(r.location)
            if m:
                r.metro = m
                n += 1
        if n:
            db.commit()
        log.info("startup: backfilled metro on %d/%d roles", n, len(rows))
    finally:
        db.close()


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)   # safety net; creates new tables (e.g. resume) too
    _ensure_schema()
    _backfill_metro()
    _backfill_state()
    added = seed_companies()
    log.info("startup: seeded %d new companies", added)
    _backfill_sector()   # after seeding so freshly-seeded companies get tagged too
    from resume.seed import seed as seed_resume
    log.info("startup: seeded %d resume rows", seed_resume())


# ─── health ─────────────────────────────────────────────────
@app.get("/health")
def health():
    model = (settings.local_llm_model if settings.llm_provider == "local"
             else settings.claude_model)
    return {"status": "ok", "scoring_mode": settings.scoring_mode,
            "llm_provider": settings.llm_provider, "model": model}


# ─── roles ──────────────────────────────────────────────────
def _mode_for(cfg) -> str:
    return "intern" if cfg.intern_only else cfg.track_mode


# How far back "recently arrived, not yet scored" reaches (see include_unscored).
NEW_ARRIVAL_DAYS = 7


@app.get("/api/roles")
def list_roles(tier: str | None = None, company: str | None = None,
               min_fit: float = 0.0, scored_only: bool | None = None,
               track: str | None = None, metro: str | None = None,
               mba: bool | None = None, sector: str | None = None,
               states: str | None = None,   # comma-separated state/remote/international slugs — multi-select
               dedupe: bool = True, include_hidden: bool = False,
               include_unscored: bool = False,
               limit: int = 300, since_days: int | None = None,
               posted_since_days: int | None = None, include_backfill: bool = True,
               relevant_only: bool = True, us_only: bool = True,
               eligible_only: bool = True, target_only: bool = True,
               show_hidden: bool = False,
               db: Session = Depends(get_db)):
    """The tracker feed: open roles in the tracks Zach is watching, newest first.

    Relevance is the title classifier (`in_active_track`), not the scorer — with
    `TRACK_MODE=intern` that is internships only. `scored_only`/`include_unscored`
    are dead parameters kept so an older build of the app doesn't 500 mid-deploy;
    pass `scored_only=false` to browse the raw set, which skips the track filter.
    """
    import re as _re
    from scan.eligibility import eligibility_reason, off_target_reason
    from scan.geo import is_us
    from scan.intern_filter import (is_internship, is_ops_strategy,
                                    in_active_track)
    q = select(Role).where(Role.status.in_(["open", "changed"]))
    if not include_hidden:
        # Hide dismissed roles, roles from dismissed companies, and cross-source
        # near-duplicates. A dismissal is permanent: `interest`/`dismissed_at`
        # survive re-ingest, since the scan updates postings in place.
        q = q.where((Role.interest.is_(None)) | (Role.interest != "down"))
        q = q.where(Role.is_duplicate == False)  # noqa: E712
        q = q.where(Role.company_id.notin_(
            select(Company.id).where(Company.dismissed_at.isnot(None))))
    if since_days:
        q = q.where(Role.first_seen >= datetime.now(timezone.utc) - timedelta(days=since_days))
    if posted_since_days is not None:
        # Strictly the employer's posting date. A role with no posted_at is NOT
        # recent-by-default — that conflation is what made "posted today" mean
        # "a board I just connected dumped its back catalogue".
        q = q.where(Role.posted_at >= datetime.now(timezone.utc) - timedelta(days=posted_since_days))
    if not include_backfill:
        q = q.where(Role.is_backfill == False)  # noqa: E712
    if relevant_only and _mode_for(settings) == "intern":
        # Coarse SQL prefilter before the Python classifiers run. Without it
        # every request loaded all ~25k open roles — with their JD text — and
        # filtered them in a loop, so even limit=50 took 5.5s and the payload
        # was 820KB. The precise decision still belongs to in_active_track;
        # this just stops the database handing over the whole table first.
        q = q.where(or_(Role.title.ilike("%intern%"),
                        Role.title.ilike("%co-op%"),
                        Role.title.ilike("%coop%")))
    # The raw-browse hatch: scored_only=false skips the relevance filter below and
    # returns everything open. Default (None) is the tracker feed.
    raw_browse = scored_only is False
    if raw_browse:
        relevant_only = False
    if min_fit:
        q = q.where(Role.fit_score >= min_fit)
    if metro:
        q = q.where(Role.metro == metro)
    if mba is not None:
        q = q.where(Role.is_mba == mba)
    # Newest first by *posting* date where the board gives one, falling back to
    # when Recon first saw it. Ordering purely on first_seen put a newly
    # connected board's decade of history above this morning's real postings.
    rows = db.scalars(q.order_by(
        func.coalesce(Role.posted_at, Role.first_seen).desc().nullslast())).all()
    _mode = "intern" if settings.intern_only else settings.track_mode
    wanted_states = {s.strip() for s in states.split(",") if s.strip()} if states else None
    out = []
    for r in rows:
        co = r.company
        if company and co and company.lower() not in co.name.lower():
            continue
        if tier and co and co.tier != tier:
            continue
        if sector and (not co or co.sector != sector):
            continue
        # Role.state may hold multiple comma-joined codes (multi-location
        # postings) — match if ANY of the role's states is in the requested set.
        if wanted_states and not (set((r.state or "").split(",")) & wanted_states):
            continue
        if us_only and not is_us(r.location, r.state, r.title):
            # Zach is not relocating abroad. A posting with a US leg still
            # counts (see geo.is_us), and an unparseable location is kept
            # rather than hidden.
            continue
        # Why Recon is hiding it, if it is. Always computed, so the payload can
        # explain a hidden role rather than it just being absent.
        hidden = None
        if eligible_only:
            hidden = eligibility_reason(r.title, r.description)
        if hidden is None and target_only:
            hidden = off_target_reason(r.title, r.department)
        if hidden and not show_hidden:
            continue
        if relevant_only and not in_active_track(r.title, r.department, _mode):
            # Out of track: 24k of the ~25k open roles are full-time postings
            # Zach isn't watching. This is the feed's whole relevance filter now
            # that the scorer is off.
            continue
        if is_internship(r.title, r.department):
            role_track = "intern"
        elif is_ops_strategy(r.title, r.department):
            role_track = "ops"
        else:
            role_track = "fulltime"
        if track and role_track != track:
            continue
        out.append({
            "track": role_track,
            "id": r.id, "company": co.name if co else None,
            "company_id": r.company_id,     # lets the app dismiss the employer
            "company_tier": co.tier if co else None,
            "sector": co.sector if co else None,
            "is_mba": r.is_mba,
            "source": r.source or "ats",        # ats | jsearch | usajobs (provenance)
            "tier": r.score_tier,               # fit tier (A/B/C/pass) from scoring
            "title": r.title,
            "location": r.location, "metro": r.metro, "state": r.state, "url": r.url, "status": r.status,
            # A list payload doesn't need the whole JD — the card shows one
            # line and the detail view fetches the full text. 4000 chars per
            # role was most of an 820KB response.
            "description": (r.description or "")[:600] or None,
            "remote": r.remote_flag,
            "posted_at": r.posted_at.isoformat() if r.posted_at else None,
            "first_seen": r.first_seen.isoformat() if r.first_seen else None,
            "is_backfill": bool(r.is_backfill),   # arrived with a board's back catalogue
            "hidden_reason": hidden,              # why it's filtered, when it is
            "fit_score": r.fit_score, "domain": r.domain,
            "why_fit": r.why_fit, "concerns": r.concerns,
            "curriculum_hook": r.curriculum_hook,
            "tc_estimate": r.tc_estimate,       # pay / stipend
            "is_product_pm": r.is_product_pm,
            "interest": r.interest,             # "up" | "down" | None
        })

    if dedupe:
        # Collapse near-duplicate reposts: same company + normalized title, keep
        # the highest fit (then most recent posting).
        def _norm(t: str) -> str:
            t = (t or "").lower()
            t = _re.sub(r"\b(senior|sr|staff|principal|lead|junior|jr|i{1,3}|\d+)\b", " ", t)
            t = _re.sub(r"[^a-z0-9 ]+", " ", t)
            return _re.sub(r"\s+", " ", t).strip()
        best: dict[tuple, dict] = {}
        for o in out:
            key = ((o["company"] or "").lower(), _norm(o["title"]))
            cur = best.get(key)
            # Tie-break on first_seen, then id: fit_score is NULL for everything
            # now, and (0, posted_at) alone left the winner dependent on row
            # order, so two consecutive requests returned different ids for the
            # same duplicate pair.
            def _rank(x):
                return (x["fit_score"] or 0, x["posted_at"] or "", x["first_seen"] or "", x["id"])
            if cur is None or _rank(o) > _rank(cur):
                best[key] = o
        out = sorted(best.values(), key=lambda o: (o["first_seen"] or "", o["id"]), reverse=True)
    return out[:limit] if limit and limit > 0 else out


# ─── semantic role search ───────────────────────────────────
@app.get("/api/roles/search")
def search_roles(q: str, limit: int = 20, db: Session = Depends(get_db)):
    """Semantic nearest-neighbour search over embedded roles.

    Embeds the query string with the same model used for roles and returns
    the most similar open, scored, non-duplicate roles by cosine similarity.
    Falls back to an empty list when embeddings are not yet populated.
    """
    from embed import _embed_texts
    from config import settings as cfg
    if not cfg.embed_enabled:
        return []
    vecs = _embed_texts([q])
    if not vecs or vecs[0] is None:
        return []
    emb_str = "[" + ",".join(f"{v:.8f}" for v in vecs[0]) + "]"
    rows = db.execute(
        text("""
            SELECT r.id, 1 - (r.embedding <=> CAST(:emb AS vector)) AS sim
            FROM   roles r
            WHERE  r.status IN ('open', 'changed')
              AND  r.scored_at IS NOT NULL
              AND  r.embedding IS NOT NULL
              AND  r.is_duplicate = FALSE
              AND  (r.interest IS NULL OR r.interest <> 'down')
            ORDER  BY sim DESC
            LIMIT  :lim
        """),
        {"emb": emb_str, "lim": limit},
    ).fetchall()
    role_ids = {row.id: row.sim for row in rows}
    if not role_ids:
        return []
    roles = db.scalars(select(Role).where(Role.id.in_(role_ids))).all()
    result = []
    for r in sorted(roles, key=lambda x: role_ids.get(x.id, 0), reverse=True):
        co = r.company
        result.append({
            "id": r.id, "company": co.name if co else None,
            "title": r.title, "location": r.location,
            "fit_score": r.fit_score, "tier": r.score_tier,
            "why_fit": r.why_fit, "url": r.url,
            "similarity": round(role_ids[r.id], 3),
        })
    return result


# ─── embedding backfill (admin) ──────────────────────────────
@app.post("/api/admin/backfill-embeddings")
def backfill_embeddings(limit: int = 200, db: Session = Depends(get_db)):
    """Populate embeddings for open roles that don't have them yet.

    Processes `limit` roles per call (highest fit-score first).
    Call repeatedly until remaining=0.  Each call takes ~30–120s depending
    on gs65 load; safe to interrupt — progress is committed after each batch.
    """
    from embed import backfill as do_backfill
    return do_backfill(db, limit=limit)


# ─── metros (geo facet) ─────────────────────────────────────
@app.get("/api/metros")
def list_metros(scored_only: bool = True, db: Session = Depends(get_db)):
    """Target metros with a count of currently-open roles, for the geo facet."""
    from scan.geo import METROS
    q = select(Role.metro, func.count(Role.id)).where(
        Role.status.in_(["open", "changed"]), Role.metro.isnot(None))
    if scored_only:
        q = q.where(Role.scored_at.isnot(None))
    counts = dict(db.execute(q.group_by(Role.metro)).all())
    return [{"slug": s, "label": l, "count": counts.get(s, 0)} for s, l in METROS]


# ─── states (broad geo facet — every US state + remote + international) ────
@app.get("/api/states")
def list_states(scored_only: bool = True, db: Session = Depends(get_db)):
    from scan.geo import STATE_LABELS
    # Role.state can hold multiple comma-joined codes (a role open in several
    # cities counts under every state it lists) — split in Python rather than
    # SQL group-by, which would treat "CA,CO" as one distinct group.
    q = select(Role.state).where(Role.status.in_(["open", "changed"]), Role.state.isnot(None))
    if scored_only:
        q = q.where(Role.scored_at.isnot(None))
    counts: dict[str, int] = {}
    for (state_csv,) in db.execute(q).all():
        for code in state_csv.split(","):
            counts[code] = counts.get(code, 0) + 1
    return [{"slug": s, "label": l, "count": counts.get(s, 0)} for s, l in STATE_LABELS]


# ─── sectors (company facet) ─────────────────────────────────
_SECTOR_LABELS = [
    ("big_tech", "Big Tech"), ("finance", "Finance"),
    ("defense_aerospace", "Defense / Aerospace"), ("consulting", "Consulting"),
]


@app.get("/api/sectors")
def list_sectors(scored_only: bool = True, db: Session = Depends(get_db)):
    """Company sectors with a count of currently-open roles, for the sector facet."""
    q = (select(Company.sector, func.count(Role.id))
         .join(Role, Role.company_id == Company.id)
         .where(Role.status.in_(["open", "changed"]), Company.sector.isnot(None)))
    if scored_only:
        q = q.where(Role.scored_at.isnot(None))
    counts = dict(db.execute(q.group_by(Company.sector)).all())
    return [{"slug": s, "label": l, "count": counts.get(s, 0)} for s, l in _SECTOR_LABELS]


# ─── companies (Plan breakdown) ─────────────────────────────
@app.get("/api/companies")
def list_companies(db: Session = Depends(get_db)):
    from scan.intern_filter import is_internship, is_ops_strategy
    cos = db.scalars(select(Company).order_by(Company.name)).all()
    out = []
    for co in cos:
        open_roles = [r for r in co.roles if r.status in ("open", "changed")]
        surfaced = [r for r in open_roles
                    if r.scored_at is not None and (r.score_tier or "").upper() != "PASS"]
        out.append({
            "id": co.id, "name": co.name, "tier": co.tier,
            "ats_name": co.ats_name, "careers_url": co.careers_url, "notes": co.notes,
            "tracked": len(open_roles), "surfaced": len(surfaced),
        })
    # tier A first, then by surfaced desc
    rank = {"A": 0, "B": 1, "C": 2}
    out.sort(key=lambda c: (rank.get(c["tier"], 3), -c["surfaced"]))
    return out


# ─── applications (pipeline) ────────────────────────────────
class AppCreate(BaseModel):
    role_id: int | None = None
    company_name: str | None = None
    role_title: str | None = None
    role_url: str | None = None
    stage: str = "watching"


class AppUpdate(BaseModel):
    stage: str | None = None
    stage_note: str | None = None
    next_action: str | None = None
    next_action_due: date | None = None
    notes: str | None = None
    outcome: str | None = None


STAGES = ["watching", "drafting", "applied", "screen", "onsite", "offer", "closed"]


@app.get("/api/pipeline/stats")
def pipeline_stats(stale_days: int = 10, db: Session = Depends(get_db)):
    """Funnel counts + what needs action — powers the dashboard + reminders."""
    apps = db.scalars(select(Application)).all()
    today = date.today()
    counts = {s: 0 for s in STAGES}
    for a in apps:
        counts[a.stage] = counts.get(a.stage, 0) + 1

    due, stale = [], []
    for a in apps:
        if a.stage == "closed":
            continue
        if a.next_action_due and a.next_action_due <= today:
            due.append(a)
        elif a.stage == "applied" and a.applied_at and a.applied_at.date() <= today - timedelta(days=stale_days):
            stale.append(a)

    active = sum(counts[s] for s in STAGES if s != "closed")
    applied_plus = sum(counts[s] for s in ("applied", "screen", "onsite", "offer"))
    return {
        "stages": counts,
        "active": active,
        "need_action": len(due) + len(stale),
        "due": [_app_dict(a) for a in due],
        "stale": [_app_dict(a) for a in stale],
        "conversion": {
            "applied_to_screen": _rate(counts, "screen", "applied"),
            "screen_to_onsite": _rate(counts, "onsite", "screen"),
            "onsite_to_offer": _rate(counts, "offer", "onsite"),
            "applied_total": applied_plus,
        },
    }


def _rate(counts: dict, num_from: str, denom_from: str) -> float | None:
    # crude funnel: how many reached >= a stage vs the prior. Counts are current
    # occupancy, so use cumulative "reached at least this stage".
    order = STAGES
    reached = lambda s: sum(counts[x] for x in order[order.index(s):] if x != "closed") + counts.get("closed", 0) * 0
    d = reached(denom_from)
    return round(reached(num_from) / d, 2) if d else None


@app.get("/api/applications")
def list_apps(stage: str | None = None, db: Session = Depends(get_db)):
    q = select(Application)
    if stage:
        q = q.where(Application.stage == stage)
    return [_app_dict(a) for a in db.scalars(q.order_by(Application.updated_at.desc())).all()]


@app.post("/api/applications")
def create_app(body: AppCreate, db: Session = Depends(get_db)):
    if body.role_id:
        r = db.get(Role, body.role_id)
        if not r:
            raise HTTPException(404, "role not found")
        a = Application(role_id=r.id,
                        company_name=r.company.name if r.company else None,
                        role_title=r.title, role_url=r.url, stage=body.stage)
    else:
        a = Application(company_name=body.company_name, role_title=body.role_title,
                        role_url=body.role_url, stage=body.stage)
    db.add(a)
    db.commit()
    return _app_dict(a)


class RoleCreate(BaseModel):
    company: str                              # company name (created if unknown)
    title: str
    url: str | None = None
    location: str | None = None
    description: str | None = None
    score: bool = True                        # score immediately so it surfaces


@app.post("/api/roles")
def add_role_manually(body: RoleCreate, db: Session = Depends(get_db)):
    """Human/agent escape hatch: drop in a role found by hand on a proprietary
    board that no parser or the JSearch sweep reached. Creates the company if
    needed, geo-tags it, and (by default) scores it inline so it shows up now."""
    from scan.geo import metro_of
    from parsers.base import NormalizedRole
    co = db.scalar(select(Company).where(func.lower(Company.name) == body.company.strip().lower()))
    if co is None:
        co = Company(name=body.company.strip(), tier="B", ats_name="manual",
                     notes=f"auto-added via manual role entry {date.today()}")
        db.add(co)
        db.flush()
    nr = NormalizedRole(ats_job_id=f"manual:{body.url or body.title}",
                        title=body.title, location=body.location,
                        description=body.description or "")
    dup = db.scalar(select(Role).where(Role.company_id == co.id,
                                       Role.ats_job_id == nr.ats_job_id))
    if dup:
        raise HTTPException(409, f"role already tracked (id={dup.id})")
    role = Role(company_id=co.id, ats_job_id=nr.ats_job_id, source="manual",
                title=nr.title, location=nr.location, metro=metro_of(nr.location),
                remote_flag=nr.remote_flag, url=body.url, description=nr.description or None,
                description_hash=nr.description_hash, status="open")
    db.add(role)
    db.flush()
    if body.score:
        from scoring.claude_scorer import score_roles
        score_roles(db, [role])
    db.commit()
    return {"id": role.id, "company": co.name, "title": role.title,
            "metro": role.metro, "fit_score": role.fit_score, "tier": role.score_tier}


@app.patch("/api/applications/{app_id}")
def update_app(app_id: int, body: AppUpdate, db: Session = Depends(get_db)):
    a = db.get(Application, app_id)
    if not a:
        raise HTTPException(404, "application not found")
    if body.stage and body.stage != a.stage:
        db.add(ApplicationEvent(application_id=a.id, from_stage=a.stage,
                                 to_stage=body.stage, note=body.stage_note))
        a.stage = body.stage
        if body.stage == "applied" and a.applied_at is None:
            from datetime import datetime, timezone
            a.applied_at = datetime.now(timezone.utc)
    for f in ("next_action", "notes", "outcome"):
        v = getattr(body, f)
        if v is not None:
            setattr(a, f, v)
    if body.next_action_due is not None:
        a.next_action_due = body.next_action_due
    db.commit()
    return _app_dict(a)


@app.get("/api/applications/{app_id}/events")
def list_app_events(app_id: int, db: Session = Depends(get_db)):
    a = db.get(Application, app_id)
    if not a:
        raise HTTPException(404, "application not found")
    rows = db.scalars(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == app_id)
        .order_by(ApplicationEvent.at)
    ).all()
    return [{"id": e.id, "from_stage": e.from_stage, "to_stage": e.to_stage,
             "note": e.note, "at": e.at.isoformat() if e.at else None} for e in rows]


def _app_dict(a: Application) -> dict:
    return {"id": a.id, "company_name": a.company_name, "role_title": a.role_title,
            "role_url": a.role_url, "stage": a.stage, "outcome": a.outcome,
            "applied_at": a.applied_at.isoformat() if a.applied_at else None,
            "next_action": a.next_action,
            "next_action_due": a.next_action_due.isoformat() if a.next_action_due else None,
            "notes": a.notes,
            "fit_score": a.role.fit_score if a.role else None}


# ─── contacts (networking CRM) ──────────────────────────────
class ContactCreate(BaseModel):
    company_id: int | None = None
    company: str | None = None
    name: str | None = None
    role: str | None = None
    email: str | None = None
    linkedin: str | None = None
    warmth: str | None = None
    status: str | None = None
    last_touch: date | None = None
    next_touch: date | None = None
    last_outreach: str | None = None
    notes: str | None = None


class ContactUpdate(ContactCreate):
    pass


@app.get("/api/contacts")
def list_contacts(company_id: int | None = None, company: str | None = None,
                  db: Session = Depends(get_db)):
    q = select(Contact)
    if company_id:
        q = q.where(Contact.company_id == company_id)
    rows = db.scalars(q.order_by(Contact.created_at.desc())).all()
    if company:  # free-text "who do I know at X" — match company or role text
        cl = company.lower()
        rows = [c for c in rows if cl in ((c.company or "") + " " + (c.role or "")).lower()]
    return [_contact_dict(c) for c in rows]


@app.post("/api/contacts")
def create_contact(body: ContactCreate, db: Session = Depends(get_db)):
    c = Contact(**body.model_dump())
    db.add(c)
    db.commit()
    return _contact_dict(c)


@app.patch("/api/contacts/{contact_id}")
def update_contact(contact_id: int, body: ContactUpdate, db: Session = Depends(get_db)):
    c = db.get(Contact, contact_id)
    if not c:
        raise HTTPException(404, "contact not found")
    for f, v in body.model_dump(exclude_unset=True).items():
        setattr(c, f, v)
    db.commit()
    return _contact_dict(c)


# ─── startups tracker (fintech / defense / sustainability-energy / product-tech-data) ──
class StartupIn(BaseModel):
    name: str
    sector: str | None = None
    hq_location: str | None = None
    stage: str | None = None
    founded_year: int | None = None
    website: str | None = None
    one_liner: str | None = None
    notes: str | None = None


class StartupUpdate(BaseModel):
    sector: str | None = None
    hq_location: str | None = None
    stage: str | None = None
    founded_year: int | None = None
    website: str | None = None
    one_liner: str | None = None
    funding_summary: str | None = None
    notes: str | None = None


class StartupContactIn(BaseModel):
    name: str | None = None
    role: str | None = None
    email: str | None = None
    linkedin: str | None = None
    warmth: str | None = None
    notes: str | None = None


def _startup_dict(s: Startup) -> dict:
    return {
        "id": s.id, "name": s.name, "sector": s.sector, "hq_location": s.hq_location,
        "stage": s.stage, "founded_year": s.founded_year, "website": s.website,
        "one_liner": s.one_liner, "funding_summary": s.funding_summary, "notes": s.notes,
        "has_writeup": bool(s.writeup_markdown),
        "writeup_generated_at": s.writeup_generated_at.isoformat() if s.writeup_generated_at else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _startup_contact_dict(c: StartupContact) -> dict:
    return {"id": c.id, "startup_id": c.startup_id, "name": c.name, "role": c.role,
            "email": c.email, "linkedin": c.linkedin, "warmth": c.warmth, "notes": c.notes,
            "created_at": c.created_at.isoformat() if c.created_at else None}


@app.get("/api/startups")
def list_startups(sector: str | None = None, db: Session = Depends(get_db)):
    q = select(Startup)
    if sector:
        q = q.where(Startup.sector == sector)
    rows = db.scalars(q.order_by(Startup.name)).all()
    return [_startup_dict(s) for s in rows]


@app.post("/api/startups")
def create_startup(body: StartupIn, db: Session = Depends(get_db)):
    existing = db.scalar(select(Startup).where(Startup.name == body.name))
    if existing:
        raise HTTPException(409, "startup already tracked")
    s = Startup(**body.model_dump())
    db.add(s)
    db.commit()
    return _startup_dict(s)


@app.get("/api/startups/{startup_id}")
def get_startup(startup_id: int, db: Session = Depends(get_db)):
    s = db.get(Startup, startup_id)
    if not s:
        raise HTTPException(404, "startup not found")
    d = _startup_dict(s)
    d["writeup_markdown"] = s.writeup_markdown
    return d


@app.patch("/api/startups/{startup_id}")
def update_startup(startup_id: int, body: StartupUpdate, db: Session = Depends(get_db)):
    s = db.get(Startup, startup_id)
    if not s:
        raise HTTPException(404, "startup not found")
    for f, v in body.model_dump(exclude_unset=True).items():
        setattr(s, f, v)
    db.commit()
    return _startup_dict(s)


@app.delete("/api/startups/{startup_id}")
def delete_startup(startup_id: int, db: Session = Depends(get_db)):
    s = db.get(Startup, startup_id)
    if s:
        db.delete(s)
        db.commit()
    return {"status": "ok"}


@app.post("/api/startups/{startup_id}/writeup")
def startup_writeup(startup_id: int, db: Session = Depends(get_db)):
    """Generate (or regenerate) the in-depth writeup. On-demand only — never
    called by the scan pipeline — so this is the only place that cost is spent."""
    s = db.get(Startup, startup_id)
    if not s:
        raise HTTPException(404, "startup not found")
    from startups.researcher import generate_writeup
    return generate_writeup(db, s)


@app.get("/api/startups/{startup_id}/contacts")
def list_startup_contacts(startup_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(StartupContact).where(StartupContact.startup_id == startup_id)
                       .order_by(StartupContact.created_at.desc())).all()
    return [_startup_contact_dict(c) for c in rows]


@app.post("/api/startups/{startup_id}/contacts")
def create_startup_contact(startup_id: int, body: StartupContactIn, db: Session = Depends(get_db)):
    s = db.get(Startup, startup_id)
    if not s:
        raise HTTPException(404, "startup not found")
    c = StartupContact(startup_id=startup_id, **body.model_dump())
    db.add(c)
    db.commit()
    return _startup_contact_dict(c)


@app.post("/api/startups/discover")
def discover_startups(n: int = 10, db: Session = Depends(get_db)):
    """Bulk discovery pass: proposes `n` new startups Zach isn't tracking yet,
    adds them, and researches a writeup + contacts for each. Also runs weekly
    from worker/scheduler.py — this endpoint lets it be triggered on demand too."""
    from startups.researcher import run_discovery
    return run_discovery(db, n=n)


@app.post("/api/startups/{startup_id}/contacts/research")
def research_startup_contacts(startup_id: int, db: Session = Depends(get_db)):
    """Who-to-reach research (warm-path personas, never invented names) — same
    pattern as the role-networking feature, scoped to a startup instead of a role."""
    s = db.get(Startup, startup_id)
    if not s:
        raise HTTPException(404, "startup not found")
    from startups.researcher import who_to_reach
    return who_to_reach(db, s)


# ─── materials vault ────────────────────────────────────────
class MaterialIn(BaseModel):
    role_id: int | None = None
    application_id: int | None = None
    kind: str
    title: str | None = None
    content: str | None = None


def _mat_dict(m: Material) -> dict:
    return {"id": m.id, "role_id": m.role_id, "application_id": m.application_id,
            "kind": m.kind, "title": m.title, "content": m.content,
            "created_at": m.created_at.isoformat() if m.created_at else None}


@app.get("/api/materials")
def list_materials(role_id: int | None = None, application_id: int | None = None,
                   db: Session = Depends(get_db)):
    q = select(Material)
    if role_id is not None:
        q = q.where(Material.role_id == role_id)
    if application_id is not None:
        q = q.where(Material.application_id == application_id)
    rows = db.scalars(q.order_by(Material.created_at.desc())).all()
    return [_mat_dict(m) for m in rows]


@app.post("/api/materials")
def create_material(body: MaterialIn, db: Session = Depends(get_db)):
    m = Material(**body.model_dump())
    db.add(m); db.commit()
    return _mat_dict(m)


@app.delete("/api/materials/{mat_id}")
def delete_material(mat_id: int, db: Session = Depends(get_db)):
    m = db.get(Material, mat_id)
    if m:
        db.delete(m); db.commit()
    return {"status": "ok"}


# ─── dismissals ─────────────────────────────────────────────
# "Wipe it away and never show it again", per role and per employer. Both are
# permanent and survive re-ingest: the scan updates postings in place, so it
# never clears `interest`, and a dismissed company keeps being scanned (cheaper
# than special-casing intake) but never reaches the feed.


def _role_out_min(r: Role) -> dict:
    """The compact shape the dismissed list returns (no JD text)."""
    return {"id": r.id, "title": r.title,
            "company": r.company.name if r.company else None,
            "company_id": r.company_id,
            "location": r.location, "metro": r.metro, "state": r.state,
            "url": r.url, "source": r.source,
            "first_seen": r.first_seen.isoformat() if r.first_seen else None,
            "dismissed_at": r.interest_at.isoformat() if r.interest_at else None}


# ─── mail: know when someone replies ────────────────────────
# Recon proposes, Zach decides. Nothing in this section moves an application
# except `accept`, and that writes an ApplicationEvent so the pipeline can
# always explain why a stage changed.
# "Thank you for applying to Lunar Energy" — the shared ATS domains
# (us.greenhouse-mail.io) carry no company at all, so the subject is the only
# place the employer's name appears.
_SUBJECT_COMPANY_RES = [
    # "to"/"at" only, never "for": "submitted application FOR Zachary Collins"
    # names the candidate, and that is exactly what it extracted on the first
    # run — an application filed under Zach's own name.
    re.compile(r"(?:applying|application)\s+(?:to|at)\s+(.+?)[!.?]*$", re.I),
    re.compile(r"^(.+?)\s*[-–]\s*application\s+update", re.I),
    re.compile(r"thank you for your (?:interest in|application to)\s+(.+?)[!.?]*$", re.I),
]


def _company_from_subject(subject: str | None) -> str | None:
    if not subject:
        return None
    text = re.sub(r"\s+", " ", subject).strip()
    for pat in _SUBJECT_COMPANY_RES:
        m = pat.search(text)
        if m:
            name = m.group(1).strip(" !.,-–—")
            # Trim trailing role/req noise: "Acme for the PM Intern role".
            name = re.split(r"\s+\b(for|regarding|re|position|role|req)\b", name, flags=re.I)[0]
            if 2 < len(name) <= 80:
                return name
    return None


def _company_from_sender(from_addr: str | None) -> str | None:
    """Company name out of a From header.

    "NVIDIA HR <nvidia@myworkday.com>" -> NVIDIA. Falls back to the sending
    domain when there's no display name, skipping the ATS domains, which name
    the vendor rather than the employer.
    """
    if not from_addr:
        return None
    m = re.match(r'\s*"?([^"<]+?)"?\s*<', from_addr)
    if m:
        # "MasterCard People Services" is Mastercard; "Visa People Team" is Visa.
        name = re.sub(r"\b(hr|recruiting|recruitment|talent|careers?|team|hiring|"
                      r"people\s+services|people|services|notifications?|"
                      r"workday|icims|greenhouse|lever|ashby)\b", "",
                      m.group(1), flags=re.I)
        name = re.sub(r"@\s*\w*\s*$", "", name)          # "Joby Aviation @ icims"
        name = re.sub(r"\s+", " ", name).strip(" -|,@")
        # A human sender's name is not the company. "Zoe Downey
        # <zoe.downey@skydio.com>" is Skydio — the domain knows, the display
        # name doesn't.
        host_all = (re.search(r"@([\w.-]+)", from_addr) or [None, ""])[1].lower()
        from mail.gmail_client import ATS_SENDERS
        from_ats_domain = any(a in host_all for a in ATS_SENDERS)
        # Only second-guess the display name for non-ATS senders: ATS mail
        # always shows the employer there, and the heuristic below reads
        # two-word company names ("Joby Aviation") as people.
        looks_personal = (not from_ats_domain
                          and bool(re.fullmatch(r"[A-Z][a-z’\']+ [A-Z][a-z’\'-]+", name)))
        if len(name) > 2 and not looks_personal:
            return name[:80]
    # Workday and iCIMS put the tenant in the local part: nvidia@myworkday.com,
    # qualcomm@myworkday.com, amd+autoreply@talent.icims.com.
    local = re.match(r"\s*([\w.+-]+)@", from_addr.split("<")[-1])
    if local:
        tenant = re.split(r"[+.]", local.group(1))[0]
        if tenant.lower() not in {"no-reply", "noreply", "donotreply", "mail",
                                  "info", "careers", "jobs", "hr", "notifications"} \
                and len(tenant) > 2:
            host = (re.search(r"@([\w.-]+)", from_addr) or [None, ""])[1].lower()
            from mail.gmail_client import ATS_SENDERS
            if any(a in host for a in ATS_SENDERS):
                return tenant.replace("-", " ").title()[:80]
    dom = re.search(r"@([\w.-]+)", from_addr)
    if dom:
        host = dom.group(1).lower()
        from mail.gmail_client import ATS_SENDERS
        if any(a in host for a in ATS_SENDERS):
            return None      # names the ATS vendor, not the employer
        # Strip the routing labels employers put in front of the real name:
        # "mail.amazon.jobs" is Amazon, "us.company.com" is Company. Without
        # this the first label wins and applications get created as "Mail"
        # and "Us".
        generic = {"mail", "email", "e", "careers", "career", "jobs", "job",
                   "noreply", "no-reply", "notifications", "notification",
                   "recruiting", "talent", "hire", "hiring", "apply", "info",
                   "hello", "news", "us", "eu", "uk", "my", "www", "smtp"}
        labels = [l for l in host.split(".") if l not in generic]
        # Drop the TLD tail (com/io/co.uk/jobs...). Matched against a known set
        # rather than by length: "e.amd.com" is AMD, and a length rule eats it.
        tlds = {"com", "io", "co", "uk", "net", "org", "ai", "dev", "app", "us",
                "ca", "de", "fr", "inc", "jobs", "careers", "info", "xyz", "tech",
                "aero", "cloud", "digital", "health", "life", "works", "team",
                "me", "tv", "so", "gg", "sh", "fm", "space"}
        while len(labels) > 1 and labels[-1] in tlds:
            labels.pop()
        if labels and labels[-1] in tlds:
            labels.pop()          # single label that is itself a TLD: nothing usable
        if not labels:
            return None
        if labels:
            return labels[-1].replace("-", " ").title()[:80]
    return None


@app.get("/api/mail/status")
def mail_status(db: Session = Depends(get_db)):
    from mail.gmail_client import configured
    last = db.scalar(select(MailMessage).order_by(MailMessage.created_at.desc()))
    counts = dict(db.execute(
        select(MailMessage.status, func.count(MailMessage.id))
        .group_by(MailMessage.status)).all())
    return {"enabled": settings.mail_enabled, "configured": configured(),
            "last_seen_at": last.created_at.isoformat() if last and last.created_at else None,
            "counts": counts,
            "setup": None if configured() else
                     "run scripts/gmail_auth.py on the Mac, then set GMAIL_* in the NUC's .env"}


@app.post("/api/mail/poll")
def mail_poll(limit: int | None = None, db: Session = Depends(get_db)):
    from mail.poll import poll
    return poll(db, limit=limit)


@app.get("/api/mail/proposals")
def mail_proposals(status: str = "pending", limit: int = 50,
                   db: Session = Depends(get_db)):
    rows = db.scalars(
        select(MailMessage).where(MailMessage.status == status)
        .order_by(MailMessage.received_at.desc().nullslast()).limit(limit)).all()
    out = []
    for m in rows:
        app_row = m.application
        out.append({
            "id": m.id, "kind": m.kind, "proposed_stage": m.proposed_stage,
            "confidence": m.confidence, "evidence": m.evidence,
            "from": m.from_addr, "subject": m.subject, "snippet": m.snippet,
            "received_at": m.received_at.isoformat() if m.received_at else None,
            "awaiting": m.awaiting,
            "last_outbound_at": m.last_outbound_at.isoformat() if m.last_outbound_at else None,
            "message_count": m.message_count,
            "application_id": m.application_id,
            "company": app_row.company_name if app_row else None,
            "role_title": app_row.role_title if app_row else None,
            "current_stage": app_row.stage if app_row else None,
        })
    return out


@app.post("/api/mail/proposals/{proposal_id}/accept")
def mail_accept(proposal_id: int, stage: str | None = None,
                db: Session = Depends(get_db)):
    """Accept a proposal: move the application and log why.

    `stage` overrides the proposal — an acknowledgement proposes no move, but
    Zach may still want to mark something from it.
    """
    m = db.get(MailMessage, proposal_id)
    if not m:
        raise HTTPException(404, "proposal not found")
    target = stage or m.proposed_stage
    m.status = "accepted"
    moved = None
    created = None
    # A proposal with no application behind it is one Recon never knew about.
    # Accepting it creates the application from the mail itself — company from
    # the sender's display name, role from the subject where it can be read.
    if not m.application_id:
        # Sender first (it names the employer on most ATS mail), subject as the
        # fallback for shared domains like us.greenhouse-mail.io that name
        # nobody.
        company = (_company_from_sender(m.from_addr)
                   or _company_from_subject(m.subject) or "(unknown)")
        app_row = Application(company_name=company,
                              role_title=(m.subject or "")[:200] or None,
                              stage=target or "applied",
                              applied_at=m.received_at or datetime.now(timezone.utc),
                              notes=f"Created from email: {(m.subject or '')[:160]}")
        db.add(app_row)
        db.flush()
        db.add(ApplicationEvent(application_id=app_row.id, from_stage=None,
                                to_stage=app_row.stage,
                                note=f"Created from email from {m.from_addr}"))
        m.application_id = app_row.id
        created = {"id": app_row.id, "company": company}
        db.commit()
        return {"status": "ok", "id": m.id, "created_application": created,
                "moved_to": app_row.stage}
    if target and m.application_id:
        app_row = db.get(Application, m.application_id)
        if app_row and app_row.stage != target:
            db.add(ApplicationEvent(
                application_id=app_row.id, from_stage=app_row.stage, to_stage=target,
                note=f"From email: {(m.subject or '')[:120]} — {m.evidence or ''}"[:500]))
            app_row.stage = target
            if target == "applied" and not app_row.applied_at:
                app_row.applied_at = datetime.now(timezone.utc)
            moved = target
    db.commit()
    return {"status": "ok", "id": m.id, "moved_to": moved, "created_application": created}


@app.post("/api/mail/proposals/{proposal_id}/dismiss")
def mail_dismiss(proposal_id: int, db: Session = Depends(get_db)):
    m = db.get(MailMessage, proposal_id)
    if not m:
        raise HTTPException(404, "proposal not found")
    m.status = "dismissed"
    db.commit()
    return {"status": "ok", "id": m.id}


# ─── résumé file (for the autofill extension) ───────────────
@app.put("/api/resume/file")
async def upload_resume_file(request: Request, filename: str = "resume.pdf",
                             db: Session = Depends(get_db)):
    """Store the résumé PDF (raw body). One row, replaced each upload."""
    data = await request.body()
    if not data:
        raise HTTPException(422, "empty body")
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "résumé larger than 10MB")
    for old in db.scalars(select(ResumeFile)).all():
        db.delete(old)
    rf = ResumeFile(filename=filename, content_type="application/pdf",
                    data=data, size=len(data))
    db.add(rf)
    db.commit()
    return {"status": "ok", "filename": rf.filename, "size": rf.size,
            "uploaded_at": rf.uploaded_at.isoformat() if rf.uploaded_at else None}


@app.get("/api/resume/file")
def get_resume_file(db: Session = Depends(get_db)):
    """The stored résumé, as a file download. The extension fetches this and
    attaches it to an application's file input via DataTransfer."""
    rf = db.scalar(select(ResumeFile).order_by(ResumeFile.uploaded_at.desc()))
    if not rf:
        raise HTTPException(404, "no résumé uploaded")
    return Response(content=rf.data, media_type=rf.content_type,
                    headers={"Content-Disposition": f'inline; filename="{rf.filename}"'})


@app.get("/api/resume/file/meta")
def get_resume_file_meta(db: Session = Depends(get_db)):
    rf = db.scalar(select(ResumeFile).order_by(ResumeFile.uploaded_at.desc()))
    if not rf:
        return {"present": False}
    return {"present": True, "filename": rf.filename, "size": rf.size,
            "uploaded_at": rf.uploaded_at.isoformat() if rf.uploaded_at else None}


@app.get("/api/roles/hidden-summary")
def hidden_summary(db: Session = Depends(get_db)):
    """How many roles the eligibility/target filters are hiding, and why.

    A feed that silently drops things is how you miss the one you wanted, so
    the count and the reasons are first-class rather than implied by absence.
    """
    from scan.eligibility import eligibility_reason, off_target_reason
    from scan.geo import is_us
    from scan.intern_filter import in_active_track
    mode = "intern" if settings.intern_only else settings.track_mode
    rows = db.scalars(select(Role).where(Role.status.in_(["open", "changed"]))).all()
    counts: dict[str, int] = {}
    for r in rows:
        if not in_active_track(r.title, r.department, mode):
            continue
        if not is_us(r.location, r.state, r.title):
            continue
        reason = eligibility_reason(r.title, r.description) or off_target_reason(r.title, r.department)
        if reason:
            counts[reason] = counts.get(reason, 0) + 1
    return {"hidden": sum(counts.values()), "by_reason": counts}


@app.get("/api/boards/recent")
def recent_boards(days: int = 7, db: Session = Depends(get_db)):
    """Boards connected in the last `days`, with how much back catalogue each
    brought in. The dashboard shows one line per board so a 396-role batch is
    explained rather than silently swelling the feed."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(
        select(Company.id, Company.name, Company.ats_name, Company.first_scanned_at,
               func.count(Role.id))
        .join(Role, Role.company_id == Company.id)
        .where(Company.first_scanned_at >= cutoff, Role.is_backfill == True)  # noqa: E712
        .group_by(Company.id, Company.name, Company.ats_name, Company.first_scanned_at)
        .order_by(Company.first_scanned_at.desc())).all()
    return [{"company_id": cid, "company": name, "ats": ats,
             "connected_at": ts.isoformat() if ts else None, "roles_added": n}
            for cid, name, ats, ts, n in rows]


@app.post("/api/admin/discover-workday")
def discover_workday_boards(limit: int = 25, only_with_roles: bool = True,
                            apply: bool = False, db: Session = Depends(get_db)):
    """Find aggregator-only companies' Workday boards (see scan/workday_discovery.py).

    Proposes by default: Workday tenants are first-come names ("emerson" is
    Emerson College, not Emerson Electric) and the API offers nothing to verify
    the employer against, so each proposal carries sample postings and flagged
    ones are never auto-applied.
    """
    from scan.workday_discovery import discover
    return discover(db, limit=limit, only_with_roles=only_with_roles, apply=apply)


@app.post("/api/admin/merge-shadow-companies")
def merge_shadow_companies(dry_run: bool = True, db: Session = Depends(get_db)):
    """Fold aggregator duplicates into the company Recon already pulls directly
    ("Anduril Industries" -> "Anduril"). Defaults to a dry run; pass
    dry_run=false to actually move the roles. See scan/company_merge.py.
    """
    from scan.company_merge import merge
    return merge(db, dry_run=dry_run)


@app.post("/api/admin/discover-ats")
def discover_ats(limit: int = 40, only_with_roles: bool = True,
                 recheck_broken: bool = True, db: Session = Depends(get_db)):
    """Resolve aggregator-invented companies to their real ATS board.

    734 of ~1,000 companies exist only because Adzuna returned a row for them,
    so Recon sees a sampled slice instead of the company's board. This promotes
    the ones whose board can be found to a direct pull, and re-checks configured
    boards that have started 404ing. See scan/ats_discovery.py.
    """
    from scan.ats_discovery import discover
    return discover(db, limit=limit, only_with_roles=only_with_roles,
                    recheck_broken=recheck_broken)


@app.post("/api/admin/backfill-descriptions")
def backfill_descriptions(limit: int = 50, source: str | None = None,
                          db: Session = Depends(get_db)):
    """Re-fetch JD text for open roles stored without one (see scan/jd_backfill.py).

    Best-effort: returns per-source attempted/filled counts so the real success
    rate is visible. Re-runnable; never overwrites a longer description.
    """
    from scan.jd_backfill import backfill
    return backfill(db, limit=limit, source=source)


@app.get("/api/roles/dismissed")
def list_dismissed_roles(limit: int = 200, db: Session = Depends(get_db)):
    """What Zach wiped, newest first — the undo list."""
    rows = db.scalars(
        select(Role).where(Role.interest == "down")
        .order_by(Role.interest_at.desc().nullslast()).limit(limit)).all()
    return [_role_out_min(r) for r in rows]


@app.post("/api/roles/{role_id}/dismiss")
def dismiss_role(role_id: int, db: Session = Depends(get_db)):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "role not found")
    role.interest = "down"
    role.interest_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ok", "id": role.id, "interest": role.interest}


@app.post("/api/roles/{role_id}/undismiss")
def undismiss_role(role_id: int, db: Session = Depends(get_db)):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "role not found")
    role.interest = None
    role.interest_at = None
    db.commit()
    return {"status": "ok", "id": role.id, "interest": None}


@app.post("/api/companies/{company_id}/dismiss")
def dismiss_company(company_id: int, db: Session = Depends(get_db)):
    """Never show this employer again. Returns how many open roles just left
    the feed, so the app can say so rather than silently emptying."""
    co = db.get(Company, company_id)
    if not co:
        raise HTTPException(404, "company not found")
    co.dismissed_at = datetime.now(timezone.utc)
    n = db.scalar(select(func.count(Role.id)).where(
        Role.company_id == co.id, Role.status.in_(["open", "changed"])))
    db.commit()
    return {"status": "ok", "id": co.id, "company": co.name,
            "dismissed_at": co.dismissed_at.isoformat(), "roles_hidden": n or 0}


@app.post("/api/companies/{company_id}/undismiss")
def undismiss_company(company_id: int, db: Session = Depends(get_db)):
    co = db.get(Company, company_id)
    if not co:
        raise HTTPException(404, "company not found")
    co.dismissed_at = None
    db.commit()
    return {"status": "ok", "id": co.id, "company": co.name, "dismissed_at": None}


@app.get("/api/companies/dismissed")
def list_dismissed_companies(db: Session = Depends(get_db)):
    rows = db.scalars(select(Company).where(Company.dismissed_at.isnot(None))
                      .order_by(Company.dismissed_at.desc())).all()
    return [{"id": c.id, "name": c.name,
             "dismissed_at": c.dismissed_at.isoformat() if c.dismissed_at else None}
            for c in rows]


@app.post("/api/roles/{role_id}/feedback")
def role_feedback(role_id: int, body: dict, db: Session = Depends(get_db)):
    """Record Zach's interest in a role: {"value": "up" | "down" | null}.
    "down" is a dismissal (see /dismiss, which is the same thing under a name
    that matches what the app calls it)."""
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "role not found")
    value = body.get("value")
    if value not in ("up", "down", None):
        raise HTTPException(422, "value must be 'up', 'down', or null")
    role.interest = value
    role.interest_at = datetime.now(timezone.utc) if value else None
    db.commit()
    return {"status": "ok", "interest": role.interest}


@app.post("/api/roles/{role_id}/cover_letter")
def cover_letter_endpoint(role_id: int, db: Session = Depends(get_db)):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "role not found")
    from resume.cover import cover_letter
    return cover_letter(db, role)


@app.post("/api/roles/{role_id}/networking")
def networking_endpoint(role_id: int, db: Session = Depends(get_db)):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "role not found")
    from resume.networking import who_to_reach
    return who_to_reach(db, role)


# ─── interviews ─────────────────────────────────────────────
class InterviewIn(BaseModel):
    kind: str | None = None
    scheduled_at: date | None = None
    interviewer: str | None = None
    notes: str | None = None
    outcome: str | None = None


def _iv_dict(i: Interview) -> dict:
    return {"id": i.id, "application_id": i.application_id, "kind": i.kind,
            "scheduled_at": i.scheduled_at.isoformat() if i.scheduled_at else None,
            "interviewer": i.interviewer, "notes": i.notes, "outcome": i.outcome}


@app.get("/api/applications/{app_id}/interviews")
def list_interviews(app_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(Interview).where(Interview.application_id == app_id)
                      .order_by(Interview.scheduled_at.nullslast())).all()
    return [_iv_dict(i) for i in rows]


@app.post("/api/applications/{app_id}/interviews")
def add_interview(app_id: int, body: InterviewIn, db: Session = Depends(get_db)):
    if not db.get(Application, app_id):
        raise HTTPException(404, "application not found")
    i = Interview(application_id=app_id, **body.model_dump(exclude_unset=True))
    db.add(i); db.commit()
    return _iv_dict(i)


@app.patch("/api/interviews/{iv_id}")
def update_interview(iv_id: int, body: InterviewIn, db: Session = Depends(get_db)):
    i = db.get(Interview, iv_id)
    if not i:
        raise HTTPException(404, "interview not found")
    for f, v in body.model_dump(exclude_unset=True).items():
        setattr(i, f, v)
    db.commit()
    return _iv_dict(i)


@app.delete("/api/interviews/{iv_id}")
def delete_interview(iv_id: int, db: Session = Depends(get_db)):
    i = db.get(Interview, iv_id)
    if i:
        db.delete(i); db.commit()
    return {"status": "ok"}


@app.post("/api/roles/{role_id}/interview_prep")
def interview_prep_endpoint(role_id: int, db: Session = Depends(get_db)):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "role not found")
    from resume.interview import interview_prep
    return interview_prep(db, role)


def _contact_dict(c: Contact) -> dict:
    return {"id": c.id, "company_id": c.company_id, "company": c.company,
            "name": c.name, "role": c.role,
            "email": c.email, "linkedin": c.linkedin, "warmth": c.warmth,
            "status": c.status or "to_reach",
            "last_touch": c.last_touch.isoformat() if c.last_touch else None,
            "next_touch": c.next_touch.isoformat() if c.next_touch else None,
            "last_outreach": c.last_outreach, "notes": c.notes,
            "created_at": c.created_at.isoformat() if c.created_at else None}


# ─── brief ──────────────────────────────────────────────────
@app.get("/api/brief")
def get_brief(d: date | None = None, db: Session = Depends(get_db)):
    target = d or date.today()
    b = db.scalar(select(DailyBrief).where(DailyBrief.brief_date == target))
    if not b:
        b = db.scalar(select(DailyBrief).order_by(DailyBrief.brief_date.desc()))
    if not b:
        return {"date": str(target), "markdown": "_No brief yet. Run a scan._"}
    return {"date": b.brief_date.isoformat(), "markdown": b.markdown,
            "new_count": b.new_count, "action_count": b.action_count}


# ─── manual scan trigger (also runs nightly via worker) ─────
@app.post("/api/scan/run")
def trigger_scan():
    from scan.runner import run_daily_scan
    return run_daily_scan()


@app.get("/api/scan/runs")
def scan_runs(db: Session = Depends(get_db)):
    rows = db.scalars(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(30)).all()
    return [{"id": r.id, "started": r.started_at.isoformat(),
             "companies": r.companies_scanned, "new": r.new_count,
             "changed": r.changed_count, "closed": r.closed_count,
             "cost_usd": r.est_cost_usd, "errors": r.errors} for r in rows]


# ─── resume ──────────────────────────────────────────────────
class ResumeProfileIn(BaseModel):
    full_name: str | None = None
    headline: str | None = None
    location: str | None = None
    summary: str | None = None
    skills: str | None = None
    education: str | None = None
    links: str | None = None


class ExperienceIn(BaseModel):
    kind: str = "work"
    company: str | None = None
    title: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    bullets: str | None = None
    sort_order: int | None = None


def _exp_dict(e: ResumeExperience) -> dict:
    return {"id": e.id, "kind": e.kind, "company": e.company, "title": e.title,
            "location": e.location, "start_date": e.start_date, "end_date": e.end_date,
            "bullets": e.bullets, "sort_order": e.sort_order}


@app.get("/api/resume")
def get_resume(db: Session = Depends(get_db)):
    r = db.scalar(select(Resume).limit(1))
    profile = ({"full_name": r.full_name, "headline": r.headline, "location": r.location,
                "summary": r.summary, "skills": r.skills, "education": r.education,
                "links": r.links} if r else {})
    exps = db.scalars(select(ResumeExperience).order_by(ResumeExperience.sort_order)).all()
    return {"profile": profile, "experiences": [_exp_dict(e) for e in exps]}


@app.put("/api/resume")
def update_resume(body: ResumeProfileIn, db: Session = Depends(get_db)):
    r = db.scalar(select(Resume).limit(1))
    if not r:
        r = Resume(id=1)
        db.add(r)
    for f, v in body.model_dump(exclude_unset=True).items():
        setattr(r, f, v)
    db.commit()
    return {"status": "ok"}


@app.post("/api/resume/experiences")
def add_experience(body: ExperienceIn, db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if data.get("sort_order") is None:
        data["sort_order"] = (db.scalar(select(func.max(ResumeExperience.sort_order))) or 0) + 1
    e = ResumeExperience(**data)
    db.add(e)
    db.commit()
    return _exp_dict(e)


@app.patch("/api/resume/experiences/{exp_id}")
def update_experience(exp_id: int, body: ExperienceIn, db: Session = Depends(get_db)):
    e = db.get(ResumeExperience, exp_id)
    if not e:
        raise HTTPException(404, "experience not found")
    for f, v in body.model_dump(exclude_unset=True).items():
        setattr(e, f, v)
    db.commit()
    return _exp_dict(e)


@app.delete("/api/resume/experiences/{exp_id}")
def delete_experience(exp_id: int, db: Session = Depends(get_db)):
    e = db.get(ResumeExperience, exp_id)
    if e:
        db.delete(e)
        db.commit()
    return {"status": "ok"}


@app.post("/api/roles/{role_id}/tailor")
def tailor_role_endpoint(role_id: int, db: Session = Depends(get_db)):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "role not found")
    from resume.tailor import tailor_role
    return tailor_role(db, role)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    messages: list[ChatMessage]


@app.post("/api/resume/chat")
def resume_chat(body: ChatIn, db: Session = Depends(get_db)):
    from resume.coach import coach_reply
    return coach_reply(db, [m.model_dump() for m in body.messages])


class AutofillProfileIn(BaseModel):
    phone: str | None = None
    email: str | None = None
    preferred_name: str | None = None
    discipline: str | None = None
    address_line1: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    country: str | None = None
    linkedin_url: str | None = None
    portfolio_url: str | None = None
    github_url: str | None = None
    work_authorized: bool | None = None
    requires_sponsorship: bool | None = None
    willing_to_relocate: bool | None = None
    pronouns: str | None = None
    veteran_status: str | None = None
    disability_status: str | None = None
    gender: str | None = None
    race_ethnicity: str | None = None
    desired_salary: str | None = None
    earliest_start_date: str | None = None
    notice_period: str | None = None
    how_heard: str | None = None


@app.get("/api/autofill/profile")
def get_autofill_profile(db: Session = Depends(get_db)):
    from resume.autofill import assemble_autofill_profile
    return assemble_autofill_profile(db)


@app.put("/api/autofill/profile")
def update_autofill_profile(body: AutofillProfileIn, db: Session = Depends(get_db)):
    from resume.autofill import upsert_autofill_profile
    upsert_autofill_profile(db, body.model_dump(exclude_unset=True))
    return {"status": "ok"}


class AutofillQuestion(BaseModel):
    id: str
    label: str


class AutofillRoleCtx(BaseModel):
    company: str | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None


class AutofillAnswerIn(BaseModel):
    questions: list[AutofillQuestion]
    role_ctx: AutofillRoleCtx = AutofillRoleCtx()


@app.post("/api/autofill/answer")
def autofill_answer(body: AutofillAnswerIn, db: Session = Depends(get_db)):
    from resume.autofill import answer_questions
    return answer_questions(
        db,
        [q.model_dump() for q in body.questions],
        body.role_ctx.model_dump(),
    )


@app.post("/api/roles/{role_id}/draft_outreach")
def draft_outreach_endpoint(role_id: int, db: Session = Depends(get_db)):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "role not found")
    from resume.outreach import draft_outreach
    return draft_outreach(db, role)


# ─── static: master dashboard at / ──────────────────────────
# Defined last on purpose: a path parameter would otherwise shadow the
# literal /api/roles/* routes above it (dismissed, hidden-summary,
# search), which FastAPI matches in definition order.
@app.get("/api/roles/{role_id}")
def get_role(role_id: int, db: Session = Depends(get_db)):
    """One role with its complete JD — what the list payload leaves out."""
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(404, "role not found")
    co = r.company
    return {"id": r.id, "title": r.title, "company": co.name if co else None,
            "company_id": r.company_id, "location": r.location, "metro": r.metro,
            "state": r.state, "url": r.url, "source": r.source, "status": r.status,
            "description": r.description, "tc_estimate": r.tc_estimate,
            "posted_at": r.posted_at.isoformat() if r.posted_at else None,
            "first_seen": r.first_seen.isoformat() if r.first_seen else None,
            "is_mba": r.is_mba, "interest": r.interest,
            "is_backfill": bool(r.is_backfill)}



@app.get("/", response_class=HTMLResponse)
def dashboard():
    return FileResponse("web/dashboard.html")

app.mount("/web", StaticFiles(directory="web"), name="web")


# ════════════════════════════════════════════════════════════
# ─── web push: subscription + service worker (added by the   ─
# ─── notification-delivery feature; see api/notify/push.py)   ─
# ════════════════════════════════════════════════════════════
class PushSubscriptionIn(BaseModel):
    endpoint: str
    keys: dict


@app.post("/api/push/subscribe")
def push_subscribe(body: PushSubscriptionIn, db: Session = Depends(get_db)):
    p256dh = body.keys.get("p256dh")
    auth = body.keys.get("auth")
    if not p256dh or not auth:
        raise HTTPException(400, "subscription missing p256dh/auth keys")

    existing = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if existing:
        existing.p256dh = p256dh
        existing.auth = auth
    else:
        db.add(PushSubscription(endpoint=body.endpoint, p256dh=p256dh, auth=auth))
    db.commit()
    return {"status": "ok"}


@app.get("/api/push/vapid-public-key")
def push_vapid_public_key():
    return {"key": settings.vapid_public_key}


class DeviceTokenIn(BaseModel):
    token: str
    platform: str = "ios"


@app.post("/api/push/register-device")
def register_device(body: DeviceTokenIn, db: Session = Depends(get_db)):
    """Native app calls this once on launch with its APNs device token."""
    existing = db.scalar(select(DeviceToken).where(DeviceToken.token == body.token))
    if not existing:
        db.add(DeviceToken(token=body.token, platform=body.platform))
        db.commit()
    return {"status": "ok"}


# service worker must be served from the site root to control the page
@app.get("/sw.js")
def service_worker():
    return FileResponse("web/sw.js", media_type="application/javascript")
