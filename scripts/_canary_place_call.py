"""Place one allowlisted transactional test call — prod container only."""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def mask(s: str) -> str:
    return re.sub(
        r"(\+?91)?(\d{6})(\d{4})",
        lambda m: (m.group(1) or "") + "******" + (m.group(3) or ""),
        str(s),
    )


async def main() -> int:
    now = datetime.now(IST)
    print("now_ist", now.strftime("%Y-%m-%d %H:%M:%S %Z"))
    if now.hour < 9:
        print("BLOCKED: before 9am IST promotional window")
        return 2

    to = os.environ.get("TO", "+919359984977")
    from app.api.telephony_vobiz import start_stream_call
    from app.telephony.compliance import CallType, get_compliance_gate
    from app.telephony.dial_gate import allowlist, test_mode
    from app.telephony.voice_launch import recording_gate_ok

    print("test_mode", test_mode())
    print("allowlist_ok", "9359984977" in allowlist())
    d = await get_compliance_gate().check(to, CallType.TRANSACTIONAL)
    print("compliance_tx", d.allowed, d.reasons)

    ok, reason = recording_gate_ok()
    print("recording_gate", ok, reason)
    if not ok:
        return 3

    res = await start_stream_call(
        to=to,
        niche="ai_marketing",
        client_id=None,
        call_type="transactional",
    )
    slim = {k: res.get(k) for k in ("placed", "error", "stream_token")}
    print("result", mask(json.dumps(slim, default=str)))

    body = (res.get("vobiz_response") or {}).get("body") or {}
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            body = {}
    uuid = None
    if isinstance(body, dict):
        uuid = body.get("request_uuid") or body.get("call_uuid") or body.get("CallUUID")
        msg = body.get("message")
        if not uuid and isinstance(msg, dict):
            uuid = msg.get("request_uuid") or msg.get("call_uuid")
    print("provider_uuid", uuid)
    print("placed", res.get("placed"))
    print("error", res.get("error"))

    with open("/tmp/last_call_uuid.txt", "w") as f:  # nosec B108 — VPS canary scratch
        f.write(str(uuid or ""))
    with open("/tmp/last_canary_call.json", "w") as f:  # nosec B108 — VPS canary scratch
        json.dump(res, f, default=str)
    return 0 if res.get("placed") else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
