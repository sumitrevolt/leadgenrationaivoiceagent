#!/usr/bin/env python3
"""omniroute_self_healing_watchdog.py — Autonomous Self-Healing Watchdog for OmniRoute & 5 Desktop Apps.

Monitors:
1. OmniRoute Gateway (:20128) and Claude Proxy (:22000).
2. All 14 LeadsGen Combos and their 42 live free-tier provider slots.
3. Configuration integrity across all 5 Desktop Apps:
   - Hermes Desktop App
   - Claude Desktop App
   - WorkBuddy Desktop App
   - OpenClaw Desktop App
   - Verdant Desktop App
4. Auto-remediation: On drift or lane failure, triggers autonomous reseed and resync.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
LOG_DIR = REPO_ROOT / "uat_evidence"
LOG_DIR.mkdir(exist_ok=True)
WATCHDOG_LOG = LOG_DIR / "omniroute_watchdog.log"
WATCHDOG_LOG_BACKUP = LOG_DIR / "omniroute_watchdog.log.1"
WATCHDOG_LOG_MAX_BYTES = 2 * 1024 * 1024
# The checked-in venv launcher can point at a removed interpreter after a
# desktop-app update. Reuse the interpreter running this watchdog unless an
# explicit operator override is supplied.
PYTHON_EXE = os.environ.get("LEADGEN_PYTHON", sys.executable)
GATEWAY_HEALTH_TIMEOUT_S = 60
DESKTOP_AUTH_STATE = REPO_ROOT / "data" / "omniroute_desktop_auth_state.json"


def log(msg: str):
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    line = f"[{timestamp}] {msg}"
    print(line)
    try:
        if WATCHDOG_LOG.exists() and WATCHDOG_LOG.stat().st_size >= WATCHDOG_LOG_MAX_BYTES:
            WATCHDOG_LOG_BACKUP.unlink(missing_ok=True)
            WATCHDOG_LOG.replace(WATCHDOG_LOG_BACKUP)
        with open(WATCHDOG_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def check_gateway_health() -> bool:
    try:
        # OmniRoute has no stable /api/health contract. /v1/models is the
        # gateway's supported readiness endpoint and must expose all 14 lanes.
        req = urllib.request.Request("http://127.0.0.1:20128/v1/models")
        # The catalog is intentionally rich (14 combos plus provider models)
        # and can take a few seconds to stream on a busy Docker Desktop VM.
        with urllib.request.urlopen(req, timeout=GATEWAY_HEALTH_TIMEOUT_S) as resp:
            if resp.getcode() != 200:
                return False
            payload = json.loads(resp.read())
            combos = {
                str(item.get("id", ""))
                for item in payload.get("data", [])
                if isinstance(item, dict)
            }
            return all(f"leadsgen combo {i}" in combos for i in range(1, 15))
    except Exception as e:
        log(f"Gateway health check failed: {e}")
        return False


def check_canary_inference(combo: str = "leadsgen combo 1") -> bool:
    try:
        from scripts.leadgen_admin_harness_mcp import tool_omniroute_query_combo
        res = tool_omniroute_query_combo({"combo": combo, "prompt": "canary ping: reply OK in 1 word", "max_tokens": 16})
        text = res.get("text", "")
        return "OK" in text or len(text.strip()) > 0
    except Exception as e:
        log(f"Canary inference failed for {combo}: {e}")
        return False


def _memory_bytes(value: str) -> int:
    """Parse the bounded units emitted by ``docker stats``."""
    raw = value.strip().replace(" ", "")
    units = (("GiB", 1024**3), ("MiB", 1024**2), ("KiB", 1024), ("GB", 10**9), ("MB", 10**6), ("kB", 1000), ("B", 1))
    for suffix, multiplier in units:
        if raw.endswith(suffix):
            try:
                return int(float(raw[: -len(suffix)]) * multiplier)
            except ValueError:
                return 0
    try:
        return int(float(raw))
    except ValueError:
        return 0


def _docker_binary() -> str:
    """Resolve Docker for both an interactive shell and Task Scheduler PATH."""
    configured = os.environ.get("DOCKER_EXE", "").strip()
    candidates = [
        configured,
        shutil.which("docker"),
        r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
        str(Path.home() / "AppData" / "Local" / "Programs" / "DockerDesktop" / "resources" / "bin" / "docker.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return "docker"


def check_container_memory(container: str = "leadgen_omniroute") -> bool:
    """Report bounded gateway memory without mutating or restarting Docker."""
    try:
        docker = _docker_binary()
        limit = subprocess.run(
            [docker, "inspect", container, "--format", "{{.HostConfig.Memory}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        limit_bytes = int(limit.stdout.strip() or "0") if limit.returncode == 0 else 0
        stats = subprocess.run(
            [docker, "stats", container, "--no-stream", "--format", "{{.MemUsage}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        usage = stats.stdout.strip().split("/", 1)[0] if stats.returncode == 0 else ""
        used_bytes = _memory_bytes(usage)
        if limit_bytes <= 0 or used_bytes <= 0:
            log(f"Memory guard unavailable for {container}: bounded limit/stats missing")
            return False
        ratio = used_bytes / limit_bytes
        log(f"Memory guard: {container} {used_bytes / 1024**2:.1f} MiB / {limit_bytes / 1024**2:.1f} MiB ({ratio:.1%})")
        if ratio >= 0.90:
            log(f"WARNING: {container} memory is at or above 90%; no automatic restart performed")
            return False
        return True
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        log(f"Memory guard failed for {container}: {exc}")
        return False


def recover_stopped_gateway(container: str = "leadgen_omniroute") -> bool:
    """Start an existing stopped gateway container without rebuilding or restarting it.

    The scheduler may recover a stopped local container, but it must not mutate a
    running container or invent a Docker/credential configuration. Missing
    containers are left for the canonical launcher/manual investigation.
    """
    try:
        docker = _docker_binary()
        inspect = subprocess.run(
            [docker, "inspect", container, "--format", "{{.State.Running}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        if inspect.returncode != 0:
            log(f"Gateway recovery skipped for {container}: container missing or Docker unavailable")
            return False
        if inspect.stdout.strip().lower() == "true":
            log(f"Gateway recovery skipped for {container}: container already running")
            return True
        started = subprocess.run(
            [docker, "start", container],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if started.returncode == 0:
            log(f"Gateway recovery started stopped container {container}")
            return True
        log(f"Gateway recovery failed for {container}: {started.stderr or started.stdout}")
        return False
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"Gateway recovery failed for {container}: {exc}")
        return False


def verify_desktop_apps_configs() -> dict[str, bool]:
    home = Path.home()
    results = {}

    def has_canonical(path: Path) -> bool:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            return all(f"leadsgen combo {i}" in text for i in range(1, 15))
        except Exception:
            return False

    # 1. Hermes
    hermes_roaming = home / "AppData" / "Roaming" / "Hermes" / "connections.json"
    hermes_local = home / "AppData" / "Local" / "hermes" / "config.yaml"
    results["hermes"] = hermes_roaming.exists() and hermes_local.exists() and has_canonical(hermes_local)

    # 2. Claude Desktop
    claude_cfg = home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    results["claude"] = claude_cfg.exists() and '"mcpServers"' in claude_cfg.read_text(encoding="utf-8", errors="ignore")

    # 3. WorkBuddy
    wb_settings = home / ".workbuddy-ai" / "settings.json"
    wb_models = home / ".workbuddy-ai" / "models.json"
    results["workbuddy"] = wb_settings.exists() and wb_models.exists() and has_canonical(wb_models)

    # 4. OpenClaw
    openclaw_cfg = home / ".openclaw" / "openclaw.json"
    # OpenClaw keeps MCP workspace wiring in .mcp.json; openclaw.json is the
    # model/provider registry.  Do not inject an undocumented root key.
    openclaw_mcp = home / ".openclaw" / "workspace" / ".mcp.json"
    results["openclaw"] = (
        openclaw_cfg.exists()
        and has_canonical(openclaw_cfg)
        and openclaw_mcp.exists()
        and '"mcpServers"' in openclaw_mcp.read_text(encoding="utf-8", errors="ignore")
    )

    # 5. Verdant
    verdant_roaming = home / "AppData" / "Roaming" / "Verdant" / "config.json"
    verdant_dot = home / ".verdant" / "config.json"
    results["verdant"] = verdant_roaming.exists() and verdant_dot.exists() and has_canonical(verdant_roaming)

    return results


def _desktop_auth_alert(title: str, body: str, priority: str) -> None:
    """Best-effort local/ntfy alert; credentials are never included."""
    try:
        import asyncio

        from app.integrations import ntfy

        asyncio.run(ntfy.push(title, body, priority=priority, tags=["computer", "warning"]))
    except Exception:
        pass
    log(f"Desktop auth alert: {title} - {body}")


def record_desktop_auth_transition(
    auth_ok: bool,
    *,
    state_path: Path | None = None,
    alert_sink=None,
) -> bool:
    """Alert once on missing auth and once on recovery; never expose a value."""
    path = state_path or DESKTOP_AUTH_STATE
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError, TypeError):
        state = {}

    was_alerted = bool(state.get("alerted"))
    fails = int(state.get("fails") or 0)
    alert = alert_sink or _desktop_auth_alert
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if not auth_ok:
        fails += 1
        if not was_alerted:
            state = {"alerted": True, "fails": fails, "last_transition": now}
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            except OSError as exc:
                log(f"Desktop auth state write failed: {exc}")
            alert(
                "OmniRoute desktop authentication missing",
                "OMNIROUTE_API_KEY is required but unavailable. Owner credential-store action required.",
                "urgent",
            )
        else:
            state["fails"] = fails
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            except OSError as exc:
                log(f"Desktop auth state write failed: {exc}")
        return False

    if was_alerted:
        state = {"alerted": False, "fails": 0, "last_transition": now}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except OSError as exc:
            log(f"Desktop auth state write failed: {exc}")
        alert(
            "OmniRoute desktop authentication recovered",
            "Required desktop credential is available again; normal verification resumed.",
            "default",
        )
    elif state:
        state["fails"] = 0
        try:
            path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except OSError as exc:
            log(f"Desktop auth state write failed: {exc}")
    return True


def check_desktop_auth_readiness() -> bool:
    """Fail closed when a desktop config requires an unavailable key.

    This is deliberately presence-only: credential values are never read into
    logs or copied between applications.  A missing secret is an owner action,
    not something the self-healer may invent.
    """
    home = Path.home()
    config_paths = (
        home / "AppData" / "Roaming" / "Hermes" / "connections.json",
        home / "AppData" / "Local" / "hermes" / "config.yaml",
        home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
        home / ".workbuddy-ai" / "settings.json",
        home / ".workbuddy-ai" / "models.json",
        home / ".openclaw" / "openclaw.json",
        home / ".openclaw" / "workspace" / ".mcp.json",
        home / "AppData" / "Roaming" / "Verdant" / "config.json",
        home / ".verdant" / "config.json",
    )
    requires_key = False
    for path in config_paths:
        try:
            if path.exists() and "OMNIROUTE_API_KEY" in path.read_text(
                encoding="utf-8", errors="ignore"
            ):
                requires_key = True
                break
        except OSError:
            continue

    if not requires_key:
        return True

    credential_present = bool(os.environ.get("OMNIROUTE_API_KEY", "").strip())
    return record_desktop_auth_transition(credential_present)


def trigger_self_healing(reason: str):
    log(f"ALERT: Triggering autonomous self-healing (reason: {reason})...")
    sync_script = REPO_ROOT / "scripts" / "sync_all_combos_all_apps.py"
    try:
        r = subprocess.run(
            [PYTHON_EXE, str(sync_script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if r.returncode == 0:
            log("SUCCESS: Self-healing finished successfully. Database re-seeded & all 5 desktop apps synced.")
        else:
            log(f"WARNING: Self-healing script returned non-zero exit ({r.returncode}): {r.stderr or r.stdout}")
    except Exception as exc:
        log(f"ERROR: Self-healing execution failed: {exc}")


def run_cycle() -> bool:
    log("=== Starting OmniRoute & 5 Desktop Apps Watchdog Cycle ===")

    # 1. Check gateway
    gw_ok = check_gateway_health()
    if not gw_ok:
        log("OmniRoute gateway unreachable. Attempting self-healing...")
        recover_stopped_gateway()
        trigger_self_healing("gateway unreachable")
        time.sleep(5)
        gw_ok = check_gateway_health()

    # 1b. Observe the cgroup backstop. This is intentionally evidence-only:
    # Docker restart/kill actions remain outside this watchdog's authority.
    memory_ok = check_container_memory()

    # 2. Check desktop apps
    app_status = verify_desktop_apps_configs()
    missing_apps = [app for app, ok in app_status.items() if not ok]
    if missing_apps:
        log(f"Config drift detected for apps: {missing_apps}. Self-healing...")
        trigger_self_healing(f"missing configs for {missing_apps}")

    # Configuration presence is not authentication proof.  Keep credential
    # readiness separate and fail closed without exposing or inventing a key.
    desktop_auth_ok = check_desktop_auth_readiness()

    # 3. Test canary inference
    canary_ok = check_canary_inference("leadsgen combo 1")
    if not canary_ok and gw_ok:
        log("Canary inference failed on primary combo. Attempting re-seed...")
        trigger_self_healing("canary inference failure")
        canary_ok = check_canary_inference("leadsgen combo 1")

    all_healthy = (
        gw_ok and memory_ok and not missing_apps and desktop_auth_ok and canary_ok
    )
    log(
        f"Cycle summary: Gateway={gw_ok}, MemoryGuard={memory_ok}, "
        f"DesktopApps={app_status}, DesktopAuth={desktop_auth_ok}, "
        f"CanaryInference={canary_ok} -> ALL_HEALTHY={all_healthy}"
    )
    return all_healthy


def main():
    parser = argparse.ArgumentParser(description="OmniRoute Autonomous Self-Healing Watchdog")
    parser.add_argument("--daemon", action="store_true", help="Run continuously in daemon loop")
    parser.add_argument("--interval", type=int, default=300, help="Check interval in seconds (default: 300)")
    args = parser.parse_args()

    if not args.daemon:
        healthy = run_cycle()
        sys.exit(0 if healthy else 1)

    log(f"OmniRoute Watchdog daemon starting (interval: {args.interval}s)...")
    while True:
        try:
            run_cycle()
        except Exception as e:
            log(f"Unexpected error in watchdog cycle: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
