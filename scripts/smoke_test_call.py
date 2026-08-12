"""Smoke /app/test-call + web-call WS on live or local. Usage:
python scripts/smoke_test_call.py
python scripts/smoke_test_call.py --base https://leadsgenai.in
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.request

try:
    import aiohttp
except ImportError:
    print("FAIL: aiohttp required")
    sys.exit(1)


def http_get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "smoke-test-call/1"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, (r.read(500) or b"").decode("utf-8", errors="replace")
    except Exception as e:
        return 0, str(e)


async def ws_ai_marketing(base: str) -> list[str]:
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    url = f"{ws_base.rstrip('/')}/api/web-call/ws"
    issues: list[str] = []
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url, timeout=30) as ws:
            await ws.send_json({"type": "start", "niche": "ai_marketing", "flow": "qualify"})
            bots: list[str] = []
            for _ in range(20):
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=15)
                except asyncio.TimeoutError:
                    break
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                d = json.loads(msg.data)
                t = d.get("type")
                if t == "bot" and d.get("text"):
                    bots.append(str(d["text"]))
                if len(bots) >= 3:
                    break
            if len(bots) < 3:
                issues.append(f"platform opener expected 3 segments, got {len(bots)}: {bots}")
            elif "LeadGen AI" not in (bots[0] or ""):
                issues.append(f"seg1 missing LeadGen AI: {bots[0]!r}")
            elif not any(
                word in (bots[2] or "").lower()
                for word in ("interested", "try", "free", "chahenge", "dekh")
            ):
                issues.append(f"seg3 not interest ask: {bots[2]!r}")

            await ws.send_json({"type": "user", "text": "haan ji", "niche": "ai_marketing"})
            praise = ""
            for _ in range(12):
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=20)
                except asyncio.TimeoutError:
                    break
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                d = json.loads(msg.data)
                if d.get("type") == "bot" and d.get("text"):
                    praise = str(d["text"])
                    break
            if not praise:
                issues.append("no bot reply after 'haan ji'")
            elif not any(
                word in praise.lower() for word in ("bahut achha", "sahi", "decision", "marketing")
            ):
                issues.append(f"expected acknowledgement/discovery after yes, got: {praise!r}")
    return issues


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="https://leadsgenai.in")
    args = p.parse_args()
    base = args.base.rstrip("/")
    fails = 0

    st, body = http_get(f"{base}/app/test-call")
    if st != 200 or "Web Call" not in body and "test" not in body.lower():
        print(f"FAIL /app/test-call status={st}")
        fails += 1
    else:
        print(f"OK /app/test-call {st}")

    st, body = http_get(f"{base}/health")
    if st != 200 or "production" not in body and "healthy" not in body.lower():
        print(f"WARN /health status={st} body={body[:120]}")
    else:
        print("OK /health")

    issues = asyncio.run(ws_ai_marketing(base))
    if issues:
        fails += len(issues)
        for i in issues:
            print(f"FAIL WS: {i}")
    else:
        print("OK web-call WS ai_marketing (3-seg opener + yes praise)")

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
