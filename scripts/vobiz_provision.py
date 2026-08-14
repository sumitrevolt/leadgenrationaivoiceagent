"""Provision Vobiz SIP trunk + credential via API (run on VPS from /opt/leadgen).

Reads VOBIZ_AUTH_ID/TOKEN from .env, creates an outbound trunk + SIP credential,
appends trunk details to .env. Prints a masked summary only.
"""

import json
import secrets
import sys
from pathlib import Path

import requests

ENV = Path(".env")


def env_get(key: str) -> str:
    for line in ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    return ""


AID = env_get("VOBIZ_AUTH_ID")
ATK = env_get("VOBIZ_AUTH_TOKEN")
if not AID or not ATK:
    sys.exit("VOBIZ creds .env me nahi mile")

BASE = f"https://api.vobiz.ai/api/v1/Account/{AID}"
H = {"X-Auth-ID": AID, "X-Auth-Token": ATK, "Content-Type": "application/json"}


def jprint(label, r):
    print(label, r.status_code, str(r.text)[:300])


# 0) Sanity: list existing trunks
r = requests.get(f"{BASE}/trunks", headers=H, timeout=20)
jprint("LIST trunks:", r)
existing = None
try:
    data = r.json()
    items = (
        data
        if isinstance(data, list)
        else data.get("trunks") or data.get("data") or data.get("objects") or []
    )
    for t in items:
        if t.get("name") == "leadgen-trunk":
            existing = t
            break
except Exception:
    pass

# 1) Create trunk (idempotent by name)
if existing:
    trunk = existing
    print("trunk already exists — reusing")
else:
    r = requests.post(
        f"{BASE}/trunks",
        headers=H,
        timeout=30,
        json={
            "name": "leadgen-trunk",
            "trunk_status": "enabled",
            "trunk_direction": "outbound",
            "concurrent_calls_limit": 5,
            "cps_limit": 2,
            "transport": "udp",
        },
    )
    jprint("CREATE trunk:", r)
    if r.status_code not in (200, 201):
        sys.exit("trunk create failed")
    trunk = r.json()

trunk_id = trunk.get("trunk_id") or trunk.get("id")
domain = trunk.get("trunk_domain") or f"{trunk_id}.sip.vobiz.ai"
print("TRUNK_ID:", trunk_id)
print("DOMAIN:", domain)

# 2) Create SIP credential (try common endpoint patterns)
sip_user = "leadgenfs"
sip_pass = secrets.token_urlsafe(18)
cred_ok = False
for path, payload in [
    (f"{BASE}/trunks/{trunk_id}/credentials", {"username": sip_user, "password": sip_pass}),
    (f"{BASE}/credentials", {"username": sip_user, "password": sip_pass, "trunk_id": trunk_id}),
]:
    r = requests.post(path, headers=H, json=payload, timeout=20)
    jprint(f"CRED try {path.split('/Account/')[1]}:", r)
    if r.status_code in (200, 201):
        cred_ok = True
        cred = r.json()
        cred_uuid = cred.get("credential_uuid") or cred.get("uuid") or cred.get("id") or ""
        break

if not cred_ok:
    print("CREDENTIAL CREATE FAILED — console me manually banana padega")
    sys.exit(2)

# 3) Attach credential to trunk (best-effort)
r = requests.put(
    f"{BASE}/trunks/{trunk_id}",
    headers=H,
    timeout=20,
    json={"credential_uuid": cred_uuid} if cred_uuid else {},
)
jprint("ATTACH cred->trunk:", r)

# 4) Persist to .env
with ENV.open("a", encoding="utf-8") as f:
    f.write(f"\nVOBIZ_TRUNK_ID={trunk_id}\nVOBIZ_TRUNK_DOMAIN={domain}\n")
    f.write(f"VOBIZ_SIP_USER={sip_user}\nVOBIZ_SIP_PASS={sip_pass}\n")
print("DONE — .env updated (trunk id/domain/sip user+pass). pass masked:", sip_pass[:4] + "***")
