"""Console Event Dispatcher — durable contract between product consoles
(EVENT_SLOTS in app/api/product_consoles.py) and the worker.

WHAT THIS IS
------------
A thin, fail-closed contract. A console event is a typed envelope:

    {
        "event_id":      "ce_<tenant>_<ts>_<hash8>",   # unique
        "event_key":     "inbound_missed",             # MUST be in EVENT_SLOTS
        "tenant_id":     "leadgen-ai",
        "occurred_at":   "2026-09-04T22:11:00+05:30",  # ISO
        "payload":       {...},                        # free-form, per-event
        "dedupe_key":    "tenant|key|payload_hash",    # optional override
        "channels":      ["voice","sms","whatsapp"],   # from slot
        "requires_dlt":  True,                         # from slot
        "source":        "app.telephony.voice_launch"  # who emitted
    }

The dispatcher writes one envelope to a per-tenant JSONL store, deduplicating
within a configurable window, and never breaks the caller's hot path. The
worker drains the queue and routes envelopes to HANDLERS (typed map below).

DESIGN PRINCIPLES
-----------------
* Fail-closed but never crash-the-caller. Every storage op is wrapped; an
  IO error is logged and the call returns ``{"emitted": False, "reason": ...}``
  so production paths (billing, voice, webhooks) keep working.
* Per-tenant isolation — ``data/console_events/<tenant_id>.jsonl`` is the
  canonical store. A tenant never sees another tenant's events.
* Dedupe is content+tenant+key based, not time based. Two identical inbound
  misses from the same number within 60s collapse to one dispatch (anti-flood).
* Kill-switch aware: voice-channel events are dropped when VOICE_LAUNCH_KILL=1,
  regardless of any other flag.
* Optional ``dry_run=True`` for tests + canary, so the same path can prove
  correctness without leaking real traffic to WAHA / Vobiz.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: Per-tenant store root. Resolves to ``data/console_events`` in the checkout,
#: which is the same legacy pattern WhatsApp drafts already uses. We deliberately
#: do NOT route this through runtime_data_authority — this is a new store, not
#: a migrated one, and adding authority coupling now would lock us into the wrong
#: layer when the cutover plan is finalized.
DEFAULT_STORE_ROOT = Path(
    os.environ.get("CONSOLE_EVENT_STORE_ROOT", "data/console_events")
)

#: In-process dedupe window. A duplicate (same dedupe_key) within this window
#: collapses to one envelope. Persistent dedupe is a separate concern handled
#: in drain (handlers are expected to be idempotent).
DEDUPE_WINDOW_S = float(os.environ.get("CONSOLE_EVENT_DEDUPE_WINDOW_S", "60"))

#: Hard cap per tenant — protects against runaway emitters. Older envelopes
#: are trimmed from the head, keeping the most recent (most actionable) state.
#: Read at call-time (NOT module import) so tests + env-var overlays work
#: without needing to reload the module.
DEFAULT_MAX_PER_TENANT = 200


def _max_per_tenant() -> int:
    return int(
        os.environ.get("CONSOLE_EVENT_MAX_PER_TENANT", str(DEFAULT_MAX_PER_TENANT))
    )


# --------------------------------------------------------------------------- #
# Fail-closed imports. The dispatcher is the seam; product_consoles is the
# source of truth for valid event keys. If product_consoles cannot import
# (rare — only happens during early bootstrap), the dispatcher still loads
# and uses a frozen fallback set, so we never crash the worker tick.
# --------------------------------------------------------------------------- #
def _load_event_slots() -> tuple[dict[str, dict[str, Any]], set[str]]:
    try:
        from app.api.product_consoles import EVENT_SLOTS  # noqa: WPS433

        by_key = {slot["key"]: slot for slot in EVENT_SLOTS}
        return by_key, set(by_key.keys())
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "console_dispatcher: EVENT_SLOTS unavailable (%s); using empty "
            "fallback so the dispatcher remains import-safe.",
            exc.__class__.__name__,
        )
        return {}, set()


_SLOTS_BY_KEY, _VALID_KEYS = _load_event_slots()


def valid_event_keys() -> frozenset[str]:
    """Frozen view of valid event keys. Useful for admin UIs + tests."""
    return frozenset(_VALID_KEYS)


def _refresh_slots_cache() -> None:
    """Test/admin hook — re-read EVENT_SLOTS after hot reload."""
    global _SLOTS_BY_KEY, _VALID_KEYS  # noqa: PLW0603
    _SLOTS_BY_KEY, _VALID_KEYS = _load_event_slots()


# --------------------------------------------------------------------------- #
# Storage helpers — pure functions, no side-effects beyond the file system.
# --------------------------------------------------------------------------- #
def _tenant_path(store_root: Path, tenant_id: str) -> Path:
    safe = tenant_id.strip() or "unknown"
    # Tenant IDs are tenant slugs already, but strip path separators defensively.
    safe = safe.replace("/", "_").replace("\\", "_")
    return store_root / f"{safe}.jsonl"


def _ensure_root(store_root: Path) -> None:
    store_root.mkdir(parents=True, exist_ok=True)


def _payload_hash(payload: Any) -> str:
    """Stable hash for a payload dict. Order-independent via sort_keys=True."""
    try:
        canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    except Exception:  # noqa: BLE001
        canonical = repr(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _now_iso() -> str:
    """ISO-8601 with local offset hint. Used only for envelope timestamps."""
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def _new_event_id(tenant_id: str) -> str:
    return f"ce_{tenant_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}"


# --------------------------------------------------------------------------- #
# In-process dedupe ring — bounded, never grows.
# Key: dedupe_key string. Value: monotonic expiry timestamp.
# --------------------------------------------------------------------------- #
_DEDUPE_RING: dict[str, float] = {}
_DEDUPE_RING_CAP = 4096


def _dedupe_seen(key: str, now: float) -> bool:
    """Return True iff this dedupe_key was emitted within the dedupe window."""
    if not key:
        return False
    expiry = now + DEDUPE_WINDOW_S
    # Drop expired entries lazily.
    expired = [k for k, v in _DEDUPE_RING.items() if v <= now]
    for k in expired:
        _DEDUPE_RING.pop(k, None)
    if key in _DEDUPE_RING:
        return True
    # Bounded insert: if ring grows past cap, drop the oldest (lowest expiry).
    if len(_DEDUPE_RING) >= _DEDUPE_RING_CAP:
        oldest_key = min(_DEDUPE_RING, key=lambda k: _DEDUPE_RING[k])
        _DEDUPE_RING.pop(oldest_key, None)
    _DEDUPE_RING[key] = expiry
    return False


def _kill_voice_active() -> bool:
    """Return True if the global outbound voice kill-switch is engaged."""
    return os.environ.get("VOICE_LAUNCH_KILL", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def emit_console_event(
    event_key: str,
    tenant_id: str,
    payload: dict[str, Any] | None = None,
    *,
    source: str = "",
    store_root: Path | str | None = None,
    dry_run: bool = False,
    override_dedupe_key: str | None = None,
) -> dict[str, Any]:
    """Emit a console event envelope. NEVER raises.

    Returns a dict with at minimum::

        {"emitted": bool, "event_id": str | None, "reason": str,
         "dedupe_key": str, "store_path": str}

    Reasons on the no-emit path:
      * "unknown_event_key" — not declared in EVENT_SLOTS
      * "voice_kill_active"  — VOICE_LAUNCH_KILL=1 and slot uses voice
      * "duplicate"          — within DEDUPE_WINDOW_S of an identical event
      * "empty_tenant"       — caller passed "" or whitespace
      * "storage_error"      — JSONL write raised; logged but not raised
    """
    payload = payload or {}
    now = time.time()
    root = Path(store_root) if store_root is not None else DEFAULT_STORE_ROOT
    store_path = _tenant_path(root, tenant_id)

    if not (tenant_id or "").strip():
        return {
            "emitted": False,
            "event_id": None,
            "reason": "empty_tenant",
            "dedupe_key": "",
            "store_path": "",
        }

    slot = _SLOTS_BY_KEY.get(event_key)
    if slot is None:
        logger.info(
            "console_dispatcher: drop unknown event_key=%r tenant=%r source=%r",
            event_key,
            tenant_id,
            source,
        )
        return {
            "emitted": False,
            "event_id": None,
            "reason": "unknown_event_key",
            "dedupe_key": "",
            "store_path": str(store_path),
        }

    # Kill-switch: voice-channel events are dropped when VOICE_LAUNCH_KILL=1.
    channels = list(slot.get("channels") or [])
    if channels and "voice" in channels and _kill_voice_active():
        logger.info(
            "console_dispatcher: VOICE_LAUNCH_KILL active, drop event_key=%r "
            "tenant=%r source=%r",
            event_key,
            tenant_id,
            source,
        )
        return {
            "emitted": False,
            "event_id": None,
            "reason": "voice_kill_active",
            "dedupe_key": "",
            "store_path": str(store_path),
        }

    dedupe_key = (
        override_dedupe_key
        or f"{tenant_id}|{event_key}|{_payload_hash(payload)}"
    )
    if _dedupe_seen(dedupe_key, now):
        return {
            "emitted": False,
            "event_id": None,
            "reason": "duplicate",
            "dedupe_key": dedupe_key,
            "store_path": str(store_path),
        }

    envelope = {
        "event_id": _new_event_id(tenant_id),
        "event_key": event_key,
        "tenant_id": tenant_id,
        "occurred_at": _now_iso(),
        "payload": payload,
        "dedupe_key": dedupe_key,
        "channels": channels,
        "requires_dlt": bool(slot.get("requires_dlt", False)),
        "source": source or "",
    }

    if dry_run:
        return {
            "emitted": True,
            "event_id": envelope["event_id"],
            "reason": "dry_run",
            "dedupe_key": dedupe_key,
            "store_path": str(store_path),
            "envelope": envelope,
        }

    try:
        _ensure_root(root)
        line = json.dumps(envelope, ensure_ascii=False, default=str)
        # Append-and-trim: best-effort, NEVER raise into the caller.
        with open(store_path, "a", encoding="utf-8") as fp:
            fp.write(line + "\n")
        _trim_to_cap(store_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "console_dispatcher: storage_error tenant=%r event=%r err=%s",
            tenant_id,
            event_key,
            exc.__class__.__name__,
        )
        return {
            "emitted": False,
            "event_id": envelope["event_id"],
            "reason": "storage_error",
            "dedupe_key": dedupe_key,
            "store_path": str(store_path),
        }

    return {
        "emitted": True,
        "event_id": envelope["event_id"],
        "reason": "ok",
        "dedupe_key": dedupe_key,
        "store_path": str(store_path),
    }


def _trim_to_cap(store_path: Path) -> None:
    """Keep the tail of the JSONL under the configured cap. Best-effort."""
    if not store_path.exists():
        return
    try:
        lines = store_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    cap = _max_per_tenant()
    if len(lines) <= cap:
        return
    kept = lines[-cap:]
    try:
        store_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("console_dispatcher: trim failed (%s)", exc.__class__.__name__)


def drain_console_events(
    tenant_id: str,
    *,
    max_count: int = 50,
    store_root: Path | str | None = None,
    clear_after: bool = False,
) -> list[dict[str, Any]]:
    """Read up to ``max_count`` envelopes for ``tenant_id``.

    With ``clear_after=True``, the store is reset after a successful read so the
    next drain starts fresh. With ``clear_after=False`` (default), this is a
    peek — useful for admin/inspect views.
    """
    root = Path(store_root) if store_root is not None else DEFAULT_STORE_ROOT
    store_path = _tenant_path(root, tenant_id)
    if not store_path.exists():
        return []
    try:
        raw = store_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    out: list[dict[str, Any]] = []
    for line in raw[:max_count]:
        line = line.strip()
        if not line:
            continue
        try:
            env = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(env, dict):
            out.append(env)

    if clear_after and out:
        try:
            remaining = raw[len(out):]
            store_path.write_text(
                "\n".join(l for l in remaining if l.strip()) + ("\n" if remaining else ""),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(
                "console_dispatcher: drain clear failed (%s)", exc.__class__.__name__
            )
    return out


def pending_event_count(
    tenant_id: str,
    *,
    store_root: Path | str | None = None,
) -> int:
    """How many envelopes are queued for ``tenant_id``. Zero if no file."""
    root = Path(store_root) if store_root is not None else DEFAULT_STORE_ROOT
    store_path = _tenant_path(root, tenant_id)
    if not store_path.exists():
        return 0
    try:
        return sum(1 for line in store_path.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return 0


# --------------------------------------------------------------------------- #
# HANDLERS — typed map of event_key -> sync handler.
# Each handler receives ``(envelope, ctx)`` where ``ctx`` is a free-form dict
# the worker tick can populate with things like ``{"dry_run": True}``.
# Handlers MUST be idempotent — drain semantics may re-deliver on crash.
#
# The default handlers are safe no-ops so the dispatcher can be deployed and
# tested without a real provider behind each event. Owners wire real handlers
# in M3+ (see PRODUCT_CONSOLES_2026-09-04.md → "real-handler backlog").
# --------------------------------------------------------------------------- #
Handler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def _noop_handler(envelope: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    return {"handled": False, "reason": "noop_default", "event_id": envelope.get("event_id")}


def _dry_run_handler(envelope: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "handled": True,
        "reason": "dry_run_logged",
        "event_id": envelope.get("event_id"),
        "event_key": envelope.get("event_key"),
    }


HANDLERS: dict[str, Handler] = dict.fromkeys(_VALID_KEYS, _noop_handler)


def register_handler(event_key: str, handler: Handler) -> bool:
    """Register a real handler. Returns False if ``event_key`` is unknown."""
    if event_key not in _VALID_KEYS:
        return False
    HANDLERS[event_key] = handler
    return True


def dispatch_envelope(
    envelope: dict[str, Any],
    *,
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Route one envelope through its handler. Returns the handler result."""
    ctx = ctx or {}
    event_key = envelope.get("event_key") or ""
    handler = HANDLERS.get(event_key, _noop_handler)
    try:
        return handler(envelope, ctx)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "console_dispatcher: handler crashed event=%s err=%s",
            event_key,
            exc.__class__.__name__,
        )
        return {
            "handled": False,
            "reason": f"handler_error:{exc.__class__.__name__}",
            "event_id": envelope.get("event_id"),
        }


# Reset handler ring when slots are refreshed (test convenience).
_orig_refresh = _refresh_slots_cache


def _refresh_slots_cache_rebound() -> None:  # noqa: D401
    _orig_refresh()
    # New keys added since last load get a no-op handler.
    for key in _VALID_KEYS:
        HANDLERS.setdefault(key, _noop_handler)


_refresh_slots_cache = _refresh_slots_cache_rebound  # type: ignore[assignment]
