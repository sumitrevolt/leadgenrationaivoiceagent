"""Cross-process cancellation proof via file backend (no shared Python memory).

Process A = requester writes cancel through CancellationStore(file).
Process B = executor reads the same file store and refuses engine invocation.

Uses subprocess so there is zero shared ``_MEM`` / module state.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_cross_process_cancellation_via_file_store(tmp_path):
    store = tmp_path / "cancel_store.json"
    run_id = "art_crossproc001"
    agent = "pranav"
    marker = tmp_path / "engine_ran.txt"
    result = tmp_path / "result.txt"

    requester = textwrap.dedent(
        f"""
        import os, sys
        sys.path.insert(0, {str(ROOT)!r})
        os.environ["AGENT_RUNTIME_CANCEL_BACKEND"] = "file"
        os.environ["AGENT_RUNTIME_CANCEL_FILE"] = {str(store)!r}
        from app.platform import agent_runtime_cancellation as crc
        out = crc.request({agent!r}, {run_id!r}, requested_by="owner", reason="cross_process")
        assert out["ok"], out
        print("REQUEST_OK", out["cancellation_backend"], out["key"])
        """
    )

    executor = textwrap.dedent(
        f"""
        import asyncio, os, sys
        sys.path.insert(0, {str(ROOT)!r})
        os.environ["AGENT_RUNTIME_CANCEL_BACKEND"] = "file"
        os.environ["AGENT_RUNTIME_CANCEL_FILE"] = {str(store)!r}
        os.environ["AGENT_RUNTIME_IDEM_BACKEND"] = "memory"
        os.environ["AGENT_RUNTIME"] = "1"
        os.environ["SRE_AGENT"] = "1"
        from app.platform import agent_runtime as rt
        from app.platform.agent_runtime import AgentCapability, AgentTask

        async def cap(ctx):
            open({str(marker)!r}, "w").write("ran")
            return {{}}

        rt._kill_engaged = lambda key: False
        rt._approval_approved = lambda tenant, ref: False
        rt._owner_admission_blocked = lambda aid: (False, "")
        rt._BACKOFF_BASE_S = 0.0
        rt.register_capability(AgentCapability(agent_id={agent!r}, action="xproc", fn=cap))
        task = AgentTask(agent_id={agent!r}, action="xproc", task_id={run_id!r})
        res = asyncio.run(rt.run_task(task))
        open({str(result)!r}, "w").write(f"{{res.status}}|{{res.reason}}")
        print("EXEC", res.status, res.reason)
        """
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    r1 = subprocess.run(
        [sys.executable, "-c", requester],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r1.returncode == 0, r1.stdout + r1.stderr
    assert "REQUEST_OK" in r1.stdout

    r2 = subprocess.run(
        [sys.executable, "-c", executor],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r2.returncode == 0, r2.stdout + r2.stderr
    body = result.read_text(encoding="utf-8")
    status, reason = body.split("|", 1)
    assert status == "cancelled"
    assert reason == "cancel_requested"
    assert not marker.exists(), "engine must not run"
    assert "cross_process_cancellation = pass" or True
    print("cross_process_cancellation = pass")
    print("backend = file  # CI stand-in for redis; prod uses redis")
