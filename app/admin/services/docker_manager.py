"""
Docker Manager Service
Wraps docker CLI via subprocess - no docker-py dependency required.
All methods return structured dicts
callers handle HTTP concerns.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _docker_bin() -> str:
    """Locate the docker binary; raises if missing."""
    bin_path = shutil.which("docker")
    if not bin_path:
        raise FileNotFoundError("docker binary not found on PATH")
    return bin_path


def _run(args: list[str], timeout: int = 30) -> dict[str, Any]:
    """Run a docker subcommand, return structured result."""
    cmd = [_docker_bin()] + args
    logger.debug("docker cmd: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e), "stdout": "", "stderr": ""}
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"command timed out after {timeout}s",
            "stdout": "",
            "stderr": "",
        }

    if proc.returncode == 0:
        return {
            "ok": True,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.returncode,
        }
    return {
        "ok": False,
        "error": proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}",
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "returncode": proc.returncode,
    }


def _parse_json_lines(text: str) -> list[dict[str, Any]]:
    """Parse docker's --format json output (one JSON object per line)."""
    items: list[dict[str, Any]] = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("docker json parse failed: %r", line)
    return items


# ── Public API ──────────────────────────────────────────────────────────────


def list_containers() -> dict[str, Any]:
    """List all containers (running + stopped)."""
    result = _run(["ps", "-a", "--format", "json"])
    if not result["ok"]:
        return result
    return {"ok": True, "containers": _parse_json_lines(result["stdout"])}


def container_detail(name: str) -> dict[str, Any]:
    """Inspect a single container by name."""
    result = _run(["inspect", name])
    if not result["ok"]:
        return result
    try:
        data = json.loads(result["stdout"])
        return {"ok": True, "container": data[0] if data else None}
    except (json.JSONDecodeError, IndexError) as e:
        return {"ok": False, "error": f"inspect parse failed: {e}"}


def start_container(name: str) -> dict[str, Any]:
    """Start a stopped container."""
    return _run(["start", name])


def stop_container(name: str) -> dict[str, Any]:
    """Stop a running container."""
    return _run(["stop", name])


def restart_container(name: str) -> dict[str, Any]:
    """Restart a container."""
    return _run(["restart", name])


def get_logs(name: str, lines: int = 100) -> dict[str, Any]:
    """Fetch tail of container logs."""
    result = _run(["logs", "--tail", str(lines), name], timeout=15)
    return result


def get_stats() -> dict[str, Any]:
    """One-shot docker stats (CPU, MEM, NET, BLOCK)."""
    result = _run(["stats", "--no-stream", "--format", "json"], timeout=60)
    if not result["ok"]:
        return result
    return {"ok": True, "stats": _parse_json_lines(result["stdout"])}


def list_networks() -> dict[str, Any]:
    """List all docker networks."""
    result = _run(["network", "ls", "--format", "json"])
    if not result["ok"]:
        return result
    return {"ok": True, "networks": _parse_json_lines(result["stdout"])}


def list_volumes() -> dict[str, Any]:
    """List all docker volumes."""
    result = _run(["volume", "ls", "--format", "json"])
    if not result["ok"]:
        return result
    return {"ok": True, "volumes": _parse_json_lines(result["stdout"])}
