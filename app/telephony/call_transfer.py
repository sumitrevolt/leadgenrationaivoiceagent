"""Live human transfer w/ context — AI call ke beech customer "owner se baat karao"
bole to owner ko turant connect + poora context summary (Hinglish).

NOTE: is path par pehle Cloud-Run-era DEAD demo code tha (CallTransferManager,
hardcoded fake sales-reps, module-level WhatsAppIntegration init) — repo me
kahin import nahi hota tha (grep-verified) → lean gated module se REPLACED.

Kyun: Vodex/Smartlead-class voice agents ka killer feature = AI stuck/asked →
HUMAN handoff with context (owner ko blind call nahi milti). Flow:
  detect_transfer_intent(text)  → voice pipeline me intent pakdo (wiring alag pass)
  request_transfer(call_context, owner_phone) →
    (a) gate: CALL_TRANSFER=1 flag (default OFF = inert, {"ok": False, "reason": "disabled"})
    (b) Hinglish context summary (free_ai, template fallback — LLM down pe bhi kaam)
    (c) Vobiz connect-leg owner↔caller (VobizClient.place_call reuse, lazy
        import; creds nahi = draft-only, raise nahi)
    (d) owner ke liye WhatsApp 1-click summary link (wa.me, draft) + email DRAFT
        (send NAHI — ban-safe)
    (e) log data/call_transfers.jsonl

GATED `CALL_TRANSFER=1` (default OFF = zero behaviour change). Free-stack.
Never raises. Auto-send kuch NAHI (sirf call-leg initiate, woh bhi flag+creds pe).
"""

from __future__ import annotations

import json
import os
import urllib.parse
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_TRANSFERS = os.path.join("data", "call_transfers.jsonl")

