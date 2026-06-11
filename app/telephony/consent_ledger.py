"""
Consent + Opt-out Ledger (TCCCPR/TRAI + DPDP Act 2023) — single source of truth.
================================================================================

Kya karta hai (free-stack, jsonl, never-raise):
  * CONSENT ledger    — timestamped consent records (source/scope/proof/client_id),
                        append-only `data/consent_ledger.jsonl` (DPDP audit trail +
                        "access right" ke liye `ledger_for(phone)`).
  * OPT-OUT           — `record_opt_out()` → instant suppression (`data/voice_suppression.jsonl`)
                        + cross-channel propagate (WA suppression list bhi) — TCCCPR ka
                        4-ghante propagation requirement INSTANT me beat hota hai.
  * SUPPRESSION check — `is_suppressed(phone)` (last-10-digit match). ComplianceGate
                        promotional calls ke liye ise enforce karta hai (wired).
  * RETENTION sweep   — `retention_sweep()` — `data/recordings/` me
                        RECORDING_RETENTION_DAYS (default 90) se purani files report;
                        DELETE sirf `RECORDING_RETENTION=1` flag pe (default = dry-run
                        report only, zero behaviour change).

Design: import-safe, koi function kabhi raise nahi karta. Stores chhote jsonl
(in-memory read per check — call volume low, fine). Empty store = zero change.
"""

from __future__ import annotations

import json
import os
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Stores (tests monkeypatch these module attrs)
LEDGER_FILE = Path("data") / "consent_ledger.jsonl"
SUPPRESSION_FILE = Path("data") / "voice_suppression.jsonl"
RECORDINGS_DIR = Path("data") / "recordings"

DEFAULT_RETENTION_DAYS = 90  # TRAI/QoS guidance: call recordings 90 din, fir delete


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _digits(phone: str) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def _key(phone: str) -> str:
    """Compare on last 10 digits (ignore +91/91 prefixes)."""
    d = _digits(phone)
    return d[-10:] if len(d) >= 10 else d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> list[dict]:
    try:
        if not path.exists():
            return []
        out: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception:
        return []


def _append(path: Path, item: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"consent_ledger: append failed ({e})")


def _write_all(path: Path, items: list[dict]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"consent_ledger: write failed ({e})")


# --------------------------------------------------------------------------- #
# Consent records (DPDP: timestamped, source + proof, queryable per phone)
# --------------------------------------------------------------------------- #
def record_consent(
    phone: str,
    scope: str = "voice_promo",
    source: str = "",
    proof: str = "",
    client_id: str = "",
) -> dict[str, Any]:
    """Timestamped consent record. source = inquiry_form/signup/wa_optin/verbal etc.;
    proof = form-id / message-id / recording ref. Never raises."""
    k = _key(phone)
    if not k:
        return {"error": "bad_phone"}
    rec = {
        "type": "consent",
        "phone": k,
        "scope": (scope or "voice_promo")[:40],
        "source": (source or "")[:80],
        "proof": (proof or "")[:160],
        "client_id": (client_id or "")[:60],
        "at": _now(),
    }
    _append(LEDGER_FILE, rec)
    return rec


