"""
dpdp.py — DPDP Act 2023 data-principal rights: discovery + export + erasure.
=============================================================================

/privacy page Access/Correction/Erasure rights PROMISE karta hai — yeh module
woh promise REAL banata hai (legal gap close):

  - find_subject(phone/email)    -> kaunse stores me data hai (masked preview)
  - export_subject(phone/email)  -> Right to Access: full JSON dump (admin path)
  - erase_subject(phone/email)   -> Right to Erasure: JSONL atomic rewrite +
                                    DB Lead anonymize (dry_run=True DEFAULT)
  - record_request(...)          -> public intake (data/dpdp_requests.jsonl)
  - audit log                    -> data/dpdp_audit.jsonl (subject = sha256
                                    HASH only — kabhi plaintext nahi)

SAFETY (destructive operation hai):
  - dry_run=True default — pehle dekho kya hatne wala hai.
  - Rewrite se PEHLE har touched file ki `.bak_dpdp_<ts>` copy (same dir).
  - Atomic rewrite: tmp file + os.replace (minisite_builder._rewrite_jsonl
    pattern) — half-written file kabhi nahi.
  - Raw lines preserve hote hain (re-serialize NAHI) — jo line parse nahi hui
    woh untouched rehti hai; jo FILE read nahi hui woh skip+report hoti hai.
  - DB Lead rows DELETE nahi hote — anonymize (phone/email/name -> ERASED),
    row billing/audit integrity ke liye rehti hai. Core UPDATE (validators
    bypass — 'ERASED' phone-format validator pass nahi karta, karna bhi nahi).
  - KABHI kisi scheduler se auto-run nahi hota — sirf admin API se.

Sab functions never-raise (error dict lautate). Free stack, pure stdlib +
lazy sqlalchemy import (DB down = graceful skip).

KNOWN LIMITS (privacy page ke liye honest):
  - Qdrant KB vectors (client:<id> namespaces) — embedded text erase nahi hota
    yahan se (KB per-client business docs hote hain, lead-PII rare).
  - Backups (pg_dump 30d, data/ tarballs, .bak_dpdp_ files khud) me purana
    data retention-window tak rehta hai.
  - Email server (Hostinger IMAP/SMTP sent-mail) is module ke scope ke bahar.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# --------------------------------------------------------------------------- #
# Stores (module-level — tests monkeypatch karte hain)
# Filenames GREP-verified from owning modules (guess nahi):
#   public_site._INQUIRIES_FILE, prospector._PROSPECTS_FILE,
#   conversion._CHATS_FILE, reply_agent._DRAFTS_FILE, cadence._LEADS,
#   dialer_log._DIALER_LOGS, customer_crm._DRAFTS_PATH, crm_lite._CRM_DIR
# --------------------------------------------------------------------------- #
_STORES: dict[str, str] = {
    "inquiries": os.path.join("data", "inquiries.jsonl"),
    "prospects": os.path.join("data", "prospects.jsonl"),
    "widget_chats": os.path.join("data", "widget_chats.jsonl"),
    "reply_drafts": os.path.join("data", "reply_drafts.jsonl"),
    "cadence_leads": os.path.join("data", "cadence_leads.jsonl"),
    "dialer_logs": os.path.join("data", "dialer_logs.jsonl"),
    "customer_wish_drafts": os.path.join("data", "customer_wish_drafts.jsonl"),
}
_CRM_DIR = os.path.join("data", "crm")  # per-client end-customer CRM (crm_lite)


def _AUDIT_FILE() -> str:
    """DPDP audit log — resolved per call, never captured at import.

    The function name keeps the allowlist symbol stable. Subject hashes only;
    never plaintext PII.
    """
    from pathlib import Path

    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="compliance.dpdp_audit",
            legacy_path=Path("data") / "dpdp_audit.jsonl",
            target_segments=("compliance", "dpdp_audit.jsonl"),
        )
    )


def _REQUESTS_FILE() -> str:
    """DPDP request intake — sibling of the audit log under the same store id.

    One manifest row covers both files; they stay two resolvers so a cutover
    cannot collapse requests into the audit path. The requests file lives
    beside the audit target (`compliance/dpdp_requests.jsonl`).
    """
    from pathlib import Path

    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="compliance.dpdp_audit",
            legacy_path=Path("data") / "dpdp_requests.jsonl",
            target_segments=("compliance", "dpdp_requests.jsonl"),
        )
    )


REQUEST_TYPES = ("access", "erasure", "correction")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Subject normalization + hashing
# --------------------------------------------------------------------------- #
def _norm_phone(raw: Any) -> str:
    """Kisi bhi format ka phone -> last-10 digits ('' = unusable)."""
    digits = "".join(c for c in str(raw or "") if c.isdigit())
    return digits[-10:] if len(digits) >= 10 else ""


def _norm_email(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    return s if ("@" in s and "." in s.split("@")[-1]) else ""


def subject_hash(phone: Any = None, email: Any = None) -> str:
    """sha256 of normalized subject — audit log me YAHI jaata hai (plaintext kabhi nahi)."""
    key = f"{_norm_phone(phone)}|{_norm_email(email)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _mask_phone(p: str) -> str:
    p = str(p or "")
    return (p[:2] + "X" * max(0, len(p) - 4) + p[-2:]) if len(p) >= 6 else "XXXX"


def _mask_email(e: str) -> str:
    e = str(e or "")
    if "@" not in e:
        return "***"
    local, _, dom = e.partition("@")
    return (local[:1] + "***@" + dom) if local else ("***@" + dom)


# --------------------------------------------------------------------------- #
# Matching — record ki saari string/number values me subject dhundo
# --------------------------------------------------------------------------- #
def _values_of(rec: Any, depth: int = 0) -> list[str]:
    """Dict/list ki saari leaf string-values (max depth 2 — nested extras bhi)."""
    out: list[str] = []
    if depth > 2:
        return out
    try:
        if isinstance(rec, dict):
            for v in rec.values():
                out.extend(_values_of(v, depth + 1))
        elif isinstance(rec, list | tuple):
            for v in rec:
                out.extend(_values_of(v, depth + 1))
        elif isinstance(rec, str | int | float) and not isinstance(rec, bool):
            out.append(str(rec))
    except Exception:
        pass
    return out


def _match(rec: dict[str, Any], phone10: str, email: str) -> bool:
    """Record subject ka hai? Phone = digit-run match (format-proof: +91/0/spaces
    sab pakde, chat-text ke andar likha number bhi). Email = substring (lower)."""
    if not isinstance(rec, dict) or not (phone10 or email):
        return False
    try:
        for val in _values_of(rec):
            if email and email in val.lower():
                return True
            if phone10:
                digits = "".join(c for c in val if c.isdigit())
                if len(digits) >= 10 and phone10 in digits:
                    return True
    except Exception:
        pass
    return False


# Free-text me likha 10+ digit phone-run (spaces/dashes allowed) bhi mask ho
_NUM_RUN_RE = re.compile(r"\d(?:[\s\-]?\d){9,}")


def _scrub_numbers(s: str) -> str:
    """Kisi bhi text-value ke andar ka 10+ digit number-run mask karo."""
    try:
        return _NUM_RUN_RE.sub("XXXXXXXXXX", s)
    except Exception:
        return s


def _mask_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Preview-safe copy — phone/email-jaisi values mask, free-text ke number-run
    scrub, lambi text truncate."""
    out: dict[str, Any] = {}
    try:
        for k, v in rec.items():
            kl = str(k).lower()
            if not isinstance(v, str | int | float) or isinstance(v, bool):
                continue
            s = str(v)
            if "email" in kl or ("@" in s and "." in s and len(s) < 80):
                out[k] = _mask_email(s) if "@" in s else _scrub_numbers(s[:60])
            elif any(t in kl for t in ("phone", "mobile", "whatsapp", "contact", "from", "to")):
                out[k] = _mask_phone(s)
            else:
                out[k] = _scrub_numbers(s[:60])
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------- #
# JSONL plumbing — raw-line preserve + atomic rewrite + .bak
# --------------------------------------------------------------------------- #
def _read_raw_lines(path: str) -> list[str] | None:
    """File ki raw lines (None = file read hi nahi hui -> store SKIP+report).
    Missing file = [] (kuch nahi hai = fine)."""
    try:
        if not os.path.exists(path):
            return []
        if not os.path.isfile(path):  # directory/odd path = SKIP, "empty" nahi
            logger.warning(f"[dpdp] store path is not a file, skipping: {path}")
            return None
        with open(path, encoding="utf-8") as f:
            return f.readlines()
    except Exception as e:
        logger.warning(f"[dpdp] store unreadable, skipping: {path}: {e}")
        return None


