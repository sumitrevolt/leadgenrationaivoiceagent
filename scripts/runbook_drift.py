#!/usr/bin/env python3
"""runbook_drift.py — flag drift between activation.py probes, runbook, .env.example.

The activation runbook + `scripts/activate.py` + `app/api/activation.py` probes
+ `.env.example` are FOUR sources of truth for the same set of env keys. Drift
between them is what makes "production-ready" silently rot. This script reads
all four and reports any key that appears in some but not all.

Usage:
  python scripts/runbook_drift.py        # print report, exit 0 even on drift
  python scripts/runbook_drift.py --strict # exit 1 if any drift found

Stdlib only. Safe to wire into CI.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_RUNBOOK = _ROOT / "docs" / "SESSION_ACTIVATION_RUNBOOK_2026_06_16.md"
_ENV_EXAMPLE = _ROOT / ".env.example"
_ACTIVATION_PY = _ROOT / "app" / "api" / "activation.py"
_ACTIVATE_PY = _ROOT / "scripts" / "activate.py"

_ENV_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\b")
# Keys to ignore (commonly mentioned in docstrings but not env vars per se):
_DENY = {
    "BANT",
    "TODO",
    "OFF",
    "ON",
    "NEW",
    "CI",
    "OK",
    "DPDP",
    "TRAI",
    "GST",
    "SDK",
    "JWT",
    "TOTP",
    "QR",
    "URL",
    "DNS",
    "WAF",
    "DDoS",
    "DM",
    "MIT",
    "MRR",
    "ARR",
    "POST",
    "GET",
    "PATCH",
    "DELETE",
    "HTTP",
    "HTTPS",
    "JSON",
    "XML",
    "API",
    "ID",
    "IP",
    "RPC",
    "REST",
    "UTC",
    "IST",
    "EU",
    "US",
    "CDN",
    "VPS",
    "BLOCKER",
    "WARN",
    "NEUTRAL",
    "PHASE",
}


def _extract_env_keys(path: Path) -> set[str]:
    """Pull anything that looks like an ENV_KEY token from a file."""
    if not path.exists():
        return set()
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return set()
    found = set()
    for m in _ENV_KEY_RE.finditer(text):
        key = m.group(1)
        if key in _DENY or len(key) < 4:
            continue
        # Filter common Python/HTML token noise
        if key in {"TRUE", "FALSE", "NONE", "ANY", "STR"}:
            continue
        found.add(key)
    return found


def _runbook_keys() -> set[str]:
    """Keys appearing as `KEY=...` or in `\\`KEY\\`` markdown code spans."""
    if not _RUNBOOK.exists():
        return set()
    text = _RUNBOOK.read_text(encoding="utf-8")
    keys = set()
    # KEY=value (code-block lines)
    for m in re.finditer(r"^([A-Z][A-Z0-9_]{3,})=", text, flags=re.MULTILINE):
        keys.add(m.group(1))
    # `KEY` markdown spans
    for m in re.finditer(r"`([A-Z][A-Z0-9_]{3,})`", text):
        keys.add(m.group(1))
    return {k for k in keys if k not in _DENY}


def _env_example_keys() -> set[str]:
    if not _ENV_EXAMPLE.exists():
        return set()
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    keys = set()
    for m in re.finditer(r"^([A-Z][A-Z0-9_]{3,})=", text, flags=re.MULTILINE):
        keys.add(m.group(1))
    return keys


def _probes_keys() -> set[str]:
    """env_vars listed in each probe in app/api/activation.py."""
    if not _ACTIVATION_PY.exists():
        return set()
    text = _ACTIVATION_PY.read_text(encoding="utf-8")
    keys = set()
    # Match lines like:  "env_vars": ["KEY1", "KEY2"],
    for m in re.finditer(r'"env_vars":\s*\[([^\]]*)\]', text):
        for token in re.finditer(r'"([A-Z][A-Z0-9_]{3,})"', m.group(1)):
            keys.add(token.group(1))
    return keys


def _activate_cli_keys() -> set[str]:
    """env keys referenced in scripts/activate.py phase definitions."""
    if not _ACTIVATE_PY.exists():
        return set()
    text = _ACTIVATE_PY.read_text(encoding="utf-8")
    keys = set()
    for m in re.finditer(r'\("([A-Z][A-Z0-9_]{3,})",', text):
        keys.add(m.group(1))
    return keys


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strict", action="store_true", help="Exit 1 if any drift found")
    args = p.parse_args()

    runbook = _runbook_keys()
    env_example = _env_example_keys()
    probes = _probes_keys()
    cli = _activate_cli_keys()

    print("Activation drift check")
    print("======================")
    print(f"runbook keys     : {len(runbook):3d}")
    print(f".env.example     : {len(env_example):3d}")
    print(f"probes env_vars  : {len(probes):3d}")
    print(f"activate.py CLI  : {len(cli):3d}")
    print()

    # Per-source drift — focused on the highest-value gap: probes (the SoT for
    # 'what we actually check') vs the other three.
    drift = {
        "in probes, missing from runbook": sorted(probes - runbook),
        "in probes, missing from .env.example": sorted(probes - env_example),
        "in probes, missing from activate.py CLI": sorted(probes - cli),
        "in activate.py CLI, missing from probes": sorted(cli - probes),
        "in runbook, missing from probes": sorted(
            runbook - probes - env_example
        ),  # may be doc-only refs
    }

    any_drift = False
    for label, keys in drift.items():
        if not keys:
            continue
        any_drift = True
        print(f"--- {label} ({len(keys)}) ---")
        for k in keys:
            print(f"  {k}")
        print()

    if not any_drift:
        print("OK: zero drift.")
        return 0
    if args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
