"""The Muse (themuse.com) public jobs API — free, no key required.

Docs: https://www.themuse.com/developers/api/v2
  GET https://www.themuse.com/api/public/jobs?category=&company=&location=&page=

Muse is curated (partner employers) and browses by CATEGORY, not free text, so:
  * search(term)  -> map our track terms to Muse categories and return
                     cross-employer results (feeds search_runner's employer
                     upsert, exactly like JSearch/USAJobs did).
  * search_company(name) -> exact company filter, used by the company sweep to
                     pin a known employer's roles.

No auth needed (500 req/hr); an optional free api_key raises the limit. Muse
won't have every employer (no Apple/Amazon/Google) — those are covered by
first-party parsers / the manual escape hatch — but it does carry a broad slice
of the long tail (Uber, Celonis, Bank of America, Flexport, ...).
"""
import logging

import httpx

from config import settings
from parsers.base import NormalizedRole, parse_dt
from search.base import SearchProvider, SearchResult

log = logging.getLogger("recon.search.themuse")
_BASE = "https://www.themuse.com/api/public/jobs"
_MAX_PAGES = 2

# our seed company name -> Muse's exact stored company name (verified live)
_COMPANY_ALIAS = {
    "Chase": "JPMorgan Chase",
    "Meta Reality Labs": "Meta",
}

# our track terms -> Muse's fixed category enum
_CATEGORY_MAP = {
    "product manager": "Product Management",
    "technical product manager": "Product Management",
    "technical program manager": "Project Management",
    "solutions engineer": "Engineering",
    "forward deployed engineer": "Engineering",
    "data engineer": "Data and Analytics",
    "developer experience": "Software Engineering",
    "autonomy engineer": "Engineering",
}


class MuseProvider(SearchProvider):
    name = "themuse"

    def enabled(self) -> bool:
        return settings.themuse_enabled

    def search(self, term: str) -> list[SearchResult]:
        cat = _CATEGORY_MAP.get(term.strip().lower())
        if not cat:
            return []                         # unmapped term -> skip (no free-text)
        return self._fetch({"category": cat})

    def search_company(self, company: str) -> list[SearchResult]:
        # Muse filters on its own exact company name; map ours where they differ.
        return self._fetch({"company": _COMPANY_ALIAS.get(company, company)})

    def _fetch(self, params: dict) -> list[SearchResult]:
        out: list[SearchResult] = []
        base = dict(params)
        if settings.themuse_api_key:
            base["api_key"] = settings.themuse_api_key
        with httpx.Client(timeout=25.0, headers={"User-Agent": settings.scan_user_agent}) as cx:
            for page in range(_MAX_PAGES):
                r = cx.get(_BASE, params={**base, "page": page})
                if r.status_code == 400:      # Muse 400s past the last page
                    break
                r.raise_for_status()
                data = r.json()
                results = data.get("results") or []
                for j in results:
                    emp = ((j.get("company") or {}).get("name") or "").strip()
                    title = (j.get("name") or "").strip()
                    if not emp or not title:
                        continue
                    locs = ", ".join(l.get("name") for l in (j.get("locations") or [])
                                     if l.get("name")) or None
                    out.append(SearchResult(
                        employer=emp,
                        role=NormalizedRole(
                            ats_job_id=f"themuse:{j.get('id')}",
                            title=title,
                            location=locs,
                            remote_flag=bool(locs and "remote" in locs.lower()),
                            url=(j.get("refs") or {}).get("landing_page"),
                            description=(j.get("contents") or "")[:4000],
                            posted_at=parse_dt(j.get("publication_date")),
                        ),
                    ))
                if page + 1 >= (data.get("page_count") or 0):
                    break
        return out
