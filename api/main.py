"""Recon API — REST endpoints + serves the dashboard and brief."""
import logging
from datetime import date, timedelta
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from config import settings
from db import (
    Base, engine, SessionLocal, Company, Role, Application, ApplicationEvent,
    Contact, DailyBrief, ScanRun, PushSubscription, Resume, ResumeExperience,
    Interview, Material,
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
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE roles ADD COLUMN IF NOT EXISTS metro VARCHAR"))
        # provenance: 'ats' (default) | 'jsearch' | 'usajobs' — Postgres backfills existing rows.
        conn.execute(text("ALTER TABLE roles ADD COLUMN IF NOT EXISTS source VARCHAR DEFAULT 'ats'"))
        # full JD text — previously only the hash was kept, so the scorer graded blind to the JD.
        conn.execute(text("ALTER TABLE roles ADD COLUMN IF NOT EXISTS description TEXT"))
        conn.execute(text("ALTER TABLE scan_runs ADD COLUMN IF NOT EXISTS searched BOOLEAN DEFAULT FALSE"))


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
    added = seed_companies()
    log.info("startup: seeded %d new companies", added)
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
@app.get("/api/roles")
def list_roles(tier: str | None = None, company: str | None = None,
               min_fit: float = 0.0, scored_only: bool = True,
               track: str | None = None, metro: str | None = None,
               dedupe: bool = True,
               db: Session = Depends(get_db)):
    import re as _re
    from scan.intern_filter import is_internship, is_ops_strategy
    q = select(Role).where(Role.status.in_(["open", "changed"]))
    if scored_only:
        # Only scored roles are surfaced (internships + full-time PM roles are
        # what gets scored). Pass scored_only=false to browse the raw set.
        q = q.where(Role.scored_at.isnot(None))
    if min_fit:
        q = q.where(Role.fit_score >= min_fit)
    if metro:
        q = q.where(Role.metro == metro)
    rows = db.scalars(q.order_by(Role.fit_score.desc().nullslast())).all()
    out = []
    for r in rows:
        co = r.company
        if company and co and company.lower() not in co.name.lower():
            continue
        if tier and co and co.tier != tier:
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
            "company_tier": co.tier if co else None,
            "source": r.source or "ats",        # ats | jsearch | usajobs (provenance)
            "tier": r.score_tier,               # fit tier (A/B/C/pass) from scoring
            "title": r.title,
            "location": r.location, "metro": r.metro, "url": r.url, "status": r.status,
            "description": (r.description or "")[:4000] or None,
            "remote": r.remote_flag,
            "posted_at": r.posted_at.isoformat() if r.posted_at else None,
            "first_seen": r.first_seen.isoformat() if r.first_seen else None,
            "fit_score": r.fit_score, "domain": r.domain,
            "why_fit": r.why_fit, "concerns": r.concerns,
            "curriculum_hook": r.curriculum_hook,
            "tc_estimate": r.tc_estimate,       # pay / stipend
            "is_product_pm": r.is_product_pm,
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
            if cur is None or (o["fit_score"] or 0, o["posted_at"] or "") > (cur["fit_score"] or 0, cur["posted_at"] or ""):
                best[key] = o
        out = sorted(best.values(), key=lambda o: (o["fit_score"] or 0), reverse=True)
    return out


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


@app.post("/api/roles/{role_id}/draft_outreach")
def draft_outreach_endpoint(role_id: int, db: Session = Depends(get_db)):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "role not found")
    from resume.outreach import draft_outreach
    return draft_outreach(db, role)


# ─── static: master dashboard at / ──────────────────────────
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


# service worker must be served from the site root to control the page
@app.get("/sw.js")
def service_worker():
    return FileResponse("web/sw.js", media_type="application/javascript")
