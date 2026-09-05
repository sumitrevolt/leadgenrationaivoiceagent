#!/usr/bin/env python3
"""LeadGen Buzz enterprise coordination setup.

Creates #build (coding-agent bridge) + #staff-pulse (31/31 STAFF mirror),
wires memberships, topics, purposes, canvases. Read/write on Buzz relay only.
Touches NOTHING in prod, .env, team.py, or the repo working tree.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

BUZZ = Path(os.environ["LOCALAPPDATA"]) / "Buzz" / "buzz.exe"
RELAY = "https://leadsgenai.communities.buzz.xyz"
GUIDES = Path.home() / ".buzz" / "GUIDES"
CHANNEL_IDS = GUIDES / "CHANNEL_IDS.json"

OWNER = "1fb82b779689c60b13f10c49f19d15884349cc5accb5b329583f6a7441a6c1a0"
BOSS = "1b13ceccc2a6966064835fd942a55c8015a34a7c0f14a3462c0d845440f4e92f"
HONEY = "b9ffabcf66e8de5f7efa7ebae8fadaee8cc32e4f812ed54325a7f1fff4cf79c6"
FIZZ = "d2fd7e85404811241bad32516d5a68c95f660b122271da8130e35a076e61609d"
BUMBLE = "a546e85c1dad69937000a35ab260127268436c3d882711633d4c54a91d36b4e1"


class CREDENTIAL(ctypes.Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_char)), ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]


def owner_nsec() -> str:
    ptr = ctypes.c_void_p()
    assert ctypes.windll.advapi32.CredReadW("secrets.buzz-desktop", 1, 0, ctypes.byref(ptr))
    c = ctypes.cast(ptr, ctypes.POINTER(CREDENTIAL)).contents
    raw = ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize)
    ctypes.windll.advapi32.CredFree(ptr)
    return json.loads(raw.decode("utf-16-le").rstrip("\x00"))["identity"]


ENV = dict(os.environ)


def buzz(args, stdin_text=None):
    r = subprocess.run([str(BUZZ), "--relay", RELAY, "--format", "json", *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=ENV, input=stdin_text)
    out = (r.stdout or "").strip()
    try:
        parsed = json.loads(out) if out else None
    except Exception:
        parsed = out
    return r.returncode, parsed, (r.stderr or "").strip()


def step(label, args, stdin_text=None):
    rc, parsed, err = buzz(args, stdin_text)
    status = "OK " if rc == 0 else f"FAIL({rc})"
    detail = err[:180] if rc != 0 else ""
    print(f"[{status}] {label} {detail}")
    time.sleep(0.4)
    return rc, parsed


BUILD_CANVAS = """# #build — Coding Agent Bridge

**Plane:** developer tooling. NOT runtime STAFF, NOT prod control.

## Who posts here

| Prefix | Tool | Typical job |
|--------|------|-------------|
| `[CURSOR]` | Cursor | IDE-side edits, refactors, inline fixes |
| `[CLAUDE]` | Claude Code / Cowork | Multi-file changes, audits, loop-engineer runs |
| `[OPENCODE]` | OpenCode | Terminal-driven patches, scripted edits |
| `[MONKEY]` | Monkey Code | Experiments, throwaway spikes |

Every message MUST start with the prefix. No prefix = untraceable = ignore it.

## Claim-before-edit (hard rule)

The repo tree is chronically dirty and multiple tools edit it at once.
Truncation and lost edits have already happened. So:

1. **CLAIM** before touching files:
   `[CLAUDE] CLAIM app/api/growth_revenue.py, tests/test_billing_truth_2026.py — reason: ADR-159 canary`
2. **RELEASE** when done:
   `[CLAUDE] RELEASE app/api/growth_revenue.py — 3 tests green, exit 0`
3. If a file is already claimed, **do not edit it**. Post `[TOOL] BLOCKED ON <file> (held by <tool>)` and pick different work.
4. Claims older than 4 hours are stale — anyone may post `STALE-BREAK <file>` and take it.

Machine-readable mirror: `docs/coordination/LOCKS.json` in the repo.

## Handoff format

```
[TOOL] HANDOFF -> <next tool>
Goal:      <one line>
Done:      <what actually landed>
Evidence:  <exit codes / pytest / /health.version>
Left:      <precise next step>
Touched:   <file list>
```

## Non-negotiable

- Never `git add -A`. Stage explicit paths only.
- No commit / push / deploy without owner asking. Deploy = `scripts/deploy_vps.sh` + `APP_VERSION=<sha>`.
- Evidence beats prose. Exit code or it did not happen.
- Secrets never in a message. Env var NAMES fine, values never.
- Swara / voice path = FROZEN.
"""

PULSE_CANVAS = """# #staff-pulse — 31/31 Runtime STAFF Mirror

**Read-only.** This channel observes; it does not command.

## Chain of control

```
Buzz (#admin)  ->  Boss  ->  Owner OS / OpenClaw  ->  31 runtime STAFF  ->  Celery
```

