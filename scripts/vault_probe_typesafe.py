#!/usr/bin/env python3
"""TypeSafe 4-slot vault probe — read-only, fingerprints only.

Probes all TypeSafe key sources and reports:
- Fingerprint (sha256[:12]) per slot — NEVER the raw key
- Slot health (PRESENT / ABSENT / EMPTY)
- Cooldown state (if in effect)

Usage:
    python scripts/vault_probe_typesafe.py           # probe + log
    python scripts/vault_probe_typesafe.py --json     # machine-readable
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def _fingerprint(val: str) -> str:
    """SHA-256 prefix — non-reversible slot identifier."""
    return hashlib.sha256(val.encode()).hexdigest()[:12]


def _slot_status(val: str | None) -> str:
    if val is None:
        return "ABSENT"
    if not val.strip():
        return "EMPTY"
    return "PRESENT"


def probe_env_slots() -> list[dict[str, Any]]:
    """Probe TYPESAFE_API_KEY and TYPEsafe_API_KEY from process env."""
    slots = []
    for name in ("TYPESAFE_API_KEY", "TYPEsafe_API_KEY"):
        val = os.getenv(name)
        slots.append(
            {
                "source": f"env:{name}",
                "status": _slot_status(val),
                "fingerprint": _fingerprint(val) if val else None,
                "length": len(val) if val else 0,
            }
        )
    return slots


def probe_runtime_keys_file() -> list[dict[str, Any]]:
    """Probe data/typesafe_keys.json (runtime override file)."""
    slots = []
    for rel in ("data/typesafe_keys.json", "data/keys.json"):
        p = ROOT / rel
        if not p.exists():
            continue
        try:
            content = p.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                for k, v in data.items():
                    slots.append(
                        {
                            "source": f"file:{rel}:{k}",
                            "status": _slot_status(v),
                            "fingerprint": _fingerprint(v) if v else None,
                            "length": len(v) if v else 0,
                        }
                    )
            elif isinstance(data, list):
                for i, v in enumerate(data):
                    slots.append(
                        {
                            "source": f"file:{rel}[{i}]",
                            "status": _slot_status(v),
                            "fingerprint": _fingerprint(v) if v else None,
                            "length": len(v) if v else 0,
                        }
                    )
        except Exception as e:
            slots.append({"source": f"file:{rel}", "status": "ERROR", "error": str(e)})
    return slots


def probe_key_manager_vault() -> list[dict[str, Any]]:
    """Probe encrypted KeyManager vault (TS_A..TS_D)."""
    slots = []
    try:
        from app.platform.key_manager import get_key_manager

        km = get_key_manager()
        raw_keys = km.get_all_typesafe_slot_keys()
        for i, k in enumerate(raw_keys):
            slots.append(
                {
                    "source": "key_manager:slot",
                    "slot_index": i,
                    "status": _slot_status(k),
                    "fingerprint": _fingerprint(k) if k else None,
                    "length": len(k) if k else 0,
                }
            )
        if not raw_keys:
            slots.append({"source": "key_manager:vault", "status": "VAULT_EMPTY"})
    except Exception as e:
        slots.append({"source": "key_manager:vault", "status": "ERROR", "error": str(e)})
    return slots


def probe_cooldown_state() -> dict[str, Any]:
    """Read current key cooldown state from typesafe module."""
    try:
        from app.platform import typesafe_integration as _ts

        cooldowns = getattr(_ts, "_KEY_COOLDOWNS", {})
        idx = getattr(_ts, "_KEY_IDX", 0)
        return {
            "active_key_index": idx,
            "cooldown_count": len(cooldowns),
            "cooldowns": {fp: round(t - time.time(), 1) for fp, t in cooldowns.items()},
        }
    except Exception as e:
        return {"error": str(e)}


def main() -> int:
    parser = argparse.ArgumentParser(description="TypeSafe 4-slot vault probe")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "slots": [],
    }
    report["slots"].extend(probe_env_slots())
    report["slots"].extend(probe_runtime_keys_file())
    report["slots"].extend(probe_key_manager_vault())
    report["cooldown"] = probe_cooldown_state()

    present = sum(1 for s in report["slots"] if s.get("status") == "PRESENT")
    report["summary"] = {
        "total_slots": len(report["slots"]),
        "present": present,
        "absent": len(report["slots"]) - present,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("=== TypeSafe 4-Slot Vault Probe ===")
        print(f"Timestamp: {report['timestamp']}")
        print(f"Slots: {report['summary']['present']}/{report['summary']['total_slots']} present")
        print()
        for s in report["slots"]:
            fp = s.get("fingerprint") or "(none)"
            print(f"  [{s['status']:7s}] {s['source']:40s} fp={fp} len={s.get('length', 0)}")
        print()
        cd = report["cooldown"]
        if "error" in cd:
            print(f"Cooldown: ERROR — {cd['error']}")
        else:
            print(f"Active key index: {cd['active_key_index']}")
            print(f"Cooldowns active: {cd['cooldown_count']}")
            for fp, remaining in cd.get("cooldowns", {}).items():
                print(f"  fp={fp} expires_in={remaining}s")

    return 0


if __name__ == "__main__":
    sys.exit(main())
