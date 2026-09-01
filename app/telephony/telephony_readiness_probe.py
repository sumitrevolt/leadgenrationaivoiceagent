
import asyncio
import os
import logging
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
        test_did = "+919998887776" 
        
        # Trigger minimal-cost call (duration < 1s)
        # This is a probe, not a real call.
        result = await client.create_call(
            to_number=test_did,
            from_number=os.environ.get("VOBIZ_CALLER_ID"),
            test_mode=True
        )
        
        # If the vendor API accepts the request, we verify ownership.
        # If vendor rejects with "not owned", call fails.
        if result.get("status") == "success":
            return {"ok": True, "why": "outbound connectivity verified"}
        
        # Parse vendor error
        err = result.get("error", "unknown rejection")
        logger.warning(f"[outbound_probe] FAILED: {err}")
        return {"ok": False, "why": f"outbound test-call rejected: {err}"}
        
    except Exception as e:
        logger.warning(f"[outbound_probe] EXCEPTION: {e}")
        return {"ok": False, "why": f"outbound probe error: {str(e)}"}
