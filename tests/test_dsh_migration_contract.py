from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest

from scripts.generate_dsh_migration_contract import build_contract, render_contract_json

ROOT = Path(__file__).resolve().parents[1]
DOC_CONTRACT = ROOT / "docs" / "evidence" / "DSH_MIGRATION_CONTRACT_20260814.json"
FIXTURE_CONTRACT = ROOT / "tests" / "fixtures" / "dsh_migration_contract.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _generated_contract() -> dict:
    return build_contract()


@lru_cache(maxsize=1)
def _rendered_contract() -> dict:
    return json.loads(render_contract_json())


@pytest.fixture()
def isolated_runtime_capabilities():
    from app.platform import agent_runtime as rt

    snapshot = dict(rt._CAPABILITIES)
    rt._CAPABILITIES.clear()
    try:
        yield
    finally:
        rt._CAPABILITIES.clear()
        rt._CAPABILITIES.update(snapshot)


def test_contract_is_deterministic_and_matches_committed_outputs(isolated_runtime_capabilities):
    generated = _generated_contract()
    rendered = _rendered_contract()
    doc_contract = _load_json(DOC_CONTRACT)
    fixture_contract = _load_json(FIXTURE_CONTRACT)

    assert generated == rendered
    assert generated == doc_contract == fixture_contract


def test_contract_counts_and_frozen_voice_posture(isolated_runtime_capabilities):
    contract = _generated_contract()
    rows = contract["matrix"]
    by_id = {row["agent_id"]: row for row in rows}

    assert len(rows) == 31
    assert sum(1 for row in rows if row["dsh_candidate"]) == 29

    for agent_id in ("swara", "ananya"):
        row = by_id[agent_id]
        assert row["lane"] == "RED"
        assert row["mode"] == "hard_off"
        assert row["rollout_wave"] == "frozen_never_dsh"
        assert row["dsh_candidate"] is False
        assert row["voice_path_allowed"] is False

    assert by_id["kavya"]["rollout_wave"] == "wave_1_read_only"
    assert by_id["isha"]["rollout_wave"] == "wave_2_draft"
    assert by_id["isha"]["tenant_scope"] == "tenant"
    assert by_id["zara"]["rollout_wave"] == "approved_social_handoff"
    assert by_id["zara"]["approval_requirement"] == "approved_content_only"
    assert all(row["voice_path_allowed"] is False for row in rows if row["team"] == "voice")


def test_runtime_baseline_and_api_contract_are_non_empty_and_stable(isolated_runtime_capabilities):
    contract = _generated_contract()
    baseline = contract["runtime_baseline"]

    assert baseline["module_level_imports"]
    assert baseline["dynamic_imports"]
    assert baseline["call_sites"]

    routes = {
        (route["method"], route["path"]): route
        for route in contract["owner_os_runtime_api"]["routes"]
    }
    assert set(routes) == {
        ("GET", "/api/admin/owner-os/runtime"),
        ("POST", "/api/admin/owner-os/runtime/run"),
    }
    assert routes[("GET", "/api/admin/owner-os/runtime")]["output_fields"] == [
        "agents",
        "calling_badge",
        "cancellation",
        "canonical_count",
        "celery_queue",
        "dlq_tail",
        "generated_at",
        "idempotency",
        "master_flag",
        "ok",
        "pilots",
        "rollout_note",
        "runtime_dlq_count",
        "runtime_enabled",
        "workforce_rollout",
    ]
    assert routes[("POST", "/api/admin/owner-os/runtime/run")]["input_fields"] == [
        "agent_id",
        "action",
        "payload",
        "tenant_id",
        "approval_ref",
        "idempotency_key",
        "timeout_s",
    ]
    assert routes[("POST", "/api/admin/owner-os/runtime/run")]["output_fields"] == [
        "agent_id",
        "capability",
        "heartbeat",
        "ok",
        "provider",
        "queue",
        "reason_code",
        "result",
        "rollout_wave",
        "runtime_version",
        "status",
    ]


def test_contract_contains_no_secret_values_or_absolute_paths(isolated_runtime_capabilities):
    payload = json.dumps(_rendered_contract(), ensure_ascii=False).lower()

    assert "postgres://" not in payload
    assert "postgresql://" not in payload
    assert "mysql://" not in payload
    assert "mongodb://" not in payload
    assert "redis://" not in payload
    assert "bearer " not in payload
    assert '"sk-' not in payload
    assert str(ROOT).lower() not in payload
    assert "c:\\users\\" not in payload
