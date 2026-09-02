"""Pehli AI test call — Vobiz Call API se (run on VPS, /opt/leadgen)."""

import asyncio
import sys

sys.path.insert(0, "/opt/leadgen")

from app.telephony.vobiz_handler import VobizClient


async def main() -> None:
    c = VobizClient()
    print("available:", c.available())

    bal = await c.get_balance()
    print("BALANCE:", str(bal)[:220])

    to = "+918459012607"
    answer_url = "https://leadsgenai.in/api/telephony/vobiz/answer/firstcall"
    r = await c.place_call(to=to, answer_url=answer_url, from_="+911171366938")
    print("PLACE_CALL:", str(r)[:400])


if __name__ == "__main__":
    asyncio.run(main())
