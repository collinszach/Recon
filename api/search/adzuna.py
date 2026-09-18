"""Adzuna public jobs API — free tier, broad cross-board aggregation.

Docs: https://developer.adzuna.com/overview (free signup for app_id/app_key,
generous free tier). Adzuna aggregates postings from many company career sites
and smaller/regional boards — meaningfully wider long-tail coverage than
JSearch/TheMuse alone, which is exactly the gap that left states like Colorado
thin (2026-08-16, Zach: "I want to expand our search to more websites").

  GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}
      ?app_id=&app_key=&what=<term>&content-type=application/json
"""
import logging

import httpx

from config import settings
from parsers.base import NormalizedRole, parse_dt
from search.base import SearchProvider, SearchResult

log = logging.getLogger("recon.search.adzuna")
_BASE = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
_MAX_PAGES = 2
_RESULTS_PER_PAGE = 50


class AdzunaProvider(SearchProvider):
    name = "adzuna"

    def enabled(self) -> bool:
        return bool(settings.adzuna_app_id and settings.adzuna_app_key)

    def search(self, term: str) -> list[SearchResult]:
        out: list[SearchResult] = []
        with httpx.Client(timeout=25.0, headers={"User-Agent": settings.scan_user_agent}) as cx:
            for page in range(1, _MAX_PAGES + 1):
                url = _BASE.format(country=settings.adzuna_country, page=page)
                r = cx.get(url, params={
                    "app_id": settings.adzuna_app_id,
                    "app_key": settings.adzuna_app_key,
                    "what": term,
                    "results_per_page": _RESULTS_PER_PAGE,
                    "content-type": "application/json",
                })
                r.raise_for_status()
                data = r.json()
                results = data.get("results") or []
                for j in results:
                    emp = ((j.get("company") or {}).get("display_name") or "").strip()
                    title = (j.get("title") or "").strip()
                    jid = j.get("id")
                    if not emp or not title or not jid:
                        continue
                    loc = (j.get("location") or {}).get("display_name")
                    out.append(SearchResult(
                        employer=emp,
                        role=NormalizedRole(
                            ats_job_id=f"adzuna:{jid}",
                            title=title,
                            location=loc,
                            remote_flag=bool(loc and "remote" in loc.lower()),
                            url=j.get("redirect_url"),
                            description=(j.get("description") or "")[:4000],
                            posted_at=parse_dt(j.get("created")),
                        ),
                    ))
                if len(results) < _RESULTS_PER_PAGE:
                    break
        return out
