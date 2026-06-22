"""B4 - customer-set lead status overrides (append-only; latest wins).

Source inquiries (data/inquiries.jsonl) stay immutable; this is a thin
overlay keyed by lead id. Each record carries the setting client_id so the
dashboard can apply only the owning client's overrides (IDOR-safe).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_OVR_FILE = os.path.join("data", "lead_status_overrides.jsonl")
ALLOWED_STATUSES = {"Hot", "Warm", "Cold", "Won", "Lost", "Follow-up"}


def read_overrides() -> dict[str, dict]:
    """{lead_id -> latest record}. Never raises."""
    out: dict[str, dict] = {}
    try:
        if not os.path.isfile(_OVR_FILE):
            return out
        with open(_OVR_FILE, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                    if isinstance(rec, dict) and rec.get("lead_id"):
                        out[str(rec["lead_id"])] = rec  # latest wins
                except Exception:
                    continue
    except Exception as e:
        logger.debug("lead_overrides read failed: %s", e)
    return out


def set_status(lead_id: str, client_id: str, status: str) -> bool:
    """Append an override. Returns False on invalid status or write failure."""
    if status not in ALLOWED_STATUSES:
        return False
    if not str(lead_id).strip():
        return False
    rec = {
        "lead_id": str(lead_id),
        "client_id": str(client_id),
        "status": status,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        os.makedirs(os.path.dirname(_OVR_FILE) or ".", exist_ok=True)
        with open(_OVR_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        logger.warning("lead_overrides write failed: %s", e)
        return False
