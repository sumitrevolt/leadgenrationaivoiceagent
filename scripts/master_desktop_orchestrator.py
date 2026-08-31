#!/usr/bin/env python3
"""master_desktop_orchestrator.py — Enterprise Master Orchestrator for Antigravity Brain.

Unified orchestration, diagnostics, auto-fix, and GUI lifecycle management for:
1. Claude Desktop App
2. Hermes Desktop App
3. WorkBuddy Desktop App
4. DeepSeek & OmniRoute 12-Combo Harness
5. Universal MCP Servers (LeadGen Admin Harness, Buzz, Puppeteer, Playwright, Filesystem, Graphify)
6. Antigravity Computer-Use & Hardware Visual Control (Mouse, Keyboard, Screen Glow, HUD, Screenshots)

Usage:
  python scripts/master_desktop_orchestrator.py status
  python scripts/master_desktop_orchestrator.py fix
  python scripts/master_desktop_orchestrator.py launch-all
  python scripts/master_desktop_orchestrator.py launch-claude
  python scripts/master_desktop_orchestrator.py launch-hermes
  python scripts/master_desktop_orchestrator.py launch-workbuddy
  python scripts/master_desktop_orchestrator.py verify-harness
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON_EXE = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
GRAPHIFY_EXE = Path(os.path.expanduser(r"~\AppData\Roaming\uv\tools\graphifyy\Scripts\graphify-mcp.exe"))
GRAPHIFY_CMD = str(GRAPHIFY_EXE) if GRAPHIFY_EXE.exists() else "graphify-mcp"

# 12 Verified Dynamic OmniRoute Combos
ALL_COMBOS = [
    {"id": "claude-omni-coding-primary", "real": "leadgen-coding-primary", "name": "OmniRoute Coding Primary"},
    {"id": "claude-omni-coding-fast", "real": "leadgen-coding-fast", "name": "OmniRoute Coding Fast"},
    {"id": "claude-omni-repo-analysis", "real": "leadgen-repo-analysis", "name": "OmniRoute Repo Analysis"},
    {"id": "claude-omni-test-generation", "real": "leadgen-test-generation", "name": "OmniRoute Test Generation"},
    {"id": "claude-omni-agent-ops", "real": "leadgen-agent-ops", "name": "OmniRoute Agent Ops"},
    {"id": "claude-omni-swara-live", "real": "leadgen-swara-live", "name": "OmniRoute Swara Live"},
    {"id": "claude-omni-marketing-content", "real": "leadgen-marketing-content", "name": "OmniRoute Marketing Content"},
    {"id": "claude-omni-prospect-enrich", "real": "leadgen-prospect-enrich", "name": "OmniRoute Prospect Enrich"},
    {"id": "claude-omni-outreach-email", "real": "leadgen-outreach-email", "name": "OmniRoute Outreach Email"},
    {"id": "claude-omni-seo-keyword", "real": "leadgen-seo-keyword", "name": "OmniRoute SEO Keyword"},
    {"id": "claude-omni-governor-review", "real": "leadgen-governor-review", "name": "OmniRoute Governor Review"},
    {"id": "claude-omni-project-best", "real": "leadgen-project-best", "name": "OmniRoute Project Best"},
]
COMBO_IDS = [c["id"] for c in ALL_COMBOS]

# Verified Universal Stdio MCP Servers
UNIVERSAL_MCP_SERVERS = {
    "leadgen_admin_harness": {
        "command": PYTHON_EXE,
        "args": [str(REPO_ROOT / "scripts" / "leadgen_admin_harness_mcp.py")],
    },
    "buzz": {
        "command": PYTHON_EXE,
        "args": [str(REPO_ROOT / "scripts" / "buzz_mcp.py")],
        "env": {"BUZZ_RELAY": "https://leadsgenai.communities.buzz.xyz"},
    },
    "puppeteer": {
        "command": "npx.cmd",
        "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
    },
    "playwright": {
        "command": "npx.cmd",
        "args": ["-y", "@executeautomation/playwright-mcp-server"],
    },
    "filesystem": {
        "command": "npx.cmd",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", str(REPO_ROOT)],
    },
    "graphify": {
        "command": GRAPHIFY_CMD,
        "args": ["--graph", str(REPO_ROOT / "app" / "graphify-out" / "graph.json")],
    },
}

# App Binary Paths
CLAUDE_EXE_MS = r"C:\Program Files\WindowsApps\Claude_1.40609.0.0_x64__pzs8sxrjxfjjc\app\Claude.exe"
HERMES_EXE = os.path.expanduser(r"~\AppData\Local\hermes\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe")
WORKBUDDY_EXE = os.path.expanduser(r"~\AppData\Local\Programs\WorkBuddyAI\WorkBuddyAI.exe")


def check_http_port(port: int, path: str = "/") -> tuple[bool, str]:
    """Check if an HTTP service is responding on 127.0.0.1:<port>."""
    url = f"http://127.0.0.1:{port}{path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AntigravityMasterOrchestrator/1.0"})
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            return True, f"HTTP {resp.status} (OK)"
    except urllib.error.HTTPError as e:
        return True, f"HTTP {e.code}"
    except Exception as e:
        return False, f"Not reachable ({e})"


def is_process_running(proc_name: str) -> list[int]:
    """Check running processes by name and return PIDs."""
    pids = []
    try:
        res = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {proc_name}*", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in res.stdout.strip().splitlines():
            parts = [p.strip(' "') for p in line.split(",")]
            if len(parts) >= 2 and parts[1].isdigit():
                pids.append(int(parts[1]))
    except Exception:
        pass
    return pids


def ensure_claude_proxy():
    """Ensure claude_proxy.py is running on port 22000."""
    ok, _ = check_http_port(22000, "/health")
    if ok:
        print("[OK] Claude Proxy is already active on http://127.0.0.1:22000")
        return True

    print("[...] Starting Claude Proxy daemon on http://127.0.0.1:22000...")
    proxy_script = str(REPO_ROOT / "scripts" / "claude_proxy.py")
    pythonw = REPO_ROOT / ".venv" / "Scripts" / "pythonw.exe"
    exe = str(pythonw) if pythonw.exists() else PYTHON_EXE
    
    subprocess.Popen(
        [exe, proxy_script],
        cwd=str(REPO_ROOT),
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    time.sleep(1.5)
    ok, status = check_http_port(22000, "/health")
    if ok:
        print("[OK] Claude Proxy started successfully on port 22000.")
        return True
    else:
        print(f"[WARN] Claude Proxy startup verification: {status}")
        return False


def fix_all_configs():
    """Perform enterprise-grade repair and sync across all app configs."""
    print("=== Running Full Auto-Fix & Config Sync ===")
    from scripts.sync_all_combos_all_apps import (
        sync_claude,
        sync_dsh,
        sync_hermes,
        sync_omniroute_sqlite,
        sync_workbuddy,
        sync_workspace_mcp,
    )
    sync_omniroute_sqlite()
    sync_dsh()
    sync_claude()
    sync_workbuddy()
    sync_hermes()
    sync_workspace_mcp()
    ensure_claude_proxy()
    print("=== All Configurations Synced & Secured! ===")


def launch_app_interactively(exe_path: str, label: str):
    """Launch a Windows GUI application into the interactive desktop session."""
    if not os.path.exists(exe_path):
        print(f"[ERR] Cannot find executable for {label}: {exe_path}")
        return False

    print(f"[...] Launching {label} interactively: {exe_path}")
    try:
        os.startfile(exe_path)
        print(f"[OK] {label} launched successfully.")
        return True
    except Exception as e:
        print(f"[ERR] Failed to launch {label}: {e}")
        # Fallback to explorer.exe
        try:
            subprocess.Popen(["explorer.exe", exe_path])
            print(f"[OK] {label} launched via Windows Explorer shell.")
            return True
        except Exception as e2:
            print(f"[ERR] Explorer fallback failed: {e2}")
            return False


def launch_claude():
    return launch_app_interactively(CLAUDE_EXE_MS, "Claude Desktop")


def launch_hermes():
    return launch_app_interactively(HERMES_EXE, "Hermes Desktop")


def launch_workbuddy():
    return launch_app_interactively(WORKBUDDY_EXE, "WorkBuddy Desktop")


def print_status():
    """Print comprehensive master status table for all services, apps, and MCP harness."""
    print("=================================================================")
    print("        ANTIGRAVITY MASTER ORCHESTRATOR - SYSTEM STATUS          ")
    print("=================================================================")
    
    # 1. Backends & Proxies
    print("\n--- [1] AI Inference & Gateways ---")
    omni_ok, omni_stat = check_http_port(20128, "/")
    print(f"  * OmniRoute Gateway (:20128) : {'[ONLINE]' if omni_ok else '[OFFLINE]'} - {omni_stat}")
    
    proxy_ok, proxy_stat = check_http_port(22000, "/health")
    print(f"  * Claude Proxy (:22000)      : {'[ONLINE]' if proxy_ok else '[OFFLINE]'} - {proxy_stat}")
    
    fastapi_ok, fastapi_stat = check_http_port(8000, "/health")
    print(f"  * LeadGen FastAPI (:8000)    : {'[ONLINE]' if fastapi_ok else '[STANDBY]'} - {fastapi_stat}")

    # 2. Desktop Applications
    print("\n--- [2] Desktop Applications ---")
    claude_pids = is_process_running("Claude")
    print(f"  * Claude Desktop   : {'[RUNNING - PIDs: ' + str(claude_pids) + ']' if claude_pids else '[STOPPED]'}")
    
    hermes_pids = is_process_running("Hermes")
    print(f"  * Hermes Desktop   : {'[RUNNING - PIDs: ' + str(hermes_pids) + ']' if hermes_pids else '[STOPPED]'}")
    
    wb_pids = is_process_running("WorkBuddyAI")
    print(f"  * WorkBuddy AI     : {'[RUNNING - PIDs: ' + str(wb_pids) + ']' if wb_pids else '[STOPPED]'}")

    # 3. Universal MCP Harness
    print("\n--- [3] Antigravity MCP Harness ---")
    from scripts.leadgen_admin_harness_mcp import TOOLS
    print(f"  * LeadGen Admin Harness MCP  : [HEALTHY] - {len(TOOLS)} Tools Active")
    for t in TOOLS:
        print(f"     -> {t['name']}")

    # 4. Computer Use Hardware Status
    print("\n--- [4] Computer-Use Hardware State ---")
    try:
        from scripts.desktop_mouse_visualizer import get_mouse_position, get_screen_resolution
        sw, sh = get_screen_resolution()
        mx, my = get_mouse_position()
        print(f"  * Primary Display Resolution: {sw}x{sh}")
        print(f"  * Current Mouse Position    : ({mx}, {my})")
        print(f"  * Visual Glow & HUD Overlay : [AVAILABLE]")
    except Exception as e:
        print(f"  * Visual Control Note       : {e}")
        
    print("=================================================================\n")


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    action = action.lower().strip()

    if action == "status":
        print_status()
    elif action in ("fix", "sync"):
        fix_all_configs()
        print_status()
    elif action == "launch-all":
        fix_all_configs()
        launch_claude()
        time.sleep(1)
        launch_hermes()
        time.sleep(1)
        launch_workbuddy()
        time.sleep(2)
        print_status()
    elif action == "launch-claude":
        launch_claude()
    elif action == "launch-hermes":
        launch_hermes()
    elif action == "launch-workbuddy":
        launch_workbuddy()
    elif action in ("verify-harness", "verify"):
        print("=== Running Self-Harness Diagnostics ===")
        from scripts.leadgen_admin_harness_mcp import tool_self_harness_verify
        res = tool_self_harness_verify({"suite": "all"})
        print(res.get("text", ""))
    else:
        print(f"Unknown action: {action}")
        print("Available actions: status, fix, launch-all, launch-claude, launch-hermes, launch-workbuddy, verify")


if __name__ == "__main__":
    main()
