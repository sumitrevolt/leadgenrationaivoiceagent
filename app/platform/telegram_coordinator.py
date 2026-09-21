"""
Telegram Dual-Bot Coordination Architecture
============================================
Single source of truth for the LeadGen AI Telegram bot architecture.

Architecture (decided via TypeSafe, 2026-09-20):
- Jarvis Bot (TELEGRAM_JARVIS_BOT_TOKEN): Interactive command bot (@Sumits_jarvis_bot)
  - Receives inbound updates via getUpdates long-polling
  - Processes /status, /tasks, /agents, /pause, /resume commands
  - Uses TypeSafe System One for intent classification and 9-bot routing
  - Executes platform skills (ops-status, task-triage, etc.)
  - Sends responses back to owner chat

- Notify Bot (TELEGRAM_NOTIFY_BOT_TOKEN): Broadcast-only egress bot (@Leadsgenai1_bot)
  - Sends system alerts, P0 incidents, UPI payment notifications
  - Delivers daily briefs, deploy notices, video delivery receipts
  - Zero getUpdates polling (prevents 409 conflict with Jarvis)
  - Pure egress via app/utils/telegram_egress.py

- Webhook endpoint (/api/webhooks/telegram): Receives Telegram updates
  - Secret-token fail-closed verification
  - Durable inbox persistence (data/telegram_inbox.jsonl)
  - Dedup by update_id (bounded cache)
  - Cross-channel opt-out handling
  - Automatic dispatch to TelegramBot.process_update

Setup spec: config/telegram/setup_spec.yaml (13 entities, single source of truth)
Egress routing: config/telegram/owner_notify_routing.yaml (severity-based)

POLLING COORDINATION (2026-09-21)
---------------------------------
A bot token may only be consumed by ONE ``getUpdates`` process at a time — a
second consumer gets HTTP 409 ``Conflict: terminated by other getUpdates``.
Three real consumers exist in this project: the local laptop runner, the VPS
runner (systemd/Docker), and the Hermes desktop gateway. Coordination rules:

1. ``TELEGRAM_INGRESS_OWNER`` (auto|local|vps|hermes|off) — when set to a role,
   only that role may poll. Others refuse (fail-closed, no 409 spam).
2. Otherwise a *polling lease* decides: Redis (cross-host) when reachable, else
   a file lease in ``data/`` (same host, cross-process). Stale leases expire.
3. A genuine 409 (an external consumer we do not control, e.g. Hermes) makes the
   runner enter standby with backoff and RELEASE its own lease instead of
   fighting for the token.

Live evidence helper: ``scripts/telegram_verify_setup.py`` (read-only truth
table for tokens, webhook, groups, lease — never prints token values).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# State
_DEDUPE_TTL = 3600.0
_processed_updates: dict[str | int, float] = {}

# Polling coordination state (process-local observability)
_LEASE_SCOPE_DEFAULT = "jarvis"
_LEASE_KEY = "leadgen:telegram:poll_lease"
_LEASE_PATH = Path(__file__).resolve().parents[2] / "data" / "telegram_poll_lease.json"
_HEARTBEAT_PATH = Path(__file__).resolve().parents[2] / "data" / "telegram_jarvis_state.json"
_LEASE_TTL_DEFAULT_S = 120.0
_INGRESS_OWNER_ROLES = {"auto", "local", "vps", "hermes"}

_conflict_count = 0
_last_conflict_at: float | None = None
_last_standby_reason: str | None = None
# After a real HTTP 409 we stop trying until this timestamp (the external
# consumer, e.g. Hermes, is the true owner for now). Keeps our own lease honest.
_external_conflict_until: float = 0.0

# Egress token blacklist (401-dead tokens) + live getMe result cache.
# Keyed by a SHA-256 fingerprint so raw tokens never live in a dict key/log.
_dead_egress_tokens: set[str] = set()
_token_cache: dict[str, tuple[float, dict[str, Any]]] = {}

_TOKEN_SLOTS: tuple[tuple[str, str], ...] = (
    ("notify", "TELEGRAM_NOTIFY_BOT_TOKEN"),
    ("fallback", "TELEGRAM_BOT_TOKEN"),
    ("jarvis", "TELEGRAM_JARVIS_BOT_TOKEN"),
)


def get_polling_token() -> str | None:
    """Get the polling (Jarvis) bot token. Fail-closed: None if missing or too short."""
    tok = os.getenv("TELEGRAM_JARVIS_BOT_TOKEN", "").strip()
    return tok if len(tok) >= 20 else None


def get_egress_token() -> str | None:
    """Get the egress (Notify) bot token. Fail-closed: None if missing or too short."""
    tok = (
        os.getenv("TELEGRAM_NOTIFY_BOT_TOKEN", "").strip()
        or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    )
    return tok if len(tok) >= 20 else None


def get_owner_chat_ids() -> set[int]:
    """Get authorized owner chat IDs from environment."""
    raw = os.getenv("TELEGRAM_OWNER_CHAT_IDS", "1621120182")
    chat_ids = set()
    for item in raw.split(","):
        try:
            chat_ids.add(int(item.strip()))
        except (ValueError, AttributeError):
            pass
    return chat_ids


def get_owner_usernames() -> set[str]:
    """Get authorized owner usernames from environment."""
    raw = os.getenv("TELEGRAM_OWNER_USERNAMES", "sumitrevolt")
    return {u.strip().lower().lstrip("@") for u in raw.split(",") if u.strip()}


def is_telegram_configured() -> bool:
    """Check if Telegram dual-bot setup has minimum viable configuration."""
    jarvis = get_polling_token()
    notify = get_egress_token()
    return bool(jarvis and notify and get_owner_chat_ids())


def is_owner_chat(chat_id: int | str) -> bool:
    """Check if chat_id is an authorized owner chat."""
    try:
        return int(chat_id) in get_owner_chat_ids()
    except (ValueError, TypeError):
        return False


def is_owner_username(username: str | None) -> bool:
    """Check if username is an authorized owner."""
    if not username:
        return False
    return username.strip().lower().lstrip("@") in get_owner_usernames()


def _mark_update_seen_cross_process(update_id: int) -> bool:
    """True when another process already handled this update. Fail-open.

    Local laptop, VPS runner and the web process can all see the same Telegram
    update (polling + webhook). The in-process cache cannot see that, so a
    best-effort Redis key provides the cross-process guard.
    """
    client = _redis_client()
    if client is None:
        return False
    try:
        key = f"leadgen:telegram:dedupe:{lease_scope()}:{update_id}"
        return not client.set(key, "1", nx=True, ex=int(_DEDUPE_TTL))
    except Exception:
        return False


def is_duplicate_update(update_id: int | None) -> bool:
    """Check if update_id was recently processed (in-process + cross-process)."""
    if not isinstance(update_id, int):
        return False
    now = time.time()
    # Clean expired entries
    expired = [k for k, v in _processed_updates.items() if now - v > _DEDUPE_TTL]
    for k in expired:
        _processed_updates.pop(k, None)
    if update_id in _processed_updates:
        return True
    if _mark_update_seen_cross_process(update_id):
        logger.info("[telegram_coordinator] duplicate update %s suppressed (cross-process)", update_id)
        return True
    _processed_updates[update_id] = now
    return False


def _send_tg_api(token: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    """Call Telegram Bot API via standard urllib."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "error_code": exc.code, "description": exc.reason}
    except Exception as exc:
        return {"ok": False, "description": str(exc)}


