"""Cross-process concurrency tests for the external-agent CAS layer.

These launch real child Python processes against a shared EXTERNAL_MISSION_DIR
using the filelock CAS backend (portalocker). Redis is preferred in production
when reachable; this suite proves the shared-volume path that VPS containers
already have via ``./data:/app/data``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable


def _run_workers(script: str, env: dict[str, str], *, n: int = 2) -> list[dict]:
    """Start n identical workers; return their JSON stdout payloads."""
    procs = [
        subprocess.Popen(
            [PY, "-c", script],
            cwd=str(REPO),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(n)
    ]
    results: list[dict] = []
    for p in procs:
        out, err = p.communicate(timeout=60)
        assert p.returncode == 0, f"worker failed rc={p.returncode} stderr={err}\nstdout={out}"
        line = (out or "").strip().splitlines()[-1]
        results.append(json.loads(line))
    return results


@pytest.fixture()
def shared_env(tmp_path, monkeypatch):
    root = tmp_path / "missions"
    root.mkdir()
    env = os.environ.copy()
    env["EXTERNAL_MISSION_DIR"] = str(root)
    env["EXTERNAL_AGENT_ORCHESTRATOR"] = "1"
    env["EXTERNAL_MISSION_CAS"] = "filelock"
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    monkeypatch.setenv("EXTERNAL_MISSION_DIR", str(root))
    monkeypatch.setenv("EXTERNAL_AGENT_ORCHESTRATOR", "1")
    monkeypatch.setenv("EXTERNAL_MISSION_CAS", "filelock")
    from app.dev_control.external_agents import cas as cas_mod

    cas_mod.reset_backend()
    yield {"root": root, "env": env}
    cas_mod.reset_backend()


def _seed_mission(root: Path, *, status: str = "PREFLIGHT") -> str:
    from app.dev_control.external_agents import cas as cas_mod
    from app.dev_control.external_agents import store
    from app.dev_control.external_agents.schema import Mission, MissionState, RiskClass

    cas_mod.reset_backend()
    m = Mission.create(
        title="cross-process claim race",
        executor="cursor",
        reviewer="claude",
        idempotency_key="mp-seed-key-0001",
        allowed_paths=["tests/test_external_agent_orchestrator.py"],
        branch="feat/mp",
        worktree="C:/wt/mp",
        risk_class=RiskClass.GREEN,
    )
    m.status = MissionState(status)
    store.save(m)
    store.register_idempotency(m.idempotency_key, m.mission_id)
    return m.mission_id


def test_concurrent_claim_exactly_one_winner(shared_env):
    mid = _seed_mission(shared_env["root"])
    script = textwrap.dedent(
        f"""
        import json, os, time, random
        os.environ['EXTERNAL_MISSION_DIR'] = {str(shared_env["root"])!r}
        os.environ['EXTERNAL_AGENT_ORCHESTRATOR'] = '1'
        os.environ['EXTERNAL_MISSION_CAS'] = 'filelock'
        from app.dev_control.external_agents import cas, store
        cas.reset_backend()
        time.sleep(random.uniform(0, 0.05))
        owner = f'worker-{{os.getpid()}}'
        out = store.claim({mid!r}, owner, ttl_s=120)
        print(json.dumps({{'claimed': out.get('claimed'), 'owner': owner,
                          'reason': out.get('reason'), 'lease_owner': out.get('lease_owner')}}))
        """
    )
    results = _run_workers(script, shared_env["env"], n=2)
    winners = [r for r in results if r.get("claimed")]
    losers = [r for r in results if not r.get("claimed")]
    assert len(winners) == 1, results
    assert len(losers) == 1, results
    assert losers[0]["reason"] == "lease_held"
    from app.dev_control.external_agents import cas, store

    cas.reset_backend()
    mission = store.get(mid)
    assert mission is not None
    assert mission.lease_owner == winners[0]["owner"]
    events = (shared_env["root"] / "events.jsonl").read_text(encoding="utf-8")
    assert events.count("lease_claimed") == 1


def test_concurrent_idempotent_create_same_mission_id(shared_env):
    script = textwrap.dedent(
        f"""
        import json, os, time, random
        os.environ['EXTERNAL_MISSION_DIR'] = {str(shared_env["root"])!r}
        os.environ['EXTERNAL_AGENT_ORCHESTRATOR'] = '1'
        os.environ['EXTERNAL_MISSION_CAS'] = 'filelock'
        from app.dev_control.external_agents import cas, orchestrator
        cas.reset_backend()
        time.sleep(random.uniform(0, 0.05))
        out = orchestrator.create_mission(
            title='idempotent create race',
            executor='cursor', reviewer='claude',
            idempotency_key='mp-idem-key-zzzz',
            allowed_paths=['tests/a.py'],
            branch='feat/idem-shared',
            worktree='C:/wt/idem-shared',
        )
        print(json.dumps({{'ok': out.get('ok'), 'reused': out.get('reused'),
                          'mission_id': (out.get('mission') or {{}}).get('mission_id')}}))
        """
    )
    results = _run_workers(script, shared_env["env"], n=2)
    ids = {r["mission_id"] for r in results}
    assert len(ids) == 1 and all(r["ok"] for r in results), results
    assert sum(1 for r in results if r.get("reused")) >= 1
    missions = list(shared_env["root"].glob("msn_*.json"))
    assert len(missions) == 1


def test_concurrent_heartbeat_owner_only(shared_env):
    mid = _seed_mission(shared_env["root"])
    from app.dev_control.external_agents import cas, store

    cas.reset_backend()
    assert store.claim(mid, "owner-a", ttl_s=120)["claimed"]
    script = textwrap.dedent(
        f"""
        import json, os
        os.environ['EXTERNAL_MISSION_DIR'] = {str(shared_env["root"])!r}
        os.environ['EXTERNAL_AGENT_ORCHESTRATOR'] = '1'
        os.environ['EXTERNAL_MISSION_CAS'] = 'filelock'
        from app.dev_control.external_agents import cas, store
        cas.reset_backend()
        owner = os.environ['WORKER_OWNER']
        print(json.dumps({{'ok': store.heartbeat({mid!r}, owner, ttl_s=120), 'owner': owner}}))
        """
    )
    env_a = dict(shared_env["env"])
    env_a["WORKER_OWNER"] = "owner-a"
    env_b = dict(shared_env["env"])
    env_b["WORKER_OWNER"] = "owner-b"
    out_a = _run_workers(script, env_a, n=1)[0]
    out_b = _run_workers(script, env_b, n=1)[0]
    assert out_a["ok"] is True
    assert out_b["ok"] is False


def test_stale_recovery_and_old_owner_blocked(shared_env):
    mid = _seed_mission(shared_env["root"], status="RUNNING")
    from app.dev_control.external_agents import cas, store
    from app.dev_control.external_agents.schema import MissionState

    cas.reset_backend()
    past = datetime.utcnow() - timedelta(hours=2)
    assert store.claim(mid, "old-owner", ttl_s=30, now=past)["claimed"]
    # Force lease expiry on the CAS record.
    backend = cas.get_backend(root=str(shared_env["root"]))
    backend.claim_lease(mid, "old-owner", ttl_s=1, now=past.timestamp())

    recovered = store.recover_stale()
    assert any(r["mission_id"] == mid for r in recovered)
    mission = store.get(mid)
    assert mission is not None and mission.status is MissionState.FAILED_RETRYABLE

    # Old owner must not be able to submit a result after ownership changed.
    from app.dev_control.external_agents import orchestrator

    orchestrator.preflight(mid)  # may fail if not PREFLIGHT — retry path
    # Re-seed to PREFLIGHT via transition for the submit attempt.
    mission = store.get(mid)
    assert mission is not None
    if mission.status is MissionState.FAILED_RETRYABLE:
        mission.transition(MissionState.PREFLIGHT)
        store.save(mission)
    orchestrator.claim(mid, "new-owner")
    out = orchestrator.submit_result(
        mid,
        "old-owner",
        {
            "mission_id": mid,
            "executor": "cursor",
            "changed_files": ["tests/test_external_agent_orchestrator.py"],
            "tests": [{"command": "x", "exit_code": 0}],
        },
    )
    assert out["ok"] is False and out["reason"] == "lease_not_owned"


def test_concurrent_transition_one_commits(shared_env):
    mid = _seed_mission(shared_env["root"], status="PREFLIGHT")
    script = textwrap.dedent(
        f"""
        import json, os, time, random
        os.environ['EXTERNAL_MISSION_DIR'] = {str(shared_env["root"])!r}
        os.environ['EXTERNAL_AGENT_ORCHESTRATOR'] = '1'
        os.environ['EXTERNAL_MISSION_CAS'] = 'filelock'
        from app.dev_control.external_agents import cas, store
        from app.dev_control.external_agents.schema import MissionState
        cas.reset_backend()
        time.sleep(random.uniform(0, 0.05))
        target = os.environ['TARGET_STATE']
        out = store.transition_cas({mid!r}, MissionState.PREFLIGHT, MissionState(target))
        print(json.dumps({{'ok': out.get('ok'), 'reason': out.get('reason'),
                          'status': (out.get('mission').status.value if out.get('mission') else None)}}))
        """
    )
    env_a = dict(shared_env["env"])
    env_a["TARGET_STATE"] = "CLAIMED"
    env_b = dict(shared_env["env"])
    env_b["TARGET_STATE"] = "CANCELLED"
    # Run both almost together via Popen directly with different env.
    procs = []
    for env in (env_a, env_b):
        procs.append(
            subprocess.Popen(
                [PY, "-c", script],
                cwd=str(REPO),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        )
    results = []
    for p in procs:
        out, err = p.communicate(timeout=60)
        assert p.returncode == 0, err
        results.append(json.loads(out.strip().splitlines()[-1]))
    ok_rows = [r for r in results if r.get("ok")]
    stale = [r for r in results if r.get("reason") == "stale_transition"]
    assert len(ok_rows) == 1, results
    assert len(stale) == 1, results
    from app.dev_control.external_agents import cas, store

    cas.reset_backend()
    final = store.get(mid)
    assert final is not None
    assert final.status.value == ok_rows[0]["status"]
    # Review gate still cannot be jumped via transition_cas to REVIEW_PASSED from PREFLIGHT.
    bad = store.transition_cas(
        mid,
        final.status,
        __import__(
            "app.dev_control.external_agents.schema", fromlist=["MissionState"]
        ).MissionState.REVIEW_PASSED,
    )
    assert bad["ok"] is False


def test_orchestrator_cancel_vs_advance_cas(shared_env):
    """Production path: race two orchestrator.cancel calls — exactly one commits."""
    mid = _seed_mission(shared_env["root"], status="REVIEW_PASSED")
    from app.dev_control.external_agents import cas, store

    script = textwrap.dedent(
        f"""
        import json, os, time, random
        os.environ['EXTERNAL_MISSION_DIR'] = {str(shared_env["root"])!r}
        os.environ['EXTERNAL_AGENT_ORCHESTRATOR'] = '1'
        os.environ['EXTERNAL_MISSION_CAS'] = 'filelock'
        from app.dev_control.external_agents import cas, orchestrator
        cas.reset_backend()
        time.sleep(random.uniform(0, 0.05))
        out = orchestrator.cancel({mid!r}, reason='race')
        print(json.dumps({{'ok': out.get('ok'), 'reason': out.get('reason'),
                          'status': (out.get('mission') or {{}}).get('status')}}))
        """
    )
    results = _run_workers(script, shared_env["env"], n=2)
    ok_rows = [r for r in results if r.get("ok")]
    assert len(ok_rows) == 1, results
    assert any(not r.get("ok") for r in results), results
    cas.reset_backend()
    final = store.get(mid)
    assert final is not None
    assert final.status.value == "CANCELLED"
