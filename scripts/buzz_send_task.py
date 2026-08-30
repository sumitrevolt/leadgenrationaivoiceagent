#!/usr/bin/env python3
"""PILOT one-shot Buzz task dispatch (reuses owner_nsec loader from staff_pulse).
Usage: python scripts/buzz_send_task.py <channel> <message...>
"""

import ctypes
import json
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

LOCALAPPDATA = os.environ.get("LOCALAPPDATA") or str(Path.home())
BUZZ = Path(LOCALAPPDATA) / "Buzz" / "buzz.exe"
RELAY = os.environ.get("BUZZ_RELAY", "wss://leadsgenai.communities.buzz.xyz")
CHANNEL_IDS = Path.home() / ".buzz" / "GUIDES" / "CHANNEL_IDS.hosted.json"


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
    if not ctypes.windll.advapi32.CredReadW("secrets.buzz-desktop", 1, 0, ctypes.byref(ptr)):
        raise RuntimeError("Buzz desktop credential not found")
    cred = ctypes.cast(ptr, ctypes.POINTER(CREDENTIAL)).contents
    raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
    ctypes.windll.advapi32.CredFree(ptr)
    return json.loads(raw.decode("utf-16-le").rstrip("\x00"))["identity"]


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: buzz_send_task.py <channel> <message>", file=sys.stderr)
        return 2
    channel = sys.argv[1]
    body = " ".join(sys.argv[2:])
    ids = json.loads(CHANNEL_IDS.read_text(encoding="utf-8-sig"))
    cid = ids[channel]
    env = dict(os.environ)
    env["BUZZ_PRIVATE_KEY"] = owner_nsec()
    r = subprocess.run(
        [
            str(BUZZ),
            "--relay",
            RELAY,
            "--format",
            "json",
            "messages",
            "send",
            "--channel",
            cid,
            "--content",
            "-",
        ],
        input=body,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
    )
    if r.returncode != 0:
        print(f"FAIL rc={r.returncode}: {(r.stderr or '')[:400]}", file=sys.stderr)
        return r.returncode
    print(f"OK sent to #{channel}: {(r.stdout or '')[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