# ---------------------------------------------------------------------------
# Live token validation (never logs or returns a token value)
# ---------------------------------------------------------------------------


def _token_fingerprint(token: str) -> str:
    """Non-reversible identifier for logs/metrics — never the token itself."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def validate_bot_token(token: str, cache_ttl: float = 300.0, force: bool = False) -> dict[str, Any]:
    """Validate a bot token against ``getMe``. Fail-closed, cached, secret-free.

    A token that is merely *present* is NOT healthy: a revoked token still
    satisfies ``len >= 20`` and silently swallows every alert. This is the check
    that distinguishes CONFIGURED from AUTHENTICATED.
    """
    if not token or len(token) < 20:
        return {"valid": False, "present": False, "reason": "missing_or_short"}

    fingerprint = _token_fingerprint(token)
    now = time.time()
    cached = _token_cache.get(fingerprint)
    if cached and not force and cached[0] > now:
        return cached[1]

    res = _send_tg_api(token, "getMe", {})
    result = res.get("result") or {}
    if res.get("ok"):
        out: dict[str, Any] = {
            "valid": True,
            "present": True,
            "reason": "ok",
            "username": "@" + str(result.get("username") or "unknown"),
            "bot_id": result.get("id"),
            "fingerprint": fingerprint,
        }
    else:
        code = res.get("error_code")
        out = {
            "valid": False,
            "present": True,
            "reason": "unauthorized" if code == 401 else str(res.get("description") or "error")[:80],
            "error_code": code,
            "fingerprint": fingerprint,
        }
    _token_cache[fingerprint] = (now + max(5.0, cache_ttl), out)
    return out


def token_health(live: bool = True) -> dict[str, Any]:
    """PRESENT/AUTHENTICATED/INVALID state for every Telegram credential slot."""
    health: dict[str, Any] = {}
    for label, env_name in _TOKEN_SLOTS:
        token = os.getenv(env_name, "").strip()
        if not token:
            health[label] = {"present": False, "valid": None, "env": env_name, "reason": "absent"}
            continue
        if live:
            probed = validate_bot_token(token)
            health[label] = {**probed, "env": env_name}
        else:
            health[label] = {"present": True, "valid": None, "env": env_name, "reason": "not_probed"}
    return health


def egress_token_candidates() -> list[tuple[str, str]]:
    """``[(slot_label, token)]`` in priority order with 401-dead tokens removed.

    Slot labels ('notify'/'fallback'/'jarvis') are safe to log; raw tokens are
    never returned to callers that log.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label, env_name in _TOKEN_SLOTS:
        token = os.getenv(env_name, "").strip()
        if len(token) < 20 or token in seen or token in _dead_egress_tokens:
            continue
        seen.add(token)
        out.append((label, token))
    return out


