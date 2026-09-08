#!/usr/bin/env python3
"""Post a read-only 31/31 STAFF pulse into the Buzz #staff-pulse channel.

Reads live state from the VPS by calling app.platform.team.team_status() inside
the running app container over SSH. Read-only: no writes, no deploy, no .env.

Usage:
    python scripts/buzz_staff_pulse.py            # fetch + post
    python scripts/buzz_staff_pulse.py --dry-run  # fetch + print, do not post

Protocol: ~/.buzz/GUIDES/AUTONOMY_POLICY.md (Stage 1 = read-only canary).
Commands never flow the other way — Buzz is an interface, not a control plane.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
from pathlib import Path

SSH = r"C:\PROGRA~1\Git\usr\bin\ssh.exe"
SSH_KEY = str(Path.home() / ".ssh" / "id_rsa")
VPS = "root@72.61.245.204"
CONTAINER = "leadgen_app"

BUZZ = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("HOME", ".")) / "Buzz" / "buzz.exe"
# Local-first relay migration (owner 2026-08-10): BUZZ_RELAY env overrides once
# the local relay is up; hosted default keeps the current workspace working.
RELAY = os.environ.get("BUZZ_RELAY", "https://leadsgenai.communities.buzz.xyz")
CHANNEL_IDS = Path.home() / ".buzz" / "GUIDES" / "CHANNEL_IDS.json"

IST = timezone(timedelta(hours=5, minutes=30))

DIVISIONS = [
    ("Platform", "platform"),
    ("Marketing", "marketing"),
    ("Voice", "voice"),
]

REMOTE_SNIPPET = (
    "import json;"
    "from app.platform.team import team_status;"
    "s=team_status();"
    "print('<<<PULSE>>>'+json.dumps({"
    "'totals':s.get('totals') or {},"
    "'members':[{"
    "'name':m.get('name'),'product':m.get('product'),'state':m.get('state'),"
    "'mins':m.get('last_active_mins'),'acts':m.get('today_actions'),"
    "'errs':m.get('today_errors'),"
    "'last':((m.get('last_activity') or {}).get('action')),"
    "'lstatus':((m.get('last_activity') or {}).get('status'))"
    "} for m in (s.get('members') or [])]}))"
)


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


def fetch_status() -> dict:
    """Read-only team_status() from the live app container."""
    remote = f'docker exec {CONTAINER} python -c "{REMOTE_SNIPPET}"'
    r = subprocess.run(
        [SSH, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-i", SSH_KEY, VPS, remote],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ssh/docker failed rc={r.returncode}: {(r.stderr or '')[:300]}")
    for line in (r.stdout or "").splitlines():
        if line.startswith("<<<PULSE>>>"):
            return json.loads(line[len("<<<PULSE>>>") :])
    raise RuntimeError("no pulse payload in remote output")


def _age(mins) -> str:
    if mins is None:
        return "never"
    try:
        m = float(mins)
    except (TypeError, ValueError):
        return "?"
    if m < 60:
        return f"{int(m)}m"
    if m < 1440:
        return f"{m / 60:.1f}h"
    return f"{m / 1440:.1f}d"


def _flag(mem: dict) -> str:
    """ok / warn / fail — warn is the useful one: silently stale or erroring."""
    if (mem.get("errs") or 0) > 0 or (mem.get("lstatus") == "error"):
        return "fail"
    if (mem.get("state") or "") in ("offline", "stalled"):
        return "fail"
    mins = mem.get("mins")
    if mins is None:
        return "warn"
    try:
        if float(mins) > 1440:
            return "warn"
    except (TypeError, ValueError):
        return "warn"
    return "ok"


def build_message(data: dict) -> str:
    totals = data.get("totals") or {}
    members = data.get("members") or []
    now = datetime.now(IST).strftime("%d-%b %H:%M IST")

    flags = [_flag(m) for m in members]
    n_fail = flags.count("fail")
    n_warn = flags.count("warn")
    headline = "all green" if not n_fail and not n_warn else f"{n_fail} fail · {n_warn} warn"

    lines = [
        f"**[PULSE] {now}** — {len(members)}/31 staff · {headline}",
        "",
        f"actions today **{totals.get('actions_today', '?')}** · "
        f"errors **{totals.get('errors_today', '?')}** · "
        f"working **{totals.get('working_members', '?')}** · "
        f"active **{totals.get('active_members', '?')}**",
    ]

    for label, product in DIVISIONS:
        group = [m for m in members if (m.get("product") or "") == product]
        if not group:
            continue
        group.sort(key=lambda m: (_flag(m) == "ok", m.get("name") or ""))
        lines.append("")
        lines.append(f"**{label} ({len(group)})**")
        for m in group:
            lines.append(
                f"`[PULSE] {label.lower()} | {m.get('name')} | {_age(m.get('mins'))} ago | "
                f"{_flag(m)} | {m.get('last') or 'no events'} · "
                f"{m.get('acts') or 0}a/{m.get('errs') or 0}e`"
            )

    lines += [
        "",
        "_Read-only mirror. Commands route through Boss only. Buzz never mutates STAFF directly._",
    ]
    return "\n".join(lines)


def post(body: str) -> None:
    ids = json.loads(CHANNEL_IDS.read_text(encoding="utf-8-sig"))
    cid = ids["staff-pulse"]
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
        raise RuntimeError(f"buzz send failed rc={r.returncode}: {(r.stderr or '')[:300]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="fetch and print, do not post")
    args = ap.parse_args()

    try:
        data = fetch_status()
    except Exception as exc:
        print(f"[pulse] FETCH FAILED: {exc}", file=sys.stderr)
        return 2

    body = build_message(data)
    if args.dry_run:
        print(body)
        return 0

    try:
        post(body)
    except Exception as exc:
        print(f"[pulse] POST FAILED: {exc}", file=sys.stderr)
        return 3

    print(f"[pulse] posted {len(data.get('members') or [])} members to #staff-pulse")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
