"""Temp: place ONE diagnostic Vobiz stream call to a given number."""

import asyncio
import sys


async def main():
    to = sys.argv[1] if len(sys.argv) > 1 else "+918459012607"
    from app.api.telephony_vobiz import start_stream_call

    r = await start_stream_call(
        to=to, niche="ai_marketing", call_type="transactional", client_id=None
    )
    print(
        "PLACED:",
        r.get("placed"),
        "| token:",
        r.get("stream_token"),
        "| err:",
        r.get("error") or "-",
    )
    vr = r.get("vobiz_response") or {}
    print("vobiz status_code:", vr.get("status_code"))


asyncio.run(main())
