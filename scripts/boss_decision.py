"""Boss Decision CLI — thin read-only adapter over boss_decision_governance.

NOT a second decision engine. Mutation/execution belongs to
app.platform.boss_autonomy (flag-gated) and Owner OS. This CLI only:
  propose  -> create a governed decision object (public bdg.propose_decision)
  show     -> read-only normalized evaluation (authority class, lane, rollout)
  pending  -> list open decisions (public bdg.list_pending)
  coverage -> typed adapter routing coverage (public bdg.routing_coverage)
  status   -> autonomy + governance status (public boss_autonomy.status)

Usage:
  python scripts/boss_decision.py propose <type> <title> [--payload k=v,k=v]
  python scripts/boss_decision.py show <decision_id>
  python scripts/boss_decision.py pending [--limit 20]
  python scripts/boss_decision.py coverage
  python scripts/boss_decision.py status
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
from app.platform import boss_decision_governance as bdg  # noqa: E402


def _parse_payload(payload_str: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for kv in (payload_str or "").split(","):
        if "=" in kv:
            k, v = kv.split("=", 1)
            payload[k.strip()] = v.strip()
    return payload


def cmd_propose(args) -> int:
    out = bdg.propose_decision(
        tenant_id=args.tenant or "platform",
        agent_id=args.agent or "manager",
        decision_type=args.dtype,
        title=args.title,
        payload=_parse_payload(args.payload),
        proposed_by="boss_cli",
        kind="decision",
    )
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") or out.get("inert") else 1


def cmd_show(args) -> int:
    out = ba.evaluate_decision(args.decision_id)
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


def cmd_pending(args) -> int:
    rows = bdg.list_pending(limit=args.limit)
    print(json.dumps({"count": len(rows), "rows": rows}, indent=2, default=str))
    return 0


def cmd_coverage(_args) -> int:
    print(json.dumps(bdg.routing_coverage(), indent=2, default=str))
    return 0


def cmd_status(_args) -> int:
    print(json.dumps(ba.status(), indent=2, default=str))
    return 0


def amain() -> int:
    ap = argparse.ArgumentParser(prog="boss_decision")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_propose = sub.add_parser("propose")
    p_propose.add_argument("dtype")
    p_propose.add_argument("title")
    p_propose.add_argument("--payload", default="")
    p_propose.add_argument("--tenant", default="")
    p_propose.add_argument("--agent", default="")
    p_propose.set_defaults(fn=cmd_propose)

    p_show = sub.add_parser("show")
    p_show.add_argument("decision_id")
    p_show.set_defaults(fn=cmd_show)

    p_pending = sub.add_parser("pending")
    p_pending.add_argument("--limit", type=int, default=20)
    p_pending.set_defaults(fn=cmd_pending)

    sub.add_parser("coverage").set_defaults(fn=cmd_coverage)
    sub.add_parser("status").set_defaults(fn=cmd_status)

    args = ap.parse_args()
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    sys.exit(amain())
