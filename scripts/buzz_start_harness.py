#!/usr/bin/env python3
"""Start a Buzz ACP harness for an agent whose key this machine holds.

!! NEVER EXECUTED PAST --dry-run !!
`--dry-run` runs and prints the correct plan; it returns before any key is read.
The real start has never run: the authoring session's sandbox classifier refuses
it even with a matching permission rule, because the capability — read an agent
private key from Windows Credential Manager, then spawn a long-running process
holding it — is gated at a layer above permission rules. Ruff passes on the file.
Treat the launch path as a reviewed proposal, not exercised tooling: read it,
run `--dry-run`, then run it for real once and check the log it prints.

Buzz Desktop normally spawns these. It does not spawn one for every stored key —
Boss had a key in the credential store and no running harness, which is why the
orchestrator never answered a mention. `buzz-acp.exe` takes the key directly, so
a harness can be started without the Desktop UI.

    python scripts/buzz_start_harness.py --agent Boss --dry-run
    python scripts/buzz_start_harness.py --agent Boss

The private key is read from Windows Credential Manager at run time, passed to
the child through its environment only, and never printed, logged or written.

Stop a harness the ordinary way: kill the PID this prints.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

HOSTED_RELAY_WS = "wss://leadsgenai.communities.buzz.xyz"


def relay_url() -> str:
    """ACP wants ws/wss. BUZZ_RELAY may be http(s) (buzzlock) or ws(s).

    Unset → hosted default (current workspace still works). Local-first is
    ``ws://127.0.0.1:3100`` once the relay publishes that loopback port.
    """
    raw = (os.environ.get("BUZZ_RELAY") or "").strip()
    if not raw:
        return HOSTED_RELAY_WS
    if raw.startswith("https://"):
        return "wss://" + raw[len("https://") :]
    if raw.startswith("http://"):
        return "ws://" + raw[len("http://") :]
    return raw


# Every hex literal below is a Nostr PUBLIC key. They are 64-char hex — the same
# shape as a private key — so the entropy scanner flags them, but they are
# published identifiers visible in any `channels members` listing. The private
# keys live only in Windows Credential Manager and are read at run time into the
# child's environment; none is ever stored, printed or committed.
OWNER_PUBKEY = (
    "1fb82b779689c60b13f10c49f19d15884349cc5accb5b329583f6a7449e0d2b0"  # pragma: allowlist secret
)

# Agent display name -> public key of the identity whose private key we expect to hold.
KNOWN = {
    "Boss": "1b13ceccc2a6966064835fd942a55c8015a34a7c0f14a3462c0d845440f4e92f",  # pragma: allowlist secret
    "Honey": "b9ffabcf66e8de5f7efa7ebae8fadaee8cc32e4f812ed54325a7f1fff4cf79c6",  # pragma: allowlist secret
    "Fizz": "d2fd7e85404811241bad32516d5a68c95f660b122271da8130e35a076e61609d",  # pragma: allowlist secret
    "Bumble": "a546e85c1dad69937000a35ab260127268436c3d882711633d4c54a91d36b4e1",  # pragma: allowlist secret
}


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


def _credential_blob() -> dict:
    ptr = ctypes.c_void_p()
    if not ctypes.windll.advapi32.CredReadW("secrets.buzz-desktop", 1, 0, ctypes.byref(ptr)):
        raise SystemExit("Buzz desktop credential not found — sign in to Buzz Desktop first.")
    cred = ctypes.cast(ptr, ctypes.POINTER(CREDENTIAL)).contents
    raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
    ctypes.windll.advapi32.CredFree(ptr)
    return json.loads(raw.decode("utf-16-le").rstrip("\x00"))


def agent_key(pubkey: str) -> str:
    """Private key for one agent. Returned to the caller, never printed."""
    blob = _credential_blob()
    key = blob.get(f"agent:{pubkey}")
    if not key:
        have = sorted(k.split(":", 1)[1][:8] for k in blob if k.startswith("agent:"))
        raise SystemExit(
            f"No stored key for {pubkey[:8]}. This machine holds keys for: {', '.join(have)}.\n"
            "An identity without a local key cannot be run here — that is an identity/"
            "credential mismatch, not a startup problem."
        )
    return key


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="buzz_start_harness",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--agent", required=True, choices=sorted(KNOWN))
    ap.add_argument(
        "--harness",
        default="claude-agent-acp",
        help="agent command buzz-acp drives (default: claude-agent-acp)",
    )
    ap.add_argument("--system-prompt-file", help="optional persona file")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, start nothing")
    args = ap.parse_args()

    pubkey = KNOWN[args.agent]
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise SystemExit("LOCALAPPDATA unset")
    acp = Path(local) / "Buzz" / "buzz-acp.exe"
    if not acp.exists():
        raise SystemExit(f"buzz-acp.exe not found at {acp}")

    harness = args.harness
    if harness == "claude-agent-acp":
        shim = Path(os.environ["APPDATA"]) / "npm" / "claude-agent-acp.cmd"
        if shim.exists():
            harness = str(shim)

    relay = relay_url()
    cmd = [
        str(acp),
        "--relay-url",
        relay,
        "--agent-owner",
        OWNER_PUBKEY,
        "--agent-command",
        harness,
        "--subscribe",
        "mentions",
    ]
    if args.system_prompt_file:
        cmd += ["--system-prompt-file", args.system_prompt_file]

    print(f"agent      : {args.agent} ({pubkey[:16]}...)")
    print(f"relay      : {relay}")
    print(f"harness    : {harness}")
    print("private key: from Windows Credential Manager (env-only, not shown)")
    print("command    :", " ".join(cmd))

    if args.dry_run:
        print("\nDRY-RUN — nothing started.")
        return 0

    key = agent_key(pubkey)
    env = dict(os.environ)
    env["BUZZ_PRIVATE_KEY"] = key

    log = Path(os.environ["LOCALAPPDATA"]) / "Buzz" / f"harness-{args.agent.lower()}.log"
    fh = log.open("ab")
    proc = subprocess.Popen(
        cmd, env=env, stdout=fh, stderr=fh, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    print(f"\nstarted pid={proc.pid}")
    print(f"log      : {log}")
    print("Presence is not proof — send a correlated canary and require a reply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
