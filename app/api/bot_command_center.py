"""Bot Command Center — Pilot multi-bot coordination surface (OWNER-facing).

Telegram-style chronological feed of task assignments / ACKs / status across the
9-bot fleet. Admin JWT-gated (same email+password as admin dashboard login —
koi alag basic-auth password NAHI).

Routes:
    GET /app/bot-command-center            → page (frontend/bot_command_center.html)
    GET /api/bot-command-center/state      → JSON state (bots/tasks/messages/pinned)

Data source: command_center/data/*.json(l) — single source of truth shared with
Kanban/chat. Container me volume path /app/data/command_center (host:
/opt/leadgen/data/command_center) taaki redeploy pe data bache.

Rollback = ye router include-block main.py se hatao. Never raises — partial
state bhi valid response deta hai (house style: fail-open read-only surface).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.api.auth_deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Platform"])

_FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


def _data_dir() -> Path:
    """Data dir resolution: env override → repo layout (dev) → volume (prod)."""
    env = os.getenv("BOT_CC_DATA_DIR")
    if env:
        return Path(env)
    local = Path(__file__).resolve().parents[2] / "command_center" / "data"
    if local.exists():
        return local
    return Path("/app/data/command_center")


def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # corrupt file → empty default, surface in warnings
        logger.warning("bot_cc._read_json failed %s: %s", path.name, e)
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if not path.exists():
            return out
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue  # skip corrupt line, rest of feed survives
    except Exception as e:
        logger.warning("bot_cc._read_jsonl failed: %s", e)
    return out


def _iso_now_ist() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _build_state() -> dict[str, Any]:
    """Assemble full CC state. Validation failures = warnings list, not 500."""
    base = _data_dir()
    bots = _read_json(base / "bots.json", {})
    tasks = _read_json(base / "tasks.json", [])
    messages = _read_jsonl(base / "messages.jsonl")
    pinned = _read_json(base / "pinned.json", {})

    warnings: list[str] = []
    active_no_owner = [
        t.get("id")
        for t in tasks
        if t.get("status") in ("ASSIGNED", "RUNNING", "BLOCKED") and not t.get("owner")
    ]
    assigned_no_ts = [
        t.get("id")
        for t in tasks
        if t.get("status") == "ASSIGNED" and not t.get("assigned_at")
    ]
    if active_no_owner:
        warnings.append(f"active task without owner: {active_no_owner}")
    if assigned_no_ts:
        warnings.append(f"ASSIGNED without assigned_at (ACK watchdog blind): {assigned_no_ts}")

    counts = {"working": 0, "idle": 0, "blocked": 0}
    for b in bots.values():
        s = str(b.get("status", "")).upper()
        if "BLOCKED" in s:
            counts["blocked"] += 1
        elif any(k in s for k in ("REV-", "WORKING", "COORDINATING")):
            counts["working"] += 1
        else:
            counts["idle"] += 1

    return {
        "ok": True,
        "generated_at": _iso_now_ist(),
        "group": "OWNER COMMAND CENTER",
        "subtitle": (
            f"Pilot + 8 bots · {counts['working']} working · "
            f"{counts['idle']} idle · {counts['blocked']} blocked"
        ),
        "counts": counts,
        "bots": bots,
        "tasks": sorted(tasks, key=lambda t: str(t.get("id", ""))),
        "messages": sorted(messages, key=lambda m: str(m.get("ts", ""))),
        "pinned": pinned,
        "warnings": warnings,
    }


@router.get("/api/bot-command-center/state")
async def bot_command_center_state(_user=Depends(require_admin)) -> dict[str, Any]:
    """Full CC state — admin JWT gated (same login as /app/admin)."""
    return _build_state()


@router.get("/app/bot-command-center")
async def bot_command_center_page(_user=Depends(require_admin)):
    """Owner-facing Telegram-style group page (admin session required)."""
    return FileResponse(str(_FRONTEND_DIR / "bot_command_center.html"))
