#!/usr/bin/env python3
"""Recreate the canonical LeadGen Buzz workspace on the LOCAL relay.

Owner decision 2026-08-10: local-first relay (ws://localhost:3000). This script
creates the canonical channel structure on the local relay with FRESH local IDs
and regenerates ~/.buzz/GUIDES/CHANNEL_IDS.json. Hosted-relay IDs are NEVER reused.

NOTE (2026-08-11 fix): relay URL MUST use host `localhost`, NOT `127.0.0.1` — the
relay routes communities by HTTP Host header (BUZZ_DOMAIN=localhost) and
`127.0.0.1` gets "no community is configured for this host" 404 on sends.

Channels: #admin #leadgen #build #dev #ops #revenue #gtm #staff-pulse (private).
Members: owner (creator) + the 4 Desktop agents (Boss/Honey/Fizz/Bumble) with
canonical roles: Boss+Honey admin on #admin/#leadgen, members elsewhere.

Idempotent: channels already present are reused (no duplicates); member add is
role-ensured. Safe to re-run.

CLI note (Buzz Desktop): `channels search` takes `--query`/`--exact` (NOT
`--name`). Channel objects expose `channel_id` (not always `id`). This script
lists first, then exact-search as fallback, so a wrong search flag cannot
create a second #admin/#build/... on every re-run.

Usage:
    python scripts/buzz_local_workspace.py
    python scripts/buzz_local_workspace.py --archive-dupes
    BUZZ_RELAY=ws://localhost:3000 python scripts/buzz_local_workspace.py
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

BUZZ = Path(os.environ["LOCALAPPDATA"]) / "Buzz" / "buzz.exe"
APPDATA = Path(os.environ["APPDATA"]) / "xyz.block.buzz.app"
AGENTS_PATH = APPDATA / "agents" / "managed-agents.json"
CHANNEL_IDS = Path.home() / ".buzz" / "GUIDES" / "CHANNEL_IDS.json"

RELAY = os.environ.get("BUZZ_RELAY", "ws://localhost:3000")

CANONICAL = [
    ("admin", "Owner decisions, launch readiness, routing"),
    ("leadgen", "Primary project home"),
    ("build", "Work mirrors - buzzlock claim/work/release + implementation progress"),
    ("dev", "Code, tests, PRs, reviewed outcomes"),
    ("ops", "Health, deploy, WAHA, queues/DLQ"),
    ("revenue", "Billing / UPI / pay-truth (no fake PAID)"),
    ("gtm", "Hot Queue to 2nd paid Marketing customer"),
    ("staff-pulse", "Read-only 31/31 runtime STAFF pulse"),
]
ADMIN_ROLE_CHANNELS = ("admin", "leadgen")
ADMIN_ROLE_AGENTS = ("Boss", "Honey")


class CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def owner_nsec() -> str:
    """Owner identity from Windows Credential Manager. Never logged, never written."""
    ptr = ctypes.c_void_p()
    if not ctypes.windll.advapi32.CredReadW("secrets.buzz-desktop", 1, 0, ctypes.byref(ptr)):
        raise RuntimeError("Buzz desktop credential not found")
    cred = ctypes.cast(ptr, ctypes.POINTER(CREDENTIAL)).contents
    raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
    ctypes.windll.advapi32.CredFree(ptr)
    return json.loads(raw.decode("utf-16-le").rstrip("\x00"))["identity"]


def buzz(args: list[str], env: dict) -> tuple[int, object, str]:
    cmd = [str(BUZZ), "--relay", RELAY, "--format", "json", *args]
    r = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env
    )
    parsed = None
    out = (r.stdout or "").strip()
    if out:
        try:
            parsed = json.loads(out)
        except Exception:
            parsed = out
    return r.returncode, parsed, (r.stderr or "").strip()


def _channel_id(c: dict) -> str | None:
    cid = c.get("channel_id") or c.get("id") or c.get("channel", {}).get("id")
    return cid if isinstance(cid, str) and cid else None


def list_channels(env: dict) -> list[dict]:
    rc, parsed, err = buzz(["channels", "list"], env)
    if rc != 0:
        print(f"  channels list FAIL {rc}: {(err or str(parsed))[:200]}")
        return []
    if isinstance(parsed, list):
        return [c for c in parsed if isinstance(c, dict)]
    if isinstance(parsed, dict):
        items = parsed.get("channels") or parsed.get("items") or parsed.get("data") or []
        return [c for c in items if isinstance(c, dict)]
    return []


def preferred_existing_ids() -> dict[str, str]:
    if not CHANNEL_IDS.exists():
        return {}
    try:
        data = json.loads(CHANNEL_IDS.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str) and v}


def find_channel(by_name: str, env: dict, listed: list[dict] | None = None) -> str | None:
    """Return one channel id for exact name match; prefer CHANNEL_IDS, else newest."""
    name_l = by_name.lower()
    matches: list[dict] = []
    for c in listed if listed is not None else list_channels(env):
        if (c.get("name") or "").lower() == name_l:
            matches.append(c)
    if not matches:
        rc, parsed, err = buzz(["channels", "search", "--query", by_name, "--exact"], env)
        if rc == 0:
            items = (
                parsed
                if isinstance(parsed, list)
                else (
                    (parsed or {}).get("channels")
                    or (parsed or {}).get("items")
                    or (parsed or {}).get("data")
                    or []
                )
            )
            for c in items:
                if isinstance(c, dict) and (c.get("name") or "").lower() == name_l:
                    matches.append(c)
    if not matches:
        return None
    prefer = preferred_existing_ids().get(by_name)
    if prefer:
        for c in matches:
            if _channel_id(c) == prefer:
                return prefer
    matches.sort(key=lambda c: int(c.get("created_at") or 0), reverse=True)
    return _channel_id(matches[0])


def create_channel(name: str, description: str, env: dict) -> str | None:
    rc, parsed, err = buzz(
        [
            "channels",
            "create",
            "--name",
            name,
            "--type",
            "stream",
            "--visibility",
            "private",
            "--description",
            description,
        ],
        env,
    )
    if rc != 0:
        print(f"  create {name}: FAIL {rc}: {(err or str(parsed))[:200]}")
        return None
    cid = _channel_id(parsed) if isinstance(parsed, dict) else None
    if not cid:
        # create response may omit id — resolve via list/search
        time.sleep(0.3)
        cid = find_channel(name, env)
    if not cid:
        print(f"  create {name}: created but id not parsed: {str(parsed)[:200]}")
    return cid


def archive_duplicate_channels(keep: dict[str, str], env: dict) -> int:
    """Archive same-name channels that are NOT the kept CHANNEL_IDS entry."""
    listed = list_channels(env)
    archived = 0
    for name, keep_id in keep.items():
        name_l = name.lower()
        for c in listed:
            if (c.get("name") or "").lower() != name_l:
                continue
            cid = _channel_id(c)
            if not cid or cid == keep_id:
                continue
            rc, parsed, err = buzz(["channels", "archive", "--channel", cid], env)
            if rc == 0:
                print(f"  archived duplicate #{name} {cid}")
                archived += 1
            else:
                print(f"  archive #{name} {cid}: FAIL {rc}: {(err or str(parsed))[:160]}")
            time.sleep(0.2)
    return archived


def members_of(cid: str, env: dict) -> dict[str, str]:
    rc, parsed, err = buzz(["channels", "members", "--channel", cid], env)
    if rc != 0:
        return {}
    items = parsed
    if isinstance(parsed, dict):
        items = parsed.get("members") or parsed.get("items") or parsed.get("data") or []
    out: dict[str, str] = {}
    for m in items or []:
        if isinstance(m, dict):
            p = m.get("pubkey") or m.get("public_key") or m.get("id") or ""
            role = m.get("role") or m.get("member_role") or "member"
            if p:
                out[p] = role
    return out


def add_member(cid: str, pubkey: str, role: str, env: dict) -> str:
    cur = members_of(cid, env).get(pubkey)
    if role == "admin" and cur in ("admin", "owner"):
        return "ok:admin"
    if role == "member" and cur in ("member", "admin", "owner", "bot"):
        return "ok:member"
    rc, parsed, err = buzz(
        ["channels", "add-member", "--channel", cid, "--pubkey", pubkey, "--role", role],
        env,
    )
    if rc == 0:
        return f"added:{role}"
    return f"fail:{rc}:{(err or str(parsed))[:160]}"


def live_agents() -> dict[str, dict]:
    agents = json.loads(AGENTS_PATH.read_text(encoding="utf-8-sig"))
    live: dict[str, dict] = {}
    for a in agents:
        pk = a.get("pubkey") or ""
        name = a.get("name") or a.get("display_name") or ""
        if not (len(pk) == 64 and a.get("is_active", True) and name):
            continue
        relay_url = a.get("relay_url") or ""
        row = {"pubkey": pk, "relay_url": relay_url}
        # Prefer the copy already pointed at the local relay when duplicates exist.
        if name not in live:
            live[name] = row
        elif "127.0.0.1" in relay_url or "localhost" in relay_url:
            live[name] = row
    return live


def main() -> int:
    archive_dupes = "--archive-dupes" in sys.argv
    env = os.environ.copy()
    env["BUZZ_PRIVATE_KEY"] = owner_nsec()
    env["BUZZ_RELAY_URL"] = RELAY

    agents = live_agents()
    print(f"relay={RELAY}")
    print(f"live agents: {', '.join(sorted(agents))}")
    if not agents:
        print("ERROR: no live agents in managed-agents.json - aborting")
        return 1

    listed = list_channels(env)
    print(f"visible channels: {len(listed)}")

    ids: dict[str, str] = {}
    print("=== ENSURE CHANNELS ===")
    for name, desc in CANONICAL:
        cid = find_channel(name, env, listed=listed)
        if cid:
            print(f"#{name}: exists {cid}")
        else:
            cid = create_channel(name, desc, env)
            print(f"#{name}: created {cid}")
            time.sleep(0.3)
            listed = list_channels(env)
        if cid:
            ids[name] = cid

    print("=== ENSURE MEMBERS ===")
    for name, cid in ids.items():
        bits = []
        for aname, a in agents.items():
            role = (
                "admin"
                if (name in ADMIN_ROLE_CHANNELS and aname in ADMIN_ROLE_AGENTS)
                else "member"
            )
            bits.append(f"{aname}->{role}:{add_member(cid, a['pubkey'], role, env)}")
            time.sleep(0.2)
        print(f"#{name}: " + ", ".join(bits))

    if len(ids) != len(CANONICAL):
        print(
            f"WARNING: only {len(ids)}/{len(CANONICAL)} channels resolved - not writing CHANNEL_IDS.json"
        )
        return 2

    if CHANNEL_IDS.exists():
        bak = CHANNEL_IDS.with_suffix(".json.bak-local-" + time.strftime("%Y%m%d_%H%M%S"))
        bak.write_text(CHANNEL_IDS.read_text(encoding="utf-8-sig"), encoding="utf-8")
        print(f"old CHANNEL_IDS.json backed up -> {bak.name}")
    CHANNEL_IDS.write_text(json.dumps(ids, indent=4) + "\n", encoding="utf-8")
    print(f"CHANNEL_IDS.json regenerated with FRESH local IDs ({len(ids)} channels)")

    if archive_dupes:
        print("=== ARCHIVE DUPLICATES ===")
        n = archive_duplicate_channels(ids, env)
        print(f"archived {n} duplicate channel(s)")

    print("=== PROOF ===")
    for name, cid in ids.items():
        mem = members_of(cid, env)
        bits = [f"{aname}={mem.get(a['pubkey'], 'MISSING')}" for aname, a in agents.items()]
        print(f"#{name} ({cid}): " + ", ".join(bits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
