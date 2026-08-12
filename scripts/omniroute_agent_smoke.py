r"""OmniRoute agent-hook smoke (ADR-108) — synthetic/public prompt ONLY.

Local dev-only verification: gates status + try_agent_chat() end-to-end via the
REAL local gateway. Kabhi secret print nahi karta; kabhi customer data nahi bhejta.

Run (flags process-only set karke, .env untouched):
  $env:OMNIROUTE_API_KEY=[Environment]::GetEnvironmentVariable('OMNIROUTE_API_KEY','User')
  $env:OMNIROUTE_ENABLED='1'; $env:OMNIROUTE_AGENTS='1'
  .venv\Scripts\python.exe scripts\omniroute_agent_smoke.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> int:
    from app.platform.omniroute_client import (
        agents_enabled,
        omniroute_available,
        omniroute_enabled,
        try_agent_chat,
    )

    print(f"[gate] OMNIROUTE_ENABLED  : {omniroute_enabled()}")
    print(f"[gate] key present        : {bool(os.getenv('OMNIROUTE_API_KEY'))}")
    print(f"[gate] omniroute_available: {omniroute_available()}")
    print(f"[gate] agents_enabled     : {agents_enabled()}")

    if not agents_enabled():
        print(
            "[skip] double gate closed — smoke needs OMNIROUTE_ENABLED=1 + OMNIROUTE_AGENTS=1 + key (process env)."
        )
        return 2

    # SYNTHETIC prompt only (runbook rule) — koi customer/lead data nahi.
    msgs = [{"role": "user", "content": "Reply with exactly: AGENT_OS_SMOKE_OK"}]
    text = await try_agent_chat(msgs)
    if text:
        print(f"[ok] gateway replied ({len(text)} chars): {text[:80]!r}")
        return 0
    print(
        "[fail-open] try_agent_chat returned None — gateway/provider fault; free chain would have handled this call."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
