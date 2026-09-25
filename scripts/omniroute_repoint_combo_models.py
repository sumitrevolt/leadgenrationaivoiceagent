#!/usr/bin/env python3
"""Repoint combo slots at model IDs the providers actually serve.

2026-09-25, the third and final layer of the same outage. Seeding credentials and
pruning credential-less slots were both necessary and both insufficient:

  * provider_connections was empty        -> "No active credentials for provider"
  * 36 of 42 slots had no credential      -> the gateway walked dead providers
  * the 8 remaining slots named RETIRED models -> 404 / "no longer available"

Observed on the surviving slots of every combo:

    groq/llama-3.3-70b-versatile        -> 404 model does not exist
    groq/deepseek-r1-distill-llama-70b  -> 404
    cerebras/llama-3.3-70b              -> 404 model does not exist
    gemini/gemini-2.0-flash             -> retired
    gemini/gemini-1.5-pro               -> retired
    openrouter/.../llama-3.3-70b-instruct:free -> 404

A slot is a promise that some model can answer. A retired model id makes the slot
a dead entry in a failover list: it cannot serve, but it still costs a round trip
and, on the retry budget, the whole request.

WHAT IT DOES
------------
For each provider, asks the provider's own /models endpoint (using the registered
key) and rewrites each slot's `model` to a live id of the SAME provider, chosen
deterministically. A provider with no live id left keeps its slots untouched and is
reported, so a genuine credential/subscription problem is never masked.

Candidate preference, per provider, is a short explicit list of known-good
inference models; when none of those are offered the first live id is used. Slots
are only ever repointed within their own provider -- a combo lane never silently
changes vendor.

SAFETY
------
  * Dry run unless --apply.
  * Full DB (+WAL) backup before any write.
  * Idempotent: a re-run reports "no change" when every slot already resolves.
  * A slot is never dropped here; pruning is omniroute_prune_combo_slots.py's job.
  * Prints model ids only; never key material.

USAGE
-----
    python3 scripts/omniroute_repoint_combo_models.py            # dry run
    python3 scripts/omniroute_repoint_combo_models.py --apply
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

GATEWAY_CONTAINER = "leadgen_omniroute"
DB_NAME = "storage.sqlite"

PROVIDER_URL: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1/models",
    "cerebras": "https://api.cerebras.ai/v1/models",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
    "nvidia": "https://integrate.api.nvidia.com/v1/models",
    "openrouter": "https://openrouter.ai/api/v1/models",
    "mistral": "https://api.mistral.ai/v1/models",
}

# Preferred live inference models per provider, best first. Only models actually
# returned by the provider's /models endpoint are used, so this is a preference
# order, never a source of model ids.
PREFERRED: dict[str, list[str]] = {
    "groq": ["qwen/qwen3.8-27b", "allam-2-7b", "openai/gpt-oss-120b"],
    "cerebras": ["gpt-oss-120b", "qwen-3.8-27b"],
    "gemini": ["gemini-2.5-flash", "gemini-2.5-flash-lite"],
    "nvidia": [
        "deepseek-ai/deepseek-v4.1-flash",
        "nvidia/nemotron-3-super-120b-a12b",
        "qwen/qwen3-coder-480b-a35b-instruct",
    ],
    "openrouter": [
        "nvidia/nemotron-3.5-lightning:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ],
    "mistral": ["codestral-2508", "mistral-large-latest", "mistral-small-latest"],
}


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
    dest = f"{db_path}.bak-repoint-{stamp}"
    shutil.copy2(db_path, dest)
    wal = db_path + "-wal"
    if os.path.exists(wal):
        shutil.copy2(wal, dest + "-wal")
    return dest


def live_ids(provider: str, key: str) -> list[str]:
    url = PROVIDER_URL.get(provider)
    if not url:
        return []
    if provider == "gemini":
        header = ["-H", f"x-goog-api-key: {key}"]
    else:
        header = ["-H", f"Authorization: Bearer {key}"]
    r = subprocess.run(
        ["curl", "-s", "--max-time", "25", url, *header],
        capture_output=True,
        text=True,
        timeout=40,
    )
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    ids: list[str] = []
    stack: list[object] = [d]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("id", "name") and isinstance(v, str) and ("/" in v or "-" in v):
                    ids.append(v.replace("models/", ""))
                stack.append(v)
        elif isinstance(node, list):
            stack.extend(node)
    return sorted(set(ids))


def pick(provider: str, ids: list[str], n: int) -> list[str]:
    """Deterministic choice of n distinct live ids for one provider."""
    lowered = {i.lower(): i for i in ids}
    ordered: list[str] = []
    for want in PREFERRED.get(provider, []):
        hit = lowered.get(want.lower())
        if hit and hit not in ordered:
            ordered.append(hit)
    for i in ids:
        if len(ordered) >= n:
            break
        if i not in ordered:
            ordered.append(i)
    return ordered[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default is dry run)")
    args = ap.parse_args()

    db_path = find_db_path()
    print(f"gateway db : {db_path}")
    print(f"mode       : {'APPLY' if args.apply else 'DRY RUN'}\n")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    keys = dict(
        # nosecurity: fixed literal against our own gateway table, no user input.
        cur.execute(  # nosecurity
            "SELECT provider, api_key FROM provider_connections WHERE is_active = 1"
        )
    )

    if args.apply:
        bak = backup(db_path)
        print(f"backup: {bak}\n")

    # Which providers appear in the combos at all, and how many slots each has.
    needed: dict[str, int] = {}
    # nosecurity: fixed literal, no user input -- the rule bans every literal
    # .execute("SELECT...") and this query interpolates nothing.
    for (data,) in cur.execute("SELECT data FROM combos WHERE data IS NOT NULL"):  # nosecurity
        for s in json.loads(data).get("models", []):
            pid = s.get("providerId")
            if pid:
                needed[pid] = needed.get(pid, 0) + 1

    chosen: dict[str, list[str]] = {}
    for provider in sorted(needed):
        key = keys.get(provider)
        if not key:
            print(f"  {provider:<11} NO CREDENTIAL - slots left untouched")
            continue
        ids = live_ids(provider, key)
        want = needed[provider]
        sel = pick(provider, ids, want)
        chosen[provider] = sel
        print(f"  {provider:<11} {len(ids):>4} live / {want:>2} slots needed -> {len(sel)} chosen")
        for i in sel[:4]:
            print(f"                 {i}")

    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    changed_combos = 0
    changed_slots = 0
    unmapped: set[str] = set()

    for combo_id, name, data in cur.execute(
        "SELECT id, name, data FROM combos ORDER BY sort_order"
    ).fetchall():
        cfg = json.loads(data)
        dirty = False
        # Round-robin the chosen ids per provider so a provider with several slots
        # spreads across distinct live models rather than repeating one.
        counters: dict[str, int] = {}
        for s in cfg.get("models", []):
            pid = s.get("providerId")
            pool = chosen.get(pid)
            if not pool:
                if pid not in keys:
                    unmapped.add(pid)
                continue
            k = counters.get(pid, 0)
            counters[pid] = k + 1
            new_id = pool[k % len(pool)]
            # Compare against the FULLY QUALIFIED id, not the bare provider
            # model id. Comparing the bare id to the stored "provider/model"
            # string made every slot look changed on every run, so the script
            # reported work that it had not actually done.
            qualified = f"{pid}/{new_id}"
            if qualified != s.get("model"):
                s["model"] = qualified
                s["label"] = f"{pid}-{new_id.split('/')[-1]}"[:60]
                dirty = True
                changed_slots += 1
        if dirty:
            print(f"  {name:<18} repointed")
            if args.apply:
                cfg["updatedAt"] = now
                cur.execute(
                    "UPDATE combos SET data = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(cfg), now, combo_id),
                )
            changed_combos += 1
        else:
            print(f"  {name:<18} no change")

    if args.apply:
        conn.commit()
    conn.close()

    print(f"\ncombos changed: {changed_combos}   slots repointed: {changed_slots}")
    if unmapped:
        print(f"no credential, slots untouched: {', '.join(sorted(unmapped))}")
    if args.apply and changed_slots:
        print(f"\nrestart the gateway: docker restart {GATEWAY_CONTAINER}")
    elif not args.apply:
        print("\nDRY RUN - re-run with --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
