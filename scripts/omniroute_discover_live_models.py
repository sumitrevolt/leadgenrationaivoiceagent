#!/usr/bin/env python3
"""Discover which model IDs each seeded provider actually serves RIGHT NOW.

2026-09-25: after seeding credentials and pruning credential-less combo slots,
combos still timed out. The remaining slots named models the providers no longer
serve -- Groq 404 on `llama-3.3-70b-versatile`, Cerebras "Model does not exist",
Google "gemini-2.5-pro is no longer available to new users". A credential that
works and a model id that exists are separate facts; only the first was proven.

This asks each provider's own /models endpoint (using the same key that is
registered in provider_connections) and reports live model IDs per provider, so
combo slots can be pointed at models that actually exist. It prints model IDs and
key LENGTHS only, never key material.

USAGE
-----
    python3 scripts/omniroute_discover_live_models.py            # human table
    python3 scripts/omniroute_discover_live_models.py --json     # machine JSON
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys

DB = "/var/lib/docker/volumes/leadgen_omniroute_data/_data/storage.sqlite"

# provider -> (models URL, auth header name, response JSON path to model ids)
PROVIDERS: dict[str, tuple[str, str, str]] = {
    "groq": (
        "https://api.groq.com/openai/v1/models",
        "Authorization: Bearer {key}",
        "data[].id",
    ),
    "cerebras": (
        "https://api.cerebras.ai/v1/models",
        "Authorization: Bearer {key}",
        "data[].id",
    ),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/models",
        "x-goog-api-key: {key}",
        "models[].name",
    ),
    "nvidia": (
        "https://integrate.api.nvidia.com/v1/models",
        "Authorization: Bearer {key}",
        "data[].id",
    ),
    "openrouter": (
        "https://openrouter.ai/api/v1/models",
        "Authorization: Bearer {key}",
        "data[].id",
    ),
    "mistral": (
        "https://api.mistral.ai/v1/models",
        "Authorization: Bearer {key}",
        "data[].id",
    ),
}


def read_keys() -> dict[str, str]:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    out = dict(conn.execute(
        "SELECT provider, api_key FROM provider_connections WHERE is_active = 1"
    ))
    conn.close()
    return out


def fetch(url: str, header: str, key: str, timeout: int = 25) -> list[str]:
    r = subprocess.run(
        ["curl", "-s", "--max-time", str(timeout), url, "-H", header.format(key=key)],
        capture_output=True, text=True, timeout=timeout + 10,
    )
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    # Every one of these endpoints returns a LIST of model objects, but under a
    # different key ("data" for the OpenAI-shaped ones, "models" for Google) and
    # with the id under a different field ("id" vs "name"). Rather than encode
    # that per-provider, take any list of dicts carrying an "id" or "name".
    ids: list[str] = []
    stack: list[object] = [d]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("id", "name") and isinstance(v, str) and v:
                    ids.append(v)
                stack.append(v)
        elif isinstance(node, list):
            stack.extend(node)
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--filter", default="", help="substring filter on model id")
    args = ap.parse_args()

    keys = read_keys()
    result: dict[str, list[str]] = {}

    for provider, (url, header, _p) in PROVIDERS.items():
        key = keys.get(provider)
        if not key:
            print(f"{provider:<11} NO CREDENTIAL")
            result[provider] = []
            continue
        ids = fetch(url, header, key)
        # The generic walk also picks up non-model ids; keep plausible ones and
        # drop the "models/" prefix Google uses.
        ids = [
            i for i in ids
            if "/" in i or "-" in i
        ]
        if args.filter:
            ids = [i for i in ids if args.filter in i.lower()]
        ids = [i.replace("models/", "") for i in ids]
        result[provider] = sorted(ids)
        print(f"{provider:<11} key_len={len(key):<3} {len(ids)} live models")
        for i in sorted(ids)[:12]:
            print(f"              {i}")

    if args.json:
        print("---JSON---")
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
