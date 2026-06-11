"""Exotel ExoPhone -> flow/applet assignment via API (ready-to-flip).

Jab Exotel support Voicebot applet enable kar de aur flow ban jaye (App Bazar
flow creation ka PUBLIC API nahi hai — flow dashboard me banta hai, yeh script
uske BAAD ExoPhone ko us flow pe point karti hai):

    docker exec leadgen_app python scripts/exotel_assign_flow.py                       # list ExoPhones + current VoiceUrl
    docker exec leadgen_app python scripts/exotel_assign_flow.py --app-id 1234567 --dry-run
    docker exec leadgen_app python scripts/exotel_assign_flow.py --app-id 1234567      # default: PEHLA non-primary ExoPhone
    docker exec leadgen_app python scripts/exotel_assign_flow.py --app-id 1234567 --number 09513886363

Kya karta: (1) IncomingPhoneNumbers list, (2) target number ka Sid dhundo,
(3) POST update VoiceUrl=https://my.exotel.com/{sid}/exoml/start_voice/{app_id}
(StatusCallback untouched), (4) GET se verify. Defensive — kabhi crash nahi.
NOTE: primary number 01141189204 (applet 1265199) ko by-default NAHI chhedte —
use --number se explicitly do to wahi update hota hai.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os

import httpx

PRIMARY_EXOPHONE = "01141189204"  # existing voice flow (applet 1265199) — default-protected


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name, "").strip()
    if v:
        return v
    try:
        from app.config import settings

        return str(getattr(settings, name.lower(), "") or default)
    except Exception:
        return default


SID = _env("EXOTEL_SID")
KEY = _env("EXOTEL_API_KEY")
TOK = _env("EXOTEL_API_TOKEN")
HOST = (_env("EXOTEL_SUBDOMAIN", "api").rstrip(".") or "api")
if not HOST.endswith(".exotel.com"):
    HOST = f"{HOST}.exotel.com"
AUTH = base64.b64encode(f"{KEY}:{TOK}".encode()).decode() if (KEY and TOK) else ""
H = {"Authorization": f"Basic {AUTH}"}
BASE = f"https://{HOST}/v1/Accounts/{SID}"


def _phones(data: dict) -> list[dict]:
    nums = (data or {}).get("IncomingPhoneNumbers") or (data or {}).get("IncomingPhoneNumber") or []
    if isinstance(nums, dict):
        nums = [nums]
    out = []
    for n in nums:
        if isinstance(n, dict) and n.get("IncomingPhoneNumber"):
            n = n["IncomingPhoneNumber"]
        out.append(n)
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-id", help="flow/applet id (exoml start_voice)")
    ap.add_argument("--number", help="ExoPhone to update (default: first non-primary)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not (SID and AUTH):
        print(json.dumps({"error": "EXOTEL_SID/API_KEY/API_TOKEN missing"}))
        return

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{BASE}/IncomingPhoneNumbers.json", headers=H)
        try:
            data = r.json()
        except Exception:
            print(json.dumps({"list_http": r.status_code, "raw": r.text[:300]}))
            return
        phones = _phones(data)
        summary = [
            {
                "PhoneNumber": p.get("PhoneNumber"),
                "Sid": p.get("Sid"),
                "VoiceUrl": p.get("VoiceUrl"),
            }
            for p in phones
        ]
        print(json.dumps({"list_http": r.status_code, "exophones": summary}, indent=1))

        if not args.app_id:
            return  # list-only mode

        target = None
        if args.number:
            want = args.number.lstrip("0+91").lstrip("0")
            for p in phones:
                have = str(p.get("PhoneNumber") or "").lstrip("0+91").lstrip("0")
                if have == want or str(p.get("PhoneNumber")) == args.number:
                    target = p
                    break
        else:
            for p in phones:
                if str(p.get("PhoneNumber")) != PRIMARY_EXOPHONE:
                    target = p
                    break
        if not target:
            print(json.dumps({"error": "target ExoPhone nahi mila (2nd number aaya kya?)",
                              "hint": "--number <exophone> do, ya support se 2nd ExoPhone lo"}))
            return

        voice_url = f"https://my.exotel.com/{SID}/exoml/start_voice/{args.app_id}"
        plan = {"number": target.get("PhoneNumber"), "sid": target.get("Sid"),
                "old_VoiceUrl": target.get("VoiceUrl"), "new_VoiceUrl": voice_url}
        if args.dry_run:
            print(json.dumps({"dry_run": True, **plan}, indent=1))
            return

        u = f"{BASE}/IncomingPhoneNumbers/{target.get('Sid')}.json"
        r2 = await client.post(u, headers=H, data={"VoiceUrl": voice_url, "VoiceMethod": "POST"})
        ok = r2.status_code
        if ok >= 400:  # kuch deployments PUT mangte hain
            r2 = await client.put(u, headers=H, data={"VoiceUrl": voice_url, "VoiceMethod": "POST"})
            ok = r2.status_code
        rv = await client.get(u, headers=H)
        try:
            now = _phones({"IncomingPhoneNumber": rv.json().get("IncomingPhoneNumber", {})})[0]
        except Exception:
            now = {}
        print(json.dumps({"update_http": ok, **plan,
                          "verified_VoiceUrl": now.get("VoiceUrl"),
                          "success": now.get("VoiceUrl") == voice_url}, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
