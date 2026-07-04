"""Automated client onboarding — client add hote hi poora setup KHUD (done-for-you).

Manual agency onboarding 5-7 din leta hai; yeh minutes me karta hai. Jaise hum apne liye
karte hain, waise client ke liye. Pieces pehle se the (clients_store, content_pack,
mini-site) — yeh unhe ek auto-flow me chain karta hai PLUS naya high-value step:

  **client ki ASLI website se KB auto-seed** (deep_extract/trafilatura → vector KB +
  LightRAG graph, namespace `client:<id>`) — taaki client ka AI agent uske apne business
  (services, USP, area) ko jaane, sirf generic niche facts nahi. Yeh dormant
  web-extraction + RAG tools ko asli value me convert karta hai.

Steps per client: website→KB seed → first content pack (welcome deliverable) → setup_done
mark → welcome event. Sab defensive (step fail → skip, never crash).

OFF by default. Enable `AUTO_ONBOARD=1`. Hourly sweep un-setup active clients ko onboard
karta hai (idempotent — setup_done wale skip).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_PACK_DIR = os.path.join("data", "client_packs")


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _website(client: dict) -> str:
    w = client.get("website") or ""
    if not w:
        w = (
            (client.get("socials") or {}).get("website", "")
            if isinstance(client.get("socials"), dict)
            else ""
        )
    return str(w or "").strip()


def _namespace(cid: str) -> str:
    try:
        from app.platform.agent_provisioner import _client_namespace

        return _client_namespace(cid)
    except Exception:
        return f"client:{cid}"


async def _seed_kb_from_website(cid: str, website: str) -> dict:
    """Scrape the client's site → vector KB + (opt-in) knowledge graph. Best-effort."""
    out = {"website": website, "kb_chunks": 0, "graph": False}
    if not website:
        return out
    try:
        from app.lead_scraper.deep_extract import extract_url

        data = await extract_url(website)
        text = (data.get("text") or data.get("markdown") or "").strip()
        if len(text) < 150:
            # Fallback: MarkItDown handles PDF/Office brochures + JS-thin pages that
            # deep_extract missed. Off-loop (sync convert), inert without markitdown
            # (returns ""). Closes the to_markdown orphan (docs/Automation_Marketing_Repos.md).
            try:
                import asyncio

                from app.lead_scraper.to_markdown import to_markdown

                md = (await asyncio.to_thread(to_markdown, website) or "").strip()
                if len(md) > len(text):
                    text = md
            except Exception as exc:
                logger.info("onboard to_markdown fallback skip: %s", exc)
            if len(text) < 150:
                return out
        ns = _namespace(cid)
        try:
            from app.voice_agent.knowledge_base import get_knowledge_base

            out["kb_chunks"] = get_knowledge_base().add_documents(
                [text[:8000]], source=f"website:{website}", namespace=ns
            )
        except Exception as exc:
            logger.info("onboard kb seed err: %s", exc)
        try:
            from app.voice_agent.graph_rag import get_graph_rag

            out["graph"] = await get_graph_rag().ainsert(text[:8000], namespace=ns)
        except Exception:
            pass
    except Exception as exc:
        logger.info("onboard website extract err: %s", exc)
    return out


async def _first_content_pack(client: dict) -> dict:
    try:
        from app.marketing.content_pack import build_client_pack

        pack = await build_client_pack(
            client.get("business_name", ""),
            client.get("niche", "general"),
            client_id=str(client.get("id", "")),
            phone=str(client.get("phone", "")),
        )
        html = pack.get("html") or ""
        if html:
            os.makedirs(_PACK_DIR, exist_ok=True)
            with open(
                os.path.join(_PACK_DIR, f"{client.get('id','client')}.html"), "w", encoding="utf-8"
            ) as f:
                f.write(html)
        return pack.get("counts", {})
    except Exception as exc:
        logger.info("onboard content pack err: %s", exc)
        return {}


