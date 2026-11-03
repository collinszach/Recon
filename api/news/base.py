"""News-provider interface — one request per company, returning recent articles.

Mirrors search/base.py: a provider knows its own credentials (enabled()) and
how many requests a day it can afford (daily_budget); news/runner.py decides
which companies to ask about and does all the dedupe, matching and tagging.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Article:
    title: str
    url: str
    source: str | None = None
    description: str | None = None
    published_at: datetime | None = None


class NewsProvider:
    name: str = "base"
    daily_budget: int = 0           # requests/day the free tier comfortably allows
    min_interval_sec: float = 1.0   # politeness gap between requests

    def enabled(self) -> bool:
        raise NotImplementedError

    def fetch(self, phrases: list[str], since: datetime) -> list[Article]:
        """Articles mentioning any of `phrases` (exact-phrase search) published
        after `since`, newest first."""
        raise NotImplementedError


def or_query(phrases: list[str]) -> str:
    """'"A"' or '("A" OR "B")' — both GNews and GDELT accept this form."""
    quoted = [f'"{p}"' for p in phrases]
    return quoted[0] if len(quoted) == 1 else "(" + " OR ".join(quoted) + ")"
