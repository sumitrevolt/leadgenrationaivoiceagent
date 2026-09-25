#!/usr/bin/env python3
"""Seed OmniRoute `provider_connections` from the app container's provider env.

WHY THIS EXISTS (2026-09-25)
---------------------------
`mcp__leadgen_admin_harness__omniroute_self_heal` reported success, but it only
re-seeds the 14 COMBOS and syncs LOCAL client config files. It never touches the
gateway's credential store. On srv1736379 the gateway's storage.sqlite had:

    combos                 = 14 rows
    provider_connections   =  0 rows   <-- no upstream providers at all
    provider_nodes         =  0 rows
    registered_keys        =  0 rows

So every combo resolved to a model that had no provider behind it, and inference
failed for all of them:

    POST /v1/chat/completions  ->  "No active credentials for provider: anthropic"
    POST /v1/chat/completions  ->  "Maximum combo retry limit reached"

Meanwhile the KEYS were fine -- they live in the `leadgen_app` container env.
The gateway simply never had them. That is the whole blocker, and it is why the
`/health` probe in the admin harness reported "401 Unauthorized" while
`/v1/models` returned 200: the gateway was up, just credential-less.

WHAT IT DOES
------------
Copies provider API keys out of the app container's environment into
`provider_connections` rows in the gateway's storage.sqlite. Idempotent: an
existing active connection for a provider is updated in place, never duplicated.

SAFETY
------
  * READ-ONLY about secrets -- key values are copied between two local
    processes on the same host and are never printed, logged, or returned.
    Only provider NAME + a length fingerprint is printed.
  * BACKUP-FIRST -- a timestamped copy of storage.sqlite is taken before any
    write, and the whole run is a no-op dry-run unless --apply is passed.
  * Idempotent -- safe to re-run.

USAGE
-----
    # from the VPS, as root
    python3 scripts/omniroute_seed_provider_connections.py            # dry run
    python3 scripts/omniroute_seed_provider_connections.py --apply     # write

Then restart the gateway so it reloads its credential store:

    docker restart leadgen_omniroute
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

GATEWAY_CONTAINER = "leadgen_omniroute"
APP_CONTAINER = "leadgen_app"
DB_NAME = "storage.sqlite"

# provider name in OmniRoute -> env var carrying its key in the app container.
# Only free/owned-tier lanes the platform actually uses are mapped; a paid
# dependency would violate the "free AI stack only" mandate.
PROVIDER_ENV_MAP: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}


def find_db_path() -> str:
    """Locate the gateway DB inside its volume, from a host-side mount point."""
    out = subprocess.run(
        [
            "docker", "inspect", GATEWAY_CONTAINER,
            "--format", "{{range .Mounts}}{{if eq .Destination \"/root/.omniroute\"}}{{.Source}}{{end}}{{end}}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    src = out.stdout.strip()
    if not src:
        raise SystemExit("could not resolve the /root/.omniroute volume mount source")
    return os.path.join(src, DB_NAME)


def read_app_provider_keys() -> dict[str, str]:
    """Read provider keys from the app container env. Values never leave here."""
    script = (
        "import os,json\n"
        "m=" + json.dumps(PROVIDER_ENV_MAP) + "\n"
        "out={}\n"
        "for p,var in m.items():\n"
        "    v=os.environ.get(var) or ''\n"
        "    if v.strip(): out[p]=v.strip()\n"
        "print(json.dumps(out))\n"
    )
    out = subprocess.run(
        ["docker", "exec", APP_CONTAINER, "python3", "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout.strip() or "{}")


def backup(db_path: str) -> str:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = f"{db_path}.bak-seedproviders-{stamp}"
    shutil.copy2(db_path, dest)
    # The WAL holds committed-but-not-checkpointed rows; copy it too so the
    # backup is a consistent snapshot rather than a torn one.
    wal = db_path + "-wal"
    if os.path.exists(wal):
        shutil.copy2(wal, dest + "-wal")
    return dest


def seed(db_path: str, keys: dict[str, str], apply: bool) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    changed = 0

    for provider, key in sorted(keys.items()):
        row = cur.execute(
            "SELECT id, is_active, api_key FROM provider_connections "
            "WHERE provider = ? ORDER BY is_active DESC LIMIT 1",
            (provider,),
        ).fetchone()

        if row is None:
            conn_id = str(uuid.uuid4())
            if apply:
                # created_at / updated_at are the only NOT NULL columns without a
                # DEFAULT, so both are required on INSERT.
                cur.execute(
                    "INSERT INTO provider_connections "
                    "(id, provider, auth_type, name, is_active, api_key, "
                    " created_at, updated_at, last_health_check_at) "
                    "VALUES (?,?,?,?,1,?,?,?,?)",
                    (conn_id, provider, "api_key", f"{provider}-seed", key, now, now, now),
                )
            action = "INSERT"
        else:
            conn_id, is_active, existing = row
            if existing == key and int(is_active or 0) == 1:
                print(f"  [{provider:<11}] already active and current - no change")
                continue
            if apply:
                cur.execute(
                    "UPDATE provider_connections "
                    "SET api_key = ?, is_active = 1, auth_type = 'api_key', "
                    "    updated_at = ? "
                    "WHERE id = ?",
                    (key, now, conn_id),
                )
            action = "UPDATE"

        changed += 1
        # Length-only fingerprint: enough to prove a value landed, never the value.
        print(f"  [{provider:<11}] {action:<6} conn={conn_id[:8]} key_len={len(key)}")

    if apply:
        conn.commit()
    conn.close()
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default is dry run)")
    args = ap.parse_args()

    db_path = find_db_path()
    print(f"gateway db : {db_path}")
    print(f"mode       : {'APPLY' if args.apply else 'DRY RUN'}")

    keys = read_app_provider_keys()
    if not keys:
        print("no provider keys found in the app container env - nothing to seed")
        return 1
    print(f"keys found : {len(keys)} ({', '.join(sorted(keys))})\n")

    before = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True).execute(
        "SELECT COUNT(*) FROM provider_connections"
    ).fetchone()[0]
    print(f"provider_connections before: {before}")

    if args.apply:
        bak = backup(db_path)
        print(f"backup     : {bak}\n")

    n = seed(db_path, keys, apply=args.apply)

    after = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True).execute(
        "SELECT COUNT(*) FROM provider_connections"
    ).fetchone()[0]
    print(f"\nprovider_connections after : {after}")
    print(f"rows written               : {n}")

    if args.apply and n:
        print("\nrestart the gateway to reload credentials:")
        print(f"  docker restart {GATEWAY_CONTAINER}")
    elif not args.apply:
        print("\nDRY RUN - re-run with --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
