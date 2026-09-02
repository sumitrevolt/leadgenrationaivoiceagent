"""Vobiz account state probe: balance, KYC, DID search/buy attempt (run on VPS)."""

import sys

sys.path.insert(0, "/opt/leadgen")
from pathlib import Path

import requests

ENV = Path("/opt/leadgen/.env")


def env_get(key):
    for line in ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    return ""


AID = env_get("VOBIZ_AUTH_ID")
H = {
    "X-Auth-ID": AID,
    "X-Auth-Token": env_get("VOBIZ_AUTH_TOKEN"),
    "Content-Type": "application/json",
}
B = f"https://api.vobiz.ai/api/v1/Account/{AID}"


def t(label, method, url, **kw):
    try:
        r = requests.request(method, url, headers=H, timeout=20, allow_redirects=True, **kw)
        print(f"{label}: {r.status_code} {str(r.text)[:260]}")
        return r
    except Exception as e:
        print(f"{label}: EXC {e}")


# Account details / balance
t("ACCOUNT /", "GET", f"{B}/")
# Phone number endpoints (common patterns)
t("DID search IN", "GET", f"{B}/PhoneNumber/?country_iso=IN&limit=5")
t("DID search alt", "GET", f"{B}/PhoneNumber/", params={"country": "IN"})
t("My numbers", "GET", f"{B}/Number/")
t("My numbers alt", "GET", f"{B}/numbers")
