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
from datetime import datetime, timezone

from mail.gmail_client import (configured, fetch_threads, is_ats_sender,
                               looks_like_marketing, sent_by_domain)

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
    """Read recent threads, file one proposal per conversation."""
    if not settings.mail_enabled:
        return {"status": "disabled", "reason": "MAIL_ENABLED is false"}
    if not configured():
        return {"status": "not_configured",
                "reason": "set GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN "
                          "(scripts/gmail_auth.py mints the refresh token)"}

    apps = db.scalars(select(Application)).all()
    names = [a.company_name for a in apps if a.company_name]

    try:
        threads = fetch_threads(names, settings.mail_lookback_days,
                                limit or settings.mail_max_messages)
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        if "invalid_grant" in str(e).lower():
            detail = ("Gmail refused the refresh token (invalid_grant). If the OAuth client "
                      "is still in 'Testing' publishing status, Google expires refresh tokens "
                      "after 7 days — publish the app (it can stay unverified) and re-run "
                      "scripts/gmail_auth.py. It also means this if you revoked access.")
        log.warning("gmail fetch failed: %s", detail)
        return {"status": "error", "reason": detail}

    # Who he last wrote to, by domain — covers replies sent as new messages
    # rather than in-thread, which is how the Skydio thank-you was sent.
    try:
        sent_map = sent_by_domain(settings.mail_lookback_days)
    except Exception as e:
        log.warning("sent-mail scan failed (non-fatal): %s: %s", type(e).__name__, e)
        sent_map = {}

    created = updated = ignored = unmatched = 0
    for th in threads:
        inbound = th["latest_inbound"]
        if not inbound:
            continue          # a thread of only your own mail says nothing yet
        latest = th["latest"]
        row = db.scalar(select(MailMessage).where(MailMessage.thread_id == th["thread_id"]))
        app, why = match_application(inbound, apps)
        verdict = classify(inbound.get("subject"), inbound.get("body"))
        from_ats = is_ats_sender(inbound.get("from_addr"))
        marketing = looks_like_marketing(inbound.get("from_addr"), inbound.get("subject"))

        if row is None:
            row = MailMessage(message_id=inbound["message_id"], thread_id=th["thread_id"])
            db.add(row)
            is_new = True
        else:
            is_new = False
        row.from_addr = (inbound.get("from_addr") or "")[:300]
        row.subject = (inbound.get("subject") or "")[:500]
        row.snippet = (inbound.get("snippet") or "")[:500]
        row.received_at = inbound.get("received_at")
        row.awaiting = th["awaiting"]
        row.last_message_at = th["last_at"]
        row.last_outbound_at = (th["latest_outbound"] or {}).get("received_at")
        # A reply sent outside the thread still counts as a reply.
        dom = (re.search(r"@([\w.-]+)", inbound.get("from_addr") or "") or [None, ""])[1].lower()
        sent_at = sent_map.get(dom)
        if sent_at and sent_at > (inbound.get("received_at") or sent_at):
            row.awaiting = "them"
            if not row.last_outbound_at or row.last_outbound_at < sent_at:
                row.last_outbound_at = sent_at
        row.message_count = len(th["messages"])

        if marketing:
            row.status, row.kind = "ignored", "marketing"
            row.evidence = "job alert / account mail, not application correspondence"
            ignored += 1
            continue
        if not app and verdict["kind"] not in ("ack", "screen", "rejection", "offer"):
            row.status, row.kind = "unmatched", verdict["kind"]
            row.evidence = "no application matched this sender or subject"
            unmatched += 1
            continue
        if app and verdict["kind"] == "other" and not from_ats:
            row.status, row.kind = "ignored", "other"
            row.evidence = f"{why}, but no application language and not from an ATS"
            ignored += 1
            continue

        row.application_id = app.id if app else None
        row.kind = verdict["kind"]
        row.confidence = verdict["confidence"]
        row.proposed_stage = verdict["proposed_stage"]
        if verdict["kind"] == "ack":
            row.proposed_stage = "applied" if (not app or (app.stage or "") in
                                               ("watching", "drafting")) else None

        # What the thread says, not just the last inbound message. A screen
        # invite you already answered and attended is not an invitation any
        # more — and 13 days of silence after your reply is the actual next
        # action.
        # row.awaiting, not th["awaiting"]: the out-of-thread reply above may
        # have corrected it, and the explanation has to agree with the state.
        if row.awaiting == "them" and row.last_outbound_at:
            days = (datetime.now(timezone.utc) - row.last_outbound_at).days
            base = f"{why}. " if app else "No application in Recon matches this. "
            row.evidence = (f"{base}You replied {days} day{'s' if days != 1 else ''} ago "
                            f"and they haven't responded. {verdict['evidence']}")
            # Don't propose re-entering a stage he's already past by replying.
            if verdict["kind"] == "screen" and app and (app.stage or "") in ("screen", "onsite", "offer"):
                row.proposed_stage = None
        else:
            base = f"{why}. " if app else "No application in Recon matches this. Accepting creates one. "
            row.evidence = f"{base}{verdict['evidence']}"

        row.status = "pending" if row.status not in ("accepted", "dismissed") else row.status
        if is_new:
            created += 1
        else:
            updated += 1

    db.commit()
    log.info("mail poll: %d threads, %d new, %d updated, %d ignored, %d unmatched",
             len(threads), created, updated, ignored, unmatched)
    return {"status": "ok", "threads": len(threads), "proposals": created,
            "updated": updated, "ignored": ignored, "unmatched": unmatched}
