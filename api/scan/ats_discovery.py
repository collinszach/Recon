"""Find a company's real ATS board so Recon can pull it directly.

Most companies in the DB were invented by an aggregator: 734 of 1,003 have
`ats_name='adzuna'`, another 71 are `jsearch_company` sweep targets. For those,
Recon sees whatever slice the aggregator happened to return — no full board, no
authoritative "closed" detection, usually no JD text. Only 149 have a direct
pull.

This probes the public board APIs for a slug derived from the company name and
its careers URL, and promotes the company to a direct pull when one answers with
actual jobs. It is deliberately conservative: a board must return at least one
posting to count, so a 200 on an empty or parked board doesn't overwrite a
working aggregator source.

Also re-checks companies whose configured board has started 404ing — Atlassian,
dbt Labs, Aurora, Snyk, Capital Rx and Mach Industries have been erroring on
every scan, which is the same problem in the other direction.
"""
from __future__ import annotations
import logging
import re
import time
from urllib.parse import urlparse

import httpx
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from db import Company, Role

log = logging.getLogger("recon.ats_discovery")

# Aggregator-invented sources: a company carrying one of these has no direct
# board configured, it's just where the rows came from.
AGGREGATOR = {"adzuna", "jsearch", "jsearch_company", "themuse", "usajobs", None, ""}

