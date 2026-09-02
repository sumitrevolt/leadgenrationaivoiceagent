"""Hostinger DNS — ek A record ADD karo (subdomain → IP).

Usage (VPS ya local, .env me HOSTINGER_API_TOKEN chahiye):
    python3 scripts/dns_add_a.py <name> <ip> [ttl]
    python3 scripts/dns_add_a.py ntfy 72.61.245.204

GOTCHA (CLAUDE.md): PUT overwrite=false = ADD (replace nahi) — naya subdomain ke
liye perfect. overwrite=true KABHI nahi (zone partial-overwrite = site down).
Browser UA header zaroori warna Cloudflare err-1010.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

DOMAIN = "leadsgenai.in"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _token() -> str:
    tok = os.environ.get("HOSTINGER_API_TOKEN", "").strip()
    if tok:
        return tok
    for envpath in (".env", "/opt/leadgen/.env"):
        try:
            with open(envpath, encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("HOSTINGER_API_TOKEN="):
                        return line.split("=", 1)[1].strip().strip('"')
        except OSError:
            continue
    return ""


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    name, ip = sys.argv[1].strip(), sys.argv[2].strip()
    ttl = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    tok = _token()
    if not tok:
        print("ERROR: HOSTINGER_API_TOKEN nahi mila (.env)")
        return 1
    body = json.dumps(
        {
            "overwrite": False,  # ADD semantics — zone untouched
            "zone": [{"name": name, "type": "A", "ttl": ttl, "records": [{"content": ip}]}],
        }
    ).encode()
    req = urllib.request.Request(
        f"https://developers.hostinger.com/api/dns/v1/zones/{DOMAIN}",
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
            "User-Agent": UA,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        print("status", r.status, r.read().decode()[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