# ---------------------------------------------------------------------------
# Polling lease + ingress ownership (local <-> VPS <-> Hermes coordination)
# ---------------------------------------------------------------------------


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


def lease_ttl_seconds() -> float:
    """Lease TTL in seconds (``TELEGRAM_POLL_LEASE_TTL``, floor 30s)."""
    return max(30.0, _env_float("TELEGRAM_POLL_LEASE_TTL", _LEASE_TTL_DEFAULT_S))


def lease_scope() -> str:
    """Lease namespace — one per bot token so two bots never block each other."""
    return (os.getenv("TELEGRAM_POLL_SCOPE", "") or _LEASE_SCOPE_DEFAULT).strip().lower()


def default_instance_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def get_instance_id(explicit: str | None = None) -> str:
    """Stable identity for this polling process (``--instance`` > env > host:pid)."""
    if explicit and explicit.strip():
        return explicit.strip()
    return os.getenv("TELEGRAM_INSTANCE_ID", "").strip() or default_instance_id()


def instance_role(explicit: str | None = None) -> str:
    """Role of THIS process: ``local`` (default) | ``vps`` | ``hermes``."""
    raw = explicit or os.getenv("TELEGRAM_INSTANCE_ROLE", "") or "local"
    return raw.strip().lower() or "local"


def ingress_owner_role() -> str:
    """``TELEGRAM_INGRESS_OWNER``: auto (default) | local | vps | hermes | off."""
    return (os.getenv("TELEGRAM_INGRESS_OWNER", "auto") or "auto").strip().lower()


def _redis_client() -> Any | None:
    """Sync Redis client for the lease/dedupe, or None (fail-open, best-effort)."""
    try:
        import redis as _redis

        from app.config import settings

        return _redis.Redis.from_url(str(settings.redis_url), socket_timeout=2, decode_responses=True)
    except Exception:
        return None


