#!/usr/bin/env python3
"""Local governed DSH planning/turn/tool loop for NEXT todos.

This is LeadGen's DeepSeek Harness runtime (ADR-181/182), NOT Harness.io.
It uses memory token/run backends + ``app.api.dsh_internal`` MCP tools — the
same seam the Linux ``dsh-jsonrpc-agent`` child would call.

Never: DSH_AGENT_ALLOWLIST=* · swara/ananya · billing/UPI/voice capability
submit · prod Redis · flag arm · deploy.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
OUT = REPO / "docs" / "gtm" / "DSH_NEXT_TODOS_PLAN.json"


def _prepare_memory_backends() -> None:
    os.environ["DSH_TOKEN_BACKEND"] = "memory"
    os.environ["DSH_RUN_STORE_BACKEND"] = "memory"
    os.environ.setdefault("AGENT_RUNTIME", "1")
    os.environ.pop("DSH_AGENT_ALLOWLIST", None)
    os.environ.pop("DSH_RUNTIME_ENABLED", None)
    os.environ.pop("DSH_SHADOW_ENABLED", None)


def _star_allowlist_collapses(dispatch: Any) -> bool:
    previous = os.environ.get("DSH_AGENT_ALLOWLIST")
    try:
        os.environ["DSH_AGENT_ALLOWLIST"] = "kavya,*"
        return dispatch._allowlist() == frozenset()
    finally:
        if previous is None:
            os.environ.pop("DSH_AGENT_ALLOWLIST", None)
        else:
            os.environ["DSH_AGENT_ALLOWLIST"] = previous


def run_plan(*, write: bool = False) -> dict[str, Any]:
    """One Kavya read-only MCP turn: heartbeat → gtm_ops_ready proposal → UPI refuse."""
    _prepare_memory_backends()
    import httpx
    from fastapi import FastAPI
    from httpx import ASGITransport

    from app.api import dsh_internal
    from app.platform.workforce_runtime import run_store, tokens
    from app.tasks import dsh_jobs

    dispatch_mod = importlib.import_module("app.platform.workforce_runtime.dispatch")

    tokens.reset_memory_for_tests()
    run_store.reset_memory_for_tests()

    frozen = sorted(dispatch_mod.FROZEN_AGENTS)
    star_refused = _star_allowlist_collapses(dispatch_mod)
    kavya_provider = dispatch_mod.provider_for("kavya")
    swara_provider = dispatch_mod.provider_for("swara")
    ananya_provider = dispatch_mod.provider_for("ananya")

    run_id = "dshrun_nexttodosplan0001"
    payload = {
        "opaque_ref": "next_todos_md",
        "source": "docs/gtm/NEXT_TODOS.md",
        "goal": "phase0_hot_queue_then_upi_then_bank",
    }
    prompt = dsh_jobs._safe_prompt(
        {
            "run_id": run_id,
            "agent_id": "kavya",
            "action": "ops_health_check",
            "shadow": False,
            "input_payload": payload,
        }
    )
    run_store.create_run(
        run_id=run_id,
        agent_id="kavya",
        tenant_id="ops-tenant",
        action="ops_health_check",
        idempotency_key="next_todos_plan_20260815",
        approval_ref="",
        trigger="owner_os",
        timeout_s=30.0,
        provider="dsh",
        shadow=False,
        deadline=time.time() + 60,
        input_payload=payload,
    )
    token, _binding = tokens.issue(
        run_id=run_id,
        tenant_id="ops-tenant",
        agent_id="kavya",
        allowed_tools=("dsh_heartbeat", "dsh_approval_proposal"),
        deadline=time.time() + 60,
        ttl_s=60,
    )
    gateway = FastAPI()
    gateway.include_router(dsh_internal.router)
    headers = {"Authorization": f"Bearer {token}"}

    async def _mcp_turn() -> tuple[Any, Any, Any]:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=gateway),
            base_url="http://dsh.test",
        ) as client:
            heartbeat = await client.post(
                "/internal/dsh/heartbeat", json={"phase": "planning"}, headers=headers
            )
            proposal = await client.post(
                "/internal/dsh/approval-proposals",
                json={
                    "decision_type": "gtm_ops_ready",
                    "title": "NEXT todos READY plan (no money mutation)",
                    "payload": {
                        "opaque_ref": "next_todos_md",
                        "owner_sequence": [
                            "hot_queue",
                            "upi_bind_reapprove",
                            "bank_confirm",
                            "phase0_exit",
                        ],
                        "eng_ready": [
                            "inbox_shell",
                            "boss_dry_run",
                            "flag_observe",
                            "capacity_honest",
                            "heavy_job_names",
                        ],
                    },
                    "idempotency_key": "next_todos_gtm_ops_ready",
                },
                headers=headers,
            )
            forbidden = await client.post(
                "/internal/dsh/approval-proposals",
                json={
                    "decision_type": "manual_upi_confirmation",
                    "payload": {"opaque_ref": "upi_queue"},
                    "idempotency_key": "next_todos_upi_must_refuse",
                },
                headers=headers,
            )
            return heartbeat, proposal, forbidden

    heartbeat, proposal, forbidden = asyncio.run(_mcp_turn())

    result = {
        "schema": "leadgen/dsh_next_todos_plan/2026-08-15",
        "runtime": "governed_dsh_mcp_memory",
        "not": "harness.io",
        "agent_id": "kavya",
        "action": "ops_health_check",
        "frozen_agents": frozen,
        "star_allowlist_collapses_to_empty": star_refused,
        "provider_for": {
            "kavya": kavya_provider,
            "swara": swara_provider,
            "ananya": ananya_provider,
        },
        "allowlist_empty": True,
        "dsh_runtime_enabled_this_process": False,
        "heartbeat_status": heartbeat.status_code,
        "gtm_ops_ready_status": proposal.status_code,
        "upi_proposal_status": forbidden.status_code,
        "upi_proposal_detail": (forbidden.json() or {}).get("detail"),
        "prompt_prefix": prompt[:80],
        "ok": (
            heartbeat.status_code == 200
            and proposal.status_code == 200
            and forbidden.status_code == 403
            and star_refused
            and kavya_provider == "direct"
            and swara_provider == "direct"
            and ananya_provider == "direct"
            and frozen == ["ananya", "swara"]
        ),
    }
    if write:
        OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    row = run_plan(write=args.write)
    print(json.dumps(row, indent=2, sort_keys=True))
    return 0 if row.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
