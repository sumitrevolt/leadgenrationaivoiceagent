#!/usr/bin/env python3
"""Resolve Buzz member pubkeys -> display names (read-only)."""
from __future__ import annotations
import ctypes, json, os, subprocess
from ctypes import wintypes
from pathlib import Path

BUZZ = Path(os.environ["LOCALAPPDATA"]) / "Buzz" / "buzz.exe"
RELAY = "https://leadsgenai.communities.buzz.xyz"


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


def buzz(args, env):
    r = subprocess.run([str(BUZZ), "--relay", RELAY, "--format", "json", *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    out = (r.stdout or "").strip()
    try:
        return r.returncode, (json.loads(out) if out else None), (r.stderr or "").strip()
    except Exception:
        return r.returncode, out, (r.stderr or "").strip()


def main():
    env = dict(os.environ)
    env["BUZZ_PRIVATE_KEY"] = owner_nsec()
    rc, users, err = buzz(["users", "get"], env)
    print("rc", rc, "err", err[:200])
    for u in (users if isinstance(users, list) else []):
        pk = u.get("pubkey", "")
        print(f"{pk}  {u.get('display_name') or u.get('name') or '?'}")


if __name__ == "__main__":
    main()
