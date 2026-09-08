"""Hostinger DNS API helper — manage leadsgenai.in DNS records safely.

Reads HOSTINGER_API_TOKEN from env or /opt/leadgen/.env (never prints it).
Endpoints: GET/PUT /api/dns/v1/zones/{domain} + POST .../validate.

Usage (on the VPS):
  python scripts/hostinger_dns.py get        # show current TXT / _dmarc records
  python scripts/hostinger_dns.py validate   # validate the new _dmarc (no change)
  python scripts/hostinger_dns.py put         # apply (overwrite=false -> only _dmarc TXT)

Only touches the _dmarc TXT record. SPF (@ TXT), DKIM (CNAMEs) and MX are untouched
(overwrite=false + a single targeted record).
"""

import json
import os
import sys
import urllib.error
import urllib.request

DOMAIN = "leadsgenai.in"
BASE = f"https://developers.hostinger.com/api/dns/v1/zones/{DOMAIN}"

# 2026-07-02 upgrade: p=none -> p=quarantine. SPF + DKIM (hostingermail-a) dono
# live/aligned verified, outbound volume chhota (cap 25/day) — direct quarantine safe.
# Spoofed mail ab spam me jayegi; rua reports admin@ pe aate rahenge.
NEW_DMARC = "v=DMARC1; p=quarantine; rua=mailto:admin@leadsgenai.in; fo=1"
PAYLOAD = {
    "overwrite": False,
    "zone": [{"name": "_dmarc", "type": "TXT", "ttl": 3600, "records": [{"content": NEW_DMARC}]}],
}

# Delete ALL _dmarc TXT records (used by `fix` to collapse duplicates back to one).
DELETE_PAYLOAD = {"filters": [{"name": "_dmarc", "type": "TXT"}]}


def _token() -> str:
    t = os.environ.get("HOSTINGER_API_TOKEN")
    if t:
        return t.strip()
    for path in ("/opt/leadgen/.env", ".env"):
        try:
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if line.startswith("HOSTINGER_API_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            continue
    return ""


def _req(method: str, url: str, body=None):
    tok = _token()
    if not tok:
        print("NO_TOKEN (HOSTINGER_API_TOKEN not found)")
        sys.exit(2)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + tok,
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Cloudflare on developers.hostinger.com bans default python-urllib UA (err 1010)
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "get"
    if cmd == "get":
        st, body = _req("GET", BASE)
        print("GET status", st)
        try:
            recs = json.loads(body)
            items = recs if isinstance(recs, list) else recs.get("data", recs)
            for r in items:
                nm = str(r.get("name", ""))
                if (
                    r.get("type") in ("TXT", "MX")
                    or "dmarc" in nm.lower()
                    or "domainkey" in nm.lower()
                ):
                    print(json.dumps(r, ensure_ascii=False))
        except Exception:
            print(body[:1800])
    elif cmd == "validate":
        st, body = _req("POST", BASE + "/validate", PAYLOAD)
        print("VALIDATE status", st, "->", body[:600])
    elif cmd == "put":
        st, body = _req("PUT", BASE, PAYLOAD)
        print("PUT status", st, "->", body[:600])
    elif cmd == "delete":
        st, body = _req("DELETE", BASE, DELETE_PAYLOAD)
        print("DELETE status", st, "->", body[:600])
    elif cmd == "fix":
        # collapse _dmarc to exactly one correct record: delete all, then add one.
        st, body = _req("DELETE", BASE, DELETE_PAYLOAD)
        print("DELETE status", st, "->", body[:300])
        st2, body2 = _req("PUT", BASE, PAYLOAD)
        print("PUT status", st2, "->", body2[:300])
    else:
        print("unknown cmd:", cmd)


if __name__ == "__main__":
    main()