def _log(kind: str, detail: str) -> None:
    try:
        from app.platform.team import log_event

        log_event("dev", kind, detail)
    except Exception:
        pass


async def _send_welcome_whatsapp(client: dict[str, Any], kb_seeded: bool) -> dict[str, Any]:
    """Welcome message right after onboarding; if the website-KB-seed step found
    nothing (no website / thin site), ask for business info in the same message —
    the WhatsApp reply becomes the KB source instead (see try_capture_onboarding_reply).
    Best-effort, never raises; no-op without a phone or a configured WA sender."""
    out: dict[str, Any] = {"sent": False}
    phone = str(client.get("phone") or "").strip()
    if not phone:
        return out
    biz = client.get("business_name") or "aapka business"
    if kb_seeded:
        msg = (
            f"Namaste! 🎉 {biz} ka LeadGen AI onboarding complete ho gaya. Aapki website se "
            "business details AI agent ko de diye gaye hain — ab woh aapke customers ke "
            "sawalon ka jawab de sakta hai."
        )
    else:
        msg = (
            f"Namaste! 🎉 {biz} ka LeadGen AI onboarding complete ho gaya.\n\n"
            "Bas ek chhoti si madad chahiye — isi message ka reply karke bata do:\n"
            "1) Aap kya services dete hain?\n"
            "2) Konsa area/city cover karte hain?\n"
            "3) Ek line jo aapko khaas banati hai\n\n"
            "Isse aapka AI agent customers ko aapke business ke hisaab se jawab de payega."
        )
    try:
        from app.integrations.whatsapp import get_whatsapp_sender

        sender = get_whatsapp_sender()
        res = await sender.send_text_message(phone, msg)
        out["sent"] = bool(res) and not (isinstance(res, dict) and res.get("error"))
    except Exception as exc:
        logger.debug("onboard welcome whatsapp err: %s", exc)
    return out


async def try_capture_onboarding_reply(from_number: str, text: str) -> bool:
    """Inbound WhatsApp reply -> if `from_number` matches a client still awaiting the
    onboarding business-info interview, feed the reply into that client's KB namespace
    (closes the KB gap for clients without a website) and clear the flag.

    Called from BOTH whatsapp webhook handlers (selfhost + Meta Cloud) before they hand
    the message to reply_agent — returns True when handled, so the caller skips the
    normal prospect-reply draft for this message. Never raises; False = not our message."""
    txt = (text or "").strip()
    digits = "".join(ch for ch in str(from_number or "") if ch.isdigit())[-10:]
    if not digits or len(txt) < 5:
        return False
    try:
        from app.marketing import clients_store

        for c in clients_store.list_clients(status="active"):
            if not c.get("awaiting_kb_interview"):
                continue
            cph = "".join(ch for ch in str(c.get("phone") or "") if ch.isdigit())[-10:]
            if cph and cph == digits:
                return await _capture_business_interview(c, txt)
    except Exception as exc:
        logger.debug("try_capture_onboarding_reply err: %s", exc)
    return False


async def _capture_business_interview(client: dict[str, Any], text: str) -> bool:
    """Add the WhatsApp business-info reply to the client's KB + clear the pending flag."""
    cid = str(client.get("id") or "")
    if not cid:
        return False
    try:
        from app.marketing import clients_store

        ns = _namespace(cid)
        try:
            from app.voice_agent.knowledge_base import get_knowledge_base

            get_knowledge_base().add_documents(
                [text[:4000]], source="whatsapp:onboarding_interview", namespace=ns
            )
        except Exception as exc:
            logger.debug("onboard interview kb seed err: %s", exc)
        clients_store.update_client(cid, awaiting_kb_interview=False)
        _log(
            "client_interview_captured",
            f"{client.get('business_name','')}: WhatsApp se business-info mila (KB seeded)",
        )
        return True
    except Exception as exc:
        logger.info("_capture_business_interview err: %s", exc)
        return False


