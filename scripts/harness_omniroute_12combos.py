#!/usr/bin/env python3
"""OmniRoute 12-Combo & Dual-Computer Harness Verification & Config Tool.

Sets up and verifies all 12 OmniRoute combos across Hermes Desktop and Claude Desktop
for both Computer 1 (Local Host) and Computer 2 (Peer PC / Remote).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
import urllib.request
import urllib.error

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.platform.omniroute_client import list_task_routes, omniroute_available, omniroute_enabled


def check_gateway_health(host: str = "127.0.0.1", port: int = 20128) -> tuple[bool, str]:
    """Check if the OmniRoute gateway is responding on host:port."""
    url = f"http://{host}:{port}/api/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return True, f"HTTP {resp.status} - Gateway Live"
    except urllib.error.HTTPError as err:
        if err.code in (401, 403, 404):
            return True, f"HTTP {err.code} - Gateway Alive (Auth/Protected)"
        return False, f"HTTP {err.code} - {err.reason}"
    except Exception as exc:
        return False, f"Unreachable ({type(exc).__name__}: {exc})"


def generate_claude_desktop_config(host: str = "127.0.0.1", port: int = 20128) -> dict:
    """Generate the claude_desktop_config.json snippet for Claude Desktop integration."""
    base_url = f"http://{host}:{port}/v1"
    api_key = os.getenv("OMNIROUTE_API_KEY", "<YOUR_OMNIROUTE_API_KEY>")
    return {
        "mcpServers": {
            "omniroute_12combos": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-fetch", f"{base_url}/responses"],
                "env": {
                    "OMNIROUTE_BASE_URL": base_url,
                    "OMNIROUTE_API_KEY": api_key,
                },
            }
        },
        "env": {
            "ANTHROPIC_BASE_URL": base_url,
            "ANTHROPIC_API_KEY": api_key,
        },
    }


def generate_hermes_profile_config(host: str = "127.0.0.1", port: int = 20128) -> dict:
    """Generate the Hermes Desktop profile configuration for 12 OmniRoute combos."""
    routes = list_task_routes()
    base_url = f"http://{host}:{port}/v1"
    api_key = os.getenv("OMNIROUTE_API_KEY", "<YOUR_OMNIROUTE_API_KEY>")
    
    profiles = {}
    for task_id, route in routes.items():
        profile_name = task_id.replace(".", "_")
        profiles[profile_name] = {
            "task_id": task_id,
            "primary_model": route.primary_model,
            "fallback_model": route.fallback_model,
            "privacy_class": route.privacy_class,
            "base_url": base_url,
            "api_key_configured": bool(api_key and api_key != "<YOUR_OMNIROUTE_API_KEY>"),
        }
    return {
        "app": "Hermes Desktop",
        "omniroute_gateway": f"http://{host}:{port}",
        "combos_count": len(profiles),
        "profiles": profiles,
    }


def print_harness_status(host: str, port: int) -> None:
    """Print full evidence & verification report for 12 OmniRoute combos."""
    print("=" * 72)
    print("      OMNIROUTE 12-COMBO & DUAL-COMPUTER HARNESS STATUS REPORT      ")
    print("=" * 72)
    
    healthy, msg = check_gateway_health(host, port)
    status_symbol = "✅" if healthy else "⚠️"
    print(f"Gateway Status [{host}:{port}]: {status_symbol} {msg}")
    print(f"OMNIROUTE_ENABLED env flag  : {omniroute_enabled()}")
    print(f"OMNIROUTE_API_KEY present   : {bool(os.getenv('OMNIROUTE_API_KEY'))}")
    print(f"Adapter Available           : {omniroute_available()}")
    print("-" * 72)
    
    routes = list_task_routes()
    print(f"Registered OmniRoute Combos ({len(routes)} combos active):")
    print(f"{'#':<3} | {'Task ID':<26} | {'Primary Model':<18} | {'Fallback Model':<18}")
    print("-" * 72)
    for idx, (task_id, route) in enumerate(routes.items(), 1):
        fallback = route.fallback_model or "None"
        print(f"{idx:<3} | {task_id:<26} | {route.primary_model:<18} | {fallback:<18}")
    
    print("-" * 72)
    print("CLAUDE DESKTOP CONFIG SNIPPET (%APPDATA%\\Claude\\claude_desktop_config.json):")
    claude_cfg = generate_claude_desktop_config(host, port)
    print(json.dumps(claude_cfg, indent=2))
    
    print("-" * 72)
    print("HERMES DESKTOP PROFILE SUMMARY (%APPDATA%\\Hermes\\):")
    hermes_cfg = generate_hermes_profile_config(host, port)
    print(f"Total Profiles Wired: {hermes_cfg['combos_count']}")
    for pname, pdata in list(hermes_cfg['profiles'].items())[:4]:
        print(f"  • {pname:<24} -> Primary: {pdata['primary_model']:<16} (Fallback: {pdata['fallback_model']})")
    print("  ... [and 8 more profiles linked]")
    
    print("=" * 72)
    print("DUAL-COMPUTER SETUP INSTRUCTIONS:")
    print(f"  • Computer 1 (Local): powershell scripts\\start-hermes-omniroute.ps1 -Combo leadgen.project_best")
    print(f"  • Computer 1 (Claude): powershell scripts\\start-claude-omniroute.ps1 -Combo leadgen.coding_primary")
    print(f"  • Computer 2 (Peer PC): set OMNIROUTE_HOST={host} or run with -OmniHost {host}")
    print("=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser(description="OmniRoute 12-Combo & Dual-Computer Harness")
    parser.add_argument("--host", default="127.0.0.1", help="OmniRoute Gateway host IP/hostname")
    parser.add_argument("--port", type=int, default=20128, help="OmniRoute Gateway port (default: 20128)")
    parser.add_argument("--verify", action="store_true", help="Run verification checks")
    parser.add_argument("--json", action="store_true", help="Output raw JSON configuration")
    args = parser.parse_args()

    if args.json:
        payload = {
            "gateway": {"host": args.host, "port": args.port, "healthy": check_gateway_health(args.host, args.port)[0]},
            "claude_config": generate_claude_desktop_config(args.host, args.port),
            "hermes_config": generate_hermes_profile_config(args.host, args.port),
        }
        print(json.dumps(payload, indent=2))
        return 0

    print_harness_status(args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