Commands go to **Boss only**. There are no direct staff mutation hooks from Buzz.
Buzz never becomes a second control plane.

## Roster (canonical = app/platform/team.py — code wins)

**Coordination (1):** Boss

**Platform (12):** Kavya · Hermes · Nikhil · Vikram · Guru · Pranav · Vidya ·
Arnav · Kabir · Diya · Aryan · Arya

**Marketing (10):** Isha · Dev · Rohan · Ravi · Neha · Kiran · Priya · Zara ·
Anika · Ira

**Voice (8):** Swara · Tara · Arjun · Meera · Ananya · Riya · Lekha · Raksha

Total 1 + 12 + 10 + 8 = **31**.

## What lands here

Pulse posts carry: agent, last run, outcome, queue depth, blockers.
Format: `[PULSE] <division> | <agent> | <last_run> | <ok|warn|fail> | <note>`

## Decision tiers

- **GREEN** — agent executes itself, reports after.
- **AMBER** — Boss decides; Council consulted where relevant.
- **RED** — refused by the system. DND, TRAI window, consent, DPDP,
  secret exposure, destructive ops. Boss cannot bypass these either.
- **Human gate** — exactly one: real UPI bank-credit confirmation and
  paid-ledger marking. `UPI_AUTO_ACTIVATE` stays fail-closed.

Full policy: `~/.buzz/GUIDES/AUTONOMY_POLICY.md`
"""


NEW_CHANNELS = [
    {
        "name": "build",
        "description": "Coding-agent bridge: Cursor / Claude / OpenCode / Monkey Code. Claim-before-edit file locks, handoffs, evidence.",
        "topic": "Coding agent coordination - CLAIM before you edit",
        "purpose": "Cursor, Claude Code, OpenCode and Monkey Code coordinate repo work here. Prefix every message, claim files before editing, hand off with evidence.",
        "canvas": BUILD_CANVAS,
    },
    {
        "name": "staff-pulse",
        "description": "Read-only mirror of the 31 runtime STAFF agents. Health, workload, blockers. Commands go to Boss only.",
        "topic": "31/31 runtime STAFF mirror - read only",
        "purpose": "Live pulse of all 31 runtime STAFF agents. Observation plane only: Buzz never mutates STAFF directly, commands route through Boss.",
        "canvas": PULSE_CANVAS,
    },
]

ROSTER = [(BOSS, "admin"), (HONEY, "member"), (FIZZ, "member"), (BUMBLE, "member")]
CORE_EXISTING = ("admin", "leadgen", "gtm", "ops", "revenue", "dev")


def load_ids() -> dict:
    raw = CHANNEL_IDS.read_text(encoding="utf-8-sig")
    return json.loads(raw)


def main():
    ENV["BUZZ_PRIVATE_KEY"] = owner_nsec()
    ids = load_ids()
    print("== existing channel ids:", len(ids))

    rc, chans, _ = buzz(["channels", "list"])
    by_name = {}
    for c in (chans if isinstance(chans, list) else []):
        by_name.setdefault(c.get("name"), c.get("channel_id"))

    # 1. create / reuse the two new channels
    for spec in NEW_CHANNELS:
        name = spec["name"]
        cid = by_name.get(name)
        if cid:
            print(f"[SKIP] channel '{name}' already exists -> {cid}")
        else:
            rc, out = step(f"create channel #{name}", [
                "channels", "create", "--name", name, "--type", "stream",
                "--visibility", "private", "--description", spec["description"],
            ])
            cid = (out or {}).get("channel_id") if isinstance(out, dict) else None
            if not cid:
                print(f"   !! could not create #{name}, skipping wiring")
                continue
        ids[name] = cid
        spec["cid"] = cid

        step(f"topic #{name}", ["channels", "topic", "--channel", cid, "--topic", spec["topic"]])
        step(f"purpose #{name}", ["channels", "purpose", "--channel", cid, "--purpose", spec["purpose"]])

        step(f"canvas #{name}", ["canvas", "set", "--channel", cid, "--content", "-"],
             stdin_text=spec["canvas"])

        for pk, role in ROSTER:
            step(f"member {pk[:8]} -> #{name} ({role})", [
                "channels", "add-member", "--channel", cid, "--pubkey", pk, "--role", role,
            ])

    # 2. restore Boss on the existing core channels
    for name in CORE_EXISTING:
        cid = ids.get(name)
        if not cid:
            continue
        role = "admin" if name in ("admin", "leadgen") else "member"
        step(f"restore Boss -> #{name} ({role})", [
            "channels", "add-member", "--channel", cid, "--pubkey", BOSS, "--role", role,
        ])

    CHANNEL_IDS.write_text(json.dumps(ids, indent=4), encoding="utf-8")
    print("== CHANNEL_IDS.json updated:", json.dumps(ids, indent=2))


if __name__ == "__main__":
    main()
