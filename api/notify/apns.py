"""Native iOS push via Apple Push Notification service (APNs).

Uses provider-token auth: one ES256 JWT signed with the account's .p8 auth key,
refreshed periodically, sent as a bearer token on every request — no per-device
certificates to manage. Mirrors notify/push.py's shape (web push): no-ops with a
log line if unconfigured, prunes dead tokens (410 Unregistered) automatically.

Sandbox vs. production: a device token is only valid against the host of the
APNs environment that issued it, and the two are indistinguishable by inspection
— a sandbox token sent to api.push.apple.com comes back 400 BadDeviceToken, the
exact same response as a genuinely dead token. A single global APNS_USE_SANDBOX
flag is therefore not enough to tell "wrong host" from "dead device", so we don't
guess: each token carries the environment that last worked for it, an unknown or
rejecting token is retried against the other host, and pruning only happens when
*both* hosts reject. Getting APNS_USE_SANDBOX wrong then costs one wasted request
per token instead of silently deleting every device Zach owns.
"""
import logging
import time

from sqlalchemy import select
from db import SessionLocal, DeviceToken
from config import settings

log = logging.getLogger("recon.notify.apns")

_TOKEN_TTL_SEC = 55 * 60  # Apple allows up to 1h; refresh a bit early
_cached_jwt: tuple[str, float] | None = None  # (token, issued_at)

SANDBOX_HOST = "api.sandbox.push.apple.com"
PRODUCTION_HOST = "api.push.apple.com"

# 400 reasons that mean "this token is wrong for THIS host" — which is also what
# a sandbox/production mismatch looks like, so they trigger the other-host retry
# rather than a prune.
_WRONG_HOST_REASONS = {"BadDeviceToken", "DeviceTokenNotForTopic"}


def _host_for(environment: str | None) -> str:
    """Host to try first for a token. A token with a known-good environment goes
    straight there; an unknown one follows the configured default."""
    if environment == "sandbox":
        return SANDBOX_HOST
    if environment == "production":
        return PRODUCTION_HOST
    return SANDBOX_HOST if settings.apns_use_sandbox else PRODUCTION_HOST


def _other(host: str) -> str:
    return PRODUCTION_HOST if host == SANDBOX_HOST else SANDBOX_HOST


def _env_of(host: str) -> str:
    return "sandbox" if host == SANDBOX_HOST else "production"


def _reason(resp) -> str:
    """APNs error reason, or "" if the body isn't the JSON Apple documents.
    Edge/proxy 5xx bodies are frequently HTML, and resp.json() raises on those —
    which httpx.HTTPError does not cover, so it would abort the whole send loop."""
    try:
        return resp.json().get("reason", "")
    except Exception:
        return ""


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
    or misconfigured. Tokens rejected by *both* APNs hosts are pruned."""
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

    payload = {
        "aps": {"alert": {"title": title, "body": body}, "sound": "default"},
        "url": url,
    }
    headers = {
        "authorization": f"bearer {token}",
        "apns-topic": settings.apns_bundle_id,
        "apns-push-type": "alert",
    }

    db = SessionLocal()
    try:
        devices = db.scalars(select(DeviceToken).where(DeviceToken.platform == "ios")).all()
        if not devices:
            log.info("apns: no device tokens registered — skipping")
            return

        sent, dead, relearned = 0, [], 0
        # http2 is mandatory for APNs; both hosts share one client via absolute URLs.
        with httpx.Client(http2=True, timeout=10) as client:

            def attempt(host: str, device_token: str):
                """POST once. Returns the response, or None if the request itself failed."""
                try:
                    return client.post(
                        f"https://{host}/3/device/{device_token}",
                        json=payload, headers=headers,
                    )
                except httpx.HTTPError as e:
                    log.warning("apns: request to %s failed: %s", host, e)
                    return None

            for d in devices:
                first = _host_for(d.environment)
                resp = attempt(first, d.token)
                if resp is None:
                    continue  # transport failure: no verdict on the token, leave it alone

                if resp.status_code == 200:
                    if d.environment != _env_of(first):
                        d.environment = _env_of(first)
                        relearned += 1
                    sent += 1
                    continue

                reason = _reason(resp)

                # 403 is an auth/config failure (bad .p8, wrong team or key id) and
                # applies to every device equally — never a dead token, and no point
                # grinding through the rest of the list.
                if resp.status_code == 403:
                    log.error("apns: provider token rejected (403 %s) — check APNS_KEY_PATH/"
                              "KEY_ID/TEAM_ID; aborting this send", reason or resp.text)
                    break

                # 410 Unregistered is Apple's unambiguous "app was uninstalled",
                # and it is host-specific only in the sense that the token belonged
                # to that host — a genuine prune.
                if resp.status_code == 410:
                    dead.append(d.id)
                    log.info("apns: pruning unregistered token %d", d.id)
                    continue

                # A wrong-host rejection is indistinguishable from a dead token, so
                # confirm against the other environment before believing it.
                if resp.status_code == 400 and reason in _WRONG_HOST_REASONS:
                    second = _other(first)
                    retry = attempt(second, d.token)
                    if retry is None:
                        continue
                    if retry.status_code == 200:
                        log.info("apns: token %d is a %s token (was trying %s) — corrected",
                                 d.id, _env_of(second), _env_of(first))
                        d.environment = _env_of(second)
                        relearned += 1
                        sent += 1
                        continue
                    if retry.status_code in (400, 410):
                        dead.append(d.id)
                        log.info("apns: pruning token %d — rejected by both hosts (%s / %s)",
                                 d.id, reason, _reason(retry) or retry.status_code)
                        continue
                    log.warning("apns: retry for token %d on %s returned %s %s",
                                d.id, second, retry.status_code, retry.text)
                    continue

                log.warning("apns: failed to deliver to token %d: %s %s",
                            d.id, resp.status_code, resp.text)

        for d_id in dead:
            d = db.get(DeviceToken, d_id)
            if d:
                db.delete(d)
        if dead or relearned:
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise

        log.info("apns: sent %d/%d notifications (%d pruned, %d environment corrections)",
                 sent, len(devices), len(dead), relearned)
    finally:
        db.close()
