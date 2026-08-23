#!/usr/bin/env python3
"""activate.py - interactive Phase-1 activation walker.

Reduces "I don't know what to do first" friction for the operator: reads the
current .env, walks Phase-1 of the activation runbook, prompts ONLY for keys
that are unset/placeholder, atomically rewrites .env (backup taken first),
and runs the verify curl per item.

Usage:
  python scripts/activate.py            # interactive Phase-1 walk
  python scripts/activate.py --status   # just show current state (no prompt)
  python scripts/activate.py --phase 2  # walk Phase-2 instead

Design rules:
- **Never destroys data**: backup .env to .env.bak_<timestamp> BEFORE any write.
- **Idempotent**: re-running after activation only re-checks; no duplicates.
- **Read-only by default**: `--status` flag is a pure inspection.
- **Never assumes prod**: hits `http://127.0.0.1:8000` (in-network); operator
  runs this on the VPS over SSH or via `docker exec`.
- **No external dep**: stdlib only (urllib for the verify hit).

Per the SESSION_ACTIVATION_RUNBOOK_2026_06_16.md, Phase-1 items have ₹0 cost
+ ~30 min total. This script is what makes that 30 min actually achievable
without context-switching between docs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable

# Items per phase - matches docs/SESSION_ACTIVATION_RUNBOOK_2026_06_16.md.
# Each item: (key, label, env_pairs, description, post_activate_curl)
_PLACEHOLDER_MARKERS = (
    "your-",
    "your_",
    "change-me",
    "change_me",
    "xxxxxxxx",
    "rzp_test_you",
    "rzp_live_xxxxx",
    "placeholder",
)


def _is_placeholder(value: str) -> bool:
    if not value:
        return False
    low = value.lower()
    return any(m in low for m in _PLACEHOLDER_MARKERS)


_PHASES: dict[int, dict] = {
    1: {
        "name": "Survival (revenue + visibility + trust + edge)",
        "items": [
            {
                "key": "razorpay",
                "label": "Razorpay live keys + webhook secret",
                "env": [
                    ("RAZORPAY_KEY_ID", "Your live key ID (starts with rzp_live_)"),
                    ("RAZORPAY_KEY_SECRET", "Your live key secret"),
                    ("RAZORPAY_WEBHOOK_SECRET", "Webhook signing secret from Razorpay dashboard"),
                ],
                "validator": lambda vals: vals.get("RAZORPAY_KEY_ID", "").startswith("rzp_live_"),
                "validator_msg": "Key ID must start with rzp_live_ (rzp_test_ keys are not production)",
            },
            {
                "key": "sentry",
                "label": "Sentry error tracking",
                "env": [
                    ("SENTRY_DSN", "DSN from Sentry project settings (https://...sentry.io/...)"),
                    ("ENVIRONMENT", "Must be 'production' for Sentry init to run", "production"),
                ],
                "validator": None,
            },
            {
                "key": "posthog",
                "label": "PostHog product analytics (cloud free tier)",
                "env": [
                    ("POSTHOG_API_KEY", "Project API key (phc_...)"),
                    (
                        "POSTHOG_HOST",
                        "us or eu - defaults to us.i.posthog.com",
                        "https://us.i.posthog.com",
                    ),
                ],
                "validator": None,
            },
            {
                "key": "turnstile",
                "label": "Cloudflare Turnstile bot-protection",
                "env": [
                    ("TURNSTILE_SITE_KEY", "Public site-key from Cloudflare dashboard"),
                    ("TURNSTILE_SECRET_KEY", "Secret key from same dashboard"),
                ],
                "validator": None,
            },
            {
                "key": "cloudflare_tunnel",
                "label": "Cloudflare Tunnel (origin-hide + WAF)",
                "env": [
                    (
                        "CLOUDFLARE_TUNNEL_TOKEN",
                        "Tunnel token from Zero Trust -> Tunnels -> create",
                    ),
                ],
                "validator": None,
                "post_command": (
                    "docker compose -f deploy/compose/docker-compose.edge.yml --profile edge up -d"
                ),
            },
        ],
    },
    2: {
        "name": "Visibility (AI safety + memory)",
        "items": [
            {
                "key": "agent_memory",
                "label": "Agent memory (cross-session lead recall)",
                "env": [("AGENT_MEMORY", "Set to 1 to arm", "1")],
                "validator": None,
            },
            {
                "key": "eval_gate",
                "label": "Eval-gate (self_improve reward signal)",
                "env": [("EVAL_GATE", "Set to 1 to start recording baseline", "1")],
                "validator": None,
            },
        ],
    },
    3: {
        "name": "AI staff (engineer agents + alerting)",
        "items": [
            {
                "key": "engineer_agents",
                "label": "Engineer agents (Pranav SRE / Vidya FinOps / Arnav Security)",
                "env": [
                    ("SRE_AGENT", "1", "1"),
                    ("FINOPS_AGENT", "1", "1"),
                    ("SECURITY_AGENT", "1", "1"),
                ],
                "validator": None,
            },
            {
                "key": "ops_alerts",
                "label": "ops_alerts ntfy fan-out",
                "env": [
                    ("OPS_ALERTS", "1", "1"),
                    (
                        "NTFY_URL",
                        "http://ntfy:80 (self-hosted) or https://ntfy.sh",
                        "http://ntfy:80",
                    ),
                    ("NTFY_TOPIC", "Topic name (random for privacy)"),
                ],
                "validator": None,
            },
        ],
    },
    4: {
        "name": "Sellable capabilities",
        "items": [
            {
                "key": "customer_webhooks",
                "label": "Customer-facing webhooks",
                "env": [("CUSTOMER_WEBHOOKS", "1", "1")],
                "validator": None,
            },
            {
                "key": "mcp_product",
                "label": "MCP-as-product metered surface",
                "env": [("MCP_PRODUCT", "1", "1")],
                "validator": None,
            },
        ],
    },
    5: {
        "name": "Margin (per-tenant cost + warm-DR)",
        "items": [
            {
                "key": "litellm_costs",
                "label": "LiteLLM gateway + per-tenant cost attribution",
                "env": [
                    ("LITELLM_COSTS", "1", "1"),
                    ("LITELLM_MASTER_KEY", "32+ char random (bearer for /spend/keys)"),
                    (
                        "LITELLM_GATEWAY_URL",
                        "http://litellm:4000 (in-network)",
                        "http://litellm:4000",
                    ),
                ],
                "validator": None,
                "post_command": (
                    "docker compose -f deploy/compose/docker-compose.edge.yml --profile gateway up -d"
                ),
            },
            {
                "key": "warm_dr",
                "label": "Warm-DR replica (Neon/Supabase free tier)",
                "env": [
                    (
                        "DR_REPLICA_URL",
                        "postgres://user:pass@neon.tech/dbname (read-only replica)",  # pragma: allowlist secret (placeholder sample)
                    ),
                    ("DR_LAG_WARN_S", "Default 60", "60"),
                    ("DR_LAG_FAIL_S", "Default 600", "600"),
                ],
                "validator": None,
            },
        ],
    },
}


# --------------------------------------------------------------------------- #
# .env parse + atomic rewrite
# --------------------------------------------------------------------------- #
_ENV_LINE_RE = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")


def _parse_env(path: Path) -> tuple[list[str], dict[str, str]]:
    """Return (raw_lines, key_value_map). Preserves order + comments via lines."""
    if not path.exists():
        return [], {}
    raw = path.read_text(encoding="utf-8").splitlines(keepends=True)
    kv: dict[str, str] = {}
    for line in raw:
        m = _ENV_LINE_RE.match(line.strip())
        if m:
            kv[m.group(1)] = m.group(2).strip()
    return raw, kv


def _atomic_write_env(path: Path, raw_lines: list[str], updates: dict[str, str]) -> Path:
    """Apply updates IN-PLACE preserving comments + ordering. Append unknown
    keys at the bottom. Returns the backup path."""
    backup = path.with_name(f".env.bak_{int(time.time())}")
    shutil.copy2(path, backup)

    seen: set[str] = set()
    out: list[str] = []
    for line in raw_lines:
        m = _ENV_LINE_RE.match(line.strip())
        if m and m.group(1) in updates:
            out.append(f"{m.group(1)}={updates[m.group(1)]}\n")
            seen.add(m.group(1))
        else:
            out.append(line if line.endswith("\n") else line + "\n")
    appended_any = False
    for k, v in updates.items():
        if k not in seen:
            if not appended_any:
                out.append("\n# Appended by scripts/activate.py\n")
                appended_any = True
            out.append(f"{k}={v}\n")

    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(out), encoding="utf-8")
    tmp.replace(path)
    return backup


# --------------------------------------------------------------------------- #
# Verify hit (no admin token by default - checks the registry shape only)
# --------------------------------------------------------------------------- #
def _verify_health(base: str = "http://127.0.0.1:8000") -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=5) as r:  # nosec B310 (localhost health check)
            body = r.read().decode("utf-8", "ignore")
            return r.status == 200 and '"environment":"production"' in body, body[:200]
    except Exception as exc:
        return False, f"unreachable: {exc}"


# --------------------------------------------------------------------------- #
# Status / walk
# --------------------------------------------------------------------------- #
def _value_is_set(key: str, current: dict[str, str], require_real: bool = True) -> bool:
    """Return True iff key has a non-empty, non-placeholder value."""
    v = (current.get(key) or "").strip()
    if not v:
        return False
    if require_real and _is_placeholder(v):
        return False
    return True


def _item_is_done(item: dict, current: dict[str, str]) -> bool:
    """An item is done iff every required env key is set AND the validator (if
    any) passes."""
    for env_entry in item["env"]:
        key = env_entry[0]
        if not _value_is_set(key, current):
            return False
    validator = item.get("validator")
    if validator and not validator(current):
        return False
    return True


def show_status(phase_n: int | None = None) -> None:
    env_path = _resolve_env_path()
    _, current = _parse_env(env_path)
    print(f"Reading .env from: {env_path}")
    print()
    phases: Iterable[int] = (phase_n,) if phase_n else _PHASES.keys()
    for n in phases:
        phase = _PHASES.get(n)
        if not phase:
            continue
        print(f"=== Phase {n}: {phase['name']} ===")
        for item in phase["items"]:
            done = _item_is_done(item, current)
            mark = "x" if done else " "
            print(f"  [{mark}] {item['label']}")
        print()


def walk_phase(phase_n: int) -> None:
    phase = _PHASES.get(phase_n)
    if not phase:
        print(f"Unknown phase {phase_n}. Valid: {sorted(_PHASES)}")
        return
    env_path = _resolve_env_path()
    raw_lines, current = _parse_env(env_path)
    print(f"=== Phase {phase_n}: {phase['name']} ===")
    print(f".env path: {env_path}")
    print()

    updates: dict[str, str] = {}
    for item in phase["items"]:
        if _item_is_done(item, current):
            print(f"OK   {item['label']} - already set, skipping.")
            continue
        print(f"\nTODO {item['label']}")
        for env_entry in item["env"]:
            key = env_entry[0]
            prompt = env_entry[1]
            default = env_entry[2] if len(env_entry) > 2 else ""
            existing = (current.get(key) or "").strip()
            display_default = default or existing
            if _is_placeholder(existing):
                display_default = ""  # don't reuse placeholder as default
            suffix = f" [{display_default}]" if display_default else ""
            try:
                val = input(f"   {key} ({prompt}){suffix}: ").strip()
            except EOFError:
                print("\n(non-interactive - aborting walk)")
                return
            if not val and display_default:
                val = display_default
            if not val:
                print(f"   (skipped {key})")
                continue
            updates[key] = val
        validator = item.get("validator")
        if validator:
            combined = {**current, **updates}
            if not validator(combined):
                print(f"   !! {item.get('validator_msg', 'validation failed')}")
                print("   Skipping this item - re-run after fixing.")
                # Roll back this item's updates so the file isn't half-set
                for env_entry in item["env"]:
                    updates.pop(env_entry[0], None)
                continue
        post = item.get("post_command")
        if post:
            print(f"   -> After save, run: {post}")

    if not updates:
        print("\nNothing to save (all items skipped or already set).")
        return

    print("\nReady to write the following to .env:")
    for k in updates:
        v = updates[k]
        masked = (
            v
            if k.endswith("_HOST") or k == "ENVIRONMENT"
            else (v[:6] + "..." + v[-4:] if len(v) > 14 else "***")
        )
        print(f"   {k}={masked}")
    confirm = input("\nWrite changes (haan/nahi)? ").strip().lower()
    if confirm not in {"haan", "yes", "y"}:
        print("Aborted - no file changes.")
        return
    backup = _atomic_write_env(env_path, raw_lines, updates)
    print(f"OK   Written. Backup at: {backup}")
    print()
    print("Next steps (do these by hand on the VPS):")
    print("  1. Recreate the app container:")
    print("     docker compose -f docker-compose.vps.yml up -d --no-deps app")
    print("  2. Verify health:")
    print("     curl -fsS http://127.0.0.1:8000/health")
    print("  3. Verify readiness regression:")
    print(
        "     curl -s http://127.0.0.1:8000/api/activation/readiness -H 'Authorization: Bearer $TOKEN'"
    )


def _resolve_env_path() -> Path:
    """Default: /opt/leadgen/.env on the VPS; fall back to ./.env locally."""
    for candidate in (Path("/opt/leadgen/.env"), Path(".env")):
        if candidate.exists():
            return candidate
    return Path(".env")  # not exists yet, will fail on parse


# --------------------------------------------------------------------------- #
# Entry
# --------------------------------------------------------------------------- #
def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--phase", type=int, default=1, help="Phase number to walk (default 1)")
    p.add_argument("--status", action="store_true", help="Show current state, don't prompt")
    args = p.parse_args()

    print("LeadGen AI - interactive activation walker")
    print("Runbook: docs/SESSION_ACTIVATION_RUNBOOK_2026_06_16.md")
    print()

    if args.status:
        show_status(None)
        ok, body = _verify_health()
        print(f"Live /health: {'OK' if ok else 'FAIL'} - {body[:100]}")
        return 0

    walk_phase(args.phase)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
