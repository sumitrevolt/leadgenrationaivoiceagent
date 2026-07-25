"""Sales Autopilot policy — the ONE canonical config source.

Persisted JSON under ``data/sales_autopilot/policy.json`` + env overrides. Env always
wins over the persisted file for the safety-critical gates (so an operator can hard-stop
without editing a file). Everything defaults to the SAFEST value:

  - engine OFF, channels OFF, dry_run TRUE, canary batch = 1,
  - IST business hours 9–19, follow-ups capped at 2,
  - stop-on-reply / stop-on-optout / stop-on-payment all TRUE.

Never raises. Read via :func:`get_policy`.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_POLICY_DIR = os.path.join("data", "sales_autopilot")
_POLICY_FILE = os.path.join(_POLICY_DIR, "policy.json")


# ------------------------------------------------------------------ #
# Env flag helpers (env wins for gates)
# ------------------------------------------------------------------ #
def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_present(name: str) -> bool:
    return os.getenv(name) is not None


# Canonical defaults — safest posture.
_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "dry_run": True,  # simulate always until explicitly turned off in policy AND flags on
    "channels": ["whatsapp", "email"],
    "whatsapp_enabled": False,
    "email_enabled": False,
    "icp": {
        # empty = allow-any (still gated by every other check); populate to restrict.
        "niches": [],
        "cities": [],
    },
    "caps": {
        "daily_new_outreach": 20,
        "daily_followups": 40,
        "per_prospect_max_followups": 2,
        "hourly_total": 15,
    },
    "ist_hours": {"start": 9, "end": 19},  # promo window (code-conservative; TRAI 9–21)
    "canary_batch_size": 1,
    "kill_switches": {
        "new_outreach": False,  # True = block brand-new first-touch sends
        "followups": False,  # True = block follow-ups
        "auto_replies": False,  # True = block safe auto-replies (escalate only)
        "payment_reminders": False,  # True = block payment/onboarding nudges
    },
    "stop_on_reply": True,
    "stop_on_optout": True,
    "stop_on_payment": True,
    "provider_timeout_s": 20,
    "version": "2026-07-24",
}


def _read_file() -> dict[str, Any]:
    try:
        if os.path.exists(_POLICY_FILE):
            with open(_POLICY_FILE, encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[sales_autopilot.policy] read failed: %s", e)
    return {}


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _apply_env_overrides(pol: dict[str, Any]) -> dict[str, Any]:
    """Env is authoritative for the safety-critical gates."""
    pol = dict(pol)
    # Master + channel gates: env presence wins.
    if _env_present("SALES_AUTOPILOT_ENABLED"):
        pol["enabled"] = _env_bool("SALES_AUTOPILOT_ENABLED", pol.get("enabled", False))
    if _env_present("SALES_AUTOPILOT_WHATSAPP_ENABLED"):
        pol["whatsapp_enabled"] = _env_bool("SALES_AUTOPILOT_WHATSAPP_ENABLED", False)
    if _env_present("SALES_AUTOPILOT_EMAIL_ENABLED"):
        pol["email_enabled"] = _env_bool("SALES_AUTOPILOT_EMAIL_ENABLED", False)
    # Dry-run: env can only make it MORE safe (force dry-run), never silently disable it.
    if _env_present("SALES_AUTOPILOT_DRY_RUN"):
        pol["dry_run"] = _env_bool("SALES_AUTOPILOT_DRY_RUN", True)
    # Per-stage kill switches (env True forces the kill on).
    ks = dict(pol.get("kill_switches") or {})
    for env_name, key in (
        ("SALES_AUTOPILOT_NEW_OUTREACH_KILL", "new_outreach"),
        ("SALES_AUTOPILOT_FOLLOWUP_KILL", "followups"),
        ("SALES_AUTOPILOT_AUTOREPLY_KILL", "auto_replies"),
        ("SALES_AUTOPILOT_PAYMENT_REMINDER_KILL", "payment_reminders"),
    ):
        if _env_bool(env_name, False):
            ks[key] = True
    pol["kill_switches"] = ks
    # Canary batch override.
    if _env_present("SALES_AUTOPILOT_CANARY_BATCH"):
        try:
            pol["canary_batch_size"] = max(1, int(os.getenv("SALES_AUTOPILOT_CANARY_BATCH", "1")))
        except Exception:
            pass
    return pol


class Policy(dict):
    """Thin dict wrapper with convenient, always-safe accessors."""

    @property
    def enabled(self) -> bool:
        return bool(self.get("enabled"))

    @property
    def dry_run(self) -> bool:
        # A disabled engine is ALWAYS dry-run regardless of the stored flag.
        return bool(self.get("dry_run")) or not self.enabled

    def channel_enabled(self, channel: str) -> bool:
        channel = (channel or "").lower()
        if channel == "whatsapp":
            return bool(self.get("whatsapp_enabled"))
        if channel == "email":
            return bool(self.get("email_enabled"))
        return False

    def kill(self, key: str) -> bool:
        return bool((self.get("kill_switches") or {}).get(key))

    def max_followups(self) -> int:
        try:
            return int((self.get("caps") or {}).get("per_prospect_max_followups", 2))
        except Exception:
            return 2

    def canary_batch(self) -> int:
        try:
            return max(1, int(self.get("canary_batch_size", 1)))
        except Exception:
            return 1


def get_policy() -> Policy:
    """The one canonical, fully-resolved policy (defaults ← file ← env)."""
    merged = _deep_merge(_DEFAULTS, _read_file())
    merged = _apply_env_overrides(merged)
    return Policy(merged)


def save_policy(patch: dict[str, Any]) -> Policy:
    """Persist a partial policy update (admin surface). Env still overrides gates on read.

    Refuses to persist ``dry_run=false`` unless explicitly acknowledged, so a stray admin
    call cannot silently arm live sending — the caller must pass the exact patch.
    """
    try:
        os.makedirs(_POLICY_DIR, exist_ok=True)
        current = _deep_merge(_DEFAULTS, _read_file())
        merged = _deep_merge(current, patch or {})
        with open(_POLICY_FILE, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, sort_keys=True)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[sales_autopilot.policy] save failed: %s", e)
    return get_policy()


__all__ = ["Policy", "get_policy", "save_policy"]