def has_consent(phone: str, scope: str = "voice_promo", max_age_days: int | None = None) -> bool:
    """True agar phone ke liye scope-consent on record hai (aur opt-out ne revoke
    nahi kiya). max_age_days set ho to itne din se purana consent invalid
    (digital consent ki validity windows ke liye)."""
    try:
        k = _key(phone)
        if not k or is_suppressed(k):
            return False
        latest: str | None = None
        for it in _read(LEDGER_FILE):
            if it.get("phone") == k and it.get("type") == "consent":
                if it.get("scope") in (scope, "all"):
                    at = str(it.get("at") or "")
                    if latest is None or at > latest:
                        latest = at
        if latest is None:
            return False
        if max_age_days is not None:
            try:
                ts = datetime.fromisoformat(latest)
                age_days = (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0
                if age_days > max_age_days:
                    return False
            except Exception:
                return False
        return True
    except Exception:
        return False


def ledger_for(phone: str, limit: int = 100) -> list[dict]:
    """DPDP access right: phone ka poora consent/opt-out history (newest first)."""
    try:
        k = _key(phone)
        if not k:
            return []
        items = [it for it in _read(LEDGER_FILE) if it.get("phone") == k]
        return items[-limit:][::-1]
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Opt-out → suppression (instant, cross-channel)
# --------------------------------------------------------------------------- #
def record_opt_out(
    phone: str, reason: str = "user_request", channel: str = "voice", call_id: str = ""
) -> dict[str, Any]:
    """Opt-out: ledger entry + voice suppression + WA suppression (cross-channel,
    best-effort). Idempotent. Never raises."""
    k = _key(phone)
    if not k:
        return {"error": "bad_phone"}
    rec = {
        "type": "opt_out",
        "phone": k,
        "reason": (reason or "user_request")[:60],
        "channel": (channel or "voice")[:20],
        "call_id": (call_id or "")[:60],
        "at": _now(),
    }
    _append(LEDGER_FILE, rec)
    if not is_suppressed(k):
        _append(
            SUPPRESSION_FILE,
            {"phone": k, "reason": rec["reason"], "channel": rec["channel"], "at": rec["at"]},
        )
    # Cross-channel propagate (TCCCPR: revocation sab commercial comms pe lagti hai).
    try:
        from app.marketing import wa_campaign_runner

        wa_campaign_runner.suppress(k, reason=f"{channel}_opt_out")
    except Exception:
        pass
    logger.info(f"🔕 opt-out recorded ***{k[-4:]} ({channel}/{rec['reason']})")
    return {"phone": k, "suppressed": True, **rec}


def is_suppressed(phone: str) -> bool:
    """True agar number opt-out suppression list par hai. Never raises."""
    try:
        k = _key(phone)
        if not k:
            return False
        return any(it.get("phone") == k for it in _read(SUPPRESSION_FILE))
    except Exception:
        return False


def opt_back_in(phone: str, source: str = "admin", proof: str = "") -> dict[str, Any]:
    """Re-consent: suppression se hatao + fresh consent record (admin/explicit only)."""
    k = _key(phone)
    if not k:
        return {"error": "bad_phone"}
    items = _read(SUPPRESSION_FILE)
    keep = [i for i in items if i.get("phone") != k]
    if len(keep) != len(items):
        _write_all(SUPPRESSION_FILE, keep)
    rec = record_consent(k, scope="all", source=source, proof=proof)
    return {"phone": k, "suppressed": False, "consent": rec}


def suppression_list(limit: int = 500) -> list[dict]:
    try:
        return _read(SUPPRESSION_FILE)[-limit:][::-1]
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Recording retention (90-din default; delete gated RECORDING_RETENTION=1)
# --------------------------------------------------------------------------- #
def retention_sweep(days: int | None = None) -> dict[str, Any]:
    """`data/recordings/` me retention se purani files: report (hamesha) +
    delete (sirf RECORDING_RETENTION=1). Dir na ho = no-op. Never raises."""
    try:
        if days is None:
            try:
                days = int(os.environ.get("RECORDING_RETENTION_DAYS", "") or DEFAULT_RETENTION_DAYS)
            except Exception:
                days = DEFAULT_RETENTION_DAYS
        delete_on = (os.environ.get("RECORDING_RETENTION", "") or "").strip() in (
            "1", "true", "yes", "on",
        )
        result: dict[str, Any] = {
            "days": days, "delete_enabled": delete_on, "expired": 0, "deleted": 0, "errors": 0,
        }
        root = RECORDINGS_DIR
        if not root.exists():
            return result
        cutoff = _time.time() - days * 86400
        for p in root.rglob("*"):
            try:
                if not p.is_file():
                    continue
                if p.stat().st_mtime < cutoff:
                    result["expired"] += 1
                    if delete_on:
                        p.unlink()
                        result["deleted"] += 1
            except Exception:
                result["errors"] += 1
        if result["deleted"]:
            logger.info(
                f"🗑️ recording retention: {result['deleted']} files deleted (>{days}d old)"
            )
        return result
    except Exception as e:
        return {"error": str(e)[:120]}


__all__ = [
    "record_consent",
    "has_consent",
    "ledger_for",
    "record_opt_out",
    "is_suppressed",
    "opt_back_in",
    "suppression_list",
    "retention_sweep",
    "LEDGER_FILE",
    "SUPPRESSION_FILE",
    "RECORDINGS_DIR",
]
