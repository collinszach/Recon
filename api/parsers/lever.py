"""Lever public postings API.

Endpoint:
  https://api.lever.co/v0/postings/{org}?mode=json

`org` is the company's Lever slug.
"""
from .base import ATSParser, NormalizedRole, client, polite_delay, parse_dt

BASE = "https://api.lever.co/v0/postings/{org}?mode=json"


class LeverParser(ATSParser):
    ats_name = "lever"

    def fetch(self, token: str) -> list[NormalizedRole]:
        url = BASE.format(org=token)
        with client() as c:
            resp = c.get(url)
            resp.raise_for_status()
            data = resp.json()
        polite_delay()

        roles: list[NormalizedRole] = []
        for job in data:
            cats = job.get("categories") or {}
            loc = cats.get("location")
            roles.append(
                NormalizedRole(
                    ats_job_id=str(job.get("id")),
                    title=job.get("text", "Untitled"),
                    location=loc,
                    remote_flag=bool(loc and "remote" in loc.lower()),
                    department=cats.get("team") or cats.get("department"),
                    url=job.get("hostedUrl") or job.get("applyUrl"),
                    description=(job.get("descriptionPlain") or "")[:6000],
                    posted_at=parse_dt(job.get("createdAt")),
                )
            )
        return roles
