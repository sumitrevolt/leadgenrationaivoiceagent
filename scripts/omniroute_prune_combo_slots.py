#!/usr/bin/env python3
"""Prune each OmniRoute combo to the providers that actually have credentials.

WHY (2026-09-25)
----------------
After seeding provider_connections, inference worked but was pathologically slow:
combos answered eventually, or hung past any sane client timeout. Two causes,
both visible in the gateway DB:

  1. Every combo declared 42 model slots across 42 distinct providers
     (opencode, opencode-zen, groq, cerebras, gemini, huggingface, openrouter,
     sambanova, together, fireworks, deepinfra, digitalocean, ollama-cloud,
     pollinations, siliconflow, volcengine, zhipu, alibaba, baidu, tencent,
     minimax, kimi, deepseek, iflytek, streamlake, telecom, sensetime, zeroone,
     mobile, kunlun, ai360, ppio, nvidia ...), but only SIX providers had
     credentials registered. So a single request walked ~36 credential-less
     providers before reaching a live one.

  2. Some of those slots name models that no longer exist on the provider, e.g.
     gemini-2.5-pro ("no longer available to new users") and
     llama-3.3-70b-versatile on Groq (404). The gateway retries them, which is
     what produced the long stalls.

A combo is a failover list, so a 42-entry list where 36 entries can never serve
is not redundancy, it is latency: the cheap lanes get starved behind dead ones
and the caller sees a timeout instead of an answer.

WHAT IT DOES
------------
Keeps only the slots whose providerId has an ACTIVE provider_connections row,
preserving the original order and the per-slot fields. It does NOT invent models
and does NOT touch providers that are already working.

SAFETY
------
  * Dry run unless --apply.
  * Full storage.sqlite (+ WAL) backup before any write.
  * Idempotent: a second run reports "no change" once the list is already pruned.
  * Refuses to write a combo down to zero models -- an empty combo is worse than
    a slow one, and it means the credential detection is wrong.
  * Prints provider names and slot counts only; no key material.

USAGE
-----
    python3 scripts/omniroute_prune_combo_slots.py            # dry run
    python3 scripts/omniroute_prune_combo_slots.py --apply
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
DB_NAME = "storage.sqlite"


def find_db_path() -> str:
    out = subprocess.run(
        [
            "docker",
            "inspect",
            GATEWAY_CONTAINER,
            "--format",
            '{{range .Mounts}}{{if eq .Destination "/root/.omniroute"}}{{.Source}}{{end}}{{end}}',
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    src = out.stdout.strip()
    if not src:
        raise SystemExit("could not resolve the /root/.omniroute volume mount source")
    return os.path.join(src, DB_NAME)


def backup(db_path: str) -> str:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = f"{db_path}.bak-pruneslots-{stamp}"
    shutil.copy2(db_path, dest)
    wal = db_path + "-wal"
    if os.path.exists(wal):
        shutil.copy2(wal, dest + "-wal")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default is dry run)")
    args = ap.parse_args()

    db_path = find_db_path()
    print(f"gateway db : {db_path}")
    print(f"mode       : {'APPLY' if args.apply else 'DRY RUN'}\n")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    active_providers = cur.execute(  # nosecurity
        "SELECT provider FROM provider_connections WHERE is_active = 1"
    )
    active = {r[0] for r in active_providers}
    print(f"providers with active credentials: {len(active)}")
    print(f"  {', '.join(sorted(active))}\n")

    if args.apply:
        bak = backup(db_path)
        print(f"backup: {bak}\n")

    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    total_dropped = 0
    blocked = 0

    for combo_id, name, data, sort_order in cur.execute(
        "SELECT id, name, data, sort_order FROM combos ORDER BY sort_order"
    ).fetchall():
        cfg = json.loads(data)
        slots = cfg.get("models", [])
        keep = [s for s in slots if s.get("providerId") in active]
        dropped = len(slots) - len(keep)

        if dropped == 0:
            print(f"  {name:<18} {len(slots):>2} slots  no change")
            continue

        if not keep:
            # An empty combo is strictly worse than a slow one: it can never
            # answer. Treat it as a hard stop rather than writing it.
            print(
                f"  {name:<18} {len(slots):>2} slots  BLOCKED - "
                "no slot has credentials, refusing to empty the combo"
            )
            blocked += 1
            continue

        print(
            f"  {name:<18} {len(slots):>2} -> {len(keep)} slots  (drop {dropped} credential-less)"
        )
        total_dropped += dropped

        if args.apply:
            cfg["models"] = keep
            cfg["updatedAt"] = now
            cur.execute(
                "UPDATE combos SET data = ?, updated_at = ? WHERE id = ?",
                (json.dumps(cfg), now, combo_id),
            )

    if args.apply:
        conn.commit()
    conn.close()

    print(f"\ntotal credential-less slots dropped: {total_dropped}")
    if blocked:
        print(f"combos blocked from being emptied  : {blocked}")
    if args.apply and total_dropped:
        print(f"\nrestart the gateway: docker restart {GATEWAY_CONTAINER}")
    elif not args.apply:
        print("\nDRY RUN - re-run with --apply to write")
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
