"""Web push notifications via pywebpush + VAPID."""
import logging
from sqlalchemy import select
from db import SessionLocal, PushSubscription
from config import settings

log = logging.getLogger("recon.notify.push")


def send_push(title: str, body: str, url: str = "/") -> None:
    """Send a web push notification to all saved subscriptions.

    No-ops (with a warning) if push is disabled or VAPID keys are missing.
    Dead subscriptions (404/410) are pruned from the database.
    """
    if not settings.notify_push_enabled:
        log.warning("push: notify_push_enabled is False — skipping")
        return
    if not settings.vapid_public_key or not settings.vapid_private_key:
        log.warning("push: VAPID keys not configured — skipping")
        return

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        log.warning("push: pywebpush not installed — skipping")
        return

    import json

    db = SessionLocal()
    try:
        subs = db.scalars(select(PushSubscription)).all()
        if not subs:
            log.info("push: no subscriptions registered — skipping")
            return

        payload = json.dumps({"title": title, "body": body, "url": url})
        sent, dead = 0, []
        for sub in subs:
            subscription_info = {
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            }
            try:
                webpush(
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=settings.vapid_private_key,
                    vapid_claims={"sub": settings.vapid_subject},
                )
                sent += 1
            except WebPushException as e:
                status = getattr(e.response, "status_code", None)
                if status in (404, 410):
                    dead.append(sub.id)
                    log.info("push: pruning dead subscription %d (status %s)", sub.id, status)
                else:
                    log.warning("push: failed to deliver to subscription %d: %s", sub.id, e)

        for sub_id in dead:
            sub = db.get(PushSubscription, sub_id)
            if sub:
                db.delete(sub)
        if dead:
            db.commit()

        log.info("push: sent %d/%d notifications", sent, len(subs))
    finally:
        db.close()
