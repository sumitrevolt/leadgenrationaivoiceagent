"""
data_privacy.py — DSAR / data-privacy helper layer.
====================================================

Ek thin orchestration layer jo existing dpdp.py ke upar baith ke 4 clean
helper functions expose karta hai (parent task requirement):

  anonymize_pii(value)              — mask phone/email/name in str or dict.
  export_subject_data(identifier)   — DSAR Right-to-Access export (wraps dpdp).
  delete_subject_data(identifier)   — DSAR erasure / dry-run preview (wraps dpdp).
  enforce_retention(dry_run=True)   — Retention sweep: old records report/purge.
  data_lineage(record)              — UTM/source/timestamp tags for a record.

Design rules (match codebase):
  - KABHI raise nahi karta — har function error dict lautata hai.
  - Destructive ops: DATA_ERASURE=1 env gate + explicit confirm=True DONO.
  - Retention real action: DATA_RETENTION=1 gate + dry_run=False.
  - Default everything to safe / dry-run.
  - Composing over dpdp.py — duplicate nahi karta.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Store path for privacy ops audit log (owned by this module — dpdp has its own)
# ---------------------------------------------------------------------------
_PRIVACY_OPS_LOG = Path("data") / "privacy_ops.jsonl"

# PII keys (case-insensitive) whose values we aggressively mask in dicts
_PII_KEYS = frozenset(
    {
        "phone",
        "mobile",
        "contact",
        "whatsapp",
        "email",
        "mail",
        "name",
        "contact_name",
        "customer_name",
        "full_name",
        "first_name",
        "last_name",
        "address",
        "location",
    }
)

# Regex to find 10+ consecutive digit runs (phone numbers in free text)
_PHONE_RUN_RE = re.compile(r"\d(?:[\s\-]?\d){9,}")

# Env gates
_ERASURE_GATE = "DATA_ERASURE"
_RETENTION_GATE = "DATA_RETENTION"

# Default retention threshold (days) — DPDP / TRAI guidance
_DEFAULT_RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "365"))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_op(action: str, identifier: str, detail: dict[str, Any]) -> None:
    """Append a line to data/privacy_ops.jsonl.  Never raises."""
    try:
        _PRIVACY_OPS_LOG.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": _now(), "action": action, "identifier": identifier[:80], **detail}
        with _PRIVACY_OPS_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:  # pragma: no cover
        logger.warning(f"[data_privacy] log_op failed: {exc}")


def _mask_phone_str(s: str) -> str:
    """Keep last 2 digits, mask rest (e.g. 9876543210 → XXXXXXXX10)."""
    s = str(s or "")
    if not s:
        return s
    # If it looks like a phone (mostly digits / standard separators)
    digits = re.sub(r"[\s\-+()]", "", s)
    if digits.isdigit() and len(digits) >= 6:
        return "X" * (len(digits) - 2) + digits[-2:]
    # Free-text with embedded numbers
    return _PHONE_RUN_RE.sub("XXXXXXXXXX", s)


def _mask_email_str(s: str) -> str:
    """Keep domain, mask local part (e.g. ravi@example.com → r***@example.com)."""
    s = str(s or "")
    if "@" not in s:
        return "***"
    local, _, domain = s.partition("@")
    masked_local = (local[:1] + "***") if local else "***"
    return f"{masked_local}@{domain}"


def _mask_name_str(s: str) -> str:
    """Keep first initial, mask rest (e.g. Ravi Sharma → R*** S***)."""
    parts = str(s or "").split()
    return " ".join((p[:1] + "***") for p in parts) if parts else "***"


def _mask_value(key: str, value: Any) -> Any:
    """Mask a single value based on key semantics."""
    if not isinstance(value, str):
        return value
    kl = key.lower()
    if any(t in kl for t in ("phone", "mobile", "contact", "whatsapp")):
        return _mask_phone_str(value)
    if "email" in kl or "mail" in kl:
        return _mask_email_str(value)
    if "name" in kl or "address" in kl or "location" in kl:
        return _mask_name_str(value)
    # Fallback: scrub any embedded phone-run
    return _PHONE_RUN_RE.sub("XXXXXXXXXX", value)


def _anonymize_dict(d: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    """Recursively mask common PII keys in a dict (max depth 4)."""
    if depth > 4:
        return d
    out: dict[str, Any] = {}
    try:
        for k, v in d.items():
            kl = str(k).lower()
            if any(pii in kl for pii in _PII_KEYS):
                if isinstance(v, str):
                    out[k] = _mask_value(k, v)
                elif isinstance(v, dict):
                    out[k] = _anonymize_dict(v, depth + 1)
                else:
                    out[k] = v
            elif isinstance(v, dict):
                out[k] = _anonymize_dict(v, depth + 1)
            elif isinstance(v, list):
                out[k] = [
                    _anonymize_dict(item, depth + 1) if isinstance(item, dict) else item
                    for item in v
                ]
            else:
                out[k] = v
    except Exception as exc:  # pragma: no cover
        logger.warning(f"[data_privacy] anonymize_dict error: {exc}")
        return d
    return out


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------


def anonymize_pii(value: Any) -> Any:
    """Mask PII in a string or dict (recursive).

    str  → scrub embedded phone-runs; return masked string.
    dict → recursively mask values for keys matching PII_KEYS.
    other types returned as-is.

    Never raises.
    """
    try:
        if isinstance(value, str):
            return _PHONE_RUN_RE.sub("XXXXXXXXXX", value)
        if isinstance(value, dict):
            return _anonymize_dict(value)
    except Exception as exc:  # pragma: no cover
        logger.warning(f"[data_privacy] anonymize_pii error: {exc}")
    return value


async def export_subject_data(identifier: str) -> dict[str, Any]:
    """DSAR Right-to-Access: gather everything tied to a phone/email identifier.

    Identifier may be a 10-digit phone or email address (auto-detected).
    Best-effort across jsonl stores + DB. Never raises.

    Returns: {identifier, records: [...], generated_at, ok, ...}
    """
    identifier = str(identifier or "").strip()
    if not identifier:
        return {"ok": False, "error": "identifier (phone ya email) zaroori hai."}
    try:
        from app.platform import dpdp

        # Auto-detect phone vs email
        phone: str | None = None
        email: str | None = None
        if "@" in identifier:
            email = identifier
        else:
            phone = identifier

        result = await dpdp.export_subject(
            phone=phone, email=email, include_db=True, actor="dsar_api"
        )
        # Normalise to expected shape
        records_dict: dict[str, list[dict]] = result.get("records", {})
        flat_records: list[dict[str, Any]] = []
        for store_name, recs in records_dict.items():
            for rec in recs if isinstance(recs, list) else []:
                flat_records.append({"_store": store_name, **rec})
        # Also include DB leads if present
        db_info = result.get("db_leads", {})
        if isinstance(db_info, dict) and db_info.get("available") and db_info.get("rows"):
            for row in db_info["rows"]:
                flat_records.append({"_store": "db_leads", **row})

        _log_op("export", identifier, {"total": len(flat_records)})
        return {
            "ok": result.get("ok", True),
            "identifier": identifier,
            "records": flat_records,
            "total_records": len(flat_records),
            "generated_at": _now(),
            "stores_searched": list(records_dict.keys()),
            "skipped_stores": result.get("skipped_stores", []),
            "note": result.get("note", ""),
        }
    except Exception as exc:
        logger.warning(f"[data_privacy] export_subject_data error: {exc}")
        return {
            "ok": False,
            "identifier": identifier,
            "records": [],
            "total_records": 0,
            "generated_at": _now(),
            "error": str(exc)[:200],
        }


async def delete_subject_data(identifier: str, confirm: bool = False) -> dict[str, Any]:
    """DSAR Right-to-Erasure.

    DRY-RUN by default — returns preview of what WOULD be deleted.

    Real erasure requires BOTH:
      - confirm=True (caller explicitly confirms)
      - env DATA_ERASURE=1 (ops-level gate)

    If either is missing → dry-run preview is returned with a clear message.
    Never raises.
    """
    identifier = str(identifier or "").strip()
    if not identifier:
        return {"ok": False, "error": "identifier (phone ya email) zaroori hai."}

    erasure_enabled = os.getenv(_ERASURE_GATE, "").strip() == "1"
    real_run = confirm and erasure_enabled

    # Explain why dry-run if caller asked for real but gate is missing
    gate_msg: str | None = None
    if confirm and not erasure_enabled:
        gate_msg = "DATA_ERASURE=1 env gate set nahi hai — dry-run mode me chal raha hai."

    try:
        from app.platform import dpdp

        phone: str | None = None
        email: str | None = None
        if "@" in identifier:
            email = identifier
        else:
            phone = identifier

        result = await dpdp.erase_subject(
            phone=phone,
            email=email,
            dry_run=not real_run,
            include_db=True,
            actor="dsar_api",
        )

        action = "delete_real" if real_run else "delete_dryrun"
        _log_op(
            action,
            identifier,
            {
                "dry_run": not real_run,
                "stores_touched": list(result.get("stores", {}).keys()),
            },
        )

        out = {**result, "dry_run": not real_run}
        if gate_msg:
            out["gate_message"] = gate_msg
        return out
    except Exception as exc:
        logger.warning(f"[data_privacy] delete_subject_data error: {exc}")
        return {
            "ok": False,
            "identifier": identifier,
            "dry_run": not real_run,
            "error": str(exc)[:200],
        }


def enforce_retention(dry_run: bool = True) -> dict[str, Any]:
    """Sweep JSONL records older than RETENTION_DAYS (env, default 365).

    dry_run=True (default)  → report only; nothing deleted.
    dry_run=False + DATA_RETENTION=1 env gate → real purge (atomic rewrite +
    .bak copy per touched file).

    Returns summary dict. Never raises.
    """
    retention_enabled = os.getenv(_RETENTION_GATE, "").strip() == "1"
    real_run = not dry_run and retention_enabled

    gate_msg: str | None = None
    if not dry_run and not retention_enabled:
        gate_msg = "DATA_RETENTION=1 env gate set nahi hai — dry-run mode me chal raha hai."
        real_run = False

    cutoff_days = _DEFAULT_RETENTION_DAYS
    try:
        import shutil
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
        cutoff_iso = cutoff.isoformat()

        # Walk the same stores as dpdp
        from app.platform import dpdp as _dpdp

        report: dict[str, dict[str, Any]] = {}
        total_old = 0
        total_purged = 0
        skipped: list[str] = []

        for store_name, path in _dpdp._iter_stores():
            try:
                if not os.path.exists(path):
                    continue
                with open(path, encoding="utf-8") as f:
                    raw_lines = f.readlines()
            except Exception as exc:
                skipped.append(store_name)
                logger.warning(f"[data_privacy] retention read failed {path}: {exc}")
                continue

            keep_lines: list[str] = []
            old_count = 0

            for ln in raw_lines:
                s = ln.strip()
                if not s:
                    continue
                try:
                    rec = json.loads(s)
                except Exception:
                    keep_lines.append(ln)  # corrupt lines always kept
                    continue

                # Look for any timestamp-like field
                ts_str = None
                for ts_key in ("ts", "created_at", "timestamp", "updated_at", "date"):
                    val = rec.get(ts_key) if isinstance(rec, dict) else None
                    if val and isinstance(val, str):
                        ts_str = val
                        break

                is_old = False
                if ts_str:
                    try:
                        # Try ISO parse (with or without tz)
                        ts_str_clean = ts_str[:26]  # trim microseconds
                        if ts_str_clean.endswith("Z"):
                            ts_str_clean = ts_str_clean[:-1] + "+00:00"
                        rec_dt = datetime.fromisoformat(ts_str_clean)
                        if rec_dt.tzinfo is None:
                            rec_dt = rec_dt.replace(tzinfo=timezone.utc)
                        is_old = rec_dt < cutoff
                    except Exception:
                        pass  # unparseable ts → keep

                if is_old:
                    old_count += 1
                else:
                    keep_lines.append(ln)

            total_old += old_count
            if old_count:
                report[store_name] = {"old_records": old_count, "purged": 0, "path": path}
                if real_run:
                    try:
                        bak = (
                            f"{path}.bak_ret_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
                        )
                        shutil.copy2(path, bak)
                        tmp = path + ".tmp_ret"
                        with open(tmp, "w", encoding="utf-8") as f:
                            for ln in keep_lines:
                                f.write(ln if ln.endswith("\n") else ln + "\n")
                        os.replace(tmp, path)
                        report[store_name]["purged"] = old_count
                        report[store_name]["backup"] = os.path.basename(bak)
                        total_purged += old_count
                    except Exception as exc:
                        logger.warning(f"[data_privacy] retention purge failed {path}: {exc}")
                        report[store_name]["error"] = str(exc)[:120]

        action = "retention_real" if real_run else "retention_dryrun"
        _log_op(
            action,
            "system",
            {
                "cutoff_days": cutoff_days,
                "total_old": total_old,
                "total_purged": total_purged,
                "dry_run": not real_run,
            },
        )

        out: dict[str, Any] = {
            "ok": True,
            "dry_run": not real_run,
            "cutoff_days": cutoff_days,
            "cutoff_date": cutoff_iso,
            "stores": report,
            "total_old_records": total_old,
            "total_purged": total_purged,
            "skipped_stores": skipped,
        }
        if gate_msg:
            out["gate_message"] = gate_msg
        return out

    except Exception as exc:
        logger.warning(f"[data_privacy] enforce_retention error: {exc}")
        return {
            "ok": False,
            "dry_run": not real_run,
            "error": str(exc)[:200],
        }


def data_lineage(record: Any) -> dict[str, Any]:
    """Extract source/lineage tags from a record dict.

    Returns dict with: source, utm_source, utm_medium, utm_campaign,
    created_at, updated_at, store_hint — whatever is available.
    Values not present are omitted. Never raises.
    """
    out: dict[str, Any] = {}
    if not isinstance(record, dict):
        return out
    try:
        # Source / channel
        for key in ("source", "utm_source", "channel", "lead_source", "origin"):
            val = record.get(key)
            if val is not None and str(val).strip():
                out[key] = str(val).strip()

        # UTM params
        for utm in ("utm_medium", "utm_campaign", "utm_term", "utm_content"):
            val = record.get(utm)
            if val is not None and str(val).strip():
                out[utm] = str(val).strip()

        # Timestamps
        for ts_key in ("created_at", "timestamp", "ts", "updated_at", "date"):
            val = record.get(ts_key)
            if val is not None and isinstance(val, str) and val.strip():
                out[ts_key] = val.strip()

        # Store hint (if record carries _store tag, e.g. from export_subject_data)
        store = record.get("_store")
        if store:
            out["store_hint"] = str(store)

        # Client / niche tags
        for tag in ("client_id", "niche", "city", "slug"):
            val = record.get(tag)
            if val is not None and str(val).strip():
                out[tag] = str(val).strip()

    except Exception as exc:  # pragma: no cover
        logger.warning(f"[data_privacy] data_lineage error: {exc}")
    return out


__all__ = [
    "anonymize_pii",
    "export_subject_data",
    "delete_subject_data",
    "enforce_retention",
    "data_lineage",
]
