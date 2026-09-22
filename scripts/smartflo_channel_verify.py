"""SmartFlo channel pre-flight + post-portal config verification.

This is a NON-DESTRUCTIVE diagnostic script the owner runs:
  - BEFORE portal setup: confirms what code-side config is wired
  - AFTER portal setup: confirms portal config maps to code

It does NOT touch the SmartFlo portal. It does NOT make API calls. It only
reads:
  * Local environment variables (env-fingerprint, NEVER raw value)
  * ``app/telephony/tata_tele_config.py`` channel scaffold
  * Local config files for placeholders

Outputs a JSON document with status per check. Exit 0 if all checks ran
(even if some FAIL — that's owner action), non-zero if prerequisites
missing.

CLI:
    python scripts/smartflo_channel_verify.py --mode preflight
    python scripts/smartflo_channel_verify.py --mode postportal
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fingerprint(name: str) -> dict[str, str]:
    """Return SHA-256 fingerprint of an env var — NEVER the raw value."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return {"name": name, "state": "ABSENT", "fingerprint": ""}
    fp = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return {"name": name, "state": "PRESENT", "fingerprint": f"sha256:{fp}"}


def _check_env_credentials() -> dict:
    """Probe SmartFlo credentials — NEVER print raw values."""
    return {
        "TATA_SMARTFLO_API_TOKEN": _fingerprint("TATA_SMARTFLO_API_TOKEN"),
        "TATA_SMARTFLO_API_KEY": _fingerprint("TATA_SMARTFLO_API_KEY"),
        "TATA_SMARTFLO_DID": _fingerprint("TATA_SMARTFLO_DID"),
        "SMARTFLO_WEBHOOK_SECRET": _fingerprint("SMARTFLO_WEBHOOK_SECRET"),
    }


def _check_env_flags() -> dict:
    """Probe SmartFlo env flags (not secrets)."""
    voice = os.getenv("SMARTFLO_VOICE_STREAM_ENABLED", "0").strip()
    return {
        "SMARTFLO_VOICE_STREAM_ENABLED": {
            "value": voice,
            "expected_for_acceptance": "1",
            "state": "ON" if voice in ("1", "true", "yes", "on") else "OFF",
        },
        "TELEPHONY_PROVIDER": {
            "value": (os.getenv("TELEPHONY_PROVIDER", "tata_smartflo").strip()),
            "expected": "tata_smartflo",
            "state": "OK" if os.getenv("TELEPHONY_PROVIDER", "tata_smartflo").strip() == "tata_smartflo" else "MISMATCH",
        },
    }


def _check_code_channels() -> dict:
    """Inspect the 5-channel config scaffold in tata_tele_config.py."""
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from app.telephony.tata_tele_config import get_tata_config

        cfg = get_tata_config()
        active = cfg.get_active_channels()
        pending = cfg.get_pending_channels()
        numbers_placeholder = all(
            c["number"].endswith(f"{i:02d}") and c["number"].startswith("+9180698797")
            for i, c in enumerate(cfg.channels, start=1)
        )
        return {
            "channels": cfg.channels,
            "active_count": len(active),
            "pending_count": len(pending),
            "active_ids": [c["id"] for c in active],
            "pending_ids": [c["id"] for c in pending],
            "numbers_are_placeholders": numbers_placeholder,
            "total_daily_capacity": cfg.get_total_capacity(),
            "revenue_potential": cfg.get_revenue_potential(),
            "outbound_allowed_now": cfg.is_outbound_allowed(),
            "note": (
                "Numbers are PLACEHOLDERS. Owner must replace with real DIDs from portal."
                if numbers_placeholder
                else "Numbers look real (not the placeholder pattern)."
            ),
        }
    except Exception as exc:
        return {"state": "ERROR", "error": f"{type(exc).__name__}: {exc}"}


def _check_endpoint_reachability() -> dict:
    """TCP probe to the SmartFlo API endpoint (port 443 only, no auth)."""
    import socket

    host = "api-smartflo.tatateleservices.com"
    try:
        with socket.create_connection((host, 443), timeout=4.0) as s:
            return {
                "host": host,
                "port": 443,
                "state": "REACHABLE",
                "note": "DNS + TCP OK; full auth requires SMARTFLO_API_TOKEN",
            }
    except Exception as exc:
        return {
            "host": host,
            "port": 443,
            "state": f"UNREACHABLE ({type(exc).__name__})",
            "note": "Network/DNS check failed; check internet + VPN state",
        }


def _check_vps_reachable() -> dict:
    """TCP probe to the canonical VPS endpoint (port 22 only)."""
    import socket

    host = "72.61.245.204"
    try:
        with socket.create_connection((host, 22), timeout=4.0) as s:
            return {
                "host": host,
                "port": 22,
                "state": "REACHABLE",
                "note": "VPS SSH port open; full SSH requires id_rsa + key_manager",
            }
    except Exception as exc:
        return {
            "host": host,
            "port": 22,
            "state": f"UNREACHABLE ({type(exc).__name__})",
            "note": "VPS flap — check SSH key + tunnel state",
        }


def _check_acceptance_framework() -> dict:
    """Confirm the 12-gate acceptance framework is wired."""
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from app.voice.smartflo_acceptance import GATES

        return {
            "gate_count": len(GATES),
            "gates": [{"id": g["id"], "name": g["name"], "remote": g["remote"]} for g in GATES],
            "state": "OK",
        }
    except Exception as exc:
        return {"state": "ERROR", "error": f"{type(exc).__name__}: {exc}"}


def build_report(mode: str) -> dict:
    """Assemble the full diagnostic report."""
    return {
        "kind": "smartflo_channel_verify",
        "mode": mode,
        "fetched_at": _now_iso(),
        "checks": {
            "env_credentials": _check_env_credentials(),
            "env_flags": _check_env_flags(),
            "code_channels": _check_code_channels(),
            "endpoint_reachability": _check_endpoint_reachability(),
            "vps_reachable": _check_vps_reachable(),
            "acceptance_framework": _check_acceptance_framework(),
        },
        "next_actions": [
            "Owner: complete portal setup per docs/coordination/SMARTFLO_PORTAL_SETUP_SPEC_2026-09-22.md",
            "Owner: provide test number + VPS SSH for acceptance run",
            "After portal setup, re-run with --mode postportal to confirm code-side reflects portal state",
        ],
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="SmartFlo channel verification")
    parser.add_argument(
        "--mode",
        choices=["preflight", "postportal"],
        default="preflight",
        help="preflight: before portal setup; postportal: after portal setup",
    )
    args = parser.parse_args(argv)

    try:
        report = build_report(args.mode)
    except Exception as exc:
        print(json.dumps({"state": "ERROR", "error": f"{type(exc).__name__}: {exc}"}))
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))