
import asyncio
import logging
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

async def verify_outbound_connectivity() -> dict[str, Any]:
    """
    Synthetic probe: Places a brief test call to a sink-endpoint
    to verify valid outbound DID ownership by the provider.
    """
    verify_outbound = os.environ.get("VOBIZ_VERIFY_CALLER_ID_OUTBOUND", "0") == "1"
    if not verify_outbound:
        return {"ok": True, "why": "skipped (VOBIZ_VERIFY_CALLER_ID_OUTBOUND=0)"}

    try:
        from app.telephony.vobiz_handler import VobizClient
        client = VobizClient()

        # NOTE: Using a non-existent or loopback DID for verification
        # The provider *must* validate ownership before triggering the call.
        # If the number is not owned, Vobiz will return a 4xx/5xx rejected state immediately.
        test_did = "+919****7776"

        # Trigger minimal-cost call (duration < 1s)
        # This is a probe, not a real call.
        # FIX (2026-09-12): VobizClient has no create_call method — use place_call
        # with skip_compliance=True (probe is internal) + test_mode forwarded via **extra.
        result = await client.place_call(
            to=test_did,
            answer_url="https://leadsgenai.in/api/webhooks/vobiz/answer",
            from_=os.environ.get("VOBIZ_CALLER_ID"),
            call_type="transactional",
            skip_compliance=True,
            test_mode=True,
        )

        # place_call returns {"status_code": int, "body": dict}.
        # status_code 200/201/202 = accepted (ownership verified).
        # status_code 0 = transport/local error.
        # body.error contains "not owned" = ownership rejection.
        if result.get("status_code") in (200, 201, 202):
            return {"ok": True, "why": "outbound connectivity verified"}

        # Parse vendor error
        err = (result.get("body") or {}).get("error") or "unknown rejection"
        logger.warning(f"[outbound_probe] FAILED: {err}")
        return {"ok": False, "why": f"outbound test-call rejected: {err}"}

    except Exception as e:
        logger.warning(f"[outbound_probe] EXCEPTION: {e}")
        return {"ok": False, "why": f"outbound probe error: {str(e)}"}

