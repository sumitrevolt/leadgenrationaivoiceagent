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

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_PACK_DIR = os.path.join("data", "client_packs")

# Re-nudge state — WhatsApp business-info interview ek hi baar bhejta tha; agar us
# din WA infra down ho (jaise jiya makeover ke saath hua — WAHA baad me linka), to
# client silently awaiting_kb_interview=true reh jata tha forever. Yahan per-client
# sent-at timestamps + count persist karte (clients_store untouched rehta).
_NUDGE_STATE_FILE = os.path.join("data", "kb_interview_nudges.json")
_RENUDGE_MAX = 3  # max total re-nudges per client (initial welcome message ke upar)
_RENUDGE_MIN_HOURS = 24  # min gap between re-nudges


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _flag_on(name: str) -> bool:
    """Default-ON flag (unset = enabled). Bug-fix of promised behaviour, isliye ON."""
    return os.getenv(name, "1").strip().lower() in {"1", "true", "yes", "on"}


def _load_nudge_state() -> dict[str, Any]:
    """Read the per-client re-nudge state file. Never raises (missing/corrupt = {})."""
    try:
        with open(_NUDGE_STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_nudge_state(state: dict[str, Any]) -> None:
    """Persist the re-nudge state. Best-effort, never raises."""
    try:
        os.makedirs(os.path.dirname(_NUDGE_STATE_FILE) or ".", exist_ok=True)
        with open(_NUDGE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=0)
    except Exception as exc:
        logger.debug("kb_interview nudge state save err: %s", exc)


def _clear_nudge_state(cid: str) -> None:
    """Drop a client's re-nudge record once the interview is captured (keeps the
    state file from growing + resets the counter if they ever re-enter awaiting).
    Best-effort, never raises."""
    try:
        state = _load_nudge_state()
        if cid in state:
            state.pop(cid, None)
            _save_nudge_state(state)
    except Exception:
        pass


def _now_utc() -> datetime:
    """Wrapper so tests can freeze time by monkeypatching this one call site."""
    return datetime.now(timezone.utc)


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
                [text[:8000]], source=f"website:{website}", namespace=ns, replace_source=True
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
                os.path.join(_PACK_DIR, f"{client.get('id', 'client')}.html"), "w", encoding="utf-8"
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


def _interview_message(biz: str, renudge: bool = False) -> str:
    """The business-info interview ask (WhatsApp). `renudge=True` softens the intro
    for a follow-up so a re-nudge doesn't repeat "onboarding complete" verbatim."""
    if renudge:
        head = (
            f"Namaste! {biz} ka AI agent ab bhi aapke business ki details ka intezaar "
            "kar raha hai. Ek chhoti si madad chahiye — isi message ka reply karke bata do:\n"
        )
    else:
        head = (
            f"Namaste! 🎉 {biz} ka LeadGen AI onboarding complete ho gaya.\n\n"
            "Bas ek chhoti si madad chahiye — isi message ka reply karke bata do:\n"
        )
    return (
        head + "1) Aap kya services dete hain?\n"
        "2) Konsa area/city cover karte hain?\n"
        "3) Ek line jo aapko khaas banati hai\n\n"
        "Isse aapka AI agent customers ko aapke business ke hisaab se jawab de payega."
    )


async def _send_whatsapp(phone: str, msg: str) -> bool:
    """Send one WhatsApp text; True on delivered-ish. Never raises; no-op without a
    configured sender. Shared by welcome + re-nudge paths."""
    try:
        from app.integrations.whatsapp import get_whatsapp_sender

        sender = get_whatsapp_sender()
        res = await sender.send_text_message(phone, msg)
        return bool(res) and not (isinstance(res, dict) and res.get("error"))
    except Exception as exc:
        logger.debug("onboard whatsapp send err: %s", exc)
        return False


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
        msg = _interview_message(biz, renudge=False)
    out["sent"] = await _send_whatsapp(phone, msg)
    return out


async def _renudge_awaiting_interviews(limit: int = 25) -> dict[str, Any]:
    """Re-send the business-info interview to active clients still stuck on
    awaiting_kb_interview=True (the WhatsApp interview is sent only ONCE at
    onboarding — if WA infra was down that day the client stays awaiting forever).

    Caps: max `_RENUDGE_MAX` (3) re-nudges per client, min `_RENUDGE_MIN_HOURS`
    (24h) apart. Gated `KB_INTERVIEW_RENUDGE` (default ON — bug-fix of promised
    behaviour). Never raises."""
    res: dict[str, Any] = {"renudged": 0, "pending": 0, "capped": 0}
    if not _flag_on("KB_INTERVIEW_RENUDGE"):
        res["skipped"] = "KB_INTERVIEW_RENUDGE off"
        return res
    try:
        from app.marketing import clients_store

        state = _load_nudge_state()
        now = _now_utc()
        dirty = False
        for c in clients_store.list_clients(status="active"):
            if not c.get("awaiting_kb_interview"):
                continue
            phone = str(c.get("phone") or "").strip()
            if not phone:
                continue
            res["pending"] += 1
            cid = str(c.get("id") or "")
            if not cid:
                continue
            rec = state.get(cid) or {}
            count = int(rec.get("count") or 0)
            if count >= _RENUDGE_MAX:
                res["capped"] += 1
                continue
            last = rec.get("last_at")
            if last:
                try:
                    last_dt = datetime.fromisoformat(last)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    if (now - last_dt).total_seconds() < _RENUDGE_MIN_HOURS * 3600:
                        continue  # too soon — 24h gap not elapsed
                except Exception:
                    pass
            biz = c.get("business_name") or "aapka business"
            sent = await _send_whatsapp(phone, _interview_message(biz, renudge=True))
            if sent:
                rec["count"] = count + 1
                rec["last_at"] = now.isoformat()
                state[cid] = rec
                dirty = True
                res["renudged"] += 1
                _log(
                    "client_interview_renudged",
                    f"{biz}: KB-interview re-nudge #{rec['count']} bheja (WhatsApp)",
                )
                if res["renudged"] >= max(1, limit):
                    break
        if dirty:
            _save_nudge_state(state)
    except Exception as exc:
        logger.info("kb_interview re-nudge sweep err: %s", exc)
        res["error"] = str(exc)
    return res


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
        # FAIL-LOUD (2026-07-05): pehle yeh logger.debug tha — ek paying customer
        # (jiya makeover) ka reply isi silent swallow me gaya, woh awaiting_kb_interview
        # me forever stuck rahi + ghost ho gayi. Ab WARNING (silent loss banned).
        logger.warning("try_capture_onboarding_reply err (reply may be LOST): %s", exc)
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
        _clear_nudge_state(cid)  # captured -> re-nudge record ki zaroorat nahi
        _log(
            "client_interview_captured",
            f"{client.get('business_name', '')}: WhatsApp se business-info mila (KB seeded)",
        )
        return True
    except Exception as exc:
        logger.info("_capture_business_interview err: %s", exc)
        return False


async def auto_onboard(cid: str, send_welcome: bool = True, force: bool = False) -> dict[str, Any]:
    """Run the full auto-setup for one client. Never raises.

    send_welcome=False skips the welcome-WhatsApp step (used when the caller —
    e.g. the /signup handler — already sent its own welcome, so the customer
    doesn't get two messages).

    IDEMPOTENT: if the client is already `setup_done`, skip the whole heavy path
    (KB re-seed / content / welcome) unless force=True. Protects the direct callers
    (onboard_client task from signup/admin-onboard) — the admin onboard endpoint is
    deliberately re-callable for password resets, and without this guard each retry
    would re-scrape + regenerate + re-welcome an existing customer. The hourly sweep
    already filters setup_done, so this is a no-op there."""
    report: dict[str, Any] = {"client_id": cid, "steps": {}}
    try:
        from app.marketing import clients_store

        client = clients_store.get_client(cid)
        if not client:
            return {"error": "client not found", "client_id": cid}
        if client.get("setup_done") and not force:
            return {"ok": True, "client_id": cid, "skipped": "already_setup"}
        biz = client.get("business_name", "")

        try:
            from app.marketing import delivery_ledger

            delivery_ledger.log_event(cid, "onboarding_started", detail=biz)
        except Exception as le:  # pragma: no cover
            logger.debug("onboard ledger log skip (started): %s", le)

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
        try:
            from app.marketing import delivery_ledger

            delivery_ledger.log_event(cid, "onboarding_completed", detail=biz, key="lc:onboarded")
        except Exception as le:  # pragma: no cover
            logger.debug("onboard ledger log skip (completed): %s", le)

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
            if send_welcome:
                report["steps"]["welcome_whatsapp"] = await _send_welcome_whatsapp(
                    client, kb_seeded
                )
            else:
                report["steps"]["welcome_whatsapp"] = {"skipped": "caller_sends_own_welcome"}
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
    """Find active clients without setup_done and auto-onboard them. Also re-nudges
    clients still stuck on the business-info interview (own flag). Never raises.

    Wall-clock budget (``ONBOARD_TIME_BUDGET_S``, default 300) — SoftTimeLimit
    DLQ on 2026-07-23 ``onboard`` job: renudge + delivery + KB seed exceeded 540s.
    """
    from app.platform.job_time_budget import JobBudget

    budget = JobBudget.from_env("ONBOARD_TIME_BUDGET_S", label="onboard")
    res: dict[str, Any] = {"onboarded": 0, "checked": 0, "budget": budget.snapshot()}
    # Re-nudge pass runs INDEPENDENTLY of AUTO_ONBOARD (own flag KB_INTERVIEW_RENUDGE)
    # — a client can be stuck awaiting the interview even after AUTO_ONBOARD is turned
    # off, and this is a bug-fix for already-promised behaviour. Never raises.
    try:
        if budget.ok(need=20.0):
            res["renudge"] = await _renudge_awaiting_interviews()
        else:
            res["renudge"] = {"skipped": "time_budget"}
    except Exception as exc:
        logger.info("onboarding sweep renudge err: %s", exc)
        res["renudge"] = {"error": str(exc)}
    # DELIVERY GUARANTEE (2026-07-05, council): dead-man sweep — koi bhi PAID customer
    # jise value deliver nahi hui woh visible + (AUTO_DELIVER_VALUE on ho to) auto-deliver
    # ho. Runs INDEPENDENTLY of AUTO_ONBOARD (delivery != onboarding). Never raises.
    try:
        if budget.ok(need=30.0):
            from app.marketing import customer_delivery

            remain = max(15.0, budget.remaining() - 10.0)
            res["delivery"] = await asyncio.wait_for(
                customer_delivery.run_delivery_sweep(), timeout=remain
            )
        else:
            res["delivery"] = {"skipped": "time_budget"}
    except TimeoutError:
        logger.warning("[onboard] delivery sweep truncated by ONBOARD_TIME_BUDGET_S")
        res["delivery"] = {"skipped": "time_budget_timeout"}
    except Exception as exc:
        logger.info("onboarding sweep delivery err: %s", exc)
        res["delivery"] = {"error": str(exc)}
    if not _flag("AUTO_ONBOARD"):
        res["skipped"] = "AUTO_ONBOARD off"
        res["budget"] = budget.snapshot()
        return res
    try:
        from app.marketing import clients_store

        for c in clients_store.list_clients(status="active"):
            if not budget.ok(need=25.0):
                res["time_budget_exhausted"] = True
                break
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
    res["budget"] = budget.snapshot()
    return res


__all__ = [
    "auto_onboard",
    "run_onboarding_sweep",
    "try_capture_onboarding_reply",
    "_renudge_awaiting_interviews",
]
