"""GNews (gnews.io) — the default when GNEWS_API_KEY is set.

Free tier: 100 requests/day, 10 articles/request, 1 request/second, articles
delayed ~12h, non-commercial use (a personal job tracker qualifies). Returns a
title and a description, which is what makes keyword tagging work well.
Docs: https://gnews.io/docs/v4#search-endpoint
"""
import logging
from datetime import datetime, timezone

import httpx

from config import settings
from news.base import Article, NewsProvider, or_query
from parsers.base import parse_dt

log = logging.getLogger("recon.news.gnews")
_URL = "https://gnews.io/api/v4/search"


class GNewsProvider(NewsProvider):
    name = "gnews"
    daily_budget = 90           # leave 10 of the 100 for manual /api/news/run calls
    min_interval_sec = 1.1

    def enabled(self) -> bool:
        return bool(settings.gnews_api_key)

    def fetch(self, phrases: list[str], since: datetime) -> list[Article]:
        params = {
            "q": or_query(phrases),
            "lang": "en",
            "max": 10,
            "sortby": "publishedAt",
            "from": since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "apikey": settings.gnews_api_key,
        }
        with httpx.Client(timeout=20.0, headers={"User-Agent": settings.scan_user_agent}) as cx:
            r = cx.get(_URL, params=params)
            r.raise_for_status()
            items = r.json().get("articles") or []
        out = []
        for it in items:
            title, url = (it.get("title") or "").strip(), (it.get("url") or "").strip()
            if not title or not url:
                continue
            out.append(Article(
                title=title, url=url,
                source=(it.get("source") or {}).get("name"),
                description=(it.get("description") or "").strip() or None,
                published_at=parse_dt(it.get("publishedAt")),
            ))
        return out
