"""Reseller / Agency program — applications store + static program info.

LeadGen AI ko marketing agencies apne local-business clients ko resell karein
(ek reseller = many customers = leverage). Free audit (``/audit``) reseller ka
sales weapon, white-label tenant (``app/middleware/tenant.py``) already exists,
aur commission har month — client relationship reseller ke paas rehta hai.

Design (pattern-match ``app/platform/upi_config.py``):
- JSON store under ``data/reseller_applications.json`` — ``_read_store()`` /
  ``_write_store()`` kabhi raise nahi karte (safe defaults).
- Har public-facing function ADDITIVE + never-raise: try/except → safe default,
  exception kabhi request-path tak nahi pahunchta (no 500s).
- Lazy/defensive imports; module load kabhi fail na ho.
- Admin notify (best-effort, OPTIONAL): ``ops_alerts._ntfy`` via try/except.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_STORE = os.path.join("data", "reseller_applications.json")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


# --------------------------------------------------------------------------- #
# Store (never-raise) — pattern-match upi_config._read_store/_write_store
# --------------------------------------------------------------------------- #
def _read_store() -> dict:
    """Return ``{"seq": int, "items": [..]}``; any error = empty default."""
    try:
        if os.path.isfile(_STORE):
            with open(_STORE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("reseller read failed: %s", e)
    return {"seq": 0, "items": []}


def _write_store(data: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
        with open(_STORE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("reseller write failed: %s", e)
        return False


def _valid_email(email: str) -> bool:
    e = (email or "").strip()
    return bool(e and _EMAIL_RE.match(e))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_id(seq: int, email: str) -> str:
    """Deterministic-ish id: ``rs-<seq>-<short-hash>`` (counter + short hash)."""
    try:
        h = hashlib.sha1(f"{seq}:{(email or '').strip().lower()}".encode()).hexdigest()[:6]
    except Exception:  # pragma: no cover - defensive
        h = "000000"
    return f"rs-{seq}-{h}"


def _notify_admin(message: str) -> None:
    """Best-effort ntfy push to operator; never raises."""
    try:
        from app.platform import ops_alerts

        ops_alerts._ntfy("New reseller application", message)
    except Exception as e:  # pragma: no cover - optional
        logger.debug("reseller notify skipped: %s", e)


# --------------------------------------------------------------------------- #
# Public API — all never-raise
# --------------------------------------------------------------------------- #
def submit_application(
    name: str,
    agency: str,
    email: str,
    phone: str = "",
    city: str = "",
    clients_estimate: int = 0,
    message: str = "",
) -> dict:
    """Validate + persist a reseller application; best-effort admin notify.

    Returns ``{"ok": True, ...record}`` on success, or
    ``{"ok": False, "error": "..."}`` on validation failure / store error.
    """
    try:
        nm = (name or "").strip()
        em = (email or "").strip()
        ph = (phone or "").strip()
        if not nm:
            return {"ok": False, "error": "Naam zaroori hai."}
        if not _valid_email(em):
            return {"ok": False, "error": "Sahi email zaroori hai (name@domain)."}
        # email or phone present — email already validated above, so this passes,
        # but keep the contract explicit per spec.
        if not (em or ph):
            return {"ok": False, "error": "Email ya phone — kam se kam ek zaroori hai."}

        try:
            est = int(clients_estimate or 0)
        except Exception:
            est = 0
        if est < 0:
            est = 0

        store = _read_store()
        seq = int(store.get("seq") or 0) + 1
        record = {
            "id": _make_id(seq, em),
            "name": nm[:120],
            "agency": (agency or "").strip()[:160],
            "email": em[:160],
            "phone": ph[:40],
            "city": (city or "").strip()[:100],
            "clients_estimate": est,
            "message": (message or "").strip()[:1000],
            "status": "pending",
            "created_at": _now(),
            "decided_at": None,
        }
        store["seq"] = seq
        store["items"].append(record)
        ok = _write_store(store)
        if not ok:
            return {"ok": False, "error": "Save nahi ho paya — thodi der baad try karo."}

        _notify_admin(
            f"{record['name']} ({record['agency'] or 'agency'}) — {record['email']} "
            f"· ~{record['clients_estimate']} clients · {record['city'] or 'city n/a'}"
        )
        return {"ok": True, **record}
    except Exception as e:  # pragma: no cover - defensive top-level guard
        logger.warning("submit_application failed: %s", e)
        return {"ok": False, "error": "Kuch galat ho gaya — thodi der baad try karo."}


def list_applications(status: str | None = None) -> list[dict]:
    """All applications (newest first), optionally filtered by ``status``."""
    try:
        items = list(_read_store().get("items") or [])
        if status:
            st = str(status).strip().lower()
            items = [r for r in items if str(r.get("status") or "").lower() == st]
        items.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return items
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("list_applications failed: %s", e)
        return []


def decide(app_id: str, approve: bool, decided_by: str = "admin") -> dict:
    """Approve/reject an application; stamp ``decided_at`` + ``decided_by``.

    Returns the updated record, or ``{"ok": False, "error": "not_found"}``.
    """
    try:
        aid = (app_id or "").strip()
        if not aid:
            return {"ok": False, "error": "not_found"}
        store = _read_store()
        items = store.get("items") or []
        for rec in items:
            if str(rec.get("id") or "") == aid:
                rec["status"] = "approved" if approve else "rejected"
                rec["decided_at"] = _now()
                rec["decided_by"] = (decided_by or "admin")[:80]
                _write_store(store)
                return rec
        return {"ok": False, "error": "not_found"}
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("decide failed: %s", e)
        return {"ok": False, "error": "not_found"}


def program_info() -> dict:
    """STATIC program description — commission tiers + what's included.

    No prices invented beyond commission % (those are program terms, generic).
    """
    return {
        "name": "LeadGen AI Reseller / Agency Program",
        "tagline_hi": "Apni agency se LeadGen AI becho — har local business pe recurring commission.",
        "tagline_en": "Resell LeadGen AI to your local-business clients and earn recurring commission — you keep the relationship.",
        "blurb_hi": (
            "Free audit tool (/audit) aapka sales weapon hai — prospect ko uska "
            "marketing gap dikhao, white-label LeadGen unke naam pe deploy karo "
            "(done-for-you onboarding hamari FDE team se), aur har month commission kamao. "
            "Client relationship hamesha aapke paas rehta hai."
        ),
        "blurb_en": (
            "The free audit tool is your sales weapon — show prospects their marketing "
            "gap, deploy white-label LeadGen under your brand (done-for-you onboarding "
            "by our FDE team), and earn monthly commission. You always own the client "
            "relationship."
        ),
        "commission_tiers": [
            {
                "name": "Partner",
                "active_clients": "1-5 active clients",
                "rate_pct": 20,
                "desc_hi": "Shuruaat — pehle 5 clients tak 20% recurring commission.",
                "desc_en": "Get started — 20% recurring commission up to your first 5 clients.",
            },
            {
                "name": "Growth Partner",
                "active_clients": "6-15 active clients",
                "rate_pct": 25,
                "desc_hi": "Scale karne par 25% recurring — jitne zyada clients, utna zyada rate.",
                "desc_en": "Scale up to 25% recurring as your active-client base grows.",
            },
            {
                "name": "Elite Partner",
                "active_clients": "16+ active clients",
                "rate_pct": 30,
                "desc_hi": "Top tier — 30% recurring commission + priority FDE support.",
                "desc_en": "Top tier — 30% recurring commission plus priority FDE support.",
            },
        ],
        "whats_included": [
            {
                "title_hi": "White-label platform",
                "title_en": "White-label platform",
                "desc_hi": "Aapke brand/subdomain pe — clients ko LeadGen ka naam nahi dikhta.",
                "desc_en": "Runs on your brand/subdomain — clients see you, not LeadGen.",
            },
            {
                "title_hi": "Free audit = sales tool",
                "title_en": "Free audit = sales tool",
                "desc_hi": "/audit se prospect ka gap dikhao — meeting book karna aasaan.",
                "desc_en": "Use /audit to show each prospect their gap and book meetings faster.",
            },
            {
                "title_hi": "Done-for-you onboarding (FDE)",
                "title_en": "Done-for-you onboarding (FDE)",
                "desc_hi": "Hamari Forward-Deployed team client ka poora stack set karti hai.",
                "desc_en": "Our Forward-Deployed Engineer team stands up each client's full stack.",
            },
            {
                "title_hi": "Monthly payouts",
                "title_en": "Monthly payouts",
                "desc_hi": "Har month commission — transparent reporting.",
                "desc_en": "Recurring commission paid out monthly with transparent reporting.",
            },
        ],
        "note_hi": "Commission % program terms hain. Pricing client plans pe depend karti hai (/pricing).",
        "note_en": "Commission % are program terms. Client pricing follows standard plans (/pricing).",
    }


__all__ = [
    "submit_application",
    "list_applications",
    "decide",
    "program_info",
]
