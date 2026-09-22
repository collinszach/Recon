"""Match recent mail to applications and file proposals.

Recon proposes; Zach decides. Nothing here moves an application — accepting a
proposal does (see `accept` in api/main.py), and every accepted proposal writes
an ApplicationEvent so the pipeline can always explain itself.
"""
from __future__ import annotations
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from db import Application, MailMessage
from mail.classify import classify
from mail.gmail_client import (configured, fetch, is_ats_sender,
                               looks_like_marketing)

log = logging.getLogger("recon.mail")

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company|group|technologies|labs)\b")


def _norm(s: str | None) -> str:
    return _PUNCT.sub(" ", _SUFFIX.sub(" ", (s or "").lower())).strip()


def match_application(msg: dict, apps: list[Application]) -> tuple[Application | None, str]:
    """The application this message is about, and why.

    Company name first: it appears in the sender's domain or display name on
    virtually every ATS mail ("Stripe via Greenhouse"). Role title is the
    tiebreak when several applications share a company.
    """
    hay = _norm(" ".join(filter(None, [msg.get("from_addr"), msg.get("subject"),
                                       (msg.get("body") or "")[:1500]])))
    candidates: list[tuple[Application, str]] = []
    for app in apps:
        name = _norm(app.company_name)
        if not name or len(name) < 3:
            continue
        if re.search(rf"\b{re.escape(name)}\b", hay):
            candidates.append((app, f"mentions {app.company_name}"))
    if not candidates:
        return None, ""
    if len(candidates) == 1:
        return candidates[0]
    # Several applications at the same company — use the role title.
    for app, why in candidates:
        title = _norm(app.role_title)
        if title and len(title) > 6 and re.search(rf"{re.escape(title[:40])}", hay):
            return app, f"{why}, and the role title"
    # Ambiguous: the most recently touched application is the likeliest, and the
    # proposal says so rather than pretending to be sure.
    best = max(candidates, key=lambda c: c[0].updated_at or c[0].created_at)
    return best[0], f"{best[1]} (several applications there; picked the most recent)"


def poll(db: Session, limit: int | None = None) -> dict:
    """Read recent mail, file proposals for anything that matches an application."""
    if not settings.mail_enabled:
        return {"status": "disabled", "reason": "MAIL_ENABLED is false"}
    if not configured():
        return {"status": "not_configured",
                "reason": "set GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN "
                          "(scripts/gmail_auth.py mints the refresh token)"}

    apps = db.scalars(select(Application)).all()
    names = [a.company_name for a in apps if a.company_name]
    seen = {m for (m,) in db.execute(select(MailMessage.message_id)).all()}

    try:
        messages = fetch(names, settings.mail_lookback_days,
                         limit or settings.mail_max_messages)
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        # The one failure that will happen on a schedule rather than at random:
        # while the OAuth client's publishing status is "Testing", Google
        # expires refresh tokens after 7 days, and the poller just starts
        # returning invalid_grant. Say so plainly instead of leaving a stack
        # trace in the worker log and an inbox that silently stops being read.
        if "invalid_grant" in str(e).lower():
            detail = ("Gmail refused the refresh token (invalid_grant). If the OAuth client "
                      "is still in 'Testing' publishing status, Google expires refresh tokens "
                      "after 7 days — publish the app (it can stay unverified) and re-run "
                      "scripts/gmail_auth.py. It also means this if you revoked access.")
        log.warning("gmail fetch failed: %s", detail)
        return {"status": "error", "reason": detail}

    created = skipped = unmatched = ignored = 0
    for msg in messages:
        if msg["message_id"] in seen:
            skipped += 1        # already looked at; a poll must be idempotent
            continue
        app, why = match_application(msg, apps)
        row = MailMessage(
            message_id=msg["message_id"], thread_id=msg.get("thread_id"),
            from_addr=(msg.get("from_addr") or "")[:300],
            subject=(msg.get("subject") or "")[:500],
            snippet=(msg.get("snippet") or "")[:500],
            received_at=msg.get("received_at"),
        )
        verdict = classify(msg.get("subject"), msg.get("body"))
        from_ats = is_ats_sender(msg.get("from_addr"))
        marketing = looks_like_marketing(msg.get("from_addr"), msg.get("subject"))

        # Three gates before anything reaches Zach as a proposal. The first
        # poll produced 8 proposals of which 7 were talent-marketing blasts,
        # LinkedIn alerts and a credit-card statement — all correctly
        # classified as `other`, so nothing moved, but all of it noise in a
        # section whose whole value is that it's short.
        if not app:
            row.status = "unmatched"
            row.kind = verdict["kind"]
            row.evidence = "no application matched this sender or subject"
            unmatched += 1
        elif marketing:
            row.status = "ignored"
            row.kind = "marketing"
            row.evidence = "job alert / account mail, not application correspondence"
            ignored += 1
        elif verdict["kind"] == "other" and not from_ats:
            # Mentions a company but says nothing an application would say, and
            # didn't come from an ATS. Kept so it isn't re-read every poll.
            row.status = "ignored"
            row.kind = "other"
            row.evidence = f"{why}, but no application language and not from an ATS"
            ignored += 1
        else:
            row.application_id = app.id
            row.kind = verdict["kind"]
            row.proposed_stage = verdict["proposed_stage"]
            row.confidence = verdict["confidence"]
            row.evidence = f"{why}. {verdict['evidence']}"
            row.status = "pending"
            created += 1
        db.add(row)
    db.commit()
    log.info("mail poll: %d messages, %d proposals, %d ignored, %d unmatched, %d already seen",
             len(messages), created, ignored, unmatched, skipped)
    return {"status": "ok", "messages": len(messages), "proposals": created,
            "ignored": ignored, "unmatched": unmatched, "already_seen": skipped}