def _lease_key() -> str:
    return f"{_LEASE_KEY}:{lease_scope()}"


def _read_lease_file() -> dict[str, Any]:
    try:
        if _LEASE_PATH.exists():
            return json.loads(_LEASE_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


def _write_lease_file(payload: dict[str, Any]) -> None:
    try:
        _LEASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _LEASE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, _LEASE_PATH)
    except Exception as exc:
        logger.debug("[telegram_coordinator] lease file write failed: %s", exc)


def acquire_polling_lease(instance_id: str, ttl: float | None = None) -> dict[str, Any]:
    """Try to become the polling owner. Returns the outcome, never raises."""
    ttl_s = float(ttl or lease_ttl_seconds())
    now = time.time()
    expires_at = now + ttl_s

    client = _redis_client()
    if client is not None:
        try:
            key = _lease_key()
            if client.set(key, instance_id, nx=True, px=int(ttl_s * 1000)):
                return {
                    "acquired": True,
                    "backend": "redis",
                    "holder": instance_id,
                    "expires_at": expires_at,
                    "reason": "acquired",
                }
            current = client.get(key)
            current = current if isinstance(current, str) else None
            if current == instance_id:
                client.pexpire(key, int(ttl_s * 1000))
                return {
                    "acquired": True,
                    "backend": "redis",
                    "holder": instance_id,
                    "expires_at": expires_at,
                    "reason": "refreshed",
                }
            return {
                "acquired": False,
                "backend": "redis",
                "holder": current,
                "expires_at": None,
                "reason": "held_by_other",
            }
        except Exception as exc:
            logger.debug("[telegram_coordinator] redis lease unavailable (%s); file lease", exc)

    data = _read_lease_file()
    holder = data.get("holder")
    try:
        holder_expires = float(data.get("expires_at") or 0.0)
    except (TypeError, ValueError):
        holder_expires = 0.0

    if holder and holder != instance_id and holder_expires > now:
        return {
            "acquired": False,
            "backend": "file",
            "holder": str(holder),
            "expires_at": holder_expires,
            "reason": "held_by_other",
        }

    stale = bool(holder and holder != instance_id)
    _write_lease_file(
        {
            "holder": instance_id,
            "acquired_at": now,
            "expires_at": expires_at,
            "ttl_s": ttl_s,
            "scope": lease_scope(),
        }
    )
    return {
        "acquired": True,
        "backend": "file",
        "holder": instance_id,
        "expires_at": expires_at,
        "reason": "stale_takeover" if stale else "acquired",
    }


def release_polling_lease(instance_id: str) -> bool:
    """Release the lease if we are the holder. Never raises."""
    client = _redis_client()
    if client is not None:
        try:
            key = _lease_key()
            if client.get(key) == instance_id:
                client.delete(key)
                return True
        except Exception:
            pass
    data = _read_lease_file()
    if data.get("holder") == instance_id:
        try:
            _LEASE_PATH.unlink(missing_ok=True)
        except Exception:
            return False
        return True
    return False


def get_polling_lease(instance_id: str | None = None) -> dict[str, Any]:
    """Read-only lease snapshot (no writes) for status surfaces."""
    me = get_instance_id(instance_id)
    now = time.time()
    client = _redis_client()
    if client is not None:
        try:
            holder = client.get(_lease_key())
            holder = holder if isinstance(holder, str) else None
            ttl_ms = client.pttl(_lease_key())
            remaining = max(0.0, float(ttl_ms) / 1000.0) if isinstance(ttl_ms, int) and ttl_ms > 0 else None
            return {
                "backend": "redis",
                "holder": holder,
                "held_by_me": bool(holder and holder == me),
                "seconds_remaining": remaining,
                "stale": bool(holder and remaining is None),
            }
        except Exception:
            pass
    data = _read_lease_file()
    holder = data.get("holder")
    try:
        expires = float(data.get("expires_at") or 0.0)
    except (TypeError, ValueError):
        expires = 0.0
    return {
        "backend": "file",
        "holder": holder,
        "held_by_me": bool(holder and holder == me),
        "seconds_remaining": max(0.0, expires - now) if expires else None,
        "stale": bool(holder and expires <= now),
    }


