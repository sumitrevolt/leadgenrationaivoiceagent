"""System Health Monitor — per-process RAM/CPU, disk, and port monitoring.

Provides CPU%, RAM usage, per-process breakdown, disk C: usage, and
port availability for the admin system health panel. Uses psutil when
installed; on Windows without psutil it falls back to PowerShell WMI
and netstat commands. Never raises — degrades to -1/"unknown" on failure.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

# Process name fragments we care about for the admin panel.
_WATCHED_PROC_FRAGMENTS = (
    "hermes",
    "python",
    "node",
    "docker",
    "celery",
    "uvicorn",
    "redis",
    "postgres",
    "qdrant",
    "freeswitch",
    "prometheus",
    "grafana",
    "caddy",
)

# Key service ports to report status for.
_KEY_PORTS = (3100, 8000, 20128, 56835)


def _psutil_available() -> bool:
    try:
        import psutil  # noqa: F401

        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Per-process metrics
# ---------------------------------------------------------------------------


def _processes_psutil() -> list[dict[str, Any]]:
    """Return per-process RAM/CPU for watched processes via psutil."""
    import psutil

    procs: list[dict[str, Any]] = []
    seen_pids: set[int] = set()

    for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
        try:
            info = p.info
            name = (info.get("name") or "").lower()
            pid = int(info.get("pid") or 0)
            if not name or pid in seen_pids:
                continue
            if not any(frag in name for frag in _WATCHED_PROC_FRAGMENTS):
                continue

            mem_info = info.get("memory_info")
            ram_mb = round(mem_info.rss / (1024 * 1024), 1) if mem_info else 0.0

            # cpu_percent(interval=None) returns 0.0 on first call (non-blocking).
            try:
                cpu_pct = round(float(p.cpu_percent(interval=None) or 0.0), 1)
            except Exception:
                cpu_pct = 0.0

            procs.append(
                {
                    "name": info.get("name") or name,
                    "pid": pid,
                    "ram_mb": ram_mb,
                    "cpu_percent": cpu_pct,
                }
            )
            seen_pids.add(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception as e:
            logger.debug("processes_psutil: skip pid due to %s", e)
            continue

    procs.sort(key=lambda x: x["ram_mb"], reverse=True)
    return procs[:15]


def _processes_powershell() -> list[dict[str, Any]]:
    """Fallback: WMI process listing via PowerShell on Windows (no psutil)."""
    procs: list[dict[str, Any]] = []
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            r"Get-CimInstance Win32_Process | Select-Object Name, ProcessId, WorkingSet64 | Sort-Object WorkingSet64 -Descending | Select-Object -First 60 | ConvertTo-Json",
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, check=False
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return procs

        import json

        raw = json.loads(proc.stdout)
        if isinstance(raw, dict):
            raw = [raw]

        seen: set[int] = set()
        for item in raw:
            name = str(item.get("Name") or "").lower()
            pid = int(item.get("ProcessId") or 0)
            ws = int(item.get("WorkingSet64") or 0)
            if not name or pid in seen or ws == 0:
                continue
            if not any(frag in name for frag in _WATCHED_PROC_FRAGMENTS):
                continue
            seen.add(pid)
            procs.append(
                {
                    "name": item.get("Name", name),
                    "pid": pid,
                    "ram_mb": round(ws / (1024 * 1024), 1),
                    "cpu_percent": -1.0,  # not available via this query
                }
            )
            if len(procs) >= 15:
                break
    except Exception as e:
        logger.debug("processes_powershell failed: %s", e)
    return procs


def get_top_processes(limit: int = 15) -> list[dict[str, Any]]:
    """Top N watched processes by RAM. psutil preferred, PS fallback."""
    try:
        if _psutil_available():
            return _processes_psutil()[:limit]
        if os.name == "nt":
            return _processes_powershell()[:limit]
    except Exception as e:
        logger.warning("get_top_processes failed: %s", e)
    return []


# ---------------------------------------------------------------------------
# CPU / RAM / Disk aggregate metrics
# ---------------------------------------------------------------------------


def _cpu_ram_disk_psutil() -> dict[str, float]:
    import psutil

    cpu = round(psutil.cpu_percent(interval=0.1), 1)
    mem = psutil.virtual_memory()
    try:
        disk_path = "C:\\" if os.name == "nt" else os.getenv("HEALTH_DISK_PATH", "/")
        disk = psutil.disk_usage(disk_path)
    except Exception:
        disk = psutil.disk_usage(os.getcwd())

    return {
        "cpu_percent": cpu,
        "ram_total_gb": round(mem.total / (1024**3), 2),
        "ram_used_gb": round(mem.used / (1024**3), 2),
        "ram_percent": round(mem.percent, 1),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "disk_percent": round(disk.percent, 1),
    }


def _cpu_ram_disk_powershell() -> dict[str, float]:
    out: dict[str, float] = {
        "cpu_percent": -1.0,
        "ram_total_gb": -1.0,
        "ram_used_gb": -1.0,
        "ram_percent": -1.0,
        "disk_total_gb": -1.0,
        "disk_used_gb": -1.0,
        "disk_percent": -1.0,
    }
    try:
        # RAM + CPU
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            r"$os = Get-CimInstance Win32_OperatingSystem; $cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average; @{cpu_pct=[math]::Round($cpu,1); ram_total=[math]::Round($os.TotalVisibleMemorySize/1MB,2); ram_free=[math]::Round($os.FreePhysicalMemory/1MB,2)} | ConvertTo-Json",
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, check=False
        )
        if proc.returncode == 0 and proc.stdout.strip():
            import json

            d = json.loads(proc.stdout)
            total = float(d.get("ram_total", -1))
            free = float(d.get("ram_free", -1))
            out["ram_total_gb"] = total
            if total > 0 and free >= 0:
                out["ram_used_gb"] = round(total - free, 2)
                out["ram_percent"] = round((total - free) / total * 100, 1)
            out["cpu_percent"] = float(d.get("cpu_pct", -1))

        # Disk C:
        cmd2 = [
            "powershell",
            "-NoProfile",
            "-Command",
            r"$d = Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3 and DeviceID=\"C:\"'; @{total=[math]::Round($d.Size/1GB,2); free=[math]::Round($d.FreeSpace/1GB,2)} | ConvertTo-Json",
        ]
        proc2 = subprocess.run(
            cmd2, capture_output=True, text=True, timeout=15, check=False
        )
        if proc2.returncode == 0 and proc2.stdout.strip():
            import json

            d2 = json.loads(proc2.stdout)
            t = float(d2.get("total", -1))
            f = float(d2.get("free", -1))
            out["disk_total_gb"] = t
            if t > 0 and f >= 0:
                out["disk_used_gb"] = round(t - f, 2)
                out["disk_percent"] = round((t - f) / t * 100, 1)
    except Exception as e:
        logger.debug("cpu_ram_disk_powershell failed: %s", e)
    return out


# ---------------------------------------------------------------------------
# Port monitoring
# ---------------------------------------------------------------------------


def _ports_psutil(ports: tuple[int, ...]) -> list[dict[str, Any]]:
    import psutil

    results: list[dict[str, Any]] = []
    # Gather all listening sockets once.
    listeners: set[int] = set()
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status == "LISTEN" and conn.laddr:
                listeners.add(conn.laddr.port)
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass

    for port in ports:
        results.append({"port": port, "status": "open" if port in listeners else "closed"})
    return results


def _ports_netstat(ports: tuple[int, ...]) -> list[dict[str, Any]]:
    """Fallback: use netstat to check listening ports on Windows."""
    results: list[dict[str, Any]] = []
    try:
        proc = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        listening_ports: set[int] = set()
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                if "LISTENING" in line or "LISTEN" in line:
                    parts = line.strip().split()
                    for part in parts:
                        if ":" in part:
                            try:
                                p = int(part.rsplit(":", 1)[-1])
                                if 0 < p < 65536:
                                    listening_ports.add(p)
                            except ValueError:
                                continue
                                # stop scanning once we have port candidates
                            break

        for port in ports:
            results.append(
                {"port": port, "status": "open" if port in listening_ports else "closed"}
            )
    except Exception as e:
        logger.debug("ports_netstat failed: %s", e)
        for port in ports:
            results.append({"port": port, "status": "unknown"})
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_ports(ports: tuple[int, ...] = _KEY_PORTS) -> list[dict[str, Any]]:
    """Check whether given TCP ports are listening. psutil preferred."""
    try:
        if _psutil_available():
            return _ports_psutil(ports)
        if os.name == "nt":
            return _ports_netstat(ports)
        # Last resort: try a plain socket connect attempt per port.
        import socket

        results = []
        for port in ports:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.5)
                    result = s.connect_ex(("127.0.0.1", port))
                    results.append(
                        {"port": port, "status": "open" if result == 0 else "closed"}
                    )
            except Exception:
                results.append({"port": port, "status": "unknown"})
        return results
    except Exception as e:
        logger.warning("get_ports failed: %s", e)
        return [{"port": p, "status": "unknown"} for p in ports]


def get_health() -> dict[str, Any]:
    """Aggregate system health payload for the admin API.

    Returns a dict with cpu/ram/disk aggregates, top processes, and
    port status. Never raises — partial data on failure.
    """
    out: dict[str, Any] = {
        "cpu_percent": -1.0,
        "ram_total_gb": -1.0,
        "ram_used_gb": -1.0,
        "ram_percent": -1.0,
        "disk_total_gb": -1.0,
        "disk_used_gb": -1.0,
        "disk_percent": -1.0,
        "processes": [],
        "ports": [],
    }

    # Aggregate metrics
    try:
        if _psutil_available():
            out.update(_cpu_ram_disk_psutil())
        elif os.name == "nt":
            out.update(_cpu_ram_disk_powershell())
        else:
            logger.info("get_health: psutil not available and not on Windows")
    except Exception as e:
        logger.warning("get_health aggregate failed: %s", e)

    # Processes
    out["processes"] = get_top_processes(limit=15)

    # Ports
    out["ports"] = get_ports(_KEY_PORTS)

    return out
