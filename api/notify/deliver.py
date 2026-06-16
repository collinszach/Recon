"""Orchestrate brief delivery across all channels.

Each channel runs in its own try/except, mirroring the per-company
discipline in scan/runner.py — one channel failing (or being
unconfigured) must never affect the others or the scan itself.
"""
import logging
from db import DailyBrief
from notify.push import send_push
from notify.email import send_email
from notify.gdoc import publish_gdoc

log = logging.getLogger("recon.notify")


def deliver_brief(brief: DailyBrief) -> dict:
    """Deliver `brief` over push, email, and Google Doc.

    Returns a dict like {"push": "ok", "email": "skipped", "gdoc": "error"}.
    """
    title = (f"Recon — {brief.brief_date}: "
             f"{brief.new_count} new, {brief.action_count} need action")
    markdown = brief.markdown or ""

    results: dict[str, str] = {}

    # ─── web push ────────────────────────────────────────────
    try:
        from config import settings
        if not settings.notify_push_enabled:
            results["push"] = "skipped"
        else:
            send_push(title=title, body=title, url="/")
            results["push"] = "ok"
    except Exception as e:
        results["push"] = "error"
        log.warning("deliver: push failed: %s: %s", type(e).__name__, e)
    else:
        log.info("deliver: push %s", results["push"])

    # ─── email ───────────────────────────────────────────────
    try:
        from config import settings
        if not settings.notify_email_enabled:
            results["email"] = "skipped"
        else:
            send_email(subject=title, markdown_body=markdown)
            results["email"] = "ok"
    except Exception as e:
        results["email"] = "error"
        log.warning("deliver: email failed: %s: %s", type(e).__name__, e)
    else:
        log.info("deliver: email %s", results["email"])

    # ─── google doc ──────────────────────────────────────────
    try:
        from config import settings
        if not settings.notify_gdoc_enabled:
            results["gdoc"] = "skipped"
        else:
            publish_gdoc(title=title, markdown_body=markdown)
            results["gdoc"] = "ok"
    except Exception as e:
        results["gdoc"] = "error"
        log.warning("deliver: gdoc failed: %s: %s", type(e).__name__, e)
    else:
        log.info("deliver: gdoc %s", results["gdoc"])

    log.info("deliver_brief: %s", results)
    return results


def deliver_alert(roles: list) -> dict:
    """Push/email an immediate alert for new high-fit roles found this scan.
    `roles` are Role objects (with .company, .title, .fit_score, .posted_at).
    No-ops gracefully when channels are disabled (no creds)."""
    if not roles:
        return {}
    from config import settings

    def line(r) -> str:
        co = r.company.name if getattr(r, "company", None) else "?"
        when = r.posted_at.date().isoformat() if getattr(r, "posted_at", None) else "recently"
        return f"• {co} — {r.title} — fit {r.fit_score:.1f} — posted {when}"

    title = f"Recon: {len(roles)} new fit-{int(min(r.fit_score for r in roles))}+ role(s)"
    body = title + "\n" + "\n".join(line(r) for r in roles[:15])
    results: dict[str, str] = {}

    try:
        if not settings.notify_push_enabled:
            results["push"] = "skipped"
        else:
            send_push(title=title, body=title, url="/")
            results["push"] = "ok"
    except Exception as e:
        results["push"] = "error"; log.warning("alert push failed: %s", e)

    try:
        if not settings.notify_email_enabled:
            results["email"] = "skipped"
        else:
            send_email(subject=title, markdown_body=body)
            results["email"] = "ok"
    except Exception as e:
        results["email"] = "error"; log.warning("alert email failed: %s", e)

    log.info("deliver_alert (%d roles): %s", len(roles), results)
    return results


def deliver_reminders(due: list, stale: list) -> dict:
    """Once-a-day pipeline reminders: follow-ups due + 'applied' gone stale.
    `due`/`stale` are Application objects. No-ops when channels are disabled."""
    if not due and not stale:
        return {}
    from config import settings

    lines = []
    for a in due:
        lines.append(f"⏰ {a.company_name or '?'} — {a.role_title or '?'}: "
                     f"{a.next_action or 'follow up'} (due {a.next_action_due})")
    for a in stale:
        when = a.applied_at.date() if a.applied_at else "?"
        lines.append(f"🕓 {a.company_name or '?'} — {a.role_title or '?'}: "
                     f"applied {when}, no movement")
    title = f"Recon: {len(due) + len(stale)} pipeline item(s) need action"
    body = title + "\n" + "\n".join(lines[:20])
    results: dict[str, str] = {}

    try:
        if not settings.notify_push_enabled:
            results["push"] = "skipped"
        else:
            send_push(title=title, body=title, url="/"); results["push"] = "ok"
    except Exception as e:
        results["push"] = "error"; log.warning("reminder push failed: %s", e)
    try:
        if not settings.notify_email_enabled:
            results["email"] = "skipped"
        else:
            send_email(subject=title, markdown_body=body); results["email"] = "ok"
    except Exception as e:
        results["email"] = "error"; log.warning("reminder email failed: %s", e)

    log.info("deliver_reminders (%d items): %s", len(due) + len(stale), results)
    return results