def should_poll(
    instance_id: str | None = None,
    role: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Decide whether THIS process may call ``getUpdates`` right now.

    Order: explicit ingress owner (strict) → polling lease. Fail-closed: an
    unknown role can never steal the token from a configured owner.

    ``dry_run=True`` is for status surfaces: same gates, but the lease is only
    READ, so asking "may I poll?" never takes ownership.
    """
    me = get_instance_id(instance_id)
    my_role = instance_role(role)
    owner = ingress_owner_role()

    if owner in {"off", "none", "disabled", "0"}:
        return {"poll": False, "reason": "ingress_owner_off", "instance_id": me, "role": my_role}

    if owner in _INGRESS_OWNER_ROLES and owner != "auto" and my_role != owner:
        return {
            "poll": False,
            "reason": f"ingress_owner_is_{owner}",
            "instance_id": me,
            "role": my_role,
            "ingress_owner": owner,
        }

    now = time.time()
    if now < _external_conflict_until:
        return {
            "poll": False,
            "reason": "external_consumer_conflict",
            "instance_id": me,
            "role": my_role,
            "ingress_owner": owner,
            "retry_in_s": round(_external_conflict_until - now, 1),
        }

    if dry_run:
        snapshot = get_polling_lease(me)
        holder = snapshot.get("holder")
        free = (not holder) or bool(snapshot.get("stale")) or bool(snapshot.get("held_by_me"))
        return {
            "poll": free,
            "reason": "lease_held_by_me" if snapshot.get("held_by_me") else ("lease_free" if free else "lease_held_by_other"),
            "instance_id": me,
            "role": my_role,
            "ingress_owner": owner,
            "holder": holder,
            "lease_backend": snapshot.get("backend"),
            "dry_run": True,
        }

    lease = acquire_polling_lease(me)
    if not lease.get("acquired"):
        return {
            "poll": False,
            "reason": "lease_held_by_other",
            "instance_id": me,
            "role": my_role,
            "ingress_owner": owner,
            "holder": lease.get("holder"),
            "lease_backend": lease.get("backend"),
        }
    return {
        "poll": True,
        "reason": str(lease.get("reason") or "acquired"),
        "instance_id": me,
        "role": my_role,
        "ingress_owner": owner,
        "holder": me,
        "lease_backend": lease.get("backend"),
        "lease_expires_at": lease.get("expires_at"),
    }


def write_polling_heartbeat(instance_id: str, role: str, **extra: Any) -> None:
    """Record liveness of the polling loop. Never raises.

    A poller that has silently died looks exactly like a healthy one from the
    outside (no HTTP surface, no port), so the loop writes its own state file and
    the container healthcheck reads it. Also the durable evidence that the VPS
    really is the active ingress owner during an owner round-trip.
    """
    payload: dict[str, Any] = {
        "at": time.time(),
        "at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "instance_id": instance_id,
        "role": role,
        "pid": os.getpid(),
        "ingress_owner": ingress_owner_role(),
        "scope": lease_scope(),
        **extra,
    }
    try:
        _HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _HEARTBEAT_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, _HEARTBEAT_PATH)
    except Exception as exc:
        logger.debug("[telegram_coordinator] heartbeat write failed: %s", exc)


def read_polling_heartbeat() -> dict[str, Any]:
    """Read the polling heartbeat. Returns {} when absent/corrupt."""
    try:
        if _HEARTBEAT_PATH.exists():
            return json.loads(_HEARTBEAT_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


def heartbeat_age_seconds() -> float | None:
    """Seconds since the last polling round, or None when never written."""
    data = read_polling_heartbeat()
    try:
        at = float(data.get("at") or 0.0)
    except (TypeError, ValueError):
        return None
    return max(0.0, time.time() - at) if at else None


def ingress_conflict_state() -> dict[str, Any]:
    """Counters from real HTTP 409 conflicts (external consumer we do not own)."""
    now = time.time()
    return {
        "conflict_count": _conflict_count,
        "last_conflict_at": _last_conflict_at,
        "last_standby_reason": _last_standby_reason,
        "external_conflict_until": _external_conflict_until or None,
        "retry_in_s": round(max(0.0, _external_conflict_until - now), 1) if now < _external_conflict_until else None,
    }


def dispatch_egress_alert(
    title: str,
    text: str,
    severity: str = "INFO",
    chat_id: str | int | None = None,
) -> dict[str, Any]:
    """Dispatch a system alert through the Notify bot (@Leadsgenai1_bot).

    Includes deep-link prompt to interact with Jarvis bot (@Sumits_jarvis_bot).

    A 401-dead Notify token must never swallow a P0 alert: candidates are tried
    in priority order (notify → legacy → jarvis) and the dead one is blacklisted
    for this process. ``via`` reports which slot actually delivered.
    """
    candidates = egress_token_candidates()
    if not candidates:
        logger.warning("[telegram_coordinator] Egress alert skipped: no live telegram token")
        return {"sent": False, "ok": False, "reason": "token_unset"}

    target_chat = str(chat_id) if chat_id else "1621120182"
    formatted = (
        f"🚨 <b>[{severity.upper()}] {title}</b>\n\n"
        f"{text}\n\n"
        f"💬 <i>Reply to @Sumits_jarvis_bot for commands & status</i>"
    )
    payload: dict[str, Any] = {
        "chat_id": target_chat,
        "text": formatted,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "💬 Open Jarvis (commands)", "url": "https://t.me/Sumits_jarvis_bot"}]
            ]
        },
    }

    last_reason = "unknown"
    for label, token in candidates:
        res = _send_tg_api(token, "sendMessage", payload)
        if res.get("ok"):
            return {"sent": True, "ok": True, "via": label, "result": res.get("result")}
        if res.get("error_code") == 401:
            _dead_egress_tokens.add(token)
            logger.warning(
                "[telegram_coordinator] Egress token slot '%s' is 401-dead — blacklisted, trying next",
                label,
            )
            last_reason = "unauthorized"
            continue
        last_reason = str(res.get("description") or "error")[:120]
        logger.warning("[telegram_coordinator] Egress alert failed via '%s': %s", label, last_reason)
        break

    return {"sent": False, "ok": False, "reason": last_reason}


def dispatch_jarvis_response(
    chat_id: int | str,
    text: str,
    parse_mode: str = "HTML",
) -> dict[str, Any]:
    """Dispatch a command response through the Jarvis bot (@Sumits_jarvis_bot)."""
    token = get_polling_token()
    if not token:
        logger.warning("[telegram_coordinator] Jarvis response skipped: TELEGRAM_JARVIS_BOT_TOKEN unset")
        return {"sent": False, "reason": "token_unset"}

    return _send_tg_api(
        token,
        "sendMessage",
        {
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        },
    )


def get_dual_bot_status(live_probe: bool = False) -> dict[str, Any]:
    """Inspect and return coordination status for both bots.

    ``live_probe=True`` additionally performs a real ``getMe`` per token slot
    (CONFIGURED → AUTHENTICATED distinction). Default is offline/no-network so
    importing or reporting can never stall on an API call.
    """
    jarvis_token = get_polling_token()
    notify_token = get_egress_token()
    me = get_instance_id()

    jarvis_token_valid: bool | None = None
    if live_probe and jarvis_token:
        jarvis_token_valid = bool(validate_bot_token(jarvis_token).get("valid"))

    status: dict[str, Any] = {
        "configured": is_telegram_configured(),
        "jarvis": {
            "token_configured": bool(jarvis_token),
            "token_valid": jarvis_token_valid,
            "role": "ingress_interactive_commands",
            "username": "@Sumits_jarvis_bot",
            "polling_enabled": True,
        },
        "notify": {
            "token_configured": bool(notify_token),
            "role": "egress_broadcast_alerts",
            "username": "@Leadsgenai1_bot",
            "polling_enabled": False,  # Strict invariant: zero 409 conflicts
        },
        "owners": {
            "chat_ids": list(get_owner_chat_ids()),
            "usernames": list(get_owner_usernames()),
        },
        "ingress": {
            "owner_role": ingress_owner_role(),
            "instance_id": me,
            "instance_role": instance_role(),
            "lease": get_polling_lease(me),
            "conflicts": ingress_conflict_state(),
            "heartbeat": read_polling_heartbeat(),
            "heartbeat_age_s": heartbeat_age_seconds(),
            # dry_run: a status read must never claim the lease it is reporting on.
            "may_poll_now": should_poll(me, dry_run=True).get("poll"),
            "may_poll_reason": should_poll(me, dry_run=True).get("reason"),
        },
    }
    if live_probe:
        status["tokens"] = token_health(live=True)
    return status


def run_jarvis_polling(
    poll_timeout: int = 25,
    max_iterations: int | None = None,
    on_message_callback: Callable[[dict[str, Any]], None] | None = None,
    instance_id: str | None = None,
    role: str | None = None,
    max_standby_rounds: int = 240,
) -> None:
    """Run long-polling for the Jarvis Bot under single-consumer coordination.

    Coordination guarantees:
      * fail-closed if the token itself is invalid (no fake ingestion);
      * only one consumer per token via ``should_poll`` (owner role + lease);
      * a real HTTP 409 from an external consumer (e.g. Hermes) puts this
        process in standby with backoff and RELEASES its lease, instead of two
        processes fighting for the token;
      * the lease is always released on exit so a supervisor restart is instant.
    """
    global _conflict_count, _last_conflict_at, _last_standby_reason, _external_conflict_until

    token = get_polling_token()
    if not token:
        logger.error("[telegram_coordinator] Cannot start Jarvis polling: TELEGRAM_JARVIS_BOT_TOKEN unset")
        return

    me = get_instance_id(instance_id)
    my_role = instance_role(role)
    health = validate_bot_token(token, force=True)
    if not health.get("valid"):
        logger.error(
            "[telegram_coordinator] Polling refused — Jarvis token invalid (%s). "
            "Fix the credential; refusing to spin in a 401 loop.",
            health.get("reason"),
        )
        return

    from app.integrations.telegram_bot import get_telegram_bot

    bot = get_telegram_bot()
    logger.info(
        "[telegram_coordinator] Jarvis polling start — instance=%s role=%s owner=%s bot=%s",
        me,
        my_role,
        ingress_owner_role(),
        health.get("username"),
    )

    offset = 0
    iteration = 0
    standby_rounds = 0
    conflict_backoff = 10.0
    updates_total = 0
    write_polling_heartbeat(me, my_role, state="starting", polls=0, updates_total=0)

    try:
        while True:
            if max_iterations is not None and iteration >= max_iterations:
                logger.info(
                    "[telegram_coordinator] Reached max_iterations (%d), exiting polling",
                    max_iterations,
                )
                break
            if standby_rounds >= max_standby_rounds:
                logger.warning(
                    "[telegram_coordinator] Standby limit reached (%d rounds) — exiting so the supervisor retries",
                    standby_rounds,
                )
                break

            guard = should_poll(me, my_role)
            if not guard.get("poll"):
                _last_standby_reason = str(guard.get("reason"))
                standby_rounds += 1
                if standby_rounds == 1 or standby_rounds % 20 == 0:
                    logger.warning(
                        "[telegram_coordinator] STANDBY (%s) — not polling. holder=%s owner=%s role=%s retry_in=%ss",
                        guard.get("reason"),
                        guard.get("holder"),
                        guard.get("ingress_owner"),
                        my_role,
                        guard.get("retry_in_s", 15.0),
                    )
                write_polling_heartbeat(
                    me,
                    my_role,
                    state="standby",
                    reason=str(guard.get("reason")),
                    standby_rounds=standby_rounds,
                    polls=iteration,
                    updates_total=updates_total,
                )
                time.sleep(float(guard.get("retry_in_s") or 15.0))
                continue

            iteration += 1
            standby_rounds = 0

            params: dict[str, Any] = {
                "timeout": poll_timeout,
                "allowed_updates": ["message", "edited_message"],
            }
            if offset:
                params["offset"] = offset

            res = _send_tg_api(token, "getUpdates", params)
            if not res.get("ok"):
                err = str(res.get("description") or "unknown error")
                if "conflict" in err.lower():
                    _conflict_count += 1
                    _last_conflict_at = time.time()
                    _external_conflict_until = time.time() + conflict_backoff
                    # An external consumer (Hermes gateway) owns the token. Release
                    # our lease so we never appear as the holder while not polling.
                    release_polling_lease(me)
                    logger.error(
                        "[telegram_coordinator] HTTP 409 conflict #%d — external getUpdates consumer detected; "
                        "released lease, standby %.0fs. Set TELEGRAM_INGRESS_OWNER to name the single owner.",
                        _conflict_count,
                        conflict_backoff,
                    )
                    write_polling_heartbeat(
                        me,
                        my_role,
                        state="external_conflict",
                        conflicts=_conflict_count,
                        polls=iteration,
                        updates_total=updates_total,
                        backoff_s=conflict_backoff,
                    )
                    time.sleep(conflict_backoff)
                    conflict_backoff = min(60.0, conflict_backoff * 2)
                    continue
                logger.warning("[telegram_coordinator] getUpdates returned error: %s", err)
                time.sleep(3.0)
                continue

            conflict_backoff = 10.0
            updates = res.get("result") or []
            updates_total += len(updates)
            write_polling_heartbeat(
                me,
                my_role,
                state="polling",
                polls=iteration,
                updates_total=updates_total,
                last_batch=len(updates),
                conflicts=_conflict_count,
            )
            for update in updates:
                up_id = update.get("update_id")
                if up_id:
                    offset = max(offset, up_id + 1)

                try:
                    bot.process_update(update, send_reply=True)
                    if on_message_callback:
                        on_message_callback(update)
                except Exception as e:
                    logger.error("[telegram_coordinator] Error processing update: %s", e)
    finally:
        release_polling_lease(me)
        write_polling_heartbeat(
            me, my_role, state="stopped", polls=iteration, updates_total=updates_total
        )


# Backward compatibility aliases
TELEGRAM_JARVIS_BOT_TOKEN = os.getenv("TELEGRAM_JARVIS_BOT_TOKEN", "").strip()
TELEGRAM_NOTIFY_BOT_TOKEN = os.getenv("TELEGRAM_NOTIFY_BOT_TOKEN", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_OWNER_CHAT_IDS = get_owner_chat_ids()
TELEGRAM_OWNER_USERNAMES = get_owner_usernames()

__all__ = [
    "is_telegram_configured",
    "get_egress_token",
    "get_polling_token",
    "get_owner_chat_ids",
    "get_owner_usernames",
    "is_owner_chat",
    "is_owner_username",
    "is_duplicate_update",
    "dispatch_egress_alert",
    "dispatch_jarvis_response",
    "get_dual_bot_status",
    "run_jarvis_polling",
    # coordination (local <-> VPS <-> Hermes)
    "validate_bot_token",
    "token_health",
    "egress_token_candidates",
    "get_instance_id",
    "instance_role",
    "ingress_owner_role",
    "lease_ttl_seconds",
    "lease_scope",
    "acquire_polling_lease",
    "release_polling_lease",
    "get_polling_lease",
    "should_poll",
    "ingress_conflict_state",
    "write_polling_heartbeat",
    "read_polling_heartbeat",
    "heartbeat_age_seconds",
    "TELEGRAM_JARVIS_BOT_TOKEN",
    "TELEGRAM_NOTIFY_BOT_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_OWNER_CHAT_IDS",
    "TELEGRAM_OWNER_USERNAMES",
]
