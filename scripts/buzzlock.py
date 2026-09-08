#!/usr/bin/env python3
"""buzzlock — claim-before-edit file locks for coding agents.

Cursor, Claude Code, Codex, OpenCode and Monkey Code all edit this checkout. This
is the registry that stops them overwriting each other, plus the matching #build
post.

    python scripts/buzzlock.py status
    python scripts/buzzlock.py claim app/api/growth_revenue.py --tool CLAUDE --reason "ADR-159 canary"
    python scripts/buzzlock.py release app/api/growth_revenue.py --tool CLAUDE --evidence "3 tests green, exit 0"
    python scripts/buzzlock.py handoff --tool CURSOR --next CLAUDE --goal "..." --done "..." --evidence "exit 0" --left "..." --touched "..."
    python scripts/buzzlock.py break app/api/growth_revenue.py --tool CURSOR

Exit codes: 0 ok · 1 usage/arg error · 2 refused (file held by another tool).
Check the exit code — a refused claim is not a warning, it means stop.

Buzz posting is best-effort: if buzz.exe or the owner credential is missing the
lock file is still authoritative and the command still succeeds. LOCKS.json is the
contract; the chat post is the human-readable mirror.

Protocol: ~/.buzz/GUIDES/CODING_AGENT_PROTOCOL.md
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOCKS = REPO / "docs" / "coordination" / "LOCKS.json"
# Local-first relay migration (owner 2026-08-10): BUZZ_RELAY env overrides once
# the local relay is up; hosted default keeps the current workspace working.
RELAY = os.environ.get("BUZZ_RELAY", "https://leadsgenai.communities.buzz.xyz")
CHANNEL_IDS = Path.home() / ".buzz" / "GUIDES" / "CHANNEL_IDS.json"
TOOLS = ("CURSOR", "CLAUDE", "CODEX", "GOOSE", "OPENCODE", "FREEBUFF", "MONKEY", "HERMES")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts: str) -> datetime | None:
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def load() -> dict:
    """LOCKS.json is gitignored and per-checkout, so a fresh tree has none yet.

    Self-initialise instead of raising — a missing registry means "no claims",
    not a broken tool. Every worktree used to crash on the first status call.
    """
    try:
        data = json.loads(LOCKS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    except json.JSONDecodeError as exc:
        raise SystemExit(f"LOCKS.json is corrupt ({exc}) — fix or delete it: {LOCKS}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"LOCKS.json must be a JSON object: {LOCKS}")
    data.setdefault("locks", [])
    data.setdefault("stale_after_minutes", 240)
    return data


def save(data: dict) -> None:
    """Atomic write — a half-written registry is worse than no registry."""
    data["updated_at"] = _iso(_now())
    fd, tmp = tempfile.mkstemp(dir=str(LOCKS.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, LOCKS)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def norm(path: str) -> str:
    p = path.replace("\\", "/").strip().lstrip("./")
    try:
        cand = Path(path)
        if cand.is_absolute():
            p = cand.resolve().relative_to(REPO).as_posix()
    except (ValueError, OSError):
        pass
    return p


def is_stale(lock: dict, stale_after: int) -> bool:
    at = _parse(lock.get("claimed_at", ""))
    if at is None:
        return True
    return _now() - at > timedelta(minutes=stale_after)


def age_str(lock: dict) -> str:
    at = _parse(lock.get("claimed_at", ""))
    if at is None:
        return "?"
    mins = (_now() - at).total_seconds() / 60
    return f"{int(mins)}m" if mins < 60 else f"{mins / 60:.1f}h"


# --------------------------------------------------------------------------- #
# Buzz posting — best effort, never blocks the lock operation
# --------------------------------------------------------------------------- #
def _owner_nsec() -> str | None:
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


def post_build(body: str) -> str:
    """Returns a short status string for the caller to print."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return "buzz skipped (no LOCALAPPDATA)"
    exe = Path(local) / "Buzz" / "buzz.exe"
    if not exe.exists() or not CHANNEL_IDS.exists():
        return "buzz skipped (cli or channel map missing)"
    nsec = _owner_nsec()
    if not nsec:
        return "buzz skipped (no owner credential)"
    try:
        cid = json.loads(CHANNEL_IDS.read_text(encoding="utf-8-sig"))["build"]
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
            input=body,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=90,
        )
        return "posted to #build" if r.returncode == 0 else f"buzz post failed rc={r.returncode}"
    except Exception as exc:
        return f"buzz post failed ({type(exc).__name__})"


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_status(args) -> int:
    data = load()
    stale_after = data["stale_after_minutes"]
    locks = data["locks"]
    if not locks:
        print("no active claims — the tree is free")
        return 0
    print(f"{len(locks)} active claim(s), stale after {stale_after}m:\n")
    for lk in locks:
        mark = " STALE" if is_stale(lk, stale_after) else ""
        print(f"  [{lk['tool']}]{mark}  {lk['path']}")
        print(f"      held {age_str(lk)} · {lk.get('reason') or 'no reason given'}")
    return 0


