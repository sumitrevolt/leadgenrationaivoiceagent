"""VPS: verify streaming caps + place a CONVERSATIONAL stream-call (run on VPS)."""

import asyncio
import sys

sys.path.insert(0, "/opt/leadgen")


async def main() -> None:
    import app.telephony.vobiz_stream as v

    print("STT_AVAILABLE:", v.STT_AVAILABLE, "| TTS_AVAILABLE:", v.TTS_AVAILABLE)

    from app.telephony.vobiz_handler import VobizClient, build_stream_xml

    ws = "wss://leadsgenai.in/api/telephony/vobiz/stream/convtest?niche=solar_residential"
    print("STREAM XML:", build_stream_xml(ws))

    c = VobizClient()
    to = "+918459012607"
    answer_url = (
        "https://leadsgenai.in/api/telephony/vobiz/answer-stream/convtest?niche=solar_residential"
    )
    r = await c.place_call(to=to, answer_url=answer_url, from_="+911171366938")
    print("STREAM CALL:", str(r)[:300])


if __name__ == "__main__":
    asyncio.run(main())
