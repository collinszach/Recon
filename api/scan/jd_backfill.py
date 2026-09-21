"""Re-fetch job descriptions for roles that were stored without one.

Search-sourced roles (Adzuna / JSearch / The Muse / USAJobs) were ingested with
`description_hash` but no `description` until 2026-09-21 — the providers return
the text, `scan/search_runner.py` simply never passed it to `Role(...)`. That
left 1,159 open roles with no JD, 138 of them internships.

The ingest bug is fixed going forward; this fills in what is already in the DB
by fetching each role's posting URL and extracting its text. It is best-effort
by nature — aggregator links redirect, boards bot-wall, postings expire — so it
reports a per-source success rate rather than pretending to be complete, never
overwrites a better description with a worse one, and is safe to re-run.
"""
from __future__ import annotations
import logging
import re

import httpx
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session

from db import Role

log = logging.getLogger("recon.jd_backfill")

# A description this short is a teaser, not a JD (Adzuna truncates to ~200).
MIN_USEFUL = 200
MAX_STORED = 4000        # same cap the ingest paths use

_DROP_RE = re.compile(r"<(script|style|noscript|svg|head)[^>]*>.*?</\1>",
                      re.IGNORECASE | re.DOTALL)
_BREAK_RE = re.compile(r"</(p|div|li|tr|h[1-6])>|<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NL_RE = re.compile(r"\n{3,}")

# Pages that came back as a bot wall / login / expired posting rather than a JD.
# Checked against the extracted text, which is why they're plain phrases.
_JUNK_RE = re.compile(
    r"(enable\s+javascript|verify\s+you\s+are\s+human|access\s+denied|"
    r"are\s+you\s+a\s+robot|sign\s+in\s+to\s+continue|this\s+job\s+is\s+no\s+longer|"
    r"job\s+not\s+found|page\s+not\s+found|has\s+been\s+filled)", re.IGNORECASE)


def html_to_text(html: str) -> str:
    """Crude but dependency-free: drop scripts, turn block ends into newlines,
    strip the remaining tags, unescape the handful of entities that matter."""
    t = _DROP_RE.sub(" ", html)
    t = _BREAK_RE.sub("\n", t)
    t = _TAG_RE.sub(" ", t)
    for ent, ch in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                    ("&quot;", '"'), ("&#39;", "'"), ("&rsquo;", "'"), ("&mdash;", "—")):
        t = t.replace(ent, ch)
    t = _WS_RE.sub(" ", t)
    t = "\n".join(line.strip() for line in t.split("\n"))
    return _NL_RE.sub("\n\n", t).strip()


def _fetch(url: str, timeout: float) -> str | None:
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                             "AppleWebKit/537.36 (KHTML, like Gecko) "
                                             "Chrome/124.0 Safari/537.36"})
        if r.status_code != 200 or not r.text:
            return None
        return r.text
    except Exception as e:
        log.debug("fetch failed %s: %s: %s", url, type(e).__name__, e)
        return None


def backfill(db: Session, limit: int = 50, source: str | None = None,
             timeout: float = 15.0) -> dict:
    """Fill in missing descriptions for open roles, newest first.

    Returns per-source counts: attempted / filled / no_url / fetch_failed /
    too_short (the page came back but held no usable JD).
    """
    q = (select(Role)
         .where(Role.status.in_(["open", "changed"]),
                Role.url.isnot(None),
                or_(Role.description.is_(None),
                    func.length(Role.description) < MIN_USEFUL))
         .order_by(Role.first_seen.desc())
         .limit(limit))
    if source:
        q = q.where(Role.source == source)
    rows = db.scalars(q).all()

    stats: dict[str, dict[str, int]] = {}

    def bump(src: str, key: str) -> None:
        stats.setdefault(src, {"attempted": 0, "filled": 0, "no_url": 0,
                               "fetch_failed": 0, "too_short": 0})[key] += 1

    for r in rows:
        src = r.source or "ats"
        bump(src, "attempted")
        if not r.url:
            bump(src, "no_url")
            continue
        html = _fetch(r.url, timeout)
        if not html:
            bump(src, "fetch_failed")
            continue
        text = html_to_text(html)[:MAX_STORED]
        # Only ever trade up: a bot wall or a stub must not clobber whatever
        # little text the provider did give us.
        if len(text) < MIN_USEFUL or len(text) <= len(r.description or "") or _JUNK_RE.search(text[:600]):
            bump(src, "too_short")
            continue
        r.description = text
        bump(src, "filled")

    db.commit()
    filled = sum(s["filled"] for s in stats.values())
    log.info("jd backfill: %d filled of %d attempted %s", filled, len(rows), stats)
    return {"attempted": len(rows), "filled": filled, "by_source": stats}
