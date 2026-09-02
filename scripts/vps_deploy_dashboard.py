#!/usr/bin/env python3
"""One-shot VPS deploy smoke — delegate the release, then verify endpoints.

CONSOLIDATED 2026-07-26. This ran the whole release chain over SSH as one
remote string:

    cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q
    && compose build app && compose up -d --no-deps app && ...

`git reset --hard` discards uncommitted files, and this checkout still holds
the live invoice, consent and suppression ledgers plus DPDP call recordings.
Being remote made it no safer — it was simply an unguarded release path with
an SSH hop in front of it.

The remote command is now a single fixed invocation of the guarded canonical
parent. It is a constant with no interpolation, and the remote exit status is
returned verbatim so 90 (guard denied) and 91 (guard unavailable) reach the
operator unchanged instead of being flattened.
"""

import json
import subprocess
import sys
import time
import urllib.request

SSH = [
    r"C:\PROGRA~1\Git\usr\bin\ssh.exe",
    "-i",
    r"C:\Users\Ratanshila\.ssh\id_rsa",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=20",
    "root@72.61.245.204",
]
# Fixed constant: no f-string, no .format(), no caller-supplied value. The only
# mutation is inside the guarded parent, and the read-only checks after it run
# only because `&&` short-circuits on the parent's non-zero exit.
REMOTE = (
    "set -e; cd /opt/leadgen && "
    "bash scripts/deploy_vps.sh && "
    "sleep 16 && "
    "curl -sf http://127.0.0.1:8000/health && echo && "
    "curl -sf http://127.0.0.1:8000/api/admin/revenue-analytics | head -c 200 && echo"
)


def main() -> int:
    print("=== VPS RELEASE (delegated to guarded parent) ===")
    r = subprocess.run(SSH + [REMOTE], capture_output=True, text=True, timeout=900)
    print(r.stdout)
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    if r.returncode != 0:
        print(f"REMOTE_EXIT_{r.returncode}")
        return r.returncode

    print("=== PUBLIC HEALTH ===")
    for attempt in range(3):
        try:
            # Literal https:// constant, no caller input, so the file:/ and
            # custom-scheme risk B310 exists for cannot arise here.
            with urllib.request.urlopen(  # nosec B310  # noqa: S310
                "https://leadsgenai.in/health", timeout=20
            ) as resp:
                data = json.loads(resp.read().decode())
                print(json.dumps(data, indent=2))
                env = data.get("environment") or data.get("env")
                if env == "production":
                    print("HEALTH_OK production")
                    break
        except Exception as e:
            print(f"health attempt {attempt + 1} fail: {e}")
            time.sleep(8)
    else:
        print("HEALTH_WARN check manually")
        return 1

    print("=== SPOT CHECKS ===")
    for path in (
        "/app/admin",
        "/api/admin/revenue-analytics",
        "/api/customer/speed-to-lead",
    ):
        try:
            req = urllib.request.Request(f"https://leadsgenai.in{path}")
            # Scheme+host are a literal prefix and `path` comes from the
            # hard-coded tuple above, never from a caller.
            with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310  # noqa: S310
                print(f"{path} -> {resp.status}")
        except urllib.error.HTTPError as e:
            print(f"{path} -> HTTP {e.code} (expected for auth routes)")
        except Exception as e:
            print(f"{path} -> ERR {e}")

    print("DEPLOY_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
