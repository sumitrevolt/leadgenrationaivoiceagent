"""Headless Telegram ingress for the 24x7 control plane.

CANONICAL CONSUMER (VPS-only) of the Jarvis bot token
(``TELEGRAM_JARVIS_BOT_TOKEN``), so owner commands/approvals keep flowing
even when the owner desktop (Hermes/OpenClaw) is closed.

SINGLE-CONSUMER CONTRACT (owner M7):
  One bot token => exactly ONE active getUpdates consumer at any time.
  This process owns the Jarvis token when ``TELEGRAM_INGRESS_ENABLED=1``.
  If another consumer (webhook, desktop poller, second ingress) is active
  Telegram answers getUpdates with HTTP 409; we surface that as
  ``conflict_another_consumer`` + a one-shot egress alert to the owner
  alerts group (30-min cooldown), and back off instead of racing.
  Never deleteWebhook and never drop pending updates to "win".

SAFETY (fail-closed, unchanged posture):
* Gated by ``TELEGRAM_INGRESS_ENABLED`` — DEFAULT OFF (0). When off, every
  entry point returns ``{"ok": False, "reason": "disabled"}`` and performs
  NO network call.
* Even when enabled, it requires the bot token. No token =>
  ``{"ok": False, "reason": "token_unconfigured"}``.
* In-memory dedupe is NOT trusted across restarts: update ids are persisted
  in Redis (``tg:ingress:seen:<update_id>`` TTL 48h) plus a per-bot
  offset watermark (``tg:ingress:offset:<bot_fp>``). Redis down => the loop
  degrades to in-memory dedupe with an honest log line (UNKNOWN state,
  never a silent double-execution claim).
* Command dispatch reuses the canonical owner-gated pipeline:
  ``TelegramBot.process_update`` (numeric/username owner allowlist,
  TypeSafe classification, orchestrator, audit trail, duplicate suppression).

Run (VPS, dedicated single-instance container ``tg-ingress``):
    python -m app.platform.telegram_ingress --loop
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Optional

logger = logging.getLogger(__name__)

_FLAG = "TELEGRAM_INGRESS_ENABLED"
_TOKEN_ENVS = ("TELEGRAM_JARVIS_BOT_TOKEN", "TELEGRAM_INGRESS_BOT_TOKEN")
_TOKEN_MIN_CHARS = 20
_API = "https://api.telegram.org"

# Redis state (persistent dedupe + watermark). Key material (token hashes)
# is truncated sha256 fingerprints — non-reversible, never raw.
_SEEN_PREFIX = "tg:ingress:seen:"
_SEEN_TTL_S = 48 * 3600
_OFFSET_KEY = "tg:ingress:offset:{fp}"
_BOTFP_KEY = "tg:ingress:botfp:{fp}"
_CONFLICT_ALERT_KEY = "tg:ingress:conflict_alert:{fp}"
_CONFLICT_ALERT_TTL_S = 30 * 60

_POLL_TIMEOUT_S = 50  # Telegram long-poll max
_BACKOFF_BASE_S = 5.0
_BACKOFF_MAX_S = 300.0
_CONFLICT_BACKOFF_S = 60.0


class IngressError(RuntimeError):
    """Structured ingress failure with a machine-readable ``kind``."""

    def __init__(self, kind: str, detail: str = ""):
        self.kind = kind
        super().__init__(f"{kind}: {detail}" if detail else kind)


def telegram_ingress_enabled() -> bool:
    return os.getenv(_FLAG, "0").strip().lower() in {"1", "true", "yes", "on"}


def _token() -> str:
    for name in _TOKEN_ENVS:
        val = os.getenv(name, "").strip()
        if len(val) >= _TOKEN_MIN_CHARS:
            return val
    return ""


def _token_fingerprint() -> str:
    import hashlib

    tok = _token()
    if not tok:
        return "none"
    return hashlib.sha256(tok.encode()).hexdigest()[:16]


def _token_configured() -> bool:
    return len(_token()) >= _TOKEN_MIN_CHARS


def readiness() -> dict[str, Any]:
    """Honest posture probe — no side effects, no network."""
    if not telegram_ingress_enabled():
        return {"ok": False, "enabled": False, "reason": "disabled"}
    if not _token_configured():
        return {"ok": True, "enabled": True, "reason": "token_unconfigured"}
    return {"ok": True, "enabled": True, "reason": "ready"}


# ---------------------------------------------------------------------------
# transport seams (kept tiny and import-safe so tests can monkeypatch)
# ---------------------------------------------------------------------------


def _http_json(method: str, token: str, params: Optional[dict] = None) -> dict:
    """One Telegram Bot API call. Returns the parsed JSON body. Raises
    IngressError(kind="http_<code>") on non-2xx so callers stay clean."""
    url = f"{_API}/bot{token}/{method}"
    data = json.dumps(params).encode() if params else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=_POLL_TIMEOUT_S + 15) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            body = {}
        raise IngressError(f"http_{e.code}", str(body.get("description", e)))
    except Exception as e:
        raise IngressError("network_error", str(e))


def _get_me(token: str) -> int:
    body = _http_json("getMe", token)
    if not body.get("ok"):
        raise IngressError("token_invalid", f"getMe ok={body.get('ok')}")
    return int(body["result"]["id"])


def _get_updates(token: str, offset: int, timeout: int) -> list[dict]:
    body = _http_json("getUpdates", token, {"offset": offset, "timeout": timeout, "limit": 100})
    if not body.get("ok"):
        raise IngressError("telegram_error", str(body.get("description")))
    return list(body.get("result", []))


def _redis():
    """Sync Redis client from REDIS_URL. None when unset/unreachable — the
    loop degrades to in-memory dedupe with an honest log line."""
    url = (os.getenv("REDIS_URL", "") or "").strip()
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, socket_timeout=5, socket_connect_timeout=5)
    except Exception:
        return None


class _MemoryDedupe:
    def __init__(self) -> None:
        self._seen: dict[int, float] = {}

    def is_new(self, update_id: int) -> bool:
        now = time.time()
        self._seen = {k: v for k, v in self._seen.items() if now - v < _SEEN_TTL_S}
        if update_id in self._seen:
            return False
        self._seen[update_id] = now
        return True

    def watermark_get(self, key: str) -> Optional[int]:
        return None

    def watermark_set(self, key: str, val: int) -> None:
        pass


class _RedisDedupe:
    def __init__(self, client) -> None:
        self._c = client

    def is_new(self, update_id: int) -> bool:
        k = f"{_SEEN_PREFIX}{update_id}"
        ok = self._c.set(k, "1", ex=_SEEN_TTL_S, nx=True)
        return bool(ok)

    def watermark_get(self, key: str) -> Optional[int]:
        v = self._c.get(key)
        try:
            return int(v) if v is not None else None
        except Exception:
            return None

    def watermark_set(self, key: str, val: int) -> None:
        self._c.set(key, val)


def _dedupe() -> Any:
    client = _redis()
    if client is not None:
        try:
            client.ping()
            return _RedisDedupe(client)
        except Exception:
            logger.warning("[telegram_ingress] redis unreachable -> in-memory dedupe (non-persistent)")
    return _MemoryDedupe()


def _alert_conflict(fp: str) -> None:
    """One-shot egress alert (30-min cooldown) so a 409 is never silent death."""
    client = _redis()
    if client is not None:
        try:
            if not client.set(f"{_CONFLICT_ALERT_KEY.format(fp=fp)}", "1", ex=_CONFLICT_ALERT_TTL_S, nx=True):
                return  # recent alert already sent
        except Exception:
            pass
    try:
        from app.utils.telegram_egress import send_to_group

        send_to_group(
            "cross.owner_alerts",
            "🚨 **Jarvis ingress conflict (409)**\n\n"
            "Another update consumer (webhook or a desktop poller) is active on the Jarvis "
            "bot token. This ingress backed off WITHOUT taking over updates.\n"
            "Action: stop the other consumer (webhook: /api/telegram/bot/set-webhook or "
            "Telegram console; desktop: close the polling consumer), or keep the desktop "
            "poller and leave TELEGRAM_INGRESS_ENABLED=0.",
        )
    except Exception as e:
        logger.warning("[telegram_ingress] conflict alert failed: %s", e)
    logger.error("[telegram_ingress] 409 conflict: another consumer owns the Jarvis token; backing off %.0fs", _CONFLICT_BACKOFF_S)


def run_ingress_once(db=None) -> dict[str, Any]:
    """One ingress pass. Fail-closed; the only entry point that does network I/O
    when the flag is on AND a token is configured."""
    status = readiness()
    if not status["ok"]:
        logger.info("[telegram_ingress] skip: %s", status["reason"])
        return status
    if status["reason"] == "token_unconfigured":
        return {
            "ok": False,
            "enabled": True,
            "reason": "token_unconfigured",
            "ingested": 0,
        }

    token = _token()
    fp = _token_fingerprint()
    dedupe = _dedupe()
    offset = dedupe.watermark_get(_OFFSET_KEY.format(fp=fp)) or 0
    try:
        updates = _get_updates(token, offset + 1, timeout=0)
    except IngressError as e:
        if e.kind == "http_409":
            _alert_conflict(fp)
            return {
                "ok": False,
                "enabled": True,
                "reason": "conflict_another_consumer",
                "ingested": 0,
                "detail": e.args[0] if e.args else "409",
            }
        return {
            "ok": False,
            "enabled": True,
            "reason": e.kind,
            "ingested": 0,
            "detail": str(e),
        }

    ingested = 0
    for update in updates:
        update_id = int(update.get("update_id") or 0)
        if update_id and not dedupe.is_new(update_id):
            logger.info("[telegram_ingress] duplicate update suppressed (update_id=%s)", update_id)
            continue
        try:
            from app.integrations.telegram_bot import get_telegram_bot

            result = get_telegram_bot().process_update(update, send_reply=True)
            ingested += 1
            logger.info(
                "[telegram_ingress] update %s -> success=%s intent=%s",
                update_id, result.success, result.intent,
            )
        except Exception as e:  # dispatch must never kill the loop
            logger.error("[telegram_ingress] dispatch failed for update %s: %s", update_id, e)
        if update_id:
            offset = max(offset, update_id)

    if updates:
        dedupe.watermark_set(_OFFSET_KEY.format(fp=fp), offset)
        client = _redis()
        if client is not None:
            try:
                client.set(_BOTFP_KEY.format(fp=fp), str(offset), ex=3600)
            except Exception:
                pass

    return {
        "ok": True,
        "enabled": True,
        "reason": "polled",
        "ingested": ingested,
        "updates": len(updates),
        "watermark": offset,
    }


def run_ingress_loop(stop_event=None) -> int:
    """The single-consumer long-poll loop. SIGTERM-safe. Returns exit code."""
    status = readiness()
    if not status["ok"]:
        logger.info("[telegram_ingress] loop not starting: %s", status["reason"])
        return 0 if status["reason"] == "disabled" else 1
    if status["reason"] == "token_unconfigured":
        logger.error("[telegram_ingress] enabled but token unconfigured — refusing to loop")
        return 1

    token = _token()
    bot_id = _get_me(token)  # fail fast on bad token before the loop
    logger.info("[telegram_ingress] loop started (bot_id=%s)", bot_id)

    backoff = _BACKOFF_BASE_S
    while stop_event is None or not stop_event.is_set():
        try:
            dedupe = _dedupe()
            fp = _token_fingerprint()
            offset = dedupe.watermark_get(_OFFSET_KEY.format(fp=fp)) or 0
            updates = _get_updates(token, offset + 1, timeout=_POLL_TIMEOUT_S)
            for update in updates:
                update_id = int(update.get("update_id") or 0)
                if update_id and not dedupe.is_new(update_id):
                    continue
                try:
                    from app.integrations.telegram_bot import get_telegram_bot

                    result = get_telegram_bot().process_update(update, send_reply=True)
                    logger.info(
                        "[telegram_ingress] update %s -> success=%s intent=%s",
                        update_id, result.success, result.intent,
                    )
                except Exception as e:
                    logger.error("[telegram_ingress] dispatch failed: %s", e)
                if update_id:
                    offset = max(offset, update_id)
            if updates:
                dedupe.watermark_set(_OFFSET_KEY.format(fp=fp), offset)
            backoff = _BACKOFF_BASE_S
        except IngressError as e:
            if e.kind == "http_409":
                _alert_conflict(_token_fingerprint())
                time.sleep(_CONFLICT_BACKOFF_S)
                continue
            logger.warning("[telegram_ingress] %s; backoff %.0fs", e, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, _BACKOFF_MAX_S)
        except Exception as e:  # keep the loop alive; never crash the container silently
            logger.error("[telegram_ingress] loop error: %s; backoff %.0fs", e, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, _BACKOFF_MAX_S)
    logger.info("[telegram_ingress] loop stopped (SIGTERM)")
    return 0


def _install_signal_handlers(stop_event) -> None:  # pragma: no cover - process glue
    def _handler(signum, frame):
        logger.info("[telegram_ingress] signal %s -> stopping", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Headless Jarvis ingress (VPS single-consumer)")
    parser.add_argument("--loop", action="store_true", help="run forever (container mode)")
    parser.add_argument("--once", action="store_true", help="one poll pass, print JSON, exit")
    parser.add_argument("--status", action="store_true", help="print readiness JSON, exit")
    args = parser.parse_args(argv)

    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    if args.status:
        print(json.dumps(readiness()))
        return 0
    if args.once:
        result = run_ingress_once()
        print(json.dumps(result, default=str))
        return 0 if result.get("ok") else 1
    # default + --loop
    import threading

    stop_event = threading.Event()
    if sys.platform != "win32":
        _install_signal_handlers(stop_event)
    return run_ingress_loop(stop_event)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
