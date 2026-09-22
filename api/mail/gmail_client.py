"""Read-only Gmail access.

Auth is a long-lived refresh token minted once by `scripts/gmail_auth.py` on
Zach's Mac. That keeps the OAuth redirect on `localhost`, which Google permits
over plain http, so the API never hosts a callback and never needs to be
publicly reachable — it only ever exchanges the refresh token for short-lived
access tokens.

Scope is `gmail.readonly`. Recon cannot send, label, or delete mail, and the
grant is revocable on its own from the Google account.
"""
from __future__ import annotations
import base64
import logging
import re
from datetime import datetime, timedelta, timezone

from config import settings

log = logging.getLogger("recon.mail")

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# The senders that carry almost all real application mail. Matching on these
# (rather than reading everything) keeps Recon's footprint to the mail it
# actually needs — see the targeted-query decision, 2026-09-21.
ATS_SENDERS = [
    "greenhouse.io", "lever.co", "hire.lever.co", "ashbyhq.com",
    "myworkday.com", "myworkdayjobs.com", "icims.com", "smartrecruiters.com",
    "workable.com", "jobvite.com", "taleo.net", "successfactors.com",
    "recruiting.paylocity.com", "phenompeople.com", "avature.net",
]


def configured() -> bool:
    return bool(settings.gmail_client_id and settings.gmail_client_secret
                and settings.gmail_refresh_token)


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=settings.gmail_refresh_token,
        client_id=settings.gmail_client_id,
        client_secret=settings.gmail_client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def build_query(company_names: list[str], lookback_days: int) -> str:
    """Gmail search for mail that could plausibly be about an application.

    Either it came from a known ATS, or it mentions a company Zach has actually
    applied to. Anything else is not read.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y/%m/%d")
    senders = " OR ".join(f"from:{d}" for d in ATS_SENDERS)
    clauses = [f"({senders})"]
    # Quoted company names, deduped and capped — Gmail's query length is finite
    # and a 200-company OR is both slow and pointless.
    names = [n for n in dict.fromkeys(company_names) if n and len(n) > 2][:40]
    if names:
        quoted = " OR ".join(f'"{n}"' for n in names)
        clauses.append(f"({quoted})")
    return f"after:{since} ({' OR '.join(clauses)})"


def _header(payload: dict, name: str) -> str | None:
    for h in payload.get("headers", []) or []:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None


def _body_text(payload: dict, depth: int = 0) -> str:
    """Plain-text body, walking multipart. Falls back to stripped HTML."""
    if depth > 6:
        return ""
    mime = payload.get("mimeType", "")
    data = (payload.get("body") or {}).get("data")
    if data and mime == "text/plain":
        return base64.urlsafe_b64decode(data + "===").decode("utf-8", "replace")
    if data and mime == "text/html":
        html = base64.urlsafe_b64decode(data + "===").decode("utf-8", "replace")
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    out = []
    for part in payload.get("parts", []) or []:
        t = _body_text(part, depth + 1)
        if t:
            out.append(t)
    return "\n".join(out)


def fetch(company_names: list[str], lookback_days: int, limit: int) -> list[dict]:
    """Recent messages matching the targeted query, newest first."""
    svc = _service()
    q = build_query(company_names, lookback_days)
    log.info("gmail query: %s", q[:200])
    listing = svc.users().messages().list(userId="me", q=q, maxResults=limit).execute()
    out = []
    for stub in listing.get("messages", []) or []:
        msg = svc.users().messages().get(
            userId="me", id=stub["id"], format="full").execute()
        payload = msg.get("payload") or {}
        ts = msg.get("internalDate")
        out.append({
            "message_id": msg.get("id"),
            "thread_id": msg.get("threadId"),
            "from_addr": _header(payload, "From"),
            "subject": _header(payload, "Subject"),
            "snippet": msg.get("snippet"),
            "body": _body_text(payload)[:8000],
            "received_at": (datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc)
                            if ts else None),
        })
    return out
