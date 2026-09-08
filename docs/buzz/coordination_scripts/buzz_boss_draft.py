#!/usr/bin/env python3
"""Open an owner-reviewed Boss create-agent draft in Buzz Desktop."""
from __future__ import annotations
import ctypes, json, os, subprocess
from ctypes import wintypes
from pathlib import Path

BUZZ = Path(os.environ["LOCALAPPDATA"]) / "Buzz" / "buzz.exe"
RELAY = "https://leadsgenai.communities.buzz.xyz"
ADMIN_CH = "bd771185-7621-4ce8-941a-1b9ada7f5783"
PROMPT = (Path.home() / ".buzz" / ".scratch" / "boss_system_prompt.txt").read_text(encoding="utf-8").strip()


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
r = subprocess.run(
    [str(BUZZ), "--relay", RELAY, "--format", "json", "agents", "draft-create",
     "--channel", ADMIN_CH, "--display-name", "Boss", "--system-prompt", "-"],
    input=PROMPT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
print("rc", r.returncode)
print("stdout", (r.stdout or "").strip()[:800])
print("stderr", (r.stderr or "").strip()[:800])
