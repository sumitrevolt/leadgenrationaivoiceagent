#!/usr/bin/env python3
"""Idempotent .env key setter (VPS).

GENERIC mode:  python3 scripts/env_set.py KEY=VALUE [KEY=VALUE ...] [--file PATH]
               (existing key REPLACE, naya APPEND; backup .env.bak_envset_<ts>)
LEGACY mode:   python3 scripts/env_set.py     (no args — purana fixed P1/P3 set)

Secrets is file me kabhi nahi — sirf flag-style keys CLI se do.
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime

_DEFAULT_ENV = "/opt/leadgen/.env" if os.path.exists("/opt/leadgen/.env") else ".env"

# LEGACY fixed set (no-args mode — backward compatible).
LEGACY_SET = {
    "NOTIFY_EMAIL": "admin@leadsgenai.in",
    "AUTO_EMAIL_OUTREACH": "true",
    "USE_AGENTIC_RAG": "1",
    "USE_LANGGRAPH_SUPERVISOR": "1",
}
REPORT_ONLY = ["UPI_VPA", "POLLINATIONS_TOKEN"]


def apply(env_path: str, pairs: dict[str, str]) -> None:
    lines: list[str] = []
    if os.path.exists(env_path):
        backup = env_path + ".bak_envset_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy(env_path, backup)
        print(f"backup: {os.path.basename(backup)}")
        lines = open(env_path, encoding="utf-8").read().splitlines()

    seen: set[str] = set()
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        key = s.split("=", 1)[0].strip() if ("=" in s and not s.startswith("#")) else None
        if key and key.startswith("export "):
            key = key[len("export ") :].strip()
        if key in pairs:
            prefix = "export " if s.startswith("export ") else ""
            out.append(f"{prefix}{key}={pairs[key]}")
            seen.add(key)
        else:
            out.append(ln)
    for k, v in pairs.items():
        if k not in seen:
            out.append(f"{k}={v}")

    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("set:", ", ".join(pairs))


def main() -> int:
    args = list(sys.argv[1:])
    env_path = _DEFAULT_ENV
    if "--file" in args:
        i = args.index("--file")
        try:
            env_path = args[i + 1]
            del args[i : i + 2]
        except IndexError:
            print("--file needs a path", file=sys.stderr)
            return 2

    pairs: dict[str, str] = {}
    for a in args:
        if "=" in a:
            k, v = a.split("=", 1)
            if k.strip():
                pairs[k.strip()] = v
        else:
            print(f"skip (no '='): {a}", file=sys.stderr)

    if pairs:
        apply(env_path, pairs)
        return 0

    # LEGACY mode
    apply(env_path, LEGACY_SET)
    cur: dict[str, str] = {}
    for ln in open(env_path, encoding="utf-8"):
        if "=" in ln and not ln.strip().startswith("#"):
            cur[ln.split("=", 1)[0].strip()] = ln.split("=", 1)[1].strip()
    print("=== NEEDS USER VALUE (left unset — can't fabricate) ===")
    for k in REPORT_ONLY:
        print(f"  {k}: {'SET' if cur.get(k) else 'NOT SET (give me the value)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