def _atomic_write_lines(path: str, lines: list[str]) -> None:
    """tmp + os.replace (minisite_builder._rewrite_jsonl pattern)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp_dpdp"
    with open(tmp, "w", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln if ln.endswith("\n") else ln + "\n")
    os.replace(tmp, path)


def _iter_stores() -> list[tuple[str, str]]:
    """(store_name, path) — fixed stores + data/crm/<client_id>.jsonl sab."""
    pairs = list(_STORES.items())
    try:
        for p in sorted(glob.glob(os.path.join(_CRM_DIR, "*.jsonl"))):
            pairs.append((f"crm/{os.path.basename(p)}", p))
    except Exception:
        pass
    return pairs


# --------------------------------------------------------------------------- #
# Audit log — subject sirf HASH (DPDP audit khud PII leak na kare)
# --------------------------------------------------------------------------- #
def _audit(
    action: str, phone: Any, email: Any, stores: list[str], actor: str, **extra: Any
) -> None:
    try:
        rec = {
            "ts": _now(),
            "action": action,
            "subject_hash": subject_hash(phone, email),
            "stores_touched": stores,
            "actor": (actor or "admin")[:80],
        }
        rec.update({k: v for k, v in extra.items() if v is not None})
        # Resolver called at each site rather than bound to a local. The local
        # was correct behaviour and wrong evidence: `runtime_data_scan`
        # attributes a finding to the expression it sees, so `open(audit_path)`
        # reports the bare name `audit_path` and the allowlist entry declaring
        # `_AUDIT_FILE` stopped binding — which turned main red with
        # "STALE - no live finding at app/platform/dpdp.py:_AUDIT_FILE".
        os.makedirs(os.path.dirname(_AUDIT_FILE()) or ".", exist_ok=True)
        with open(_AUDIT_FILE(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[dpdp] audit write failed: {e}")


# --------------------------------------------------------------------------- #
# 1) DISCOVERY (sync file core — DB-wala async find_subject neeche)
# --------------------------------------------------------------------------- #
def scan_stores(phone: Any = None, email: Any = None, preview_per_store: int = 3) -> dict[str, Any]:
    """Saare JSONL stores scan — {store: count} + masked previews. Never raises."""
    phone10, em = _norm_phone(phone), _norm_email(email)
    if not (phone10 or em):
        return {"ok": False, "error": "valid phone (10-digit) ya email do."}
    counts: dict[str, int] = {}
    previews: dict[str, list[dict[str, Any]]] = {}
    skipped: list[str] = []
    for name, path in _iter_stores():
        lines = _read_raw_lines(path)
        if lines is None:
            skipped.append(name)
            continue
        n = 0
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except Exception:
                continue  # corrupt line — match nahi, erase me bhi untouched
            if isinstance(rec, dict) and _match(rec, phone10, em):
                n += 1
                if len(previews.setdefault(name, [])) < preview_per_store:
                    previews[name].append(_mask_record(rec))
        if n:
            counts[name] = n
    return {
        "ok": True,
        "subject_hash": subject_hash(phone, email),
        "stores": counts,
        "total_records": sum(counts.values()),
        "preview": previews,
        "skipped_stores": skipped,
    }


async def _db_lead_query(phone10: str, em: str) -> tuple[list[dict[str, Any]] | None, str]:
    """DB Lead rows for subject (best-effort). (rows|None, note)."""
    try:
        from sqlalchemy import or_, select

        from app.models.base import get_async_session
        from app.models.lead import Lead
    except Exception as e:
        return None, f"db imports unavailable: {str(e)[:80]}"
    try:
        conds = []
        if phone10:
            conds.append(Lead.phone.like(f"%{phone10}"))
        if em:
            conds.append(Lead.email == em)
        async with get_async_session() as session:  # type: ignore
            res = await session.execute(select(Lead).where(or_(*conds)).limit(200))
            rows = []
            for lead in res.scalars().all():
                try:
                    rows.append(
                        lead.to_dict() if hasattr(lead, "to_dict") else {"id": str(lead.id)}
                    )
                except Exception:
                    continue
            return rows, "ok"
    except Exception as e:
        return None, f"db unavailable: {str(e)[:80]}"


async def find_subject(
    phone: Any = None, email: Any = None, include_db: bool = True, actor: str = "admin"
) -> dict[str, Any]:
    """Discovery: files + (best-effort) DB Lead count. Masked — admin overview."""
    out = scan_stores(phone, email)
    if not out.get("ok"):
        return out
    if include_db:
        rows, note = await _db_lead_query(_norm_phone(phone), _norm_email(email))
        if rows is None:
            out["db_leads"] = {"available": False, "note": note}
        else:
            out["db_leads"] = {"available": True, "count": len(rows)}
            if rows:
                out["total_records"] = out["total_records"] + len(rows)
    _audit("find", phone, email, list(out.get("stores", {}).keys()), actor)
    return out


# --------------------------------------------------------------------------- #
# 2) EXPORT — Right to Access (full, unmasked — ADMIN-only route pe)
# --------------------------------------------------------------------------- #
async def export_subject(
    phone: Any = None, email: Any = None, include_db: bool = True, actor: str = "admin"
) -> dict[str, Any]:
    """Subject ka POORA data ek JSON me (DPDP Right to Access). Never raises."""
    phone10, em = _norm_phone(phone), _norm_email(email)
    if not (phone10 or em):
        return {"ok": False, "error": "valid phone (10-digit) ya email do."}
    records: dict[str, list[dict[str, Any]]] = {}
    skipped: list[str] = []
    for name, path in _iter_stores():
        lines = _read_raw_lines(path)
        if lines is None:
            skipped.append(name)
            continue
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            if isinstance(rec, dict) and _match(rec, phone10, em):
                records.setdefault(name, []).append(rec)
    out: dict[str, Any] = {
        "ok": True,
        "generated_at": _now(),
        "subject": {"phone": phone10 or None, "email": em or None},
        "records": records,
        "total_records": sum(len(v) for v in records.values()),
        "skipped_stores": skipped,
        "note": (
            "DPDP Act 2023 Right-to-Access export. Backups/email-server copies "
            "is export me shamil nahi (retention window tak rehte hain)."
        ),
    }
    if include_db:
        rows, note = await _db_lead_query(phone10, em)
        if rows is None:
            out["db_leads"] = {"available": False, "note": note}
        else:
            out["db_leads"] = {"available": True, "rows": rows}
            out["total_records"] += len(rows)
    _audit("export", phone, email, list(records.keys()), actor, records=out["total_records"])
    return out


# --------------------------------------------------------------------------- #
# 3) ERASURE — Right to Erasure (dry_run DEFAULT; atomic + .bak)
# --------------------------------------------------------------------------- #
def _erase_file(path: str, phone10: str, em: str, dry_run: bool) -> dict[str, Any]:
    """Ek store: matching records hatao (raw non-matching lines AS-IS preserve).
    Real run = pehle .bak_dpdp_<ts> copy, phir tmp+os.replace atomic rewrite."""
    lines = _read_raw_lines(path)
    if lines is None:
        return {"skipped": True, "removed": 0}
    keep: list[str] = []
    removed = 0
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        try:
            rec = json.loads(s)
        except Exception:
            keep.append(ln)  # un-parseable line KABHI mat chhedo
            continue
        if isinstance(rec, dict) and _match(rec, phone10, em):
            removed += 1
        else:
            keep.append(ln)
    if removed == 0 or dry_run:
        return {"skipped": False, "removed": removed, "dry_run": dry_run}
    try:
        bak = f"{path}.bak_dpdp_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        shutil.copy2(path, bak)
        _atomic_write_lines(path, keep)
        return {
            "skipped": False,
            "removed": removed,
            "dry_run": False,
            "backup": os.path.basename(bak),
        }
    except Exception as e:
        logger.warning(f"[dpdp] erase rewrite failed for {path}: {e}")
        return {"skipped": True, "removed": 0, "error": str(e)[:120]}


async def _db_anonymize(phone10: str, em: str, dry_run: bool) -> dict[str, Any]:
    """DB Lead rows anonymize — phone/email/name -> ERASED, row REHTI hai
    (billing/audit integrity). Core UPDATE = validators bypass. Best-effort."""
    rows, note = await _db_lead_query(phone10, em)
    if rows is None:
        return {"available": False, "note": note, "anonymized": 0}
    if dry_run or not rows:
        return {"available": True, "would_anonymize" if dry_run else "anonymized": len(rows)}
    try:
        from sqlalchemy import or_, update

        from app.models.base import get_async_session
        from app.models.lead import Lead

        conds = []
        if phone10:
            conds.append(Lead.phone.like(f"%{phone10}"))
        if em:
            conds.append(Lead.email == em)
        async with get_async_session() as session:  # type: ignore
            await session.execute(
                update(Lead)
                .where(or_(*conds))
                .values(
                    phone="ERASED",
                    email=None,
                    contact_name="ERASED",
                    notes="[ERASED — DPDP erasure request]",
                )
            )
            await session.commit()
        return {"available": True, "anonymized": len(rows)}
    except Exception as e:
        return {"available": False, "note": f"db anonymize failed: {str(e)[:80]}", "anonymized": 0}


async def erase_subject(
    phone: Any = None,
    email: Any = None,
    dry_run: bool = True,
    include_db: bool = True,
    actor: str = "admin",
) -> dict[str, Any]:
    """Right to Erasure. dry_run=True (DEFAULT) = sirf dikhao kya hatega.
    Real run: har touched jsonl ki .bak copy + atomic rewrite; DB anonymize.
    KABHI scheduler se mat chalana — sirf admin-confirmed API call."""
    phone10, em = _norm_phone(phone), _norm_email(email)
    if not (phone10 or em):
        return {"ok": False, "error": "valid phone (10-digit) ya email do."}
    results: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []
    touched: list[str] = []
    total = 0
    for name, path in _iter_stores():
        res = _erase_file(path, phone10, em, dry_run)
        if res.get("skipped"):
            skipped.append(name)
            continue
        if res.get("removed"):
            results[name] = res
            touched.append(name)
            total += int(res["removed"])
    out: dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "subject_hash": subject_hash(phone, email),
        "stores": results,
        "total_removed" if not dry_run else "total_would_remove": total,
        "skipped_stores": skipped,
        "note": (
            "Backups (pg_dump/tarballs/.bak_dpdp_) + Qdrant KB vectors + email-server "
            "copies retention window tak rehte hain — privacy policy me disclosed."
        ),
    }
    if include_db:
        out["db_leads"] = await _db_anonymize(phone10, em, dry_run)
    _audit(
        "erase_dry_run" if dry_run else "erase",
        phone,
        email,
        touched,
        actor,
        removed_total=total,
    )
    return out


# --------------------------------------------------------------------------- #
# 4) REQUEST INTAKE (public) — 30-din processing promise
# --------------------------------------------------------------------------- #
def record_request(
    phone: Any = None, email: Any = None, req_type: str = "access", note: str = ""
) -> dict[str, Any]:
    """Data-principal ki request store karo (status=pending). Never raises.
    NOTE: yahan contact PLAINTEXT store hota hai — process karne ke liye
    zaroori hai (audit log me sirf hash jaata hai)."""
    phone10, em = _norm_phone(phone), _norm_email(email)
    if not (phone10 or em):
        return {"ok": False, "error": "valid phone (10-digit) ya email zaroori hai."}
    t = (req_type or "access").strip().lower()
    if t not in REQUEST_TYPES:
        t = "access"
    rec = {
        "id": uuid.uuid4().hex[:10],
        "ts": _now(),
        "type": t,
        "phone": phone10,
        "email": em,
        "note": str(note or "")[:500],
        "status": "pending",
    }
    try:
        os.makedirs(os.path.dirname(_REQUESTS_FILE()) or ".", exist_ok=True)
        with open(_REQUESTS_FILE(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[dpdp] request write failed: {e}")
        return {"ok": False, "error": "request save nahi hui — baad me try karo."}
    _audit("request_" + t, phone10, em, [], "public")
    return {"ok": True, "request_id": rec["id"], "type": t}


def list_requests(status: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    """Saved requests (newest first). Optional status filter. Never raises."""
    rows: list[dict[str, Any]] = []
    try:
        lines = _read_raw_lines(_REQUESTS_FILE())
    except Exception as e:
        logger.warning(f"[dpdp] requests authority unresolvable: {e}")
        return []
    for ln in lines or []:
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
            if isinstance(rec, dict):
                rows.append(rec)
        except Exception:
            continue
    st = (status or "").strip().lower()
    if st:
        rows = [r for r in rows if str(r.get("status", "")).lower() == st]
    return list(reversed(rows))[: max(1, min(int(limit or 200), 1000))]


def mark_request_done(request_id: str, actor: str = "admin") -> dict[str, Any]:
    """Request status pending -> done (atomic rewrite). Never raises."""
    rid = str(request_id or "").strip()
    if not rid:
        return {"ok": False, "error": "request_id chahiye."}
    # Probe the authority first so an unresolvable root fails closed rather than
    # raising mid-rewrite. The result is deliberately DISCARDED: passing it to the
    # I/O calls below would make `runtime_data_scan` attribute those accesses to
    # the local name instead of `_REQUESTS_FILE`, which is what unbound the
    # allowlist declaration and turned main red.
    try:
        _REQUESTS_FILE()
    except Exception as e:
        logger.warning(f"[dpdp] requests authority unresolvable: {e}")
        return {"ok": False, "error": "requests store unreadable."}
    lines = _read_raw_lines(_REQUESTS_FILE())
    if lines is None:
        return {"ok": False, "error": "requests store unreadable."}
    out_lines: list[str] = []
    found = False
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        try:
            rec = json.loads(s)
        except Exception:
            out_lines.append(ln)
            continue
        if isinstance(rec, dict) and rec.get("id") == rid and rec.get("status") != "done":
            rec["status"] = "done"
            rec["done_at"] = _now()
            rec["done_by"] = (actor or "admin")[:80]
            out_lines.append(json.dumps(rec, ensure_ascii=False))
            found = True
        else:
            out_lines.append(ln)
    if not found:
        return {"ok": False, "error": f"request {rid} nahi mili (ya already done)."}
    try:
        _atomic_write_lines(_REQUESTS_FILE(), out_lines)
    except Exception as e:
        logger.warning(f"[dpdp] request update failed: {e}")
        return {"ok": False, "error": "update save nahi hua."}
    return {"ok": True, "request_id": rid, "status": "done"}


__all__ = [
    "scan_stores",
    "find_subject",
    "export_subject",
    "erase_subject",
    "record_request",
    "list_requests",
    "mark_request_done",
    "subject_hash",
    "REQUEST_TYPES",
]
