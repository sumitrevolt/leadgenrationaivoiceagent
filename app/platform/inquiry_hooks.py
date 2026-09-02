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

# Application-owned fire-and-forget tasks (strong refs until done).
# Without this, asyncio only weak-refs create_task() results and a Task can be
# GC/destroyed mid-session — DB checkout never closes (SQLAlchemy #13039 /
# aiosqlite #369 → orphan worker / CI exit-139).
_BG_TASKS: set[asyncio.Task] = set()
_ACCEPTING_BG: bool = True
_DEFAULT_DRAIN_TIMEOUT_S = float(os.environ.get("INQUIRY_BG_DRAIN_TIMEOUT_S", "10") or "10")


def _spawn(coro: Any, *, name: str = "inquiry_bg") -> asyncio.Task | None:
    """Own a background coroutine until it finishes (request stays non-blocking)."""
    global _ACCEPTING_BG
    if not _ACCEPTING_BG:
        logger.debug("[inquiry_hooks] spawn refused (shutting down): %s", name)
        if asyncio.iscoroutine(coro):
            coro.close()
        return None
    try:
        task = asyncio.create_task(coro, name=f"inquiry:{name}")
    except Exception as e:
        logger.debug(f"[inquiry_hooks] spawn skip ({name}): {e}")
        if asyncio.iscoroutine(coro):
            try:
                coro.close()
            except Exception:
                pass
        return None

    _BG_TASKS.add(task)

    def _on_done(t: asyncio.Task, *, _name: str = name) -> None:
        _BG_TASKS.discard(t)
        try:
            exc = t.exception()
        except asyncio.CancelledError:
            return
        except Exception:
            return
        if exc is not None:
            logger.warning("[inquiry_hooks] bg task %s failed: %s", _name, exc)

    task.add_done_callback(_on_done)
    return task


def stop_accepting_inquiry_bg() -> None:
    """Refuse new inquiry background work (shutdown phase 1)."""
    global _ACCEPTING_BG
    _ACCEPTING_BG = False


def resume_accepting_inquiry_bg() -> None:
    """Re-open the spawn gate (tests / rare recover paths only)."""
    global _ACCEPTING_BG
    _ACCEPTING_BG = True


def pending_inquiry_bg_count() -> int:
    return len([t for t in _BG_TASKS if not t.done()])


async def await_inquiry_bg_tasks(*, timeout: float | None = None) -> dict[str, int]:
    """Wait for currently owned inquiry BG tasks without closing the accept gate.

    Use from tests / request-scoped helpers. Shutdown must use
    ``drain_inquiry_bg_tasks`` instead (stop accepting → await → cancel).
    """
    limit = _DEFAULT_DRAIN_TIMEOUT_S if timeout is None else float(timeout)
    pending = [t for t in list(_BG_TASKS) if not t.done()]
    if not pending:
        return {"awaited": 0, "cancelled": 0, "remaining": 0}

    done, still = await asyncio.wait(pending, timeout=max(0.0, limit))
    cancelled = 0
    if still:
        for t in still:
            t.cancel()
        cancelled = len(still)
        await asyncio.gather(*still, return_exceptions=True)

    return {
        "awaited": len(done),
        "cancelled": cancelled,
        "remaining": pending_inquiry_bg_count(),
    }


async def drain_inquiry_bg_tasks(*, timeout: float | None = None) -> dict[str, int]:
    """Canonical shutdown drain — call BEFORE close_async_db()/engine.dispose().

    Ordering (required):
      1. stop accepting new work
      2. await owned tasks (bounded timeout)
      3. cancel still-pending
      4. await cancelled with return_exceptions=True
    """
    stop_accepting_inquiry_bg()
    result = await await_inquiry_bg_tasks(timeout=timeout)
    if result["remaining"]:
        logger.warning(
            "[inquiry_hooks] drain finished with %d task(s) still pending "
            "(awaited=%d cancelled=%d)",
            result["remaining"],
            result["awaited"],
            result["cancelled"],
        )
    else:
        logger.info(
            "[inquiry_hooks] bg drain complete (awaited=%d cancelled=%d)",
            result["awaited"],
            result["cancelled"],
        )
    return result


def resolve_wizard_opening(
    *,
    business_type: str = "",
    niche: str = "",
    business_name: str = "",
) -> str:
    """Wizard business-type se personalized opening_line resolve karo.

    Lead-magnet pages (/audit /site-audit /demo) visitor ko business type select
    karwate hain → business_type label + niche key aate hain. Har AI-call path
    (auto-callback, voice-followup, missed-call) isi opening se greet kare
    (generic niche script ki jagah wizard ka done-for-you opening). Resolve fail
    ho to "" — call niche-script chain pe girta hai (unchanged). Best-effort,
    kabhi raise nahi. business_name zaroori hai (personalization); label ya niche
    me se koi ek wizard business type se match hona chahiye.
    """
    try:
        from app.marketing.onboard_wizard import BUSINESS_TYPES, get_script_preview

        label = str(business_type or "").strip().lower()
        niche_key = str(niche or "").strip().lower()
        biz = str(business_name or "").strip()
        if not (label or niche_key) or not biz:
            return ""
        btype: str | None = None
        for b in BUSINESS_TYPES:
            if b.get("niche") == "general":
                continue
            if (label and str(b.get("label") or "").strip().lower() == label) or (
                niche_key and str(b.get("niche") or "").strip().lower() == niche_key
            ):
                btype = b.get("id")
                break
        if not btype:
            return ""
        preview = get_script_preview(btype, business_name=biz)
        return str(preview.get("suggested_opening") or "").strip()[:500]
    except Exception:
        return ""


