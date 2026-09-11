"""Owner Command Center — unified L1→L4 aggregator API.

ONE call powers the entire Owner Command Center dashboard. Fans IN over
existing modules (today_overview, automation_health, activation_summary,
workforce, omniroute combos, task ledger, admin dashboard) — each in its OWN
try/except so partial data is fine, NEVER raises.

GET /api/owner-command-center/overview  → full JSON payload
GET /app/owner-command-center           → dashboard page

Rollback: remove the include_router block from app/main.py.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

from app.api.auth_deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Owner Command Center"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe(fn, default=None, label=""):
    """Call fn() safely; log + return default on any error."""
    try:
        return fn()
    except Exception as e:
        logger.debug("OCC block %s failed: %s", label, e)
        return default


def _safe_async(coro_fn, default=None, label=""):
    """Run an async fn safely; return default on error."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an async context; schedule and return default
            return default
        return loop.run_until_complete(coro_fn())
    except Exception as e:
        logger.debug("OCC async block %s failed: %s", label, e)
        return default


@router.get("/overview", response_model=None)
async def owner_command_center_overview(
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Full Owner Command Center payload — L1 executive + L2 automation + L3 detail."""
    start = time.monotonic()

    # --- 1. Today Overview (marketing/email/content/social stats) ---
    today_overview = _safe(
        lambda: __import__("app.platform.today_overview", fromlist=["build"]).build().totals,
        default={},
        label="today_overview",
    )

    # --- 2. Automation Health (scheduler jobs + heartbeats) ---
    automation_health = _safe(
        lambda: __import__("app.platform.automation_health", fromlist=["health"])().health(),
        default={},
        label="automation_health",
    )

    # --- 3. Activation Summary (money path readiness) ---
    activation = {}
    try:
        from app.api.activation import get_activation_summary

        activation = await get_activation_summary() or {}
    except Exception as e:
        logger.debug("activation summary failed: %s", e)

    # --- 4. Workforce Live Status (31 agents + desktop apps) ---
    # TRUTH GATE: workforce_live_status.json was previously populated by
    # a synthetic orchestrator. Now NOT_INSTRUMENTED — only show real data.
    def _get_workforce():
        from app.platform import runtime_data

        p = runtime_data.store_path("workforce_live_status.json")
        if not p.is_file():
            return {}
        try:
            with open(p, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return {}
        if raw.get("evidence_kind") == "inference_probe_only":
            return {"status": "NOT_INSTRUMENTED", "note": "Real worker activity tracked via Celery/team.log_event"}
        return raw
    workforce = _safe(_get_workforce, default={}, label="workforce")

    # --- 5. OmniRoute 14 Combos health ---
    combos = _safe(
        lambda: _get_combo_health(),
        default=[],
        label="combos",
    )

    # --- 6. Task Ledger (from admin module SQLite) ---
    task_ledger = _safe(
        lambda: _get_task_ledger_summary(),
        default={"total": 0, "by_status": {}, "by_owner": {}},
        label="task_ledger",
    )

    # --- 7. Admin Dashboard KPIs (prospects, clients, emails, revenue) ---
    admin_kpis = _safe(
        lambda: _get_admin_kpis(),
        default={},
        label="admin_kpis",
    )

    # --- 8. System Health (local) ---
    system = _safe(
        lambda: _get_local_system_health(),
        default={},
        label="system",
    )

    # --- 9. Wiring Gaps (flag ON but backend missing) ---
    wiring_gaps = _safe(
        lambda: __import__("app.platform.automation_health", fromlist=["wiring_gaps"])().wiring_gaps(),
        default=[],
        label="wiring_gaps",
    )

    elapsed_ms = round((time.monotonic() - start) * 1000, 1)

    return {
        "ok": True,
        "at": _now_iso(),
        "elapsed_ms": elapsed_ms,
        "today_overview": today_overview,
        "automation_health": automation_health,
        "activation": activation,
        "workforce": workforce,
        "combos": combos,
        "task_ledger": task_ledger,
        "admin_kpis": admin_kpis,
        "system": system,
        "wiring_gaps": wiring_gaps,
    }


def _read_json_file(path: str, default: Any) -> Any:
    import json

    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_combo_health() -> list[dict]:
    """Fetch 14 combo health from OmniRoute gateway."""
    import urllib.request

    try:
        req = urllib.request.Request(
            "http://127.0.0.1:20128/v1/models",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return []

    combos = []
    for m in data.get("data", []):
        mid = m.get("id", "")
        if "combo" not in mid.lower():
            continue
        combos.append({
            "id": mid,
            "object": m.get("object", "model"),
            "created": m.get("created", 0),
        })
    return combos


def _get_task_ledger_summary() -> dict:
    """Summarize task ledger from admin module."""
    try:
        from app.admin.services.task_ledger import (
            get_kanban,
            get_worker_statuses,
        )

        kanban = get_kanban()
        workers = get_worker_statuses()
        by_status = {
            "backlog": len(kanban.backlog),
            "in_progress": len(kanban.in_progress),
            "review": len(kanban.review),
            "done": len(kanban.done),
        }
        by_owner = {w.name: w.active_tasks for w in workers if w.active_tasks > 0}
        total = sum(by_status.values())
        return {"total": total, "by_status": by_status, "by_owner": by_owner}
    except Exception:
        return {"total": 0, "by_status": {}, "by_owner": {}}


def _get_admin_kpis() -> dict:
    """Read key KPIs from local data files (via the canonical runtime resolver)."""
    from app.platform import runtime_data

    kpis = {}

    # Prospects
    try:
        prospects_p = runtime_data.store_path("prospects.jsonl")
        if prospects_p.is_file():
            with open(prospects_p, encoding="utf-8") as f:
                lines = [l for l in f if l.strip()]
            kpis["prospects_total"] = len(lines)
    except Exception:
        pass

    # Marketing clients
    try:
        clients_p = runtime_data.store_path("marketing_clients.jsonl")
        if clients_p.is_file():
            with open(clients_p, encoding="utf-8") as f:
                lines = [l for l in f if l.strip()]
            kpis["clients_total"] = len(lines)
    except Exception:
        pass

    # Content queue
    try:
        cq_dir = "data/content_queue"
        if os.path.isdir(cq_dir):
            kpis["content_queue"] = len(
                [f for f in os.listdir(cq_dir) if f.endswith(".jsonl")]
            )
    except Exception:
        pass

    return kpis


def _get_local_system_health() -> dict:
    """Local system health (CPU/RAM/disk) — best effort."""
    result = {}
    try:
        import shutil

        total, used, free = shutil.disk_usage("C:\\")
        result["disk_total_gb"] = round(total / (1024**3), 1)
        result["disk_used_gb"] = round(used / (1024**3), 1)
        result["disk_free_gb"] = round(free / (1024**3), 1)
        result["disk_percent"] = round(used / total * 100, 1)
    except Exception:
        pass

    # Port checks
    import socket

    ports = {
        "omniroute": 20128,
        "local_app": 8000,
        "buzz_relay": 3100,
    }
    for name, port in ports.items():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(("127.0.0.1", port))
                result[f"port_{name}"] = "open"
        except Exception:
            result[f"port_{name}"] = "closed"

    return result


import json  # noqa: E402 — used in _get_combo_health
