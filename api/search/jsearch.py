"""JSearch (RapidAPI) — Google-for-Jobs aggregator that indexes LinkedIn,
Indeed, Glassdoor, ZipRecruiter, and employer boards. Free tier available.

Docs: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
We query nationwide per term (few requests = free-tier friendly) and let the
caller geo-filter to the target metros.
"""
import logging

import httpx

from config import settings
from parsers.base import NormalizedRole, parse_dt
from search.base import SearchProvider, SearchResult

log = logging.getLogger("recon.search.jsearch")
_HOST = "jsearch.p.rapidapi.com"


class JSearchProvider(SearchProvider):
    name = "jsearch"

    def enabled(self) -> bool:
        return bool(settings.jsearch_api_key)

    def search(self, term: str) -> list[SearchResult]:
        headers = {"X-RapidAPI-Key": settings.jsearch_api_key, "X-RapidAPI-Host": _HOST}
        out: list[SearchResult] = []
        with httpx.Client(timeout=25.0, headers=headers) as cx:
            for page in range(1, max(1, settings.search_max_pages) + 1):
                r = cx.get(f"https://{_HOST}/search", params={
                    "query": f"{term} in United States",
                    "date_posted": settings.search_date_posted,
                    "country": "us",
                    "page": page,
                    "num_pages": 1,
                })
                r.raise_for_status()
                data = r.json().get("data") or []
                for j in data:
                    emp = (j.get("employer_name") or "").strip()
                    title = (j.get("job_title") or "").strip()
                    if not emp or not title:
                        continue
                    jid = j.get("job_id") or j.get("job_apply_link") or title
                    loc = ", ".join(x for x in (j.get("job_city"), j.get("job_state")) if x) \
                        or j.get("job_country") or None
                    out.append(SearchResult(
                        employer=emp,
                        role=NormalizedRole(
                            ats_job_id=f"jsearch:{jid}",
                            title=title,
                            location=loc,
                            remote_flag=bool(j.get("job_is_remote")),
                            url=j.get("job_apply_link") or j.get("job_google_link"),
                            description=(j.get("job_description") or "")[:4000],
                            posted_at=parse_dt(j.get("job_posted_at_datetime_utc")),
                        ),
                    ))
                if len(data) < 10:        # last page reached
                    break
        return out
