#!/usr/bin/env python3
"""Read-only probe of current Buzz relay state (channels, members, agents)."""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
from ctypes import wintypes
from pathlib import Path

BUZZ = Path(os.environ["LOCALAPPDATA"]) / "Buzz" / "buzz.exe"
APPDATA = Path(os.environ["APPDATA"]) / "xyz.block.buzz.app"
AGENTS_PATH = APPDATA / "agents" / "managed-agents.json"
RELAY = "https://leadsgenai.communities.buzz.xyz"


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
    ptr = ctypes.c_void_p()
    assert ctypes.windll.advapi32.CredReadW("secrets.buzz-desktop", 1, 0, ctypes.byref(ptr))
    cred = ctypes.cast(ptr, ctypes.POINTER(CREDENTIAL)).contents
    raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
    ctypes.windll.advapi32.CredFree(ptr)
    return json.loads(raw.decode("utf-16-le").rstrip("\x00"))["identity"]


def buzz(args, env):
    cmd = [str(BUZZ), "--relay", RELAY, "--format", "json", *args]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    out = (r.stdout or "").strip()
    try:
        return r.returncode, json.loads(out) if out else None, (r.stderr or "").strip()
    except Exception:
        return r.returncode, out, (r.stderr or "").strip()


def main():
    env = dict(os.environ)
    env["BUZZ_PRIVATE_KEY"] = owner_nsec()
    print("BUZZ_EXE_EXISTS", BUZZ.exists())

    rc, chans, err = buzz(["channels", "list"], env)
    print("== CHANNELS rc", rc, "err", err[:200])
    rows = chans if isinstance(chans, list) else []
    for c in rows:
        print("CH", c.get("channel_id"), "|", c.get("name"), "|", (c.get("description") or "")[:60])

    for c in rows:
        cid = c.get("channel_id")
        rc2, mem, err2 = buzz(["channels", "members", "--channel", cid], env)
        items = mem if isinstance(mem, list) else (mem or {}).get("members", []) if isinstance(mem, dict) else []
        names = []
        for m in items or []:
            if isinstance(m, dict):
                names.append(f"{(m.get('display_name') or m.get('name') or m.get('pubkey', '')[:8])}:{m.get('role', 'member')}")
        print("MEM", c.get("name"), "->", ", ".join(names) or f"rc={rc2} {err2[:120]}")

    print("== MANAGED AGENTS FILE", AGENTS_PATH.exists())
    if AGENTS_PATH.exists():
        data = json.loads(AGENTS_PATH.read_text(encoding="utf-8"))
        print(json.dumps(data, indent=2)[:6000])


if __name__ == "__main__":
    main()
