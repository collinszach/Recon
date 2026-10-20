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
from mail.classify import classify, placeholder_title, role_title, same_role
from datetime import datetime, timezone

from mail.gmail_client import (configured, fetch_threads, is_ats_sender,
                               looks_like_marketing, mailbox_address, sent_by_domain)

log = logging.getLogger("recon.mail")

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company|group|technologies|labs)\b")


def _norm(s: str | None) -> str:
    return _PUNCT.sub(" ", _SUFFIX.sub(" ", (s or "").lower())).strip()


def match_application(msg: dict, apps: list[Application],
                      role: str | None = None) -> tuple[Application | None, str]:
    """The application this message is about, and why.

    Company name first: it appears in the sender's domain or display name on
    virtually every ATS mail ("Stripe via Greenhouse"). When the mail names a
    role, the role decides among that company's applications — and a role
    Recon has no application for is a NEW application, not the nearest
    existing one. Before this, Intuit's six confirmations all attached to
    whichever Intuit row came first, and five applications never existed.
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
    if role:
        for app, why in candidates:
            if same_role(app.role_title, role):
                return app, f"{why}, and the role ({role})"
        # An application titled with an email subject is one whose role was
        # never known; the mail can claim it rather than create a twin.
        # Only applications not yet past "applied": one in screen has a human
        # history, and on 2026-10-20 an untitled Skydio screen was claimed —
        # and retitled — by a rejection for a different Skydio role.
        unknown = [c for c in candidates if placeholder_title(c[0].role_title)
                   and (c[0].stage or "applied") in ("watching", "drafting", "applied")]
        if len(unknown) == 1:
            # Record the role now, so the company's next confirmation for a
            # different role doesn't claim the same row (Mastercard's TPM and PM
            # mail both did). Correcting a title the mail states isn't a
            # pipeline move, so it doesn't wait for acceptance.
            unknown[0][0].role_title = role[:200]
            return unknown[0][0], f"{unknown[0][1]} (its role was never recorded; this mail says {role})"
        return None, f"a role Recon has no application for at {candidates[0][0].company_name}"
    if len(candidates) == 1:
        return candidates[0]
    # Several applications at the same company — use the role title.
    for app, why in candidates:
        title = _norm(app.role_title)
        if title and len(title) > 6 and re.search(rf"{re.escape(title[:40])}", hay):
            return app, f"{why}, and the role title"
    # Ambiguous: don't guess. Guessing "the most recent" put a Skydio
    # rejection for one role on the Skydio application in screen for another,
    # one tap away from closing it.
    return None, (f"{len(candidates)} applications at {candidates[0][0].company_name} "
                  "and this mail doesn't say which role")


def _units(th: dict) -> list[dict]:
    """The messages in a thread that each deserve a proposal.

    Normally just the newest inbound one. But an ATS will drop several
    confirmations into one thread when the subject repeats — Nike's two roles,
    sent minutes apart as "You have successfully applied to NIKE!" — and
    reading only the newest loses the others. So a thread made purely of
    acknowledgements files one proposal per distinct role it names.
    """
    inbound = [m for m in th["messages"] if not m["outbound"]]
    if not inbound:
        return []
    latest = th["latest_inbound"]
    if len(inbound) == 1 or any(classify(m.get("subject"), m.get("body"))["kind"] != "ack"
                                for m in inbound):
        return [latest]
    by_role: dict[str, dict] = {}
    for m in inbound:                       # oldest first; later wins per role
        by_role[(role_title(m.get("subject"), m.get("body")) or "").lower()] = m
    units = list(by_role.values())
    return units if latest in units else units + [latest]


def poll(db: Session, limit: int | None = None, full: bool = False) -> dict:
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
        if settings.mail_account:
            actual = mailbox_address()
            if actual.lower() != settings.mail_account.lower():
                log.warning("gmail token is for %s, expected %s", actual, settings.mail_account)
                return {"status": "error",
                        "reason": f"the Gmail token reads {actual}, not {settings.mail_account}. "
                                  "Re-run scripts/gmail_auth.py and sign in as "
                                  f"{settings.mail_account}."}
        # full=True re-reads every thread — needed after the rules change,
        # since an unchanged thread is otherwise never re-classified.
        known = {} if full else {
            t: h for t, h in db.execute(select(MailMessage.thread_id, MailMessage.history_id)
                                        .where(MailMessage.history_id.is_not(None))).all()}
        threads = fetch_threads(names, settings.mail_lookback_days,
                                limit or settings.mail_max_messages, known)
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
    for th, inbound in ((th, u) for th in threads for u in _units(th)):
        # (a thread of only your own mail has no units — it says nothing yet)
        role = role_title(inbound.get("subject"), inbound.get("body"))
        existing = db.scalars(select(MailMessage).where(
            MailMessage.thread_id == th["thread_id"])).all()
        # This role's row; else, for the thread's newest message, the row a
        # poll before role-splitting filed for the whole thread.
        row = next((r for r in existing if role and r.role_title
                    and r.role_title.lower() == role.lower()), None)
        if row is None and inbound is th["latest_inbound"]:
            row = next((r for r in existing if not r.role_title), None)
        if row is None:
            row = next((r for r in existing if r.message_id == inbound["message_id"]), None)
        app, why = match_application(inbound, apps, role)
        verdict = classify(inbound.get("subject"), inbound.get("body"))
        from_ats = is_ats_sender(inbound.get("from_addr"))
        marketing = looks_like_marketing(inbound.get("from_addr"), inbound.get("subject"))

        if row is None:
            row = MailMessage(message_id=inbound["message_id"], thread_id=th["thread_id"])
            db.add(row)
            is_new = True
        else:
            is_new = False
        decided_at = row.received_at
        row.history_id = th.get("history_id")
        # What this read says, not what an older rule extracted.
        row.role_title = role[:200] if role else None
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

        # "Thanks for joining our career network" reads like a confirmation
        # but is a talent-community sign-up (Under Armour, GM).
        if re.search(r"\b(career|talent)\s+(network|community)\b",
                     f"{inbound.get('subject') or ''} {(inbound.get('body') or '')[:1500]}", re.I) \
                and verdict["kind"] in ("ack", "other"):
            marketing = True
        if marketing:
            row.status, row.kind = "ignored", "marketing"
            row.evidence = "job alert / account mail, not application correspondence"
            ignored += 1
            continue
        # A decided proposal stays decided while the thread says nothing new —
        # re-reading it must not re-match it to a different application. A NEW
        # message from them (the rejection that lands in the screen thread) is
        # a new question, so it reopens.
        if row.status in ("accepted", "dismissed"):
            if row.message_id == inbound["message_id"] or (
                    decided_at and inbound.get("received_at")
                    and inbound["received_at"] <= decided_at):
                continue
            row.message_id, row.status = inbound["message_id"], "pending"
        if not app and verdict["kind"] not in ("ack", "screen", "rejection", "offer", "info_request"):
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
        if app and row.proposed_stage == app.stage:
            row.proposed_stage = None      # already there; a second invite isn't news
        # A confirmation for an application already tracked past "applied"
        # says nothing new. Filing it as pending buried the four real
        # rejections under a dozen "we received your application" rows.
        if verdict["kind"] in ("ack", "screen") and app and row.proposed_stage is None:
            row.status, row.evidence = "ignored", (f"{why}. Nothing new for an application "
                                                   f"already at {app.stage}.")
            ignored += 1
            continue

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
            base = (f"{why}. " if app else
                    f"{(why[:1].upper() + why[1:]) if why else 'No application in Recon matches this'}. "
                    "Accepting creates one. ")
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