async def auto_onboard(cid: str) -> dict[str, Any]:
    """Run the full auto-setup for one client. Never raises."""
    report: dict[str, Any] = {"client_id": cid, "steps": {}}
    try:
        from app.marketing import clients_store

        client = clients_store.get_client(cid)
        if not client:
            return {"error": "client not found", "client_id": cid}
        biz = client.get("business_name", "")

        report["steps"]["kb_website"] = await _seed_kb_from_website(cid, _website(client))
        report["steps"]["content_pack"] = await _first_content_pack(client)

        # Day-1 value: customer-visible content QUEUE bhi bharo (portal_content
        # isi list_queue se padhta — pehle sirf HTML pack banta tha jo portal me
        # nahi dikhta tha, customer ko ~07:00 daily-sweep tak khaali queue dikhti).
        # date+type DEDUPE = daily job ke saath idempotent. Best-effort, never raises.
        try:
            from app.marketing import auto_content

            report["steps"]["content_queue"] = await auto_content.seed_client_content(client)
        except Exception as exc:
            logger.debug("onboard content_queue skip: %s", exc)
            report["steps"]["content_queue"] = 0

        # GHL-style niche template — mini-site palette, journeys, festival schedule (best-effort)
        try:
            from app.platform import client_snapshots

            report["steps"]["niche_snapshot"] = client_snapshots.apply_niche_to_client(cid)
        except Exception as exc:
            logger.debug("onboard niche_snapshot skip: %s", exc)
            report["steps"]["niche_snapshot"] = {"ok": False, "skipped": str(exc)[:80]}

        try:
            clients_store.update_client(
                cid, setup_done=True, setup_at=datetime.now(timezone.utc).isoformat()
            )
        except Exception:
            pass

        kb = report["steps"]["kb_website"].get("kb_chunks", 0)
        kb_seeded = bool(kb)
        if not kb_seeded:
            # No usable website -> mark pending so the WhatsApp reply (below) becomes
            # the KB source (see try_capture_onboarding_reply / _capture_business_interview).
            try:
                clients_store.update_client(cid, awaiting_kb_interview=True)
            except Exception:
                pass
        try:
            report["steps"]["welcome_whatsapp"] = await _send_welcome_whatsapp(client, kb_seeded)
        except Exception as exc:
            logger.debug("onboard welcome whatsapp step err: %s", exc)
            report["steps"]["welcome_whatsapp"] = {"sent": False}

        _log("client_onboarded", f"{biz}: auto-setup done (website KB {kb} chunks + content pack)")
        # Funnel event (audit 2026-07-04) — silent no-op without POSTHOG_API_KEY.
        try:
            from app.analytics import posthog_client as _ph

            _ph.capture(cid, "onboarding_completed", {"kb_chunks": kb})
        except Exception:
            pass
        report["ok"] = True
        return report
    except Exception as exc:
        logger.info("auto_onboard err: %s", exc)
        return {"error": str(exc), "client_id": cid}


async def run_onboarding_sweep(limit: int = 10) -> dict[str, Any]:
    """Find active clients without setup_done and auto-onboard them. Never raises."""
    if not _flag("AUTO_ONBOARD"):
        return {"skipped": "AUTO_ONBOARD off"}
    res = {"onboarded": 0, "checked": 0}
    try:
        from app.marketing import clients_store

        for c in clients_store.list_clients(status="active"):
            res["checked"] += 1
            if c.get("setup_done"):
                continue
            await auto_onboard(str(c.get("id", "")))
            res["onboarded"] += 1
            if res["onboarded"] >= max(1, limit):
                break
    except Exception as exc:
        logger.info("onboarding sweep err: %s", exc)
        res["error"] = str(exc)
    return res


__all__ = ["auto_onboard", "run_onboarding_sweep", "try_capture_onboarding_reply"]