def cmd_claim(args) -> int:
    data = load()
    stale_after = data["stale_after_minutes"]
    paths = [norm(p) for p in args.paths]
    held = {lk["path"]: lk for lk in data["locks"]}

    blocked = [
        (p, held[p])
        for p in paths
        if p in held and held[p]["tool"] != args.tool and not is_stale(held[p], stale_after)
    ]
    if blocked:
        for p, lk in blocked:
            print(
                f"REFUSED: {p} is held by [{lk['tool']}] for {age_str(lk)} — {lk.get('reason')}",
                file=sys.stderr,
            )
        print(
            "\nPick different work, or post BLOCKED ON in #build. Do not edit these files.",
            file=sys.stderr,
        )
        names = ", ".join(f"`{p}`" for p, _ in blocked)
        holders = ", ".join(sorted({lk["tool"] for _, lk in blocked}))
        post_build(f"`[{args.tool}] BLOCKED ON` {names} (held by {holders})")
        return 2

    data["locks"] = [lk for lk in data["locks"] if lk["path"] not in paths]
    for p in paths:
        data["locks"].append(
            {
                "path": p,
                "tool": args.tool,
                "reason": args.reason,
                "claimed_at": _iso(_now()),
            }
        )
    data["locks"].sort(key=lambda lk: lk["path"])
    save(data)

    files = ", ".join(f"`{p}`" for p in paths)
    status = post_build(f"`[{args.tool}] CLAIM` {files}\nreason: {args.reason}")
    print(f"CLAIMED {len(paths)} file(s) as [{args.tool}] — {status}")
    return 0


def cmd_release(args) -> int:
    data = load()
    paths = [norm(p) for p in args.paths]
    before = len(data["locks"])
    mine = [lk for lk in data["locks"] if lk["path"] in paths and lk["tool"] == args.tool]
    data["locks"] = [
        lk for lk in data["locks"] if not (lk["path"] in paths and lk["tool"] == args.tool)
    ]
    save(data)

    if not mine:
        print(f"nothing to release for [{args.tool}] on {', '.join(paths)}", file=sys.stderr)
        return 0

    files = ", ".join(f"`{lk['path']}`" for lk in mine)
    status = post_build(f"`[{args.tool}] RELEASE` {files}\nevidence: {args.evidence}")
    print(f"RELEASED {before - len(data['locks'])} file(s) — {status}")
    return 0


def cmd_break(args) -> int:
    data = load()
    stale_after = data["stale_after_minutes"]
    p = norm(args.path)
    match = next((lk for lk in data["locks"] if lk["path"] == p), None)
    if match is None:
        print(f"no claim on {p}", file=sys.stderr)
        return 1
    if not is_stale(match, stale_after):
        print(
            f"REFUSED: {p} held by [{match['tool']}] for only {age_str(match)} "
            f"(stale at {stale_after}m). Not stale — leave it alone.",
            file=sys.stderr,
        )
        return 2

    data["locks"] = [lk for lk in data["locks"] if lk["path"] != p]
    save(data)
    status = post_build(
        f"`[{args.tool}] STALE-BREAK` `{p}` — was held by [{match['tool']}] for {age_str(match)}"
    )
    print(f"STALE-BREAK {p} (was [{match['tool']}], {age_str(match)}) — {status}")
    return 0


def format_handoff(
    tool: str, next_tool: str, goal: str, done: str, evidence: str, left: str, touched: str
) -> str:
    """Canonical #build HANDOFF. A post with no Evidence line is a rumour."""
    return (
        f"[{tool}] HANDOFF -> {next_tool}\n"
        f"Goal: {goal.strip()}\n"
        f"Done: {done.strip()}\n"
        f"Evidence: {evidence.strip()}\n"
        f"Left: {left.strip()}\n"
        f"Touched: {touched.strip()}"
    )


def cmd_handoff(args) -> int:
    evidence = (args.evidence or "").strip()
    if not evidence:
        print(
            "REFUSED: Evidence line required — a handoff without it is a rumour.", file=sys.stderr
        )
        return 1
    body = format_handoff(
        args.tool,
        args.next_tool,
        args.goal,
        args.done,
        evidence,
        args.left,
        args.touched,
    )
    print(body)
    status = post_build(body)
    print(status)
    return 0


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on usage errors — the same code we use for REFUSED.

    A caller branching on `rc == 2` would read a typo'd `--tool` as "another tool
    holds this file" and quietly take different work. Found by an independent
    review of this file (Buzz canary GRID-CANARY-20260809-104317, 2026-08-09).
    Usage errors now exit 1, which is what the docstring always claimed.
    """

    def error(self, message: str):  # noqa: D102 - argparse override
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(1)


def main() -> int:
    ap = _Parser(
        prog="buzzlock", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="show active claims").set_defaults(func=cmd_status)

    c = sub.add_parser("claim", help="claim files before editing")
    c.add_argument("paths", nargs="+")
    c.add_argument("--tool", required=True, choices=TOOLS)
    c.add_argument("--reason", required=True)
    c.set_defaults(func=cmd_claim)

    r = sub.add_parser("release", help="release files when you stop")
    r.add_argument("paths", nargs="+")
    r.add_argument("--tool", required=True, choices=TOOLS)
    r.add_argument("--evidence", required=True, help="exit code / test result — required")
    r.set_defaults(func=cmd_release)

    b = sub.add_parser("break", help="take over a stale claim")
    b.add_argument("path")
    b.add_argument("--tool", required=True, choices=TOOLS)
    b.set_defaults(func=cmd_break)

    h = sub.add_parser("handoff", help="post a #build HANDOFF (Evidence required)")
    h.add_argument("--tool", required=True, choices=TOOLS)
    h.add_argument("--next", dest="next_tool", required=True, help="next tool or Boss")
    h.add_argument("--goal", required=True)
    h.add_argument("--done", required=True)
    h.add_argument("--evidence", required=True, help="exit code / test result — required")
    h.add_argument("--left", required=True)
    h.add_argument("--touched", required=True)
    h.set_defaults(func=cmd_handoff)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
