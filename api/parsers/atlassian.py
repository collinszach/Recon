"""Atlassian's own careers feed.

Atlassian moved off Lever to iCIMS, which has no public board API — the
configured `lever:atlassian` board has 404'd on every scan since. Their site
publishes the whole board as JSON instead:

  https://www.atlassian.com/endpoint/careers/listings

285 listings with title, locations, category, and the JD split across
`overview` / `responsibilities` / `qualifications`. `portalJobPost.portalUrl`
is the real application link (globalcareers-atlassian.icims.com/...), which is
what the app should open.

`token` is ignored — the feed is the whole company, there is no slug.
"""
from .base import ATSParser, NormalizedRole, client, polite_delay, parse_dt

FEED = "https://www.atlassian.com/endpoint/careers/listings"


class AtlassianParser(ATSParser):
    ats_name = "atlassian"

    def fetch(self, token: str) -> list[NormalizedRole]:
        with client() as c:
            resp = c.get(FEED)
            resp.raise_for_status()
            data = resp.json()
        polite_delay()

        roles: list[NormalizedRole] = []
        for job in data if isinstance(data, list) else []:
            post = job.get("portalJobPost") or {}
            locs = [l for l in (job.get("locations") or []) if l]
            # "Remote - Japan - Remote" style strings; join so geo.states_of
            # sees every office, and let it decide what's US.
            location = "; ".join(dict.fromkeys(locs)) or None
            roles.append(
                NormalizedRole(
                    ats_job_id=str(job.get("id") or post.get("id") or ""),
                    title=job.get("title", "Untitled"),
                    location=location,
                    remote_flag=any("remote" in l.lower() for l in locs),
                    department=job.get("category"),
                    url=post.get("portalUrl"),
                    description=_text(job),
                    posted_at=parse_dt(post.get("updatedDate")),
                )
            )
        return [r for r in roles if r.ats_job_id]


def _text(job: dict) -> str:
    """The JD, which the feed splits across three HTML fields."""
    import html as _html
    import re
    parts = [job.get("overview"), job.get("responsibilities"), job.get("qualifications")]
    blob = "\n\n".join(p for p in parts if p)
    text = re.sub(r"<[^>]+>", " ", _html.unescape(blob))
    return re.sub(r"\s+", " ", text).strip()[:6000]
