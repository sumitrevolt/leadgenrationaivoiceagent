"""Outbound connectivity probe (Tata SmartFlo — Vobiz removed 2026-09-15)."""

import asyncio
import logging
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

async def verify_outbound_connectivity() -> dict[str, Any]:
    """
    Synthetic probe: Places a brief test call to verify valid outbound DID
    ownership by the active provider (Tata SmartFlo).
    """
    verify_outbound = os.environ.get("SMARTFLO_VERIFY_CALLER_ID_OUTBOUND", "0") == "1"
    if not verify_outbound:
        return {"ok": True, "why": "skipped (SMARTFLO_VERIFY_CALLER_ID_OUTBOUND=0)"}

    try:
        from app.telephony.tata_smartflo_handler import TataSmartfloClient

        client = TataSmartfloClient()
        if not client.available():
            return {
                "ok": False,
                "why": "Tata SmartFlo not configured — TATA_SMARTFLO_API_TOKEN + TATA_SMARTFLO_API_KEY required",
            }

        # Use the SmartFlo DID (or the probe target if explicitly set).
        test_did = os.environ.get("SMARTFLO_VERIFY_TEST_NUMBER", client.did)
        if not test_did:
            return {"ok": False, "why": "No SmartFlo DID configured for probe (TATA_SMARTFLO_DID)"}

        # Trigger minimal-cost call — SmartFlo C2C test-mode
        result = await client.place_call(
            to=test_did,
            call_type="transactional",
            skip_compliance=True,
            test_mode=True,
        )

        # place_call returns {"status_code": int, "body": dict}.
        if result.get("status_code") in (200, 201, 202):
            return {"ok": True, "why": "outbound connectivity verified (SmartFlo)"}

        # Parse vendor error
        err = (result.get("body") or {}).get("error") or "unknown rejection"
        logger.warning(f"[outbound_probe] FAILED: {err}")
        return {"ok": False, "why": f"outbound test-call rejected: {err}"}

    except Exception as e:
        logger.warning(f"[outbound_probe] EXCEPTION: {e}")
        return {"ok": False, "why": f"outbound probe error: {str(e)}"}
