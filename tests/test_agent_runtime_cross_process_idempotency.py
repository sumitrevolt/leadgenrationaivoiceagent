"""Cross-process idempotency via file backend (no shared Python memory)."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cross_process_duplicate_suppression_file_backend(tmp_path):
    store = tmp_path / "idem_store.json"
    marker = tmp_path / "engine_count.txt"
    result_a = tmp_path / "a.txt"
    result_b = tmp_path / "b.txt"
    key = "xproc-idem-1"
    agent = "pranav"

    def script(out_path: str) -> str:
        return textwrap.dedent(
            f"""
            import asyncio, os, sys
            sys.path.insert(0, {str(ROOT)!r})
            os.environ["AGENT_RUNTIME_IDEM_BACKEND"] = "file"
            os.environ["AGENT_RUNTIME_IDEM_FILE"] = {str(store)!r}
            os.environ["AGENT_RUNTIME_CANCEL_BACKEND"] = "memory"
            os.environ["AGENT_RUNTIME"] = "1"
            os.environ["SRE_AGENT"] = "1"
            from app.platform import agent_runtime as rt
            from app.platform.agent_runtime import AgentCapability

            async def cap(ctx):
                p = {str(marker)!r}
                n = 0
                if os.path.exists(p):
                    n = int(open(p).read() or "0")
                open(p, "w").write(str(n + 1))
                return {{"ok": True}}

            rt._kill_engaged = lambda key: False
            rt._approval_approved = lambda tenant, ref: False
            rt._owner_admission_blocked = lambda aid: (False, "")
            rt._BACKOFF_BASE_S = 0.0
            rt.register_capability(AgentCapability(agent_id={agent!r}, action="idem_x", fn=cap))
            res = asyncio.run(rt.submit({agent!r}, "idem_x", idempotency_key={key!r}))
            open({out_path!r}, "w").write(f"{{res.status}}|{{res.reason}}|{{res.task_id}}")
            print("DONE", res.status, res.reason)
            """
        )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    r1 = subprocess.run(
        [sys.executable, "-c", script(str(result_a))],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert r1.returncode == 0, r1.stdout + r1.stderr
    r2 = subprocess.run(
        [sys.executable, "-c", script(str(result_b))],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert r2.returncode == 0, r2.stdout + r2.stderr

    sa, ra, _ta = result_a.read_text(encoding="utf-8").split("|", 2)
    sb, rb, _tb = result_b.read_text(encoding="utf-8").split("|", 2)
    assert sa == "succeeded"
    assert sb == "skipped" and rb == "duplicate_suppressed"
    assert marker.exists() and marker.read_text(encoding="utf-8").strip() == "1"
    print("cross_process_idempotency = pass")
    print("backend = file")


def test_concurrent_claim_one_winner(monkeypatch):
    import threading

    monkeypatch.setenv("AGENT_RUNTIME_IDEM_BACKEND", "memory")
    from app.platform import agent_runtime_idempotency as arid

    arid.reset_memory_for_tests()
    wins = []

    def go(i):
        out = arid.claim(
            "pranav",
            "run_owned_workflow",
            "race-key",
            runtime_run_id=f"art_race{i:04d}xx",
        )
        wins.append(out.claimed)

    threads = [threading.Thread(target=go, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for w in wins if w) == 1
    assert sum(1 for w in wins if not w) == 7