# Legal-entity noise that never appears in a board slug.
_SUFFIX_RE = re.compile(
    r"\b(inc|inc\.|llc|l\.l\.c\.|ltd|limited|corp|corporation|co|company|"
    r"holdings|group|technologies|technology|labs|systems|solutions|plc|"
    r"gmbh|sa|nv|ag|pbc)\b", re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def slug_candidates(name: str, careers_url: str | None = None) -> list[str]:
    """Plausible board slugs for a company, best guess first.

    The careers URL is the strongest signal when it exists — plenty of boards
    are hosted at job-boards.greenhouse.io/<slug> or <slug>.ashbyhq.com, which
    names the slug outright.
    """
    out: list[str] = []

    def add(s: str | None) -> None:
        if s and s not in out and len(s) > 1:
            out.append(s)

    if careers_url:
        u = careers_url.lower()
        # The slug straight out of a hosted board URL.
        for pat in (r"greenhouse\.io/(?:embed/job_board\?for=)?([a-z0-9_-]+)",
                    r"lever\.co/([a-z0-9_-]+)",
                    r"jobs\.ashbyhq\.com/([a-z0-9_-]+)",
                    r"([a-z0-9-]+)\.ashbyhq\.com"):
            m = re.search(pat, u)
            if m:
                add(m.group(1))
        host = (urlparse(u).hostname or "").removeprefix("www.")
        if host:
            add(_NON_ALNUM_RE.sub("", host.split(".")[0]))

    base = _NON_ALNUM_RE.sub(" ", name.lower()).strip()
    stripped = _SUFFIX_RE.sub(" ", base).strip()
    for variant in (stripped, base):
        if not variant:
            continue
        add(variant.replace(" ", ""))          # "dbt labs" -> "dbtlabs"
        add(variant.replace(" ", "-"))         # -> "dbt-labs"
    add(_NON_ALNUM_RE.sub("", name.lower()) + "inc")   # the "dbtlabsinc" pattern
    # Deliberately NOT the first word of a multi-word name. "Capital Rx" ->
    # "capital" matches a live Lever board belonging to someone else entirely
    # (42 postings, none of them Capital Rx), and a wrong board is worse than
    # no board: it files another company's roles under this one, with this
    # company's name on them.
    return out[:8]


# (ats_name, url template, how to count postings in the response)
PROBES: list[tuple[str, str, str]] = [
    ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", "jobs"),
    ("ashby", "https://api.ashbyhq.com/posting-api/job-board/{slug}", "jobs"),
    ("lever", "https://api.lever.co/v0/postings/{slug}?mode=json", "list"),
]


def _count(kind: str, data) -> int:
    try:
        if kind == "list":
            return len(data) if isinstance(data, list) else 0
        return len(data.get("jobs") or []) if isinstance(data, dict) else 0
    except Exception:
        return 0


def probe_one(ats: str, slug: str, timeout: float = 8.0) -> int | None:
    """Posting count for one board, or None if it isn't there / isn't JSON."""
    entry = next((p for p in PROBES if p[0] == ats), None)
    if not entry:
        return None
    _, tmpl, kind = entry
    try:
        r = httpx.get(tmpl.format(slug=slug), timeout=timeout,
                      headers={"User-Agent": "recon/1.0 (+job tracker)"})
    except Exception:
        return None
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("application/json"):
        return None
    return _count(kind, r.json())


def probe(slug: str, timeout: float = 8.0) -> tuple[str, str, int] | None:
    """Try each board API for `slug`. Returns (ats_name, slug, job_count).

    A board must return at least one posting: a 200 on an empty or parked board
    is not evidence that this is the company's board, and promoting on it would
    replace a working aggregator feed with nothing.
    """
    for ats, _tmpl, _kind in PROBES:
        n = probe_one(ats, slug, timeout)
        if n:
            return ats, slug, n
    return None


def discover(db: Session, limit: int = 40, only_with_roles: bool = True,
             recheck_broken: bool = True, delay: float = 0.4) -> dict:
    """Resolve aggregator-only companies (and re-check broken boards).

    `only_with_roles` prioritises companies Recon has actually seen postings
    from — those are the ones a direct pull immediately improves.
    """
    q = select(Company).where(or_(Company.ats_name.in_([a for a in AGGREGATOR if a]),
                                  Company.ats_name.is_(None)))
    if only_with_roles:
        with_roles = select(Role.company_id).where(Role.status.in_(["open", "changed"]))
        q = q.where(Company.id.in_(with_roles))
    targets = list(db.scalars(q.order_by(Company.tier, Company.name).limit(limit)).all())

    if recheck_broken:
        # Companies with a configured board that no longer answers — same fix,
        # opposite direction (Atlassian, dbt Labs, Aurora, Snyk, Capital Rx and
        # Mach Industries have 404'd on every scan for weeks). One probe each,
        # against the ATS they're configured for, not all three.
        configured = db.scalars(
            select(Company).where(Company.ats_name.in_(["greenhouse", "ashby", "lever"]),
                                  Company.ats_token.isnot(None))).all()
        for co in configured:
            if len(targets) >= limit * 2:
                break
            if not probe_one(co.ats_name, co.ats_token):
                targets.append(co)

    resolved, checked = [], 0
    for co in targets:
        checked += 1
        hit = None
        for slug in slug_candidates(co.name, co.careers_url):
            hit = probe(slug)
            time.sleep(delay)          # be polite to the board APIs
            if hit:
                break
        if not hit:
            continue
        ats, slug, n = hit
        was = f"{co.ats_name}:{co.ats_token}"
        co.ats_name, co.ats_token = ats, slug
        resolved.append({"company": co.name, "from": was, "ats": ats,
                         "slug": slug, "postings": n})
        log.info("ats discovery: %s %s -> %s:%s (%d postings)", co.name, was, ats, slug, n)
        # Commit as we go. A long run is minutes of probing, and committing only
        # at the end meant an API restart (or a client timeout) threw away every
        # resolution it had already found — which is exactly what happened on
        # the first 120-company batch.
        db.commit()

    db.commit()
    return {"checked": checked, "resolved": len(resolved), "details": resolved}


# ─── Startups -> scanned companies ─────────────────────────────────────────
# `discover()` only ever promotes Company rows that already exist, so a startup
# tracked in the `startups` table — researched, written up, never scanned — is
# invisible to it. On 2026-09-28, 47 of 66 tracked startups had no Company row,
# including all 18 in climate/energy.

# Startup.sector uses the researcher's vocabulary; Company.sector uses the
# classifier's. Only the unambiguous overlaps are mapped.
_STARTUP_SECTOR = {"sustainability_energy": "climate_energy", "fintech": "finance",
                   "defense": "defense_aerospace"}


def board_evidence(ats: str, slug: str, timeout: float = 8.0
                   ) -> tuple[str | None, list[str], list[str]]:
    """(board display name, posting URLs, posting text) for identity checks.

    Greenhouse boards carry their own display name; Lever and Ashby don't, so
    for those the postings themselves are the only evidence of whose board it
    is. A sample is enough — this is identification, not ingestion.
    """
    headers = {"User-Agent": "recon/1.0 (+job tracker)"}

    def get(url):
        try:
            r = httpx.get(url, timeout=timeout, headers=headers)
            return r.json() if r.status_code == 200 else None
        except Exception:
            return None

    if ats == "greenhouse":
        meta = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}") or {}
        jobs = (get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs") or {}).get("jobs") or []
        return meta.get("name"), [j.get("absolute_url") or "" for j in jobs[:20]], []
    if ats == "lever":
        jobs = get(f"https://api.lever.co/v0/postings/{slug}?mode=json") or []
        jobs = jobs if isinstance(jobs, list) else []
        return None, ([j.get("hostedUrl") or "" for j in jobs[:15]]
                      + [j.get("applyUrl") or "" for j in jobs[:15]]), \
            [(j.get("descriptionPlain") or "") + " " + (j.get("additionalPlain") or "")
             for j in jobs[:10]]
    if ats == "ashby":
        jobs = (get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}") or {}).get("jobs") or []
        return None, ([j.get("jobUrl") or "" for j in jobs[:15]]
                      + [j.get("applyUrl") or "" for j in jobs[:15]]), \
            [j.get("descriptionPlain") or "" for j in jobs[:10]]
    return None, [], []


def promote_startups(db: Session, limit: int = 100, delay: float = 0.4,
                     dry_run: bool = False) -> dict:
    """Wire tracked startups into the job scan, where their board can be found
    *and shown to be theirs*.

    For each startup: if a Company with the same identity already has a direct
    board, it is already scanned (this is what stops "Anduril Industries"
    becoming a second Anduril). If that Company exists only as an aggregator
    row, it is upgraded in place. Otherwise a new Company is created.

    Nothing is promoted on "the board has postings" alone — see
    scan/identity.py for the five boards that proved why. A board that can't be
    confirmed goes to `review`; one that belongs to someone else goes to
    `rejected`. Neither creates anything. Startups with no findable board stay
    research-only (by decision: no jsearch_company fallback, which would dilute
    the sweep's daily rotation of the 70 large employers).
    """
    from datetime import date
    from db import Startup
    from seed.sectors import sector_for
    from scan.identity import identity_key, judge

    by_key: dict[str, Company] = {}
    for co in db.scalars(select(Company)).all():
        by_key.setdefault(identity_key(co.name), co)

    out = {"checked": 0, "already_scanned": [], "promoted": [], "upgraded": [],
           "review": [], "rejected": [], "no_board": [], "dry_run": dry_run}

    for s in db.scalars(select(Startup).order_by(Startup.name)).all():
        co = by_key.get(identity_key(s.name))
        if co is not None and (co.ats_name or "").lower() not in AGGREGATOR:
            out["already_scanned"].append({"startup": s.name, "company": co.name,
                                           "ats": co.ats_name})
            continue
        if out["checked"] >= limit:
            break
        out["checked"] += 1

        chosen, seen = None, []
        for slug in slug_candidates(s.name, s.website):
            hit = probe(slug)
            time.sleep(delay)          # be polite to the board APIs
            if not hit:
                continue
            ats, slug, n = hit
            board_name, urls, texts = board_evidence(ats, slug)
            verdict, why = judge(s.name, s.website, board_name, urls, texts)
            rec = {"startup": s.name, "ats": ats, "slug": slug, "postings": n,
                   "board_name": board_name, "reason": why}
            if verdict == "promote":
                chosen = rec
                break
            seen.append((verdict, rec))

        if chosen is None:
            if not seen:
                out["no_board"].append(s.name)
            for verdict, rec in seen:
                out["review" if verdict == "review" else "rejected"].append(rec)
            continue

        if dry_run:
            out["upgraded" if co is not None else "promoted"].append(chosen)
            continue

        if co is not None:
            was = f"{co.ats_name}:{co.ats_token}"
            co.ats_name, co.ats_token = chosen["ats"], chosen["slug"]
            co.careers_url = co.careers_url or s.website
            out["upgraded"].append({**chosen, "from": was})
        else:
            co = Company(name=s.name, tier="B", ats_name=chosen["ats"], ats_token=chosen["slug"],
                         careers_url=s.website,
                         sector=sector_for(s.name) or _STARTUP_SECTOR.get(s.sector or ""),
                         notes=f"Promoted from startups {date.today()}: {chosen['reason']}")
            db.add(co)
            by_key[identity_key(s.name)] = co
            out["promoted"].append(chosen)
        log.info("startup promotion: %s -> %s:%s (%s)", s.name, chosen["ats"],
                 chosen["slug"], chosen["reason"])
        # Commit per promotion, like discover(): a long probing run that only
        # committed at the end has already lost its work to a client timeout.
        db.commit()

    return out
