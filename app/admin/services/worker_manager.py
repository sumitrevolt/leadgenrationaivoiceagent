"""
Worker Manager Service
Scans Hermes profiles, tracks per-worker RAM/CPU, detects idle/stale state.

Returns structured worker status for the admin worker panel.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

HERMES_PROFILES_DIR = os.path.expanduser(r"~\AppData\Local\hermes\profiles")

# Worker categories for display
WORKER_CATEGORIES = {
    "hermes": "AI Agent",
    "claude": "Desktop",
    "openclaw": "Desktop",
    "workbuddy": "Desktop",
    "verdant": "Desktop",
    "board": "Council",
    "engineering": "Engineering",
    "guardian": "Security",
    "hunter": "Sales",
    "operations": "Operations",
    "pilot": "Pilot",
    "platform": "Platform",
    "sales": "Sales",
    "success": "Customer Success",
}


def _profiles_dir() -> str:
    """Return Hermes profiles directory."""
    return HERMES_PROFILES_DIR


def list_profiles() -> list[str]:
    """List all Hermes profile names."""
    d = _profiles_dir()
    if not os.path.isdir(d):
        return []
    try:
        return sorted(name for name in os.listdir(d) if os.path.isdir(os.path.join(d, name)))
    except OSError:
        return []


def _get_hermes_processes() -> list[dict[str, Any]]:
    """Get all Hermes-related processes (hermes.exe, Hermes.exe, python.exe, node.exe for Hermes)."""
    procs = []
    try:
        # Use tasklist for reliable Windows process listing
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                parts = line.strip('"').split('","')
                if len(parts) >= 2:
                    name = parts[0]
                    pid_str = parts[1]
                    if "hermes" in name.lower():
                        try:
                            pid = int(pid_str)
                            # Get memory and command line via PowerShell
                            ps_result = subprocess.run(
                                [
                                    "powershell",
                                    "-NoProfile",
                                    "-Command",
                                    f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | Select-Object CommandLine, WorkingSetSize | ConvertTo-Json",
                                ],
                                capture_output=True,
                                text=True,
                                timeout=5,
                            )
                            cmdline = ""
                            mem = 0
                            if ps_result.returncode == 0 and ps_result.stdout.strip():
                                pdata = json.loads(ps_result.stdout)
                                cmdline = pdata.get("CommandLine", "") or ""
                                mem = int(pdata.get("WorkingSetSize") or 0)
                            procs.append(
                                {
                                    "Name": name,
                                    "ProcessId": pid,
                                    "CommandLine": cmdline,
                                    "WorkingSetSize": mem,
                                }
                            )
                        except (ValueError, json.JSONDecodeError):
                            continue
    except Exception as e:
        logger.debug("Failed to get Hermes processes: %s", e)
    return procs


def _match_profile_to_process(profile: str, processes: list[dict]) -> dict | None:
    """Match a Hermes profile to a running process."""
    profile_lower = profile.lower()
    for proc in processes:
        cmdline = (proc.get("CommandLine") or "").lower()
        name = (proc.get("Name") or "").lower()
        if profile_lower in cmdline or profile_lower in name:
            return proc
    return None


def _read_worker_task(profile: str) -> str | None:
    """Try to read current task from worker memory/profile files."""
    profile_dir = os.path.join(_profiles_dir(), profile)
    if not os.path.isdir(profile_dir):
        return None
    # Check for recent memory files
    memory_dir = os.path.join(profile_dir, "memory")
    if os.path.isdir(memory_dir):
        try:
            files = sorted(os.listdir(memory_dir), reverse=True)
            if files:
                latest = os.path.join(memory_dir, files[0])
                with open(latest, encoding="utf-8", errors="ignore") as f:
                    content = f.read(500)
                    # Extract first meaningful line as task
                    for line in content.split("\n"):
                        line = line.strip()
                        if line and not line.startswith("#"):
                            return line[:100]
        except OSError:
            pass
    return None


def get_workers() -> list[dict[str, Any]]:
    """Return list of all workers with status."""
    profiles = list_profiles()
    processes = _get_hermes_processes()
    workers = []

    for profile in profiles:
        proc = _match_profile_to_process(profile, processes)
        if proc:
            ws = int(proc.get("WorkingSetSize") or proc.get("WorkingSet64") or 0)
            workers.append(
                {
                    "name": profile,
                    "status": "active",
                    "pid": int(proc.get("ProcessId") or 0),
                    "ram_mb": round(ws / (1024 * 1024), 1),
                    "category": WORKER_CATEGORIES.get(profile, "Agent"),
                    "current_task": _read_worker_task(profile),
                }
            )
        else:
            workers.append(
                {
                    "name": profile,
                    "status": "idle",
                    "pid": None,
                    "ram_mb": 0,
                    "category": WORKER_CATEGORIES.get(profile, "Agent"),
                    "current_task": None,
                }
            )

    # Sort: active first, then by RAM
    workers.sort(key=lambda x: (0 if x["status"] == "active" else 1, -x["ram_mb"]))
    return workers


def get_idle_workers() -> list[dict[str, Any]]:
    """Return idle workers available for task assignment."""
    return [w for w in get_workers() if w["status"] == "idle"]


def get_worker(name: str) -> dict[str, Any] | None:
    """Get single worker detail."""
    for w in get_workers():
        if w["name"] == name:
            return w
    return None


def kill_worker(name: str) -> dict[str, Any]:
    """Kill a worker process by profile name."""
    result = subprocess.run(
        ["taskkill", "/F", "/FI", f"WINDOWTITLE eq *{name}*"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode == 0:
        return {"ok": True}
    # Try by command line match
    result2 = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Get-CimInstance Win32_Process | Where-Object {{$_.CommandLine -like '*{name}*'}} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return {
        "ok": result2.returncode == 0,
        "error": result2.stderr if result2.returncode != 0 else None,
    }


def get_worker_count() -> dict[str, int]:
    """Return active/idle/total counts."""
    workers = get_workers()
    active = sum(1 for w in workers if w["status"] == "active")
    return {
        "total": len(workers),
        "active": active,
        "idle": len(workers) - active,
    }
