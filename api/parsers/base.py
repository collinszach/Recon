"""Parser interface. Each ATS implements fetch() -> list[NormalizedRole]."""
from __future__ import annotations
import hashlib
import html
import random
import re
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
import httpx
from config import settings


def parse_dt(value) -> datetime | None:
    """Best-effort parse of an ATS posting date: ISO-8601 string or epoch (s/ms)."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 1e12:  # epoch milliseconds
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        s = str(value).strip()
        if not s:
            return None
        if s.isdigit():
            return parse_dt(int(s))
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, OSError, OverflowError):
        return None


_DROP_RE = re.compile(r"<(script|style|noscript|svg|head)[^>]*>.*?</\1>",
                      re.IGNORECASE | re.DOTALL)
_BREAK_RE = re.compile(r"</(p|div|li|tr|ul|ol|h[1-6])>|<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
# \u00a0 belongs here: an unescaped &nbsp; is a non-breaking space, and left
# alone it survives every later collapse and reaches the reader as a gap.
_WS_RE = re.compile(r"[ \t\r\f\v\u00a0]+")
_NL_RE = re.compile(r"\n{3,}")


def html_to_text(raw: str, *, pre_unescape: bool = False) -> str:
    """HTML to readable plain text, keeping block boundaries as newlines.

    A job description is read by a person, so the structure is the point:
    dropping it turns a posting into one unbroken paragraph. Block ends become
    newlines before the tags are stripped, rather than after, when the
    information is already gone.

    `pre_unescape` is for feeds that deliver their HTML *escaped* — Greenhouse's
    `content` arrives as `&lt;div class=&quot;…`. One unescape yields real tags
    whose own entities are still escaped, so those feeds need a pass before the
    tags are handled and another after, or `&nbsp;` survives into the text.
    """
    t = html.unescape(raw) if pre_unescape else raw
    t = _DROP_RE.sub(" ", t)
    t = _BREAK_RE.sub("\n", t)
    t = _TAG_RE.sub(" ", t)
    t = html.unescape(t)
    t = _WS_RE.sub(" ", t)
    t = "\n".join(line.strip() for line in t.split("\n"))
    return _NL_RE.sub("\n\n", t).strip()


@dataclass
class NormalizedRole:
    ats_job_id: str
    title: str
    location: str | None = None
    remote_flag: bool = False
    department: str | None = None
    url: str | None = None
    description: str = ""
    posted_at: "datetime | None" = None      # when the ATS says it was posted
    description_hash: str = field(default="")

    def __post_init__(self):
        if not self.description_hash:
            blob = f"{self.title}|{self.location}|{self.department}|{self.description}"
            self.description_hash = hashlib.sha256(blob.encode()).hexdigest()[:32]


def polite_delay() -> None:
    time.sleep(random.uniform(settings.scan_min_delay_sec, settings.scan_max_delay_sec))


def client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": settings.scan_user_agent, "Accept": "application/json"},
        timeout=20.0,
        follow_redirects=True,
    )


class ATSParser:
    """Subclass and implement fetch()."""
    ats_name: str = "base"
    # True: fetch() returns the company's full board, so roles absent from the
    # result are genuinely gone and reconcile may close them. False: fetch()
    # returns a sampled slice (e.g. targeted keyword queries against a huge
    # board), so missing roles must NOT be closed — same rule as search results.
    authoritative: bool = True

    def fetch(self, token: str) -> list[NormalizedRole]:
        raise NotImplementedError
