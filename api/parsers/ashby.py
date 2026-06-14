"""Ashby public job board posting API.

Endpoint:
  https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true

`org` is the company's Ashby job-board slug.
"""
from .base import ATSParser, NormalizedRole, client, polite_delay, parse_dt

BASE = "https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true"


class AshbyParser(ATSParser):
    ats_name = "ashby"

    def fetch(self, token: str) -> list[NormalizedRole]:
        url = BASE.format(org=token)
        with client() as c:
            resp = c.get(url)
            resp.raise_for_status()
            data = resp.json()
        polite_delay()

        roles: list[NormalizedRole] = []
        for job in data.get("jobs", []):
            roles.append(
                NormalizedRole(
                    ats_job_id=str(job.get("id")),
                    title=job.get("title", "Untitled"),
                    location=job.get("location"),
                    remote_flag=bool(job.get("isRemote")),
                    department=job.get("department") or job.get("team"),
                    url=job.get("jobUrl") or job.get("applyUrl"),
                    description=(job.get("descriptionPlain") or "")[:6000],
                    posted_at=parse_dt(job.get("publishedAt") or job.get("publishedDate")),
                )
            )
        return roles
