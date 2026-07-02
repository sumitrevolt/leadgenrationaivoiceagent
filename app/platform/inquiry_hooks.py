"""Shared inquiry funnel hooks — har entry path pe same downstream automation.

submit_inquiry, widget-chat, lead-in webhook, WhatsApp Flow sab yahi reuse karte
hain taaki journeys/cadence/sales/callback/webhooks miss na hon.
Never raises.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Fire-and-forget task refs (GC-safe)
_BG_TASKS: set[asyncio.Task] = set()


def _spawn(coro: Any) -> None:
    try:
        task = asyncio.create_task(coro)
        _BG_TASKS.add(task)
        task.add_done_callback(_BG_TASKS.discard)
    except Exception as e:
        logger.debug(f"[inquiry_hooks] spawn skip: {e}")


async def run_after_inquiry(
    rec: dict[str, Any],
    *,
    mini_client_id: str | None = None,
    utm_source: str | None = None,
    lead_id: str | None = None,
) -> None:
    """Post-store automation for any inquiry record. Storage caller ne pehle hi kar diya."""
    cid = (mini_client_id or rec.get("client_id") or "").strip() or None
    lid = lead_id or rec.get("lead_id")

    # BANT auto-qualify (sales_qualify) — pure-Python, never-raise. Har inbound lead ko
    # A-D grade + Hinglish next-action turant (rep ko speed-to-lead priority milti).
    try:
        from app.platform import sales_qualify as _bant

        _bq = _bant.bant_score(rec)
        rec["bant"] = _bq
        rec["bant_grade"] = _bq.get("grade")
        try:
            from app.platform.team import log_event as _le

            _le(
                "neha",
                "lead_qualified",
                f"{rec.get('business_name') or rec.get('name') or 'Lead'} → BANT "
                f"{_bq.get('grade')} ({_bq.get('total')}/100) · {_bq.get('action')}",
                meta={
                    "lead_id": lid,
                    "grade": _bq.get("grade"),
                    "total": _bq.get("total"),
                    "source": rec.get("source"),
                },
                status="ok",
            )
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"[inquiry_hooks] bant skip: {e}")

    try:
        from app.platform.lead_alerts import notify_new_lead_bg

        notify_new_lead_bg(rec)
    except Exception:
        pass

    if cid:
        try:
            from app.platform import customer_webhooks as _cw

            payload = {
                "client_id": cid,
                "lead_id": lid,
                "business_name": rec.get("business_name"),
                "phone": rec.get("phone"),
                "city": rec.get("city"),
                "niche": rec.get("niche"),
                "source_slug": rec.get("source_slug"),
                "source": rec.get("source"),
                "created_at": rec.get("at"),
            }
            _spawn(_cw.emit(cid, "lead.created", payload))
        except Exception:
            pass

    try:
        from app.platform.team import log_event

        if rec.get("source_slug"):
            log_event(
                "rohan",
                "mini_site_inquiry",
                f"{rec.get('business_name')} (/b/{rec['source_slug']}) - {rec.get('phone')}"
                + (f" · {rec.get('preferred_time')}" if rec.get("preferred_time") else ""),
                meta={
                    "lead_id": lid,
                    "source_slug": rec.get("source_slug"),
                    "client_id": cid,
                    "preferred_time": rec.get("preferred_time"),
                    "via": rec.get("source") or "mini_site",
                },
            )
        else:
            log_event(
                "rohan",
                "inquiry_received",
                f"{rec.get('business_name')} ({rec.get('niche') or 'unknown'}) - {rec.get('phone')}",
                meta={
                    "lead_id": lid,
                    "city": rec.get("city"),
                    "via": rec.get("source") or "inquiry",
                },
            )
    except Exception:
        pass

    try:
        if os.environ.get("AUTO_CALLBACK_INQUIRY", "1").strip() != "0":
            from app.api.public_site import _auto_callback

            _spawn(
                _auto_callback(
                    str(rec.get("phone") or ""),
                    str(rec.get("niche") or "general"),
                    str(rec.get("business_name") or ""),
                    client_id=cid or "",
                )
            )
    except Exception as e:
        logger.debug(f"[inquiry_hooks] auto-callback spawn skip: {e}")

    try:
        from app.api.public_site import _notify_inquiry_email

        _spawn(_notify_inquiry_email(dict(rec)))
    except Exception as e:
        logger.debug(f"[inquiry_hooks] notify-email spawn skip: {e}")

    try:
        utm = (utm_source or rec.get("utm_source") or "").strip().lower()
        if utm:
            _UTM_MAP = {
                "quora": "quora",
                "reddit": "reddit",
                "linkedin": "linkedin_article",
                "medium": "medium",
                "whatsapp": "whatsapp_group",
                "wa": "whatsapp_group",
                "seo": "seo_page",
                "google": "seo_page",
                "organic": "seo_page",
                "partner": "partnership",
                "partnership": "partnership",
                "widget_chat": "whatsapp_group",
            }
            ch = _UTM_MAP.get(utm)
            if ch:
                from app.marketing import channel_experiments

                channel_experiments.record_outcome(ch, "inquiry", 1, f"utm:{utm}")
    except Exception as e:
        logger.debug(f"[inquiry_hooks] utm skip: {e}")

    try:
        from app.platform import revenue_attribution

        _utm = (utm_source or rec.get("utm_source") or "").strip()
        revenue_attribution.record_touch(
            client_id=str(cid or rec.get("client_id") or ""),
            channel="inquiry",
            utm_source=_utm,
            utm_campaign=str(rec.get("utm_campaign") or ""),
            event="inquiry",
        )
    except Exception as e:
        logger.debug(f"[inquiry_hooks] attribution skip: {e}")

    try:
        from app.platform import interaction_log

        _spawn(
            interaction_log.record(
                channel="inquiry",
                direction="in",
                phone=str(rec.get("phone") or ""),
                email=str(rec.get("email") or ""),
                client_id=str(cid or ""),
                lead_id=str(lid or ""),
                body_summary=str(rec.get("message") or rec.get("business_name") or "")[:200],
                outcome="received",
            )
        )
    except Exception as e:
        logger.debug(f"[inquiry_hooks] interaction skip: {e}")

    try:
        from app.platform import outbound_webhooks

        _spawn(
            outbound_webhooks.emit(
                "inquiry_received",
                {
                    "business_name": str(rec.get("business_name") or "")[:80],
                    "name": str(rec.get("name") or "")[:60],
                    "phone": str(rec.get("phone") or "")[-10:],
                    "niche": rec.get("niche"),
                    "city": rec.get("city"),
                },
            )
        )
    except Exception:
        pass

    try:
        from app.marketing import journeys

        _spawn(
            journeys.emit_event(
                "inquiry_received",
                {
                    "business_name": rec.get("business_name"),
                    "name": rec.get("name"),
                    "phone": rec.get("phone"),
                    "niche": rec.get("niche"),
                    "city": rec.get("city"),
                },
            )
        )
    except Exception:
        pass

    try:
        from app.integrations import ntfy as _ntfy

        _ntfy.push_bg(
            "Naya inquiry aaya 🔔",
            f"{rec.get('business_name') or rec.get('name') or 'Unknown'} — "
            f"{rec.get('phone') or rec.get('email') or ''} ({rec.get('niche') or ''}/{rec.get('city') or ''})",
            priority="default",
            tags=["bell"],
        )
    except Exception:
        pass

    if cid:
        try:
            from app.platform import lead_distribution as _ld

            assign_out = _ld.maybe_assign(
                cid,
                {
                    "name": rec.get("name") or rec.get("business_name") or "",
                    "phone": rec.get("phone") or "",
                    "message": rec.get("message") or "",
                    "source": rec.get("source") or "inquiry",
                },
            )
            if assign_out:
                rec["lead_assignment"] = {
                    "member": assign_out.get("assigned_to"),
                    "wa_link": assign_out.get("wa_link"),
                }
        except Exception as e:
            logger.debug(f"[inquiry_hooks] lead_distribution skip: {e}")

    try:
        from app.marketing import sales_pipeline as _sp

        _sp.upsert_deal(
            {
                "phone": rec.get("phone") or "",
                "email": rec.get("email") or "",
                "business_name": rec.get("business_name") or rec.get("name") or "",
                "niche": rec.get("niche") or "",
                "city": rec.get("city") or "",
                "source": rec.get("source") or "inquiry",
            },
            stage="new",
        )
    except Exception:
        pass

    try:
        from app.platform import crm_sync as _crm

        # Inbound web/widget/webhook lead → client (ya global) CRM me auto-push.
        # Pehle sirf voice path (call_manager) push karta tha; yeh cross-path
        # parity gap close karta. Gated CRM_SYNC (default OFF), never-raise.
        if _crm.auto_enabled():
            _spawn(
                _crm.push_lead(
                    {
                        "business_name": rec.get("business_name") or rec.get("name") or "",
                        "name": rec.get("name") or "",
                        "phone": rec.get("phone") or "",
                        "email": rec.get("email") or "",
                        "niche": rec.get("niche") or "",
                        "city": rec.get("city") or "",
                        "source": rec.get("source") or "inquiry",
                    },
                    client_id=cid or "",
                    note=f"Inbound inquiry (web/widget/webhook) · BANT {rec.get('bant_grade') or '?'}",
                )
            )
    except Exception as e:
        logger.debug(f"[inquiry_hooks] crm_sync spawn skip: {e}")

    try:
        from app.marketing import cadence as _cadence

        _cadence.enroll(
            {
                "phone": rec.get("phone") or "",
                "email": rec.get("email") or "",
                "name": rec.get("business_name") or rec.get("name") or "",
                "niche": rec.get("niche") or "",
                "city": rec.get("city") or "",
                "source": rec.get("source") or "inquiry",
            },
        )
    except Exception:
        pass


__all__ = ["run_after_inquiry"]
