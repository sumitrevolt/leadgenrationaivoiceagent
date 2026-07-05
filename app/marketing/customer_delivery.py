"""Customer value-delivery — value-first, delivery-guaranteed (2026-07-05).

WHY: a paying customer (jiya makeover, ₹1,999) was GHOSTED — the system BUILT her
value (live mini-site, content pack, brand kit) but delivered NONE of it because
onboarding asked her to "describe your business" first and her reply was never
captured (silent single-thread failure). Council decision (docs/
CUSTOMER_DELIVERY_AUTOMATION_2026_07_05.md): on `paid`, DELIVER value first — don't
ask, don't wait — and never let a paid customer sit silently undelivered.

This module is the P0 delivery guarantee:
  - `deliver_client_value(client)` — WhatsApp the live mini-site link + what they
    got. GATED `AUTO_DELIVER_VALUE` (default OFF) so real customer sends are
    reviewed before going live; `force=True` for an operator-triggered single send.
  - `find_undelivered_paid_clients()` — read-only dead-man detector: paid+active
    clients not yet delivered (powers the founder alert + operator surface).
  - `run_delivery_sweep()` — the dead-man sweep (fail-LOUD: records stuck customers,
    never a silent swallow).

Delivery state lives on the client record: `delivery_state` in
{paid, assets_built, delivered, acknowledged} + `delivered_at`. "delivered" is set
ONLY after an actual send (never a backend flag like setup_done).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PAID_PLACEHOLDER_PLANS = {"", "free", "trial", "none", "pending"}
_STUCK_LOG = os.path.join("data", "delivery_stuck.jsonl")


def _flag_on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _is_self_brand(client: dict[str, Any]) -> bool:
    """LeadGen AI ka apna self-brand record (delivery target NAHI — ye company khud hai).
    Markers mirror auto_content._ensure_self_client."""
    if str(client.get("id") or "") == "leadgenai-self":
        return True
    if str(client.get("niche") or "").strip().lower() == "ai_marketing":
        return True
    return str(client.get("business_name") or "").strip().lower() in ("leadgen ai", "leadsgenai")


def is_paid_client(client: dict[str, Any]) -> bool:
    """Active client on a real (non-free/trial) plan = someone who paid. Self-brand
    (LeadGen AI apna record) delivery target nahi — exclude."""
    if not isinstance(client, dict):
        return False
    if _is_self_brand(client):
        return False
    if str(client.get("status") or "").lower() != "active":
        return False
    plan = str(client.get("plan") or "").strip().lower()
    return bool(plan) and plan not in _PAID_PLACEHOLDER_PLANS


def mini_site_url(client: dict[str, Any]) -> str:
    """Live mini-site URL from the client's slug, or "" if none. Pure."""
    slug = str((client or {}).get("slug") or "").strip()
    if not slug:
        return ""
    try:
        from app.config import settings

        base = str(getattr(settings, "public_base_url", "") or "https://leadsgenai.in").rstrip("/")
    except Exception:
        base = "https://leadsgenai.in"
    return f"{base}/b/{slug}"


def is_delivered(client: dict[str, Any]) -> bool:
    """True once value has actually been delivered (received-side, not a backend flag)."""
    return str((client or {}).get("delivery_state") or "").lower() in ("delivered", "acknowledged")


def build_delivery_message(client: dict[str, Any]) -> str:
    """The WhatsApp value-delivery text: live mini-site link + what they got + next
    step. Pure (no side effects) so it is unit-testable. Value-first — no info-ask."""
    biz = str((client or {}).get("business_name") or "aapka business").strip() or "aapka business"
    url = mini_site_url(client)
    lines = [
        f"Namaste! 🎉 {biz} ke liye aapka LeadGen AI setup taiyaar hai —",
    ]
    if url:
        lines.append(f"👉 Aapki LIVE business site: {url}")
        lines.append("(Ye link customers ko WhatsApp/Instagram pe share karein — enquiry seedhe aapke phone pe.)")
    lines.append("📸 Aapke liye ready-to-post content bhi ban chuka hai — har hafte naya milega.")
    lines.append("Koi badlaav chahiye (services/area/photos)? Bas isi message ka reply kar dijiye — main update kar dungi. 🙏")
    return "\n".join(lines)


