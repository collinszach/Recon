"""Greenhouse public job board API.

Endpoint:
  https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

`token` is the board slug, e.g. the company's greenhouse board name.
"""
from .base import ATSParser, NormalizedRole, client, polite_delay

BASE = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"


class GreenhouseParser(ATSParser):
    ats_name = "greenhouse"

    def fetch(self, token: str) -> list[NormalizedRole]:
        url = BASE.format(token=token)
        with client() as c:
            resp = c.get(url)
            resp.raise_for_status()
            data = resp.json()
        polite_delay()

        roles: list[NormalizedRole] = []
        for job in data.get("jobs", []):
            loc = (job.get("location") or {}).get("name")
            roles.append(
                NormalizedRole(
                    ats_job_id=str(job["id"]),
                    title=job.get("title", "Untitled"),
                    location=loc,
                    remote_flag=bool(loc and "remote" in loc.lower()),
                    department=_first_department(job),
                    url=job.get("absolute_url"),
                    description=_strip(job.get("content", "")),
                )
            )
        return roles


def _first_department(job: dict) -> str | None:
    depts = job.get("departments") or []
    return depts[0]["name"] if depts else None


def _strip(html: str) -> str:
    # Greenhouse returns HTML-escaped content; keep a light text version for hashing/scoring.
    import html as _html
    import re
    text = re.sub(r"<[^>]+>", " ", _html.unescape(html))
    return re.sub(r"\s+", " ", text).strip()[:6000]
