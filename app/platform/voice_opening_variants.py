"""Kiran-approved voice_opening variants for Swara phone/web greetings."""

from __future__ import annotations

import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_SCRIPT_ID = "voice_opening"


def voice_variants_on() -> bool:
    try:
        return os.environ.get("VOICE_CAMPAIGN_VARIANTS", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    except Exception:
        return False


def format_opening(content: str, client_name: str) -> str:
    """Proposal content → single Swara-friendly opener line."""
    text = (content or "").strip()
    if not text:
        return ""
    parts = text.split("\n\n", 1)
    line = parts[1].strip() if len(parts) > 1 and parts[1].strip() else parts[0].strip()
    name = (client_name or "aap").strip()
    for tok in ("{name}", "[Name]", "{Name}", "[Company]"):
        line = line.replace(tok, name)
    line = line.replace("raha hoon", "rahi hoon").replace("Raha hoon", "Rahi hoon")
    return line.strip()


async def resolve(
    *,
    phone: str = "",
    niche: str = "general",
    client_name: str = "",
) -> dict[str, Any]:
    """Pick champion/challenger voice opener. Empty dict if gated off or <2 arms."""
    if not voice_variants_on():
        return {}
    try:
        from app.platform import campaign_variants

        stable = (phone or "").strip() or f"voice:{niche}:{client_name}"
        picked = await campaign_variants.pick_for_outreach(
            _SCRIPT_ID,
            email=stable,
            niche=niche or "general",
        )
        if not picked:
            return {}
        line = format_opening(str(picked.get("content") or ""), client_name)
        if not line:
            return {}
        return {
            "variant_id": str(picked.get("id") or ""),
            "variant_key": picked.get("variant_key"),
            "opening_line": line,
            "script_id": _SCRIPT_ID,
        }
    except Exception as e:
        logger.debug("[voice_opening] resolve skip: %s", e)
        return {}


async def record_impression(variant_id: str) -> None:
    if not variant_id:
        return
    try:
        from app.platform import campaign_variants

        await campaign_variants.record_event(variant_id, impression=True)
    except Exception:
        pass


async def record_outcome(
    variant_id: str, *, answered: bool = False, interested: bool = False
) -> None:
    if not variant_id:
        return
    try:
        from app.platform import campaign_variants

        if answered:
            await campaign_variants.record_event(variant_id, reply=True)
        if interested:
            await campaign_variants.record_event(variant_id, meeting=True)
    except Exception:
        pass


__all__ = [
    "voice_variants_on",
    "format_opening",
    "resolve",
    "record_impression",
    "record_outcome",
    "SCRIPT_ID",
]

SCRIPT_ID = _SCRIPT_ID