def find_undelivered_paid_clients() -> list[dict[str, Any]]:
    """Read-only dead-man detector: paid+active clients NOT yet delivered.
    Never raises — returns [] on any error."""
    out: list[dict[str, Any]] = []
    try:
        from app.marketing import clients_store

        for c in clients_store.list_clients(status="active"):
            if is_paid_client(c) and not is_delivered(c):
                out.append(c)
    except Exception as exc:
        logger.warning("find_undelivered_paid_clients err: %s", exc)
    return out


def _record_stuck(client: dict[str, Any], reason: str) -> None:
    """Fail-LOUD: append a stuck-customer record (NOT a silent debug swallow) so a
    ghosted paying customer is always visible + alertable. Never raises."""
    try:
        os.makedirs("data", exist_ok=True)
        rec = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "client_id": str(client.get("id") or ""),
            "business_name": client.get("business_name"),
            "phone": client.get("phone"),
            "plan": client.get("plan"),
            "reason": reason,
        }
        with open(_STUCK_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("delivery _record_stuck err: %s", exc)
    logger.warning(
        "🚨 PAID customer undelivered: %s (%s) — %s",
        client.get("business_name"),
        client.get("id"),
        reason,
    )


async def deliver_client_value(client: dict[str, Any], force: bool = False) -> dict[str, Any]:
    """Value-first delivery: WhatsApp the live mini-site link + content note to the
    paying customer, then mark delivery_state='delivered'. GATED AUTO_DELIVER_VALUE
    (default OFF) unless force=True (operator single-send). Never raises; fail-LOUD."""
    res: dict[str, Any] = {"delivered": False, "client_id": str((client or {}).get("id") or "")}
    if not is_paid_client(client):
        res["skipped"] = "not_paid"
        return res
    if is_delivered(client):
        res["skipped"] = "already_delivered"
        res["delivered"] = True
        return res
    if not (force or _flag_on("AUTO_DELIVER_VALUE")):
        _record_stuck(client, "auto_delivery_off")
        res["skipped"] = "AUTO_DELIVER_VALUE off"
        return res
    phone = str(client.get("phone") or "").strip()
    if not phone:
        _record_stuck(client, "no_phone")
        res["skipped"] = "no_phone"
        return res
    try:
        from app.integrations.whatsapp import get_whatsapp_sender

        sender = get_whatsapp_sender()
        sent = await sender.send_text_message(phone, build_delivery_message(client))
        ok = bool(sent) and not (isinstance(sent, dict) and sent.get("error"))
    except Exception as exc:
        _record_stuck(client, f"send_error:{type(exc).__name__}")
        res["error"] = str(exc)
        return res
    if not ok:
        _record_stuck(client, "send_failed")
        res["error"] = "send_failed"
        return res
    try:
        from app.marketing import clients_store

        clients_store.update_client(
            str(client.get("id") or ""),
            delivery_state="delivered",
            delivered_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
    except Exception as exc:
        logger.warning("deliver_client_value state-update err: %s", exc)
    res["delivered"] = True
    return res


async def run_delivery_sweep(limit: int = 20) -> dict[str, Any]:
    """Dead-man sweep: find paid customers not yet delivered → deliver (if
    AUTO_DELIVER_VALUE) else record-loud for founder review. Returns a summary.
    Never raises. Registered for the scheduler (staff 'onboard'/dedicated job)."""
    res: dict[str, Any] = {"undelivered": 0, "delivered": 0, "stuck": 0}
    try:
        pending = find_undelivered_paid_clients()
        res["undelivered"] = len(pending)
        auto = _flag_on("AUTO_DELIVER_VALUE")
        for c in pending[: max(1, limit)]:
            if auto:
                r = await deliver_client_value(c)
                if r.get("delivered"):
                    res["delivered"] += 1
                else:
                    res["stuck"] += 1
            else:
                _record_stuck(c, "sweep_auto_off")
                res["stuck"] += 1
    except Exception as exc:
        logger.warning("run_delivery_sweep err: %s", exc)
        res["error"] = str(exc)
    return res


__all__ = [
    "is_paid_client",
    "mini_site_url",
    "is_delivered",
    "build_delivery_message",
    "find_undelivered_paid_clients",
    "deliver_client_value",
    "run_delivery_sweep",
]
