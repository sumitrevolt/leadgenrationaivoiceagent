"""Boss Full Autonomy CLI — thin adapter over app.platform.boss_autonomy.

Canonical runtime logic lives in app.platform.boss_autonomy (public API only,
no monkey-patching, no private catalog access). This script is a thin CLI.

Setup (one-time, owner-gated):
  .env:
    BOSS_DECISION_GOVERNANCE=1
    BOSS_FULL_AUTONOMY=1
    BOSS_GOV_AUTHORITY_KEY=<random 32+ char secret>

Usage:
  python scripts/boss_autonomy.py decide <type> <title> [--payload k=v,k=v] [--agent manager]
  python scripts/boss_autonomy.py sweep [--limit 30] [--tenant platform]
  python scripts/boss_autonomy.py status
  python scripts/boss_autonomy.py metrics
  python scripts/boss_autonomy.py simulate <title> [--agent hermes]

Sweep advances EXISTING decision ids (never re-proposes). Execution requires a
canary (PILOT_AGENTS) executor; manager is held until its mutating canary.
Boss authority = HMAC via BOSS_GOV_AUTHORITY_KEY, verified by governance.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.platform import boss_autonomy as ba  # noqa: E402


def _parse_payload(payload_str: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for kv in (payload_str or "").split(","):
        if "=" in kv:
            k, v = kv.split("=", 1)
            payload[k.strip()] = v.strip()
    return payload


def cmd_decide(args) -> int:
    out = ba.propose_and_decide(
        decision_type=args.dtype,
        title=args.title,
        payload=_parse_payload(args.payload),
        agent_id=args.agent or None,
    )
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


def cmd_sweep(args) -> int:
    out = ba.sweep_due(limit=args.limit, tenant_id=args.tenant or None)
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


def cmd_status(_args) -> int:
    print(json.dumps(ba.status(), indent=2, default=str))
    return 0


def cmd_metrics(_args) -> int:
    print(json.dumps(ba.metrics(), indent=2, default=str))
    return 0


def cmd_simulate(args) -> int:
    out = ba.propose_and_decide(
        decision_type="internal_plan",
        title=f"simulate:{args.title}",
        payload={"note": "cli smoke"},
        agent_id=args.agent or None,
    )
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


def amain() -> int:
    ap = argparse.ArgumentParser(prog="boss_autonomy")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_decide = sub.add_parser("decide")
    p_decide.add_argument("dtype")
    p_decide.add_argument("title")
    p_decide.add_argument("--payload", default="")
    p_decide.add_argument("--agent", default="")
    p_decide.set_defaults(fn=cmd_decide)

    p_sweep = sub.add_parser("sweep")
    p_sweep.add_argument("--limit", type=int, default=30)
    p_sweep.add_argument("--tenant", default="")
    p_sweep.set_defaults(fn=cmd_sweep)

    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("metrics").set_defaults(fn=cmd_metrics)

    p_sim = sub.add_parser("simulate")
    p_sim.add_argument("title")
    p_sim.add_argument("--agent", default="")
    p_sim.set_defaults(fn=cmd_simulate)

    args = ap.parse_args()
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    sys.exit(amain())
