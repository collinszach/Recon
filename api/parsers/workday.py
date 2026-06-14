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
"""
from .base import ATSParser, NormalizedRole, client, polite_delay, parse_dt

BASE = "https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
PUBLIC_URL = "https://{tenant}.{dc}.myworkdayjobs.com/{site}{path}"
PAGE_SIZE = 20
MAX_POSTINGS = 250  # politeness cap on the N95


class WorkdayParser(ATSParser):
    ats_name = "workday"

    def fetch(self, token: str) -> list[NormalizedRole]:
        tenant, dc, site = _parse_token(token)
        url = BASE.format(tenant=tenant, dc=dc, site=site)

        roles: list[NormalizedRole] = []
        offset = 0
        total = None
        with client() as c:
            while total is None or offset < min(total, MAX_POSTINGS):
                resp = c.post(
                    url,
                    json={"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": ""},
                )
                resp.raise_for_status()
                data = resp.json()
                total = data.get("total", 0)

                for job in data.get("jobPostings", []):
                    roles.append(_normalize(job, tenant, dc, site))

                offset += PAGE_SIZE
                polite_delay()

        return roles


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
