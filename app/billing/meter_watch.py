"""meter_watch.py — billing meter-failure WATCHER (SP1 code half).

WHY: dono billing meters fail-OPEN hain (call kabhi billing-bug se na ruke) —
`lead_usage.py` (qualified-lead meter, Product 2) aur `usage.py` (minute meter,
marketing-Advanced prepaid-minutes revenue path). Fail-open ka matlab: meter
write fail ho to call CHALTI rehti par revenue SILENTLY leak ho sakta. Dono
meters ab failure ko durable Redis list `billing:meter_failures` me record karte
(`_record_meter_failure`). Yeh module wahi list WATCH karta — agar failures
threshold se zyada badh jaayein, ops ko ALERT karo (ntfy via ops_alerts pattern).

Design (ops_alerts.py jaisa hi posture):
- **Master flag `METER_ALERTS=1`** — OFF default = INERT, zero behaviour change.
  (ntfy bhejne ke liye OPS_ALERTS infra/ntfy creds bhi chahiye, par yeh module
  apni khud ki gate rakhta taaki minute-meter watcher independently toggle ho.)
- **Delta-based**: har run pe Redis list ki LENGTH padho. Pichli baar dekhi gayi
  length se compare — agar GROWTH > threshold ho to alert. Last-seen count ek
  chhoti state-file me persist (data/meter_watch_state.json) taaki har run pe
  re-alert na ho (sirf naye failures pe).
- **Cooldown**: alert ke baad min-interval tak dobara alert nahi.
- **NEVER raises**: redis unset / file IO / kuch bhi = silent no-op dict.

Wiring (main session applies — see wiring_snippets):
  scheduler hourly job  -> meter_watch.check_meter_failures()
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FLAG = "METER_ALERTS"
_REDIS_LIST = "billing:meter_failures"
_DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
_STATE_PATH = _DATA_DIR / "meter_watch_state.json"

# Naye failures (delta) jiske baad alert (ek run me itne naye = page).
_GROWTH_THRESHOLD = int(os.environ.get("METER_ALERT_GROWTH_THRESHOLD", "5") or "5")
# Alert cooldown (seconds) — meter list lagataar badhti rahe to spam na ho.
_COOLDOWN_SEC = int(os.environ.get("METER_ALERT_COOLDOWN_SEC", str(6 * 3600)) or str(6 * 3600))


def enabled() -> bool:
    """Master gate. OFF default = INERT."""
    return os.environ.get(_FLAG, "0").strip().lower() in ("1", "true", "yes")


def _redis_list_len() -> int:
    """`billing:meter_failures` list ki length. -1 = redis unset/unreadable.
    KABHI raise nahi."""
    try:
        import redis as _redis

        url = os.environ.get("REDIS_URL")  # main noeviction redis (jahan failures lpush hote)
        if not url:
            return -1
        r = _redis.from_url(url, socket_timeout=2)
        return int(r.llen(_REDIS_LIST) or 0)
    except Exception as exc:
        logger.debug("meter_watch redis llen swallowed: %s", exc)
        return -1


def _read_state() -> dict[str, Any]:
    """{last_count, last_alert_ts}. {} on missing/error."""
    try:
        if not _STATE_PATH.exists():
            return {}
        return json.loads(_STATE_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _write_state(state: dict[str, Any]) -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_PATH.with_suffix(f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, _STATE_PATH)
    except Exception as exc:
        logger.debug("meter_watch state write swallowed: %s", exc)


def _alert(count: int, delta: int) -> None:
    """ops_alerts/ntfy ke through page bhejo. Best-effort, kabhi raise nahi."""
    try:
        from app.platform import ops_alerts as _oa

        title = f"🚨 Billing meter failures: +{delta} (total {count})"
        body = (
            f"{delta} naye meter-write failures last check ke baad — total {count} "
            f"in {_REDIS_LIST}. Revenue-leak risk (fail-open billing). "
            f"Replay: redis-cli lrange {_REDIS_LIST} 0 -1"
        )[:1500]
        # ops_alerts._ntfy = sync/async-safe scheduler. (Module-private par sahi
        # transport; ops_alerts is the project's single ntfy fan-out point.)
        _oa._ntfy(title, body, priority="urgent", tags=["rotating_light", "billing"])
    except Exception as exc:
        logger.debug("meter_watch alert swallowed: %s", exc)


def check_meter_failures() -> dict[str, Any]:
    """Redis `billing:meter_failures` list ko WATCH karo — naye failures (delta)
    threshold se zyada badhe to ops ko ntfy alert. State-file me last-seen count +
    last-alert-ts persist taaki re-alert/spam na ho. Returns small status dict
    (scheduler log ke liye). KABHI raise nahi karta.

    Flag `METER_ALERTS` OFF (default) = INERT no-op. Redis unset = INERT.
    """
    try:
        if not enabled():
            return {"alerted": False, "reason": "disabled"}

        count = _redis_list_len()
        if count < 0:
            return {"alerted": False, "reason": "redis_unavailable"}

        state = _read_state()
        last_count = int(state.get("last_count") or 0)
        last_alert_ts = float(state.get("last_alert_ts") or 0.0)
        now = time.time()

        # Delta — list trimmed/replayed ho ke ghat bhi sakti, to negative ko 0.
        delta = max(0, count - last_count)

        # Har run pe last_count refresh (warna trim ke baad delta galat aata).
        new_state = {"last_count": count, "last_alert_ts": last_alert_ts}

        if delta < _GROWTH_THRESHOLD:
            _write_state(new_state)
            return {"alerted": False, "reason": "below_threshold", "count": count, "delta": delta}

        if (now - last_alert_ts) < _COOLDOWN_SEC:
            _write_state(new_state)
            return {"alerted": False, "reason": "cooldown", "count": count, "delta": delta}

        _alert(count, delta)
        new_state["last_alert_ts"] = now
        _write_state(new_state)
        return {"alerted": True, "count": count, "delta": delta, "threshold": _GROWTH_THRESHOLD}
    except Exception as exc:  # never-raise: watcher kabhi scheduler na tode
        logger.debug("check_meter_failures swallowed: %s", exc)
        return {"alerted": False, "reason": "error"}


__all__ = ["enabled", "check_meter_failures"]
