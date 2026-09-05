#!/usr/bin/env python3
"""Point every channel at the NEW Boss pubkey and drop the stale one."""
from __future__ import annotations
import ctypes, json, os, subprocess, time
from ctypes import wintypes
from pathlib import Path

BUZZ = Path(os.environ["LOCALAPPDATA"]) / "Buzz" / "buzz.exe"
RELAY = "https://leadsgenai.communities.buzz.xyz"
GUIDES = Path.home() / ".buzz" / "GUIDES"
IDS = json.loads((GUIDES / "CHANNEL_IDS.json").read_text(encoding="utf-8-sig"))

OLD_BOSS = "1b13ceccc2a6966064835fd942a55c8015a34a7c0f14a3462c0d845440f4e92f"
NEW_BOSS = "20b69265b32c3f4f07db0cdd457c329c4618434d23f9e5c54ada84720a31270a"

ADMIN_ON = ("admin", "leadgen", "build", "staff-pulse")
MEMBER_ON = ("gtm", "ops", "revenue", "dev")


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


def step(label, args):
    r = subprocess.run([str(BUZZ), "--relay", RELAY, "--format", "json", *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=ENV)
    ok = r.returncode == 0
    print(f"[{'OK ' if ok else f'FAIL({r.returncode})'}] {label} {'' if ok else (r.stderr or '').strip()[:160]}")
    time.sleep(0.4)
    return ok


def main():
    ENV["BUZZ_PRIVATE_KEY"] = owner_nsec()
    for name in ADMIN_ON + MEMBER_ON:
        cid = IDS.get(name)
        if not cid:
            print(f"[SKIP] no id for #{name}")
            continue
        role = "admin" if name in ADMIN_ON else "member"
        step(f"new Boss -> #{name} ({role})",
             ["channels", "add-member", "--channel", cid, "--pubkey", NEW_BOSS, "--role", role])
        step(f"drop stale Boss <- #{name}",
             ["channels", "remove-member", "--channel", cid, "--pubkey", OLD_BOSS])

    (GUIDES / "BOSS_PUBKEY.txt").write_text(NEW_BOSS + "\n", encoding="utf-8")
    print("BOSS_PUBKEY.txt updated ->", NEW_BOSS)


if __name__ == "__main__":
    main()
