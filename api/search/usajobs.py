"""USAJobs — the official US federal jobs API (free). High signal for Zach's
Charleston / DC-NoVA defense & gov-tech target metros.

Docs: https://developer.usajobs.gov/  (key from developer.usajobs.gov/apirequest/)
Auth: User-Agent = your contact email, Authorization-Key = your API key.
"""
import logging

import httpx

from config import settings
from parsers.base import NormalizedRole, parse_dt
from search.base import SearchProvider, SearchResult

log = logging.getLogger("recon.search.usajobs")
_URL = "https://data.usajobs.gov/api/search"


class USAJobsProvider(SearchProvider):
    name = "usajobs"

    def enabled(self) -> bool:
        return bool(settings.usajobs_api_key and settings.usajobs_email)

    def search(self, term: str) -> list[SearchResult]:
        headers = {
            "Host": "data.usajobs.gov",
            "User-Agent": settings.usajobs_email,
            "Authorization-Key": settings.usajobs_api_key,
        }
        params = {"Keyword": term, "ResultsPerPage": min(settings.search_max_results_per_query, 500)}
        out: list[SearchResult] = []
        with httpx.Client(timeout=25.0, headers=headers) as cx:
            r = cx.get(_URL, params=params)
            r.raise_for_status()
            items = ((r.json().get("SearchResult") or {}).get("SearchResultItems") or [])
            for it in items:
                d = it.get("MatchedObjectDescriptor") or {}
                emp = (d.get("OrganizationName") or "").strip()
                title = (d.get("PositionTitle") or "").strip()
                if not emp or not title:
                    continue
                loc = d.get("PositionLocationDisplay") or ""
                if not loc:
                    pl = d.get("PositionLocation") or []
                    loc = "; ".join(x.get("LocationName", "") for x in pl if x.get("LocationName"))
                apply = d.get("ApplyURI") or []
                url = apply[0] if apply else d.get("PositionURI")
                cats = d.get("JobCategory") or []
                dept = cats[0].get("Name") if cats and isinstance(cats[0], dict) else None
                summary = (((d.get("UserArea") or {}).get("Details") or {}).get("JobSummary")
                           or d.get("QualificationSummary") or "")
                out.append(SearchResult(
                    employer=emp,
                    role=NormalizedRole(
                        ats_job_id=f"usajobs:{d.get('PositionID') or url or title}",
                        title=title,
                        location=loc or None,
                        remote_flag="remote" in loc.lower(),
                        department=dept,
                        url=url,
                        description=summary[:4000],
                        posted_at=parse_dt(d.get("PublicationStartDate")),
                    ),
                ))
        return out
