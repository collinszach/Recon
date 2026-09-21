"""Find a company's Workday board so Recon can pull it directly.

The big employers that only reach Recon through aggregators — Vanguard,
Emerson, TransUnion and friends — are mostly on Workday, and the Workday CXS
API works fine once you know the board. The problem is that a board is three
unknowns, `{tenant}:{dc}:{site}`, and guessing all three is ~120 requests per
company.

Two things make it cheap instead:

1. `GET /wday/cxs/{tenant}/{anything}` answers **200** whenever the tenant and
   datacenter are both right, and **422** when they aren't — even for a site
   that doesn't exist. So the tenant is found in one GET per datacenter,
   without touching the job API at all.
2. `robots.txt` on the tenant host **lists the career sites** and explicitly
   `Allow`s them. Vanguard's is `vanguard_external`, Micron's is `External` —
   neither is guessable, and both are published. No scraping, no guessing.

Only then does it POST the jobs endpoint, once per listed site, to pick the
one with the most postings.
"""
from __future__ import annotations
import logging
import re
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import Company, Role
from scan.ats_discovery import AGGREGATOR

log = logging.getLogger("recon.workday_discovery")

# Workday datacenters, most common first.
DATACENTERS = ["wd1", "wd5", "wd3", "wd12", "wd10", "wd2", "wd103"]
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_ALLOW_RE = re.compile(r"^Allow:\s*/([^/\s]+)/\s*$", re.MULTILINE)
_SITEMAP_RE = re.compile(r"^Sitemap:\s*https?://[^/]+/([^/]+)/siteMap\.xml", re.MULTILINE)
# Boards that exist but aren't open external hiring.
_SKIP_SITE_RE = re.compile(r"(contractor|restricted|internal|alumni|intern_only_.*_test)",
                           re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^a-z0-9]+")


def tenant_candidates(name: str) -> list[str]:
    """Plausible tenant names. No truncation of multi-word names — the same
    rule ats_discovery learned the hard way ("Capital Rx" -> "capital" is
    someone else's board entirely)."""
    base = _PUNCT_RE.sub("", (name or "").lower())
    out = [base]
    hyph = _PUNCT_RE.sub("-", (name or "").lower()).strip("-")
    if hyph != base:
        out.append(hyph)
    return [t for t in out if len(t) > 2]


def find_tenant(tenant: str, timeout: float = 6.0) -> str | None:
    """The datacenter this tenant lives in, or None. One GET per datacenter."""
    for dc in DATACENTERS:
        url = f"https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/x"
        try:
            r = httpx.get(url, timeout=timeout, headers={"User-Agent": UA})
        except Exception:
            continue
        if r.status_code == 200:
            return dc
    return None


def list_sites(tenant: str, dc: str, timeout: float = 8.0) -> list[str]:
    """Career sites this tenant publishes, straight out of robots.txt."""
    url = f"https://{tenant}.{dc}.myworkdayjobs.com/robots.txt"
    try:
        r = httpx.get(url, timeout=timeout, headers={"User-Agent": UA})
    except Exception:
        return []
    if r.status_code != 200:
        return []
    sites: list[str] = []
    for m in (_ALLOW_RE.findall(r.text) + _SITEMAP_RE.findall(r.text)):
        if m not in sites and not _SKIP_SITE_RE.search(m):
            sites.append(m)
    return sites


def sample_board(tenant: str, dc: str, site: str, timeout: float = 12.0) -> tuple[int, list[str]]:
    """(posting count, a few sample titles). The samples are the only identity
    evidence available — the board API never names the employer, and the public
    site page renders its title in JS, so there is nothing to match on
    server-side."""
    url = f"https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    try:
        r = httpx.post(url, timeout=timeout,
                       headers={"User-Agent": UA, "Content-Type": "application/json"},
                       json={"appliedFacets": {}, "limit": 3, "offset": 0, "searchText": ""})
    except Exception:
        return 0, []
    if r.status_code != 200:
        return 0, []
    try:
        d = r.json()
        posts = d.get("jobPostings") or []
        return int(d.get("total") or 0), [
            f"{p.get('title', '')} — {p.get('locationsText', '')}"[:90] for p in posts[:3]]
    except Exception:
        return 0, []


# An entity word in the site name that the company name doesn't have is the
# tell for a tenant collision: "Emerson" resolves to emerson:wd5:
# Emerson_College_Staff, which is Emerson College, not Emerson Electric —
# the same trap as "Capital Rx" -> lever/capital.
_ENTITY_RE = re.compile(
    r"\b(college|university|school|academy|hospital|health|medical|clinic|"
    r"bank|credit\s*union|county|city|state|district|foundation|church|"
    r"ministry|institute)\b", re.IGNORECASE)


def looks_mismatched(company: str, tenant: str, site: str) -> str | None:
    """A reason to distrust this match, or None."""
    co_words = set(_PUNCT_RE.sub(" ", company.lower()).split())
    for m in _ENTITY_RE.findall(_PUNCT_RE.sub(" ", site.lower())):
        if m.lower().replace(" ", "") not in {w.replace(" ", "") for w in co_words}:
            return f"site name says {m!r}, company name doesn't"
    return None


def resolve(name: str, delay: float = 0.3) -> dict | None:
    """Proposed Workday board for a company name, with the evidence for it.

    Returns {token, postings, samples, suspect} — token in the
    "{tenant}:{dc}:{site}" form parsers/workday.py expects.
    """
    for tenant in tenant_candidates(name):
        dc = find_tenant(tenant)
        time.sleep(delay)
        if not dc:
            continue
        best: dict | None = None
        for site in list_sites(tenant, dc):
            n, samples = sample_board(tenant, dc, site)
            time.sleep(delay)
            if n and (best is None or n > best["postings"]):
                best = {"token": f"{tenant}:{dc}:{site}", "postings": n,
                        "samples": samples,
                        "suspect": looks_mismatched(name, tenant, site)}
        if best:
            return best
    return None


def discover(db: Session, limit: int = 25, only_with_roles: bool = True,
             apply: bool = False) -> dict:
    """Propose (or with apply=True, write) a direct Workday pull per company.

    Proposes by default. A Workday tenant is claimed by whoever registered the
    name — "emerson" is Emerson College — and the API gives nothing to verify
    identity against, so each proposal carries sample postings to eyeball and
    anything the mismatch guard flags is never auto-applied.
    """
    q = select(Company).where(Company.ats_name.in_(AGGREGATOR - {None, ""}))
    if only_with_roles:
        q = q.where(Company.id.in_(
            select(Role.company_id).where(Role.status.in_(["open", "changed"]))))
    targets = db.scalars(q.order_by(Company.tier, Company.name).limit(limit)).all()

    resolved, checked = [], 0
    for co in targets:
        checked += 1
        hit = resolve(co.name)
        if not hit:
            continue
        was = f"{co.ats_name}:{co.ats_token}"
        entry = {"company": co.name, "company_id": co.id, "from": was, **hit,
                 "applied": False}
        if apply and not hit["suspect"]:
            co.ats_name, co.ats_token = "workday", hit["token"]
            db.commit()      # commit per hit; a long run must survive a restart
            entry["applied"] = True
        resolved.append(entry)
        log.info("workday discovery: %s %s -> workday:%s (%d postings)%s",
                 co.name, was, hit["token"], hit["postings"],
                 " [SUSPECT: %s]" % hit["suspect"] if hit["suspect"] else "")
    return {"checked": checked, "proposed": len(resolved),
            "applied": sum(1 for r in resolved if r["applied"]), "details": resolved}