def _wizard_opening_for(rec: dict[str, Any]) -> str:
    """Inquiry record se wizard opening_line (business_type/niche + business_name). Wrapper."""
    return resolve_wizard_opening(
        business_type=str(rec.get("business_type") or ""),
        niche=str(rec.get("niche") or ""),
        business_name=str(rec.get("business_name") or ""),
    )


async def run_after_inquiry(
    rec: dict[str, Any],
    *,
    mini_client_id: str | None = None,
    utm_source: str | None = None,
    lead_id: str | None = None,
    dry_run: bool = False,
) -> None:
    """Post-store automation for any inquiry record. Storage caller ne pehle hi kar diya.

    dry_run=True (verification smoke): auto-callback chain poora chalta hai par
    ASLI call nahi lagta (start_stream_call dry_run). Baaki hooks unaffected.
    """
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

    # Owner Hot Queue bridge — platform inquiries only (speed-to-lead action).
    try:
        from app.platform.inquiry_hq_bridge import bridge_inquiry_to_hot_queue

        bridge_inquiry_to_hot_queue(rec)
    except Exception as e:
        logger.debug(f"[inquiry_hooks] hq bridge skip: {e}")

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
            _spawn(_cw.emit(cid, "lead.created", payload), name="customer_webhook")
        except Exception:
            pass
    # Funnel event (audit 2026-07-04) — silent no-op without POSTHOG_API_KEY.
    # 2026-08-18: `if cid` ke ANDAR tha — platform leads (/audit /demo) kabhi
    # fire nahi hote the (cid sirf mini-site pe hota hai). Ab HAR inquiry pe
    # fire hota hai (cid ke bahar), distinct_id = phone (payment_activated bhi
    # phone-keyed hai — isliye funnel dono steps same person pe match karta hai).
    try:
        from app.analytics import posthog_client as _ph

        _ph.capture(
            cid or str(rec.get("phone") or rec.get("id") or "lead"),
            "lead_captured",
            {
                "source": rec.get("source"),
                "niche": rec.get("niche"),
                "business_type": rec.get("business_type"),
            },
        )
    except Exception:
        pass
    # Customer Delivery OS ledger event — same "lead_captured" name as the
    # PostHog analytics capture above but a distinct system (delivery_ledger
    # drives the customer timeline/Command Center, not product analytics).
    # Mini-site (cid) leads ke liye — client timeline record.
    if cid:
        try:
            from app.marketing import delivery_ledger

            delivery_ledger.log_event(
                cid, "lead_captured", detail=str(rec.get("business_name") or rec.get("phone") or "")
            )
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
                    opening_line=_wizard_opening_for(rec),
                    dry_run=bool(dry_run),
                ),
                name="auto_callback",
            )
    except Exception as e:
        logger.debug(f"[inquiry_hooks] auto-callback spawn skip: {e}")

    try:
        from app.api.public_site import _notify_inquiry_email

        _spawn(_notify_inquiry_email(dict(rec)), name="notify_email")
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
            ),
            name="interaction_log",
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
            ),
            name="outbound_webhook",
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
            ),
            name="journey_emit",
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
                # Client-owned inquiry ka deal client_id se stamp karo taaki
                # LeadGen ki sales-pipeline (run_pipeline) ise skip kare — yeh
                # client ke apne funnel ka lead hai, LeadGen ke sales-funnel ka nahi.
                "client_id": cid or "",
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
                ),
                name="crm_push",
            )
    except Exception as e:
        logger.debug(f"[inquiry_hooks] crm_sync spawn skip: {e}")

    # LeadGen's OWN sales cadence — SIRF platform leads ke liye. Agar inquiry kisi
    # CLIENT ka hai (cid set), toh woh lead client ke apne funnel ka hai — usko
    # LeadGen ke "Rs 1999 plan lo" cadence me KABHI enroll nahi karna (isolation).
    if not cid:
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

        # Sales Autopilot feed — platform inquiries only (never client-owned leads).
        # consent_basis = website form first-contact (DPDP purpose limitation).
        try:
            maybe_ingest_sales_autopilot(rec)
        except Exception as e:
            logger.debug(f"[inquiry_hooks] sales_autopilot ingest skip: {e}")


def maybe_ingest_sales_autopilot(rec: dict[str, Any]) -> dict[str, Any] | None:
    """Upsert a platform inquiry into sales_autopilot prospects. Never raises to caller.

    Skips when: client-owned (isolation), missing phone+email, or store unavailable.
    """
    if (rec.get("client_id") or "").strip():
        return None
    email = str(rec.get("email") or "").strip().lower()
    phone = str(rec.get("phone") or "").strip()
    if not email and not phone:
        return None
    from app.platform.sales_autopilot import store as _store

    pid = str(rec.get("id") or "").strip()
    if not pid:
        digits = _store.digits(phone) or email.replace("@", "_").replace(".", "_")
        pid = f"inq_{digits}"[:64]
    return _store.upsert_prospect(
        {
            "id": pid,
            "name": str(rec.get("business_name") or rec.get("name") or "")[:200],
            "phone": phone,
            "email": email,
            "city": str(rec.get("city") or "")[:100],
            "niche": str(rec.get("niche") or "")[:60],
            "source": "website_inquiry",
            "consent_basis": "website_inquiry_form",
            "status": _store.STATUS_NEW,
            "inquiry_id": str(rec.get("id") or ""),
        }
    )


__all__ = ["run_after_inquiry", "maybe_ingest_sales_autopilot"]
