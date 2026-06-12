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
