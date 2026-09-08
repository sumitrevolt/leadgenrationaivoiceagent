#!/usr/bin/env python3
"""Read the last few #admin messages (read-only)."""
from __future__ import annotations
import ctypes, json, os, subprocess, sys
from ctypes import wintypes
from pathlib import Path
from datetime import datetime, timezone

BUZZ = Path(os.environ["LOCALAPPDATA"]) / "Buzz" / "buzz.exe"
RELAY = "https://leadsgenai.communities.buzz.xyz"
IDS = json.loads((Path.home() / ".buzz" / "GUIDES" / "CHANNEL_IDS.json").read_text(encoding="utf-8-sig"))
CH = IDS[sys.argv[1] if len(sys.argv) > 1 else "admin"]
NAMES = {
    "1fb82b779689c60b13f10c49f19d15884349cc5accb5b329583f6a7441a6c1a0": "sumit",
    "20b69265b32c3f4f07db0cdd457c329c4618434d23f9e5c54ada84720a31270a": "Boss",
    "b9ffabcf66e8de5f7efa7ebae8fadaee8cc32e4f812ed54325a7f1fff4cf79c6": "Honey",
    "d2fd7e85404811241bad32516d5a68c95f660b122271da8130e35a076e61609d": "Fizz",
    "a546e85c1dad69937000a35ab260127268436c3d882711633d4c54a91d36b4e1": "Bumble",
}


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


env = dict(os.environ)
env["BUZZ_PRIVATE_KEY"] = owner_nsec()
r = subprocess.run([str(BUZZ), "--relay", RELAY, "--format", "json", "messages", "get",
                    "--channel", CH, "--limit", "6"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
msgs = json.loads((r.stdout or "[]").strip() or "[]")
for m in msgs[-4:]:
    who = NAMES.get(m.get("pubkey", ""), m.get("pubkey", "")[:8])
    ts = datetime.fromtimestamp(m.get("created_at", 0), timezone.utc).astimezone().strftime("%H:%M:%S")
    print(f"\n===== {who} @ {ts} =====")
    print((m.get("content") or "")[:3000])
