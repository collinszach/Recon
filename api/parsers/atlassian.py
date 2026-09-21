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

        # The feed repeats a job once per regional portal — 289 listings, 272
        # distinct ids, one id three times. Inserting them as-is violates the
        # (company_id, ats_job_id) unique constraint, which aborts the whole
        # company's scan and leaves Atlassian with zero roles. Merge instead of
        # dropping, so a job posted in two regions keeps both locations.
        merged: dict[str, dict] = {}
        for job in data if isinstance(data, list) else []:
            post = job.get("portalJobPost") or {}
            job_id = str(job.get("id") or post.get("id") or "")
            if not job_id:
                continue
            locs = [l for l in (job.get("locations") or []) if l]
            prev = merged.get(job_id)
            if prev:
                prev["locs"].extend(l for l in locs if l not in prev["locs"])
                # Keep the fullest copy of the JD; the portals differ slightly.
                if len(_text(job)) > len(prev["description"]):
                    prev["description"] = _text(job)
                continue
            merged[job_id] = {"job": job, "post": post, "locs": list(locs),
                              "description": _text(job)}

        roles: list[NormalizedRole] = []
        for job_id, m in merged.items():
            job, post, locs = m["job"], m["post"], m["locs"]
            # "Remote - Japan - Remote" style strings; join so geo.states_of
            # sees every office, and let it decide what's US.
            roles.append(
                NormalizedRole(
                    ats_job_id=job_id,
                    title=job.get("title", "Untitled"),
                    location="; ".join(dict.fromkeys(locs)) or None,
                    remote_flag=any("remote" in l.lower() for l in locs),
                    department=job.get("category"),
                    url=post.get("portalUrl"),
                    description=m["description"],
                    posted_at=parse_dt(post.get("updatedDate")),
                )
            )
        return roles


def _text(job: dict) -> str:
    """The JD, which the feed splits across three HTML fields."""
    import html as _html
    import re
    parts = [job.get("overview"), job.get("responsibilities"), job.get("qualifications")]
    blob = "\n\n".join(p for p in parts if p)
    text = re.sub(r"<[^>]+>", " ", _html.unescape(blob))
    return re.sub(r"\s+", " ", text).strip()[:6000]
