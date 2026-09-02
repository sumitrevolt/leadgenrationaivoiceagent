"""Place ONE allowlisted Swara acceptance call on prod (run inside leadgen_app)."""

import asyncio
import datetime
import json

from app.api.telephony_vobiz import start_stream_call
from app.telephony.voice_launch import recording_gate_ok


async def main() -> None:
    ok, reason = recording_gate_ok()
    print("GATE", ok, reason)
    if not ok:
        raise SystemExit(reason)
    to = "+918459012607"
    print("PLACE", datetime.datetime.utcnow().isoformat() + "Z")
    r = await start_stream_call(to=to, niche="ai_marketing", call_type="transactional")
    print(json.dumps({k: r.get(k) for k in ("placed", "error", "stream_token")}, default=str))
    with open("/tmp/last_accept_call.json", "w", encoding="utf-8") as f:  # nosec B108 — VPS canary scratch
        f.write(json.dumps(r, default=str))


asyncio.run(main())
