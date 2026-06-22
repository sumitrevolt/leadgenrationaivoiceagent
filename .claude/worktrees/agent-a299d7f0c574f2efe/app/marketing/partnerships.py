"""Partnership / reseller outreach agent — B2B2B leverage (telephony-free).

Complementary businesses (CA/accountant, web-designer, IT-vendor, business-consultant,
marketing-agency, printer) WAHI local SMBs serve karte jo humein chahiye. Inse
partnership/refer/resell/white-label = ek partner se kaiyon clients (Zapier model).

Yeh module AI se partnership PITCH draft karta (draft-only, ban-safe manual send).
free-LLM (template fallback). Import-safe, kabhi raise nahi karta.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Partner type -> (kya woh karte, kyun fit, model)
PARTNER_TYPES: dict[str, dict[str, str]] = {
    "ca": {
        "label": "Chartered Accountant / Accountant",
        "serves": "har local business (filing/GST)",
        "model": "refer — har client jo marketing-help maange, hamein bhejo; commission per close",
    },
    "web_designer": {
        "label": "Web Designer / Developer",
        "serves": "businesses jinko website chahiye",
        "model": "bundle — website ke saath hamara AI lead-gen bechо; revenue-share",
    },
    "it_vendor": {
        "label": "IT / Software Vendor",
        "serves": "SMBs ka tech setup",
        "model": "add-on — apne clients ko hamara AI marketing offer karo",
    },
    "business_consultant": {
        "label": "Business Consultant / Coach",
        "serves": "growth chahne wale businesses",
        "model": "refer — growth-advice ke saath hamein recommend karo",
    },
    "marketing_agency": {
        "label": "Small Marketing Agency",
        "serves": "clients jinko marketing chahiye",
        "model": "WHITE-LABEL — hamara AI voice-agent apne brand me bechо (B2B2B)",
    },
    "printer": {
        "label": "Printing / Signage Shop",
        "serves": "local shop-owners",
        "model": "refer — har shop-owner ko hamara Google/marketing audit bhejo",
    },
}


def list_partner_types() -> list[dict[str, str]]:
    return [{"key": k, **v} for k, v in PARTNER_TYPES.items()]


def _tpl(ptype: str, name: str) -> str:
    p = PARTNER_TYPES.get(ptype, {})
    label = p.get("label", "Partner")
    model = p.get("model", "refer karke commission kamao")
    who = name or label
    return (
        f"Namaste {who} ji 🙏 Main Sumit, LeadGen AI se. Aap jaise {label.lower()} ke clients ko "
        f"naye customers + Google presence chahiye hi hota hai — hum AI se woh sambhalte hain "
        f"(har inquiry ko 2-min me call karke qualified lead). Aap {model}. "
        f"Aapke liye zero kaam, extra income. 10-min baat karein? Free demo: leadsgenai.in/audit"
    )


async def draft_partnership(
    partner_type: str, partner_name: str = "", city: str = ""
) -> dict[str, Any]:
    """Ek partner ke liye partnership/white-label pitch draft. free-LLM, fallback template."""
    ptype = (partner_type or "ca").strip().lower()
    cfg = PARTNER_TYPES.get(ptype, PARTNER_TYPES["ca"])
    pitch = _tpl(ptype, partner_name)
    try:
        from app.voice_agent import free_ai

        sys = (
            "Tum ek B2B partnership manager ho (India). Ek SHORT (3-4 line) Hinglish "
            "partnership/referral/white-label pitch likho ek complementary business ko. "
            "Value-first, win-win, zero-effort-for-them angle. LeadGen AI = AI voice agent "
            "jo inquiries ko call karke qualified leads laata. Sirf message text."
        )
        prompt = f"Partner type: {cfg['label']} ({cfg['serves']}). Model: {cfg['model']}. Name: {partner_name or 'unknown'}. City: {city}."
        txt, _ = await free_ai.chat(
            sys, [{"role": "user", "content": prompt}], max_tokens=200, temperature=0.7
        )
        if txt and txt.strip():
            pitch = txt.strip()
    except Exception as e:
        logger.debug(f"[partnerships] llm skip: {e}")
    return {
        "ok": True,
        "partner_type": ptype,
        "partner_name": partner_name or cfg["label"],
        "model": cfg["model"],
        "pitch": pitch,
        "cta": "leadsgenai.in/audit",
        "auto_sent": False,
    }


async def draft_batch(partner_types: list[str] | None = None, city: str = "") -> dict[str, Any]:
    """Multiple partner-types ke pitches (outreach plan)."""
    types = partner_types or list(PARTNER_TYPES.keys())
    out = []
    for t in types[:8]:
        out.append(await draft_partnership(t, "", city))
    return {"ok": True, "count": len(out), "partnerships": out}


__all__ = ["PARTNER_TYPES", "list_partner_types", "draft_partnership", "draft_batch"]