# Hinglish transfer-intent keywords (voice pipeline / chat dono ke liye)
_INTENT_KEYWORDS = (
    "owner se baat",
    "malik se baat",
    "manager se baat",
    "insaan se baat",
    "insan se baat",
    "aadmi se baat",
    "asli aadmi",
    "real person",
    "human se",
    "transfer kar",
    "transfer karo",
    "transfer me",
    "kisi aur se baat",
    "boss se baat",
    "sir se baat",
    "madam se baat",
    "speak to owner",
    "talk to owner",
    "talk to human",
    "talk to a human",
    "speak to a human",
    "speak to manager",
    "not a robot",
    "agent se baat",
    "customer care se",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _phone10(raw: Any) -> str:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits if len(digits) == 10 else ""


def enabled() -> bool:
    """Flag gate — CALL_TRANSFER=1 hone par hi active (default OFF = inert)."""
    return os.getenv("CALL_TRANSFER", "0").strip().lower() in ("1", "true", "yes")


def detect_transfer_intent(text: str) -> bool:
    """Customer ke utterance me human-transfer intent hai? Pure-python, fast
    (voice hot-path safe — koi LLM nahi). Never raises."""
    try:
        t = (text or "").strip().lower()
        if not t:
            return False
        return any(kw in t for kw in _INTENT_KEYWORDS)
    except Exception:
        return False


def _conversation_text(call_context: dict[str, Any]) -> str:
    """call_context se conversation-so-far nikaalo (jo bhi shape mile)."""
    ctx = call_context or {}
    conv = ctx.get("conversation") or ctx.get("transcript") or ctx.get("history") or ""
    if isinstance(conv, list):
        lines = []
        for turn in conv[-20:]:
            if isinstance(turn, dict):
                role = str(turn.get("role") or turn.get("speaker") or "?")
                content = str(turn.get("content") or turn.get("text") or "")
                lines.append(f"{role}: {content}")
            else:
                lines.append(str(turn))
        conv = "\n".join(lines)
    return str(conv or "").strip()[:3000]


def _template_summary(call_context: dict[str, Any]) -> str:
    """LLM-free fallback summary (hamesha kaam karta)."""
    ctx = call_context or {}
    who = str(ctx.get("name") or ctx.get("business_name") or "Customer")
    phone = _phone10(ctx.get("phone") or ctx.get("phone_number")) or "unknown"
    niche = str(ctx.get("niche") or "general")
    conv = _conversation_text(ctx)
    last_line = conv.splitlines()[-1][:140] if conv else "baat-cheet record nahi mili"
    return (
        f"📞 Live transfer: {who} ({phone}, {niche}) AI call par hain aur aapse "
        f'baat karna chahte hain. Aakhri baat: "{last_line}". Turant connect ho rahe hain.'
    )


async def _summarize(call_context: dict[str, Any]) -> tuple[str, str]:
    """Hinglish context summary (free_ai → template fallback). Returns (summary, provider)."""
    fallback = _template_summary(call_context)
    conv = _conversation_text(call_context)
    if not conv:
        return fallback, ""
    try:
        from app.voice_agent import free_ai

        ctx = call_context or {}
        who = str(ctx.get("name") or ctx.get("business_name") or "Customer")
        reply, provider = await free_ai.chat(
            system=(
                "Tu ek call-transfer assistant hai. AI agent ki customer se chal rahi call ka "
                "context owner ko dena hai. 2-3 line Hinglish me: customer kaun, kya chahiye, "
                "kya discuss hua, ab kya karna. Owner ko turant samajh aaye — concise."
            ),
            messages=[{"role": "user", "content": f"Customer: {who}\n\nConversation:\n{conv}"}],
            max_tokens=160,
            temperature=0.2,
        )
        summary = (reply or "").strip()
        if summary:
            return summary[:600], provider
    except Exception as e:
        logger.info(f"[call_transfer] summary LLM skipped: {e}")
    return fallback, ""


def _log(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_TRANSFERS) or ".", exist_ok=True)
        with open(_TRANSFERS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        logger.warning(f"[call_transfer] log failed: {e}")


async def _initiate_connect_leg(owner10: str, call_id: str) -> dict[str, Any]:
    """Vobiz connect-leg: owner ko call lagao. Lazy import, creds nahi = graceful
    skip. Never raises. (Calls DLT/recharge-blocked abhi — structural wiring.)"""
    try:
        import os

        from app.telephony.vobiz_handler import VobizClient

        client = VobizClient()
        if not client.available():
            return {"initiated": False, "reason": "vobiz_not_configured"}
        base = (os.getenv("PUBLIC_BASE_URL") or os.getenv("SITE_BASE") or "").rstrip("/")
        answer_url = f"{base}/api/webhooks/vobiz/answer" if base else ""
        result = await client.place_call(
            to=owner10,
            answer_url=answer_url,
            call_type="transactional",
        )
        if result.get("status_code") in (200, 201, 202):
            sid = str((result.get("body") or {}).get("id") or "")
            return {"initiated": True, "call_sid": sid}
        return {"initiated": False, "reason": f"vobiz status {result.get('status_code')}"}
    except Exception as e:
        logger.warning(f"[call_transfer] connect-leg failed: {e}")
        return {"initiated": False, "reason": str(e)[:200]}


async def request_transfer(call_context: dict[str, Any], owner_phone: str) -> dict[str, Any]:
    """AI call → live human (owner) transfer with Hinglish context. Never raises.

    Flag OFF / owner_phone invalid = inert. Flag ON: summary + Vobiz connect-leg
    (creds pe) + owner ke liye WA 1-click link + email DRAFT + jsonl log.
    """
    try:
        if not enabled():
            return {"ok": False, "reason": "disabled", "hint": "CALL_TRANSFER=1 set karo"}

        owner10 = _phone10(owner_phone)
        if not owner10:
            return {"ok": False, "reason": "owner_phone invalid (10-digit chahiye)"}

        ctx = call_context if isinstance(call_context, dict) else {}
        summary, provider = await _summarize(ctx)

        call_id = str(
            ctx.get("call_id") or f"transfer-{int(datetime.now(timezone.utc).timestamp())}"
        )
        leg = await _initiate_connect_leg(owner10, call_id)

        wa_link = f"https://wa.me/91{owner10}?text={urllib.parse.quote(summary[:320])}"
        email_draft = {
            "subject": f"📞 Live call transfer — {ctx.get('name') or ctx.get('business_name') or 'Customer'}",
            "body": (
                f"{summary}\n\n"
                f"Customer phone: {_phone10(ctx.get('phone') or ctx.get('phone_number')) or 'unknown'}\n"
                f"Call ID: {call_id}\n"
                f"Transfer time: {_now()}"
            ),
            "auto_sent": False,  # draft only — ban/spam-safe
        }

        rec = {
            "call_id": call_id,
            "owner_phone": owner10,
            "customer_phone": _phone10(ctx.get("phone") or ctx.get("phone_number")),
            "summary": summary,
            "provider": provider,
            "connect_leg": leg,
            "wa_link": wa_link,
            "at": _now(),
        }
        _log(rec)

        # AI staff feed (best-effort). Attributed to Raksha — transfer is HER
        # role (team.py roster); logging as swara left raksha with zero events
        # ever, indistinguishable from a broken agent (audit 2026-07-04).
        try:
            from app.platform import team

            team.log_event(
                "raksha",
                "call_transfer",
                f"Live transfer → owner {owner10} ({'connected' if leg.get('initiated') else 'draft'})",
            )
        except Exception:
            pass

        return {
            "ok": True,
            "transferred": bool(leg.get("initiated")),
            "summary": summary,
            "wa_link": wa_link,
            "email_draft": email_draft,
            "connect_leg": leg,
            "call_id": call_id,
        }
    except Exception as e:
        logger.warning(f"[call_transfer] request_transfer failed: {e}")
        return {"ok": False, "reason": str(e)[:200]}


def list_transfers(limit: int = 50) -> list[dict[str, Any]]:
    """Recent transfers (newest first). Never raises."""
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(_TRANSFERS):
            return out
        with open(_TRANSFERS, encoding="utf-8") as f:
            for ln in f:
                try:
                    rec = json.loads(ln)
                    if isinstance(rec, dict):
                        out.append(rec)
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"[call_transfer] list failed: {e}")
    return list(reversed(out))[: max(1, min(int(limit or 50), 200))]


__all__ = ["enabled", "detect_transfer_intent", "request_transfer", "list_transfers"]
