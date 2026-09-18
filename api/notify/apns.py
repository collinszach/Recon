"""Native iOS push via Apple Push Notification service (APNs).

Uses provider-token auth: one ES256 JWT signed with the account's .p8 auth key,
refreshed periodically, sent as a bearer token on every request — no per-device
certificates to manage. Mirrors notify/push.py's shape (web push): no-ops with a
log line if unconfigured, prunes dead tokens (410 Unregistered) automatically.
"""
import logging
import time

from sqlalchemy import select
from db import SessionLocal, DeviceToken
from config import settings

log = logging.getLogger("recon.notify.apns")

_TOKEN_TTL_SEC = 55 * 60  # Apple allows up to 1h; refresh a bit early
_cached_jwt: tuple[str, float] | None = None  # (token, issued_at)


def _provider_token() -> str | None:
    global _cached_jwt
    now = time.time()
    if _cached_jwt and (now - _cached_jwt[1]) < _TOKEN_TTL_SEC:
        return _cached_jwt[0]

    try:
        import jwt
    except ImportError:
        log.warning("apns: PyJWT not installed — skipping")
        return None

    try:
        with open(settings.apns_key_path) as f:
            key = f.read()
    except OSError as e:
        log.warning("apns: could not read APNS_KEY_PATH %r: %s", settings.apns_key_path, e)
        return None

    token = jwt.encode(
        {"iss": settings.apns_team_id, "iat": int(now)},
        key, algorithm="ES256",
        headers={"kid": settings.apns_key_id},
    )
    _cached_jwt = (token, now)
    return token


def send_apns(title: str, body: str, url: str = "/") -> None:
    """Push to every registered iOS device. No-ops (with a warning) if disabled
    or misconfigured. Dead tokens (410 Unregistered / BadDeviceToken) are pruned."""
    if not settings.notify_apns_enabled:
        log.warning("apns: notify_apns_enabled is False — skipping")
        return
    if not (settings.apns_key_path and settings.apns_key_id and settings.apns_team_id
            and settings.apns_bundle_id):
        log.warning("apns: APNS_KEY_PATH/KEY_ID/TEAM_ID/BUNDLE_ID not fully configured — skipping")
        return

    token = _provider_token()
    if not token:
        return

    import httpx

    host = ("api.sandbox.push.apple.com" if settings.apns_use_sandbox
            else "api.push.apple.com")
    payload = {
        "aps": {"alert": {"title": title, "body": body}, "sound": "default"},
        "url": url,
    }

    db = SessionLocal()
    try:
        devices = db.scalars(select(DeviceToken).where(DeviceToken.platform == "ios")).all()
        if not devices:
            log.info("apns: no device tokens registered — skipping")
            return

        sent, dead = 0, []
        with httpx.Client(http2=True, base_url=f"https://{host}", timeout=10) as client:
            for d in devices:
                try:
                    resp = client.post(
                        f"/3/device/{d.token}", json=payload,
                        headers={
                            "authorization": f"bearer {token}",
                            "apns-topic": settings.apns_bundle_id,
                            "apns-push-type": "alert",
                        },
                    )
                    if resp.status_code == 200:
                        sent += 1
                    elif resp.status_code == 410 or (
                            resp.status_code == 400
                            and resp.json().get("reason") == "BadDeviceToken"):
                        dead.append(d.id)
                        log.info("apns: pruning dead token %d (status %s)", d.id, resp.status_code)
                    else:
                        log.warning("apns: failed to deliver to token %d: %s %s",
                                   d.id, resp.status_code, resp.text)
                except httpx.HTTPError as e:
                    log.warning("apns: request failed for token %d: %s", d.id, e)

        for d_id in dead:
            d = db.get(DeviceToken, d_id)
            if d:
                db.delete(d)
        if dead:
            db.commit()

        log.info("apns: sent %d/%d notifications", sent, len(devices))
    finally:
        db.close()
