"""GDELT DOC 2.0 — keyless fallback when no GNews key is configured.

Free, no account, global coverage — but headlines only (no description), more
syndication noise, and an unofficial limit of one request per 5 seconds,
enforced per IP. A throttled or rejected query comes back as plain text, not
JSON, so a non-JSON body is treated as "no articles", never as a crash.
Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
"""
import logging
from datetime import datetime, timezone

import httpx

from config import settings
from news.base import Article, NewsProvider, or_query

log = logging.getLogger("recon.news.gdelt")
_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def _seendate(s: str | None) -> datetime | None:
    # "20261101T123000Z"
    try:
        return datetime.strptime(s or "", "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class GdeltProvider(NewsProvider):
    name = "gdelt"
    daily_budget = 250
    min_interval_sec = 6.0

    def enabled(self) -> bool:
        return True

    def fetch(self, phrases: list[str], since: datetime) -> list[Article]:
        days = max(1, (datetime.now(timezone.utc) - since).days)
        params = {
            "query": f"{or_query(phrases)} sourcelang:english",
            "mode": "artlist",
            "format": "json",
            "maxrecords": 15,
            "sort": "datedesc",
            "timespan": f"{days}d",
        }
        with httpx.Client(timeout=30.0, headers={"User-Agent": settings.scan_user_agent}) as cx:
            r = cx.get(_URL, params=params)
            r.raise_for_status()
            try:
                items = r.json().get("articles") or []
            except ValueError:
                log.info("gdelt non-JSON reply for %s: %s", phrases, r.text[:120])
                return []
        out = []
        for it in items:
            title, url = (it.get("title") or "").strip(), (it.get("url") or "").strip()
            if not title or not url:
                continue
            out.append(Article(title=title, url=url, source=it.get("domain"),
                               published_at=_seendate(it.get("seendate"))))
        return out
