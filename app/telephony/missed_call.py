"""Missed-call -> instant AI callback (62% inbound SMB calls unanswered = leak).

Koi number humein ring kare aur miss ho jaye -> 2 min me AI us number ko wapas
call kare (qualify + book). Research: missed-call-callback = highest SMB ROI.

Reuses EXISTING callback path (telephony_vobiz.start_stream_call — wahi jo
public_site._auto_callback use karta). Lead bhi capture hota.

STATUS: ready-to-flip. GATED `MISSED_CALL_CALLBACK=1` + telephony reachable +
Vobiz DID (`VOBIZ_CALLER_ID`). Bina flag/DID = inert (sirf lead capture + log).
Dedupe: same number 1/hour. Ban-safe: caller ne KHUD ring kiya (transactional),
promotional cold-call nahi.
"""

from __future__ import annotations

import os
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_RECENT: dict[str, float] = {}  # number -> last-callback ts (in-memory dedupe)
_DEDUPE_S = 3600  # 1/hour per number


def _enabled() -> bool:
    return os.environ.get("MISSED_CALL_CALLBACK", "0").strip().lower() in ("1", "true", "yes")


def _recently_called(number: str) -> bool:
    now = time.time()
    # purge old
    for k in [k for k, t in _RECENT.items() if now - t > _DEDUPE_S]:
        _RECENT.pop(k, None)
    return (now - _RECENT.get(number, 0)) < _DEDUPE_S


async def handle_missed_call(
    from_number: str, niche: str = "general", business: str = ""
) -> dict[str, Any]:
    """Missed inbound call -> lead capture + (gated) instant AI callback. Kabhi raise nahi.

    Inbound webhook (Vobiz "no-answer"/"missed") isse call kare.
    """
    num = (from_number or "").strip()
    if not num:
        return {"ok": False, "reason": "no number"}

    # 1) Lead capture (hamesha — callback ho ya na ho, lead na khoye)
    try:
        from app.api.public_site import _append_jsonl, _save_lead_db

        rec = {
            "name": "Missed caller",
            "business_name": business or "Missed caller",
            "phone": num,
            "niche": niche or "general",
            "message": "Missed inbound call — callback pending",
            "source": "missed_call",
        }
        _append_jsonl(rec)
        _save_lead_db(rec)
    except Exception as e:
        logger.debug(f"[missed_call] lead capture skip: {e}")

    # 2) Dedupe
    if _recently_called(num):
        return {"ok": True, "callback": False, "reason": "deduped (called within 1h)"}

    # 3) Callback (GATED + best-effort, reuse existing streaming-call path)
    if not _enabled():
        return {"ok": True, "callback": False, "reason": "MISSED_CALL_CALLBACK off (lead captured)"}
    try:
        from app.api import telephony_vobiz

        starter = getattr(telephony_vobiz, "start_stream_call", None)
        if starter is None:
            return {
                "ok": True,
                "callback": False,
                "reason": "telephony start_stream_call unavailable",
            }
        _RECENT[num] = time.time()
        # transactional callback to a number that rang us. NOTE: positional call
        # here previously stuffed `business` (free text) into start_stream_call's
        # 3rd positional param, which is `client_id` — not a display name (there
        # is no client_name param; the callee resolves the real business name
        # from a genuine client_id via clients_store, if one is ever threaded
        # through here). Keyword args prevent that class of bug from recurring.
        # Wizard opening: webhook niche (e.g. salon_spa) + business name ho to
        # wahi personalized opening use karein — resolve fail = "" → niche-script
        # chain (unchanged).
        from app.platform.inquiry_hooks import resolve_wizard_opening

        await starter(
            num,
            niche=niche or "general",
            call_type="transactional",
            opening_line=resolve_wizard_opening(niche=niche or "", business_name=business or ""),
        )
        logger.info(f"[missed_call] AI callback triggered -> {num}")
        return {"ok": True, "callback": True, "number": num}
    except Exception as e:
        logger.warning(f"[missed_call] callback failed: {e}")
        return {"ok": False, "callback": False, "reason": str(e)[:200]}


__all__ = ["handle_missed_call"]
