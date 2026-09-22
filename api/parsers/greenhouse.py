"""Greenhouse public job board API.

Endpoint:
  https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

`token` is the board slug, e.g. the company's greenhouse board name.
"""
from .base import (ATSParser, NormalizedRole, client, html_to_text,
                   polite_delay, parse_dt)

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
                    posted_at=parse_dt(job.get("first_published") or job.get("updated_at")),
                )
            )
        return roles


def _first_department(job: dict) -> str | None:
    depts = job.get("departments") or []
    return depts[0]["name"] if depts else None


def _strip(content: str) -> str:
    """Greenhouse delivers `content` HTML-escaped, so it needs the pre-unescape
    pass — without it `&nbsp;` survives tag-stripping and is shown to the reader
    verbatim, which is what happened until 2026-09-22.

    This used to flatten every tag and newline into a single space. That was
    fine while the JD was only hashed and fed to the scorer; it is now read by a
    person, and a 6,000-character posting with no paragraph breaks is unusable.
    """
    return html_to_text(content, pre_unescape=True)[:6000]
