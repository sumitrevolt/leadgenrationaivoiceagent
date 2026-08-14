"""Local websocket test for the web-call bot (run on the VPS)."""

import asyncio
import json

import aiohttp


async def chat() -> None:
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect("http://127.0.0.1:8000/api/web-call/ws", timeout=20) as ws:
            ready = json.loads((await ws.receive()).data)
            print("ready responder:", ready.get("responder"))
            await ws.send_json({"type": "start", "niche": "solar", "flow": "qualify"})
            await ws.receive()
            await ws.send_json({"type": "text", "text": "hello"})
            d = json.loads((await asyncio.wait_for(ws.receive(), 45)).data)
            print("BOT:", str(d.get("text"))[:300])


if __name__ == "__main__":
    asyncio.run(chat())
