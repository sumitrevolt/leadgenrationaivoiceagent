#!/usr/bin/env python3
"""buzz_mcp.py — stdio MCP server: Buzz workspace access for opencode (and any MCP client).

Exposes a small, read-mostly surface on the Buzz coordination plane (owner
policy 2026-08-10: Buzz = interface, never a control plane; production commands
route through Owner OS/OpenClaw -> 31 runtime STAFF only):

    buzz_channels   : list known channels (name -> id) from ~/.buzz/GUIDES/CHANNEL_IDS.json
    buzz_send       : post a message to a channel (evidence/coordination posts via buzz.exe)
    buzz_lock_status: read-only view of docs/coordination/LOCKS.json (buzzlock registry)

No VPS SSH, no deploy, no DB writes. Tools fail with a clear message instead of
crashing when buzz.exe / owner credential / channel map are missing (dev boxes
without the Buzz toolchain keep working).

Stdlib only — no new dependency (supply-chain discipline). Protocol: MCP over
stdio (JSON-RPC 2.0, line-delimited).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHANNEL_IDS = Path.home() / ".buzz" / "GUIDES" / "CHANNEL_IDS.json"
LOCKS = REPO / "docs" / "coordination" / "LOCKS.json"
RELAY = os.environ.get("BUZZ_RELAY", "https://leadsgenai.communities.buzz.xyz")


def _buzz_exe() -> Path | None:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    exe = Path(local) / "Buzz" / "buzz.exe"
    return exe if exe.exists() else None


def _owner_nsec() -> str | None:
    """Owner identity from Windows Credential Manager (same store as buzzlock)."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

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

    try:
        ptr = ctypes.c_void_p()
        if not ctypes.windll.advapi32.CredReadW("secrets.buzz-desktop", 1, 0, ctypes.byref(ptr)):
            return None
        cred = ctypes.cast(ptr, ctypes.POINTER(CREDENTIAL)).contents
        raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        ctypes.windll.advapi32.CredFree(ptr)
        return json.loads(raw.decode("utf-16-le").rstrip("\x00"))["identity"]
    except Exception:
        return None


def _channel_map() -> dict:
    if not CHANNEL_IDS.exists():
        return {}
    try:
        return json.loads(CHANNEL_IDS.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def tool_channels(args: dict) -> dict:
    cmap = _channel_map()
    if not cmap:
        return {"text": "channel map missing: ~/.buzz/GUIDES/CHANNEL_IDS.json"}
    lines = [f"relay: {RELAY}"]
    for name, cid in sorted(cmap.items()):
        lines.append(f"  #{name} = {cid}")
    return {"text": "\n".join(lines)}


def tool_lock_status(args: dict) -> dict:
    if not LOCKS.exists():
        return {"text": "no LOCKS.json — the tree is free"}
    try:
        data = json.loads(LOCKS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"text": f"LOCKS.json unreadable: {exc}"}
    locks = data.get("locks") or []
    if not locks:
        return {"text": "no active claims — the tree is free"}
    return {
        "text": "\n".join(
            f"  [{lk.get('tool')}] {lk.get('path')} — {lk.get('reason') or 'no reason'}"
            for lk in locks
        )
    }


def tool_send(args: dict) -> dict:
    exe = _buzz_exe()
    if not exe:
        return {"text": "buzz.exe missing (LOCALAPPDATA\\Buzz\\buzz.exe) — install Buzz Desktop"}
    nsec = _owner_nsec()
    if not nsec:
        return {
            "text": "owner credential missing (secrets.buzz-desktop in Windows Credential Manager)"
        }
    cmap = _channel_map()
    if not cmap:
        return {"text": "channel map missing: ~/.buzz/GUIDES/CHANNEL_IDS.json"}
    channel = str(args.get("channel") or "").strip()
    content = str(args.get("content") or "").strip()
    if not channel or not content:
        return {"text": "both 'channel' (name or id) and 'content' are required"}
    cid = cmap.get(channel, channel)
    if channel not in cmap and not (
        len(channel) >= 8 and all(c in "0123456789abcdef" for c in channel.lower())
    ):
        return {"text": f"unknown channel {channel!r}; known: {', '.join(sorted(cmap))}"}
    if len(content) > 4000:
        content = content[:4000] + " ...[truncated]"
    try:
        env = dict(os.environ)
        env["BUZZ_PRIVATE_KEY"] = nsec
        r = subprocess.run(
            [
                str(exe),
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
            input=content,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=90,
        )
        if r.returncode != 0:
            return {"text": f"buzz send failed rc={r.returncode}: {(r.stderr or '')[:300]}"}
        return {"text": f"posted to #{channel} ({cid})"}
    except Exception as exc:
        return {"text": f"buzz send failed ({type(exc).__name__})"}


TOOLS = [
    {
        "name": "buzz_channels",
        "description": "List known Buzz channels (name -> id) and the relay in use.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "buzz_send",
        "description": "Post a message to a Buzz channel (evidence/coordination posts).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "channel name (e.g. build) or id"},
                "content": {"type": "string", "description": "message body"},
            },
            "required": ["channel", "content"],
        },
    },
    {
        "name": "buzz_lock_status",
        "description": "Read-only buzzlock registry: which coding agent holds which files.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "buzz_channels": tool_channels,
    "buzz_send": tool_send,
    "buzz_lock_status": tool_lock_status,
}


def _resp(id, result=None, error=None) -> dict:
    msg = {"jsonrpc": "2.0", "id": id}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    return msg


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = req.get("id")
        method = req.get("method", "")
        if method == "initialize":
            out = _resp(
                rid,
                {
                    "protocolVersion": req.get("params", {}).get("protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "buzz-mcp", "version": "1.0.0"},
                },
            )
        elif method == "notifications/initialized" or method.startswith("notifications/"):
            continue
        elif method == "ping":
            out = _resp(rid, {})
        elif method == "tools/list":
            out = _resp(rid, {"tools": TOOLS})
        elif method == "tools/call":
            name = req.get("params", {}).get("name", "")
            args = req.get("params", {}).get("arguments", {}) or {}
            handler = HANDLERS.get(name)
            if handler is None:
                out = _resp(rid, error={"code": -32601, "message": f"unknown tool {name}"})
            else:
                try:
                    text = handler(args)["text"]
                    out = _resp(rid, {"content": [{"type": "text", "text": text}]})
                except Exception as exc:
                    out = _resp(
                        rid, error={"code": -32603, "message": f"{type(exc).__name__}: {exc}"}
                    )
        else:
            out = _resp(rid, error={"code": -32601, "message": f"method not found: {method}"})
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
