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


# A company name alone is not a reason to read an email. The first live poll
# matched a Capital One AutoPay statement because Zach has a Capital One
# application, and LinkedIn job alerts because they mention companies he's
# applied to. So the company clause additionally requires application language,
# and these senders are never read at all.
APPLICATION_WORDS = [
    '"your application"', '"thank you for applying"', "candidacy", "candidate",
    "recruiter", "interview", '"move forward"', '"next steps"', '"application"',
]
SENDER_DENYLIST = [
    "jobalerts-noreply@linkedin.com", "notifications-noreply@linkedin.com",
    "jobs-listings@linkedin.com", "notification.capitalone.com",
    "email.careers.microsoft.com", "indeedemail.com", "ziprecruiter.com",
    "glassdoor.com", "jobright.ai", "hellofresh", "noreply@medium.com",
]
# Marketing and account mail that survives the sender rules.
SUBJECT_DENYLIST = re.compile(
    r"(job alert|new jobs?\b|jobs? (for|at|that match)|roles at |profile is popular|"
    r"search appearances|payment|autopay|statement|invoice|receipt|"
    r"your account|verify your|newsletter|unsubscribe|webinar|"
    r"people you may know|who viewed)", re.IGNORECASE)


def build_query(company_names: list[str], lookback_days: int) -> str:
    """Gmail search for mail that could plausibly be about an application.

    Either it came from a known ATS, or it mentions a company Zach applied to
    **and** talks like application correspondence. The second half of that is
    not optional: without it, any mail mentioning the company matches, which on
    the first live poll meant a credit-card statement.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y/%m/%d")
    senders = " OR ".join(f"from:{d}" for d in ATS_SENDERS)
    clauses = [f"({senders})"]
    # Quoted company names, deduped and capped — Gmail's query length is finite
    # and a 200-company OR is both slow and pointless.
    names = [n for n in dict.fromkeys(company_names) if n and len(n) > 2][:40]
    if names:
        quoted = " OR ".join(f'"{n}"' for n in names)
        words = " OR ".join(APPLICATION_WORDS)
        clauses.append(f"(({quoted}) AND ({words}))")
    excluded = " ".join(f"-from:{d}" for d in SENDER_DENYLIST)
    return f"after:{since} ({' OR '.join(clauses)}) {excluded}"


def is_ats_sender(from_addr: str | None) -> bool:
    low = (from_addr or "").lower()
    return any(d in low for d in ATS_SENDERS)


def looks_like_marketing(from_addr: str | None, subject: str | None) -> bool:
    low = (from_addr or "").lower()
    if any(d in low for d in SENDER_DENYLIST):
        return True
    return bool(SUBJECT_DENYLIST.search(subject or ""))


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
