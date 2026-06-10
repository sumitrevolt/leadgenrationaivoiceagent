"""Exotel API setup-audit — account/credits/numbers/calls EK command me.

VPS pe chalao (creds /opt/leadgen/.env me):
    docker exec leadgen_app python scripts/exotel_setup_audit.py            # audit only
    docker exec leadgen_app python scripts/exotel_setup_audit.py --call 08459012607  # + test call (credits use)

Kya karta: (1) account details (Type/KycStatus/Status), (2) balance (v2 + v1
dono try), (3) ExoPhones list, (4) recent calls, (5) optional verified-number pe
test call (connect.json, EXOTEL_APP_ID applet). Sab defensive — jo endpoint na
mile uska error print, script kabhi crash nahi.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys

import httpx


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


async def _get(client: httpx.AsyncClient, url: str):
    try:
        r = await client.get(url, headers=H, timeout=20.0)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:300]}
    except Exception as e:
        return 0, {"error": str(e)[:200]}


async def main() -> None:
    if not (SID and AUTH):
        print(json.dumps({"error": "EXOTEL_SID/API_KEY/API_TOKEN missing"}))
        return
    out: dict = {"sid": SID, "host": HOST}
    async with httpx.AsyncClient() as client:
        # 1) Account details (v1)
        code, acc = await _get(client, f"https://{HOST}/v1/Accounts/{SID}.json")
        a = (acc or {}).get("Account") or {}
        out["account"] = {
            "http": code,
            "type": a.get("Type"),
            "status": a.get("Status"),
            "kyc": a.get("KycStatus"),
            "created": a.get("DateCreated"),
        }
        # 2) Balance — v2 pehle, phir v1 variants
        for label, url in [
            ("v2_balance", f"https://{HOST}/v2/accounts/{SID}/balance"),
            ("v1_balance", f"https://{HOST}/v1/Accounts/{SID}/Balance.json"),
            ("v2_account", f"https://{HOST}/v2/accounts/{SID}"),
        ]:
            code, data = await _get(client, url)
            out[label] = {"http": code, "data": data if code == 200 else (data.get("error") or data)}
            if code == 200:
                pass  # sab capture; pehla success kaafi par poora picture achha
        # 3) ExoPhones / numbers
        code, nums = await _get(client, f"https://{HOST}/v1/Accounts/{SID}/IncomingPhoneNumbers.json")
        items = (nums or {}).get("IncomingPhoneNumbers") or (nums or {}).get("incoming_phone_numbers") or []
        out["exophones"] = {"http": code, "count": len(items) if isinstance(items, list) else "?",
                            "numbers": [
                                {k: n.get(k) for k in ("PhoneNumber", "FriendlyName", "VoiceEnabled", "SMSEnabled")}
                                for n in (items if isinstance(items, list) else [])
                            ][:5] or nums}
        # 4) Recent calls
        code, calls = await _get(client, f"https://{HOST}/v1/Accounts/{SID}/Calls.json?PageSize=5")
        cl = (calls or {}).get("Calls") or []
        out["recent_calls"] = {
            "http": code,
            "calls": [
                {k: c.get(k) for k in ("Sid", "To", "Status", "Duration", "StartTime", "Price")}
                for c in (cl if isinstance(cl, list) else [])
            ],
        }
        # 5) Optional test call (credits USE hote)
        if "--call" in sys.argv:
            try:
                num = sys.argv[sys.argv.index("--call") + 1]
            except Exception:
                num = ""
            app_id = _env("EXOTEL_APP_ID") or _env("EXOTEL_FLOW_APP_ID")
            caller = _env("EXOTEL_CALLER_ID")
            if num and app_id and caller:
                data = {
                    "From": num if num.startswith("0") else f"0{num[-10:]}",
                    "CallerId": caller,
                    "CallType": "trans",
                    "TimeLimit": 60,
                    "Url": f"http://my.exotel.com/{SID}/exoml/start_voice/{app_id}",
                }
                try:
                    r = await client.post(
                        f"https://{HOST}/v1/Accounts/{SID}/Calls/connect.json",
                        data=data, headers=H, timeout=30.0,
                    )
                    j = r.json() if r.status_code == 200 else {"raw": r.text[:300]}
                    c = (j or {}).get("Call") or {}
                    out["test_call"] = {"http": r.status_code, "sid": c.get("Sid"), "status": c.get("Status"), "to": c.get("To")}
                except Exception as e:
                    out["test_call"] = {"error": str(e)[:200]}
            else:
                out["test_call"] = {"error": f"need number+EXOTEL_APP_ID+CALLER_ID (num={bool(num)}, app={bool(app_id)}, caller={bool(caller)})"}
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    asyncio.run(main())
