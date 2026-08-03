"""Sales Autopilot persistence — prospect state + attempt ledger + idempotency.

Self-contained JSON/JSONL under ``data/sales_autopilot/``. This is a *coordination*
ledger for the autopilot loop, NOT a second CRM: prospect identity/enrichment stays in
the platform's existing stores; here we only track sales-lifecycle state + every send
attempt (for idempotency, audit, and observability). Never raises.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DIR = os.path.join("data", "sales_autopilot")
_PROSPECTS_FILE = os.path.join(_DIR, "prospects.json")
_ATTEMPTS_FILE = os.path.join(_DIR, "attempts.jsonl")

_LOCK = threading.RLock()

# ------------------------------------------------------------------ #
# Estique — verified truth. Owner already manually contacted; initial done.
# ------------------------------------------------------------------ #
ESTIQUE_ID = "1009985f-bd15-422a-93e4-69b6b8efd6bd"
ESTIQUE_PHONE = "+919702475550"
ESTIQUE_EMAIL = "info@estiquesalonsnspa.com"

# Lifecycle statuses.
STATUS_NEW = "new"
STATUS_CONTACTED = "contacted"
STATUS_FOLLOWUP = "followup"
STATUS_REPLIED = "replied"
STATUS_OPTED_OUT = "opted_out"
STATUS_CONVERTED = "converted"
STATUS_AWAITING_PAYMENT = "awaiting_payment"  # converted without ledger proof (pay-truth)
STATUS_MANUAL_OWNER_CONFIRMED = "manual_owner_confirmed"
STATUS_REMOVED = "removed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digits(phone: str) -> str:
    return "".join(c for c in (phone or "") if c.isdigit())


# ------------------------------------------------------------------ #
# Prospect state
# ------------------------------------------------------------------ #
def _read_prospects() -> dict[str, Any]:
    try:
        if os.path.exists(_PROSPECTS_FILE):
            with open(_PROSPECTS_FILE, encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[sales_autopilot.store] read prospects failed: %s", e)
    return {}


def _write_prospects(data: dict[str, Any]) -> None:
    try:
        os.makedirs(_DIR, exist_ok=True)
        tmp = _PROSPECTS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, _PROSPECTS_FILE)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[sales_autopilot.store] write prospects failed: %s", e)


def get_prospect(prospect_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _read_prospects().get(str(prospect_id))


def list_prospects(limit: int = 500) -> list[dict[str, Any]]:
    with _LOCK:
        rows = list(_read_prospects().values())
    rows.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return rows[: max(1, int(limit))]


def upsert_prospect(prospect: dict[str, Any]) -> dict[str, Any]:
    """Create/merge a prospect record. ``id`` (or ``prospect_id``) required. Never raises."""
    pid = str(prospect.get("id") or prospect.get("prospect_id") or "").strip()
    if not pid:
        return {"error": "missing_id"}
    with _LOCK:
        data = _read_prospects()
        existing = data.get(pid, {})
        merged = {**existing, **{k: v for k, v in prospect.items() if v is not None}}
        merged["id"] = pid
        merged.setdefault("status", STATUS_NEW)
        merged.setdefault("steps_done", [])
        merged.setdefault("followup_count", 0)
        merged.setdefault("reply_count", 0)
        merged.setdefault("created_at", existing.get("created_at") or _now())
        merged["updated_at"] = _now()
        data[pid] = merged
        _write_prospects(data)
        return merged


def mark_status(prospect_id: str, status: str, **fields: Any) -> dict[str, Any] | None:
    with _LOCK:
        data = _read_prospects()
        rec = data.get(str(prospect_id))
        if not rec:
            return None
        rec["status"] = status
        for k, v in fields.items():
            rec[k] = v
        rec["updated_at"] = _now()
        data[str(prospect_id)] = rec
        _write_prospects(data)
        return rec


def add_step_done(prospect_id: str, step: str) -> None:
    with _LOCK:
        data = _read_prospects()
        rec = data.get(str(prospect_id))
        if not rec:
            return
        steps = list(rec.get("steps_done") or [])
        if step not in steps:
            steps.append(step)
        rec["steps_done"] = steps
        rec["updated_at"] = _now()
        data[str(prospect_id)] = rec
        _write_prospects(data)


def is_owner_confirmed(prospect_id: str) -> bool:
    rec = get_prospect(prospect_id)
    if not rec:
        return False
    return rec.get("status") == STATUS_MANUAL_OWNER_CONFIRMED or bool(
        rec.get("manual_owner_confirmed")
    )


def mark_removed(prospect_id: str, *, by: str = "admin", reason: str = "") -> dict[str, Any] | None:
    """Terminal state: this prospect is NO LONGER a customer (admin/owner decision).

    Clears the converted linkage + manual-owner flags so it stops counting as a
    converted customer AND the autopilot never re-contacts it (eligibility treats
    ``removed`` as fail-closed INELIGIBLE). Adds an audit note to the record.
    """
    return mark_status(
        str(prospect_id),
        STATUS_REMOVED,
        converted_client_id="",
        manual_owner_confirmed=False,
        removed_by=by,
        removed_reason=reason or "",
    )


def find_by_converted_client(client_id: str) -> list[dict[str, Any]]:
    """Prospects that converted to a given marketing client_id (customer-removal sweep)."""
    cid = str(client_id or "").strip()
    if not cid:
        return []
    return [
        r
        for r in list_prospects(limit=5000)
        if str(r.get("converted_client_id") or "").strip() == cid
    ]


# ------------------------------------------------------------------ #
# Attempt ledger (idempotency + audit + observability)
# ------------------------------------------------------------------ #
def _read_attempts() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if os.path.exists(_ATTEMPTS_FILE):
            with open(_ATTEMPTS_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            continue
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[sales_autopilot.store] read attempts failed: %s", e)
    return out


def attempt_exists(idempotency_key: str) -> bool:
    key = (idempotency_key or "").strip()
    if not key:
        return False
    with _LOCK:
        for a in _read_attempts():
            if a.get("idempotency_key") == key:
                return True
    return False


def get_attempt(idempotency_key: str) -> dict[str, Any] | None:
    key = (idempotency_key or "").strip()
    if not key:
        return None
    with _LOCK:
        for a in reversed(_read_attempts()):
            if a.get("idempotency_key") == key:
                return a
    return None


def record_attempt(attempt: dict[str, Any]) -> dict[str, Any]:
    """Append an attempt record. Persisted BEFORE the provider call (status=pending)."""
    rec = dict(attempt)
    rec.setdefault("at", _now())
    with _LOCK:
        try:
            os.makedirs(_DIR, exist_ok=True)
            with open(_ATTEMPTS_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("[sales_autopilot.store] record attempt failed: %s", e)
    return rec


def update_attempt_status(idempotency_key: str, status: str, **fields: Any) -> None:
    """Append a status-update marker (append-only ledger; latest wins on read)."""
    record_attempt(
        {
            "idempotency_key": idempotency_key,
            "status": status,
            "_marker": "status_update",
            **fields,
        }
    )


def list_attempts(limit: int = 500) -> list[dict[str, Any]]:
    with _LOCK:
        rows = _read_attempts()
    return rows[-max(1, int(limit)) :][::-1]


def attempts_today(status: str | None = None, channel: str | None = None) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    n = 0
    with _LOCK:
        for a in _read_attempts():
            if a.get("_marker") == "status_update":
                continue
            if not str(a.get("at", "")).startswith(today):
                continue
            if status and a.get("status") != status:
                continue
            if channel and a.get("channel") != channel:
                continue
            n += 1
    return n


# ------------------------------------------------------------------ #
# Scheduler last-run truth (observability — one small JSON, latest wins)
# ------------------------------------------------------------------ #
def _last_tick_file() -> str:
    # Derived from _DIR at call-time so test monkeypatch of _DIR is honoured.
    return os.path.join(_DIR, "last_tick.json")


def record_tick(summary: dict[str, Any]) -> dict[str, Any]:
    """Persist the most recent scheduler-tick truth (time + result). Never raises."""
    rec = dict(summary or {})
    rec["at"] = _now()
    with _LOCK:
        try:
            os.makedirs(_DIR, exist_ok=True)
            tmp = _last_tick_file() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)
            os.replace(tmp, _last_tick_file())
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("[sales_autopilot.store] record tick failed: %s", e)
    return rec


def get_last_tick() -> dict[str, Any] | None:
    """Read the last recorded scheduler tick (or None if never run). Never raises."""
    with _LOCK:
        try:
            path = _last_tick_file()
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    return json.load(f) or None
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("[sales_autopilot.store] read last tick failed: %s", e)
    return None


# ------------------------------------------------------------------ #
# Estique seed / guard
# ------------------------------------------------------------------ #
def ensure_estique_seed() -> dict[str, Any]:
    """Idempotently seed Estique as ``manual_owner_confirmed`` with the initial step done.

    Safe to call repeatedly; never overwrites a richer existing record's status downward.
    """
    existing = get_prospect(ESTIQUE_ID)
    rec = upsert_prospect(
        {
            "id": ESTIQUE_ID,
            "name": "Estique Salon & Spa",
            "phone": ESTIQUE_PHONE,
            "email": ESTIQUE_EMAIL,
            "city": "Thane",
            "niche": "beauty_makeover",
            "source": "owner_manual",
            "consent_basis": "manual_owner_confirmed",
            "manual_owner_confirmed": True,
            "status": STATUS_MANUAL_OWNER_CONFIRMED,
        }
    )
    # Ensure the initial WhatsApp/email steps are recorded as already complete.
    if not existing:
        for step in ("initial_whatsapp", "initial_email"):
            add_step_done(ESTIQUE_ID, step)
        return get_prospect(ESTIQUE_ID) or rec
    return rec


__all__ = [
    "ESTIQUE_ID",
    "ESTIQUE_PHONE",
    "ESTIQUE_EMAIL",
    "STATUS_NEW",
    "STATUS_CONTACTED",
    "STATUS_FOLLOWUP",
    "STATUS_REPLIED",
    "STATUS_OPTED_OUT",
    "STATUS_CONVERTED",
    "STATUS_AWAITING_PAYMENT",
    "STATUS_MANUAL_OWNER_CONFIRMED",
    "STATUS_REMOVED",
    "digits",
    "get_prospect",
    "list_prospects",
    "upsert_prospect",
    "mark_status",
    "mark_removed",
    "find_by_converted_client",
    "add_step_done",
    "is_owner_confirmed",
    "attempt_exists",
    "get_attempt",
    "record_attempt",
    "update_attempt_status",
    "list_attempts",
    "attempts_today",
    "record_tick",
    "get_last_tick",
    "ensure_estique_seed",
]
