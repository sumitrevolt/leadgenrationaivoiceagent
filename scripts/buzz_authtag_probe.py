#!/usr/bin/env python3
"""One-off diagnostic — NOT part of the daily loop. Kept because the answer it
found is load-bearing and someone will doubt it.

What does the Buzz Desktop credential actually contain?

`buzz agents draft-create` fails with "agent draft requests require
BUZZ_AUTH_TAG" — the NIP-OA owner attestation. This prints the SHAPE of the
stored credential (key names, types, lengths) so we can find where that tag
lives, without ever printing a value.

    python scripts/buzz_authtag_probe.py

Structure only. No secret is written, logged, or returned.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def describe(obj, prefix: str = "") -> None:
    if isinstance(obj, dict):
        for k in sorted(obj):
            v = obj[k]
            if isinstance(v, dict | list):
                print(f"  {prefix}{k}: {type(v).__name__}")
                describe(v, prefix + f"{k}.")
            else:
                kind = type(v).__name__
                size = len(v) if isinstance(v, str) else "-"
                print(f"  {prefix}{k}: {kind} (len={size})")
    elif isinstance(obj, list):
        print(f"  {prefix}[]: {len(obj)} item(s)")
        if obj:
            describe(obj[0], prefix + "0.")


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    # buzzlock defines this inside its accessor, so redeclare it here rather than
    # refactoring a working script for a diagnostic.
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

    targets = [
        "secrets.buzz-desktop",
        "secrets.buzz-auth-tag",
        "buzz-desktop",
        "secrets.buzz",
    ]
    for target in targets:
        ptr = ctypes.c_void_p()
        ok = ctypes.windll.advapi32.CredReadW(target, 1, 0, ctypes.byref(ptr))
        if not ok:
            print(f"[miss] {target}")
            continue
        cred = ctypes.cast(ptr, ctypes.POINTER(CREDENTIAL)).contents
        raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        ctypes.windll.advapi32.CredFree(ptr)
        print(f"[hit ] {target}  ({cred.CredentialBlobSize} bytes)")
        try:
            data = json.loads(raw.decode("utf-16-le").rstrip("\x00"))
        except Exception as exc:
            print(f"  <not JSON: {type(exc).__name__}>")
            continue
        describe(data)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
