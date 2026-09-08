"""social_engine.pause — Phase 8 pause + emergency-stop gates.

Three independent kill-switches for the social publish drain:
  - SOCIAL_EMERGENCY_STOP           → global brake (blocks EVERY job)
  - SOCIAL_PAUSED_PLATFORMS (csv)   → per-platform brake (e.g. "instagram,x")
  - SOCIAL_PAUSED_CLIENTS   (csv)   → per-customer brake (client_id list)

Each gate honours the same shape as `engine.enabled()` — env explicit wins,
`data/social_engine.json` fallback (`{"emergency_stop": true}`, `{"paused_platforms": [...]}`,
`{"paused_clients": [...]}`). Fail-CLOSED on config-file JSON error: **treat as
paused**, not open. A corrupt pause config must never cause a publish burst.

  should_pause_job(job)  → (paused: bool, reason: str)  # never raises

Reason strings feed `_dispatch_one` short-circuit + delivery_ledger event
`customer_action_required` so admin cockpit + customer wizard reflect state.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CONFIG_KEY = "SOCIAL_ENGINE_CONFIG"
_DEFAULT_CONFIG = "data/social_engine.json"


def _read_cfg() -> dict[str, Any]:
    """Load the pause config file. Returns `{"_corrupt": True}` if the file
    exists but can't be parsed — caller must treat corruption as PAUSE
    (fail-CLOSED). File-absent = clean empty dict (nothing paused explicitly)."""
    path = os.getenv(_CONFIG_KEY, _DEFAULT_CONFIG)
    try:
        if not os.path.isfile(path):
            return {}
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {"_corrupt": True}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"[pause] config parse failed → fail-closed PAUSE: {e}")
        return {"_corrupt": True}


def _env_csv(name: str) -> set[str]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return set()
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def emergency_stop_active() -> bool:
    """Global brake. env explicit → config fallback → default OFF."""
    v = (os.getenv("SOCIAL_EMERGENCY_STOP") or "").strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    cfg = _read_cfg()
    if cfg.get("_corrupt"):
        # Fail-closed: assume STOP if we can't read config.
        logger.warning("[pause] emergency_stop_active — corrupt config → fail-closed")
        return True
    return bool(cfg.get("emergency_stop"))


def paused_platforms() -> set[str]:
    env = _env_csv("SOCIAL_PAUSED_PLATFORMS")
    if env:
        return env
    cfg = _read_cfg()
    if cfg.get("_corrupt"):
        # Fail-closed: pause ALL known platforms if config unreadable.
        from .base import PLATFORMS

        return set(PLATFORMS) | {"whatsapp"}
    raw = cfg.get("paused_platforms") or []
    if isinstance(raw, str):
        return {x.strip().lower() for x in raw.split(",") if x.strip()}
    if isinstance(raw, list | tuple):
        return {str(x).strip().lower() for x in raw if str(x).strip()}
    return set()


def paused_clients() -> set[str]:
    # Client IDs are case-sensitive (e.g. "c_A"), so DON'T route through _env_csv
    # which lowercases everything. Only platforms need normalization.
    raw_env = (os.getenv("SOCIAL_PAUSED_CLIENTS") or "").strip()
    if raw_env:
        return {x.strip() for x in raw_env.split(",") if x.strip()}
    cfg = _read_cfg()
    if cfg.get("_corrupt"):
        # Config corruption ≠ default-pause EVERY client (that's what emergency
        # stop is for); pause-platforms already covered. Return empty here so
        # the platform-wide pause is the visible signal, not a mystery client
        # pause list.
        return set()
    raw = cfg.get("paused_clients") or []
    if isinstance(raw, str):
        return {x.strip() for x in raw.split(",") if x.strip()}
    if isinstance(raw, list | tuple):
        return {str(x).strip() for x in raw if str(x).strip()}
    return set()


def should_pause_job(job: dict[str, Any]) -> tuple[bool, str]:
    """Decide if a claimed job must be skipped. Returns (paused, reason).
    reason ∈ {"emergency_stop", "paused_platform", "paused_client", ""}.
    Never raises — logs + returns (True, "gate_error") on unexpected error
    (fail-CLOSED)."""
    try:
        if emergency_stop_active():
            return True, "emergency_stop"
        # Owner OS publishing kill (Postgres/JSONL) — fail-closed if engaged.
        try:
            from app.platform.owner_os import kill_engaged

            if kill_engaged("owner_publishing"):
                return True, "owner_publishing_kill"
        except Exception:
            pass
        plat = str(job.get("platform") or "").strip().lower()
        if plat and plat in paused_platforms():
            return True, "paused_platform"
        cid = str(job.get("client_id") or "").strip()
        if cid and cid in paused_clients():
            return True, "paused_client"
        return False, ""
    except Exception as e:
        logger.warning(f"[pause] should_pause_job error → fail-closed: {e}")
        return True, "gate_error"


def set_config(**partial: Any) -> dict[str, Any]:
    """Runtime toggle helper (admin-endpoint uses this). Rewrites the config
    file additive over current values. Never raises (returns {} on failure)."""
    try:
        path = os.getenv(_CONFIG_KEY, _DEFAULT_CONFIG)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        cur = _read_cfg()
        if cur.get("_corrupt"):
            cur = {}
        for k, v in partial.items():
            if v is None:
                continue
            cur[k] = v
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cur, fh, indent=2, ensure_ascii=False)
        return cur
    except Exception as e:
        logger.warning(f"[pause] set_config failed: {e}")
        return {}
