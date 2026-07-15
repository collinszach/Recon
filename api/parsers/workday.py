"""Workday public CXS job-board API.

Endpoint (per tenant):
  POST https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
  body: {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}

Paginated via the response's `total` field; loop offset += 20 until
offset >= total (capped to stay polite).

`token` encodes the tenant, datacenter, and career site as a single
colon-delimited string: "{tenant}:{dc}:{site}", e.g.
"nvidia:wd5:NVIDIAExternalCareerSite" maps to
https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs

Large enterprise boards (Capital One ~1400 postings, Visa ~940, Palo Alto
Networks ~1400+) blow past MAX_POSTINGS, and blind pagination only ever sees
whatever Workday's default (unfiltered) order happens to put first -- the
handful of PM/TPM/MBA-track roles Zach actually cares about can be buried past
that cutoff and never get seen at all (2026-07-07: confirmed this on Capital
One). So once a board is bigger than the cap, this backfills with targeted
searchText queries (the same track term list the JSearch/USAJobs aggregator
uses, plus mba/internship) so those roles get pulled in regardless of where
they sit in the board. This step is about *recall* only -- scan.intern_filter's
title classifiers still decide what's actually relevant to score.
"""
from .base import ATSParser, NormalizedRole, client, polite_delay, parse_dt

BASE = "https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
PUBLIC_URL = "https://{tenant}.{dc}.myworkdayjobs.com/{site}{path}"
PAGE_SIZE = 20
MAX_POSTINGS = 250       # politeness cap on the N95 for blind (unfiltered) pagination
SUPPLEMENT_PAGES = 2     # extra pages (40 postings) per keyword, only when board > MAX_POSTINGS


class WorkdayParser(ATSParser):
    ats_name = "workday"

    def fetch(self, token: str) -> list[NormalizedRole]:
        tenant, dc, site = _parse_token(token)
        url = BASE.format(tenant=tenant, dc=dc, site=site)

        roles: list[NormalizedRole] = []
        seen_ids: set[str] = set()

        def _add(job: dict) -> None:
            role = _normalize(job, tenant, dc, site)
            if role.ats_job_id not in seen_ids:
                seen_ids.add(role.ats_job_id)
                roles.append(role)

        with client() as c:
            offset = 0
            total = None
            while True:
                resp = c.post(
                    url,
                    json={"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": ""},
                )
                resp.raise_for_status()
                data = resp.json()
                page = data.get("jobPostings", [])
                # Workday only reports the real total on the FIRST page; deeper
                # pages intermittently report total=0. Capture it once and rely on
                # an empty page to detect the true end, so a spurious 0 can't
                # truncate a large board to a couple pages.
                if total is None:
                    total = data.get("total", 0) or 0
                for job in page:
                    _add(job)
                offset += PAGE_SIZE
                if not page or offset >= min(total or MAX_POSTINGS, MAX_POSTINGS):
                    break
                polite_delay()

            if total and total > MAX_POSTINGS:
                for term in _supplement_terms():
                    s_offset = 0
                    s_cap = SUPPLEMENT_PAGES * PAGE_SIZE
                    while s_offset < s_cap:
                        resp = c.post(
                            url,
                            json={"appliedFacets": {}, "limit": PAGE_SIZE, "offset": s_offset, "searchText": term},
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        page = data.get("jobPostings", [])
                        for job in page:
                            _add(job)
                        s_offset += PAGE_SIZE
                        if not page:            # end of this keyword's results
                            break
                        polite_delay()

        return roles


def _supplement_terms() -> list[str]:
    """Track-relevant keywords to backfill a big board with, beyond blind
    pagination. Reuses the aggregator's term list (search/__init__.py) plus
    mba/internship, which the JSearch term list doesn't always cover (e.g.
    "MBA Summer Associate" / "Management Internship Program" titles)."""
    from search import default_terms
    terms = list(default_terms())
    lower = {t.lower() for t in terms}
    for extra in ("mba", "internship"):
        if extra not in lower:
            terms.append(extra)
    return terms


def _parse_token(token: str) -> tuple[str, str, str]:
    parts = token.split(":")
    if len(parts) != 3:
        raise ValueError(f"workday token must be 'tenant:dc:site', got {token!r}")
    return parts[0], parts[1], parts[2]


def _normalize(job: dict, tenant: str, dc: str, site: str) -> NormalizedRole:
    path = job.get("externalPath", "")
    loc = job.get("locationsText")
    bullets = job.get("bulletFields") or []
    description = " ".join(str(b) for b in bullets)
    return NormalizedRole(
        ats_job_id=path or job.get("title", "Untitled"),
        title=job.get("title", "Untitled"),
        location=loc,
        remote_flag=bool(loc and "remote" in loc.lower()),
        department=None,
        url=PUBLIC_URL.format(tenant=tenant, dc=dc, site=site, path=path),
        description=f"{loc or ''} {description}".strip()[:6000],
        posted_at=parse_dt(job.get("startDate") or job.get("postedOnDate")),
    )
