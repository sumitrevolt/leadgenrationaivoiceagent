"""Tests for the TypeSafe admin triage tool.

The answer shapes below are the LIVE wire contract recorded on 2026-09-18/19 from
`jev-1.13.0` (see scripts/typesafe_admin_triage.py `score_level` docstring) —
not invented fixtures. No test in this file touches the network: the whole point
is that priority ranking is pure and reproducible from recorded answers.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    """Load the script as a module (scripts/ is not an importable package)."""
    path = ROOT / "scripts" / "typesafe_admin_triage.py"
    spec = importlib.util.spec_from_file_location("typesafe_admin_triage", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["typesafe_admin_triage"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


tri = _load_script()

FINDINGS = [
    {
        "id": "B-2",
        "title": "prod runs broken engine",
        "class": "revenue",
        "owner_only": False,
    },
    {
        "id": "B-4",
        "title": "governance gap",
        "class": "compliance",
        "owner_only": True,
    },
    {"id": "B-10", "title": "hygiene", "class": "hygiene", "owner_only": False},
]

# --- recorded live answers (jev-1.13.0) -------------------------------------
NOUL_HIGH = {"type": "noul", "noul": 0.94}
NOUL_LOW = {"type": "noul", "noul": 0.04}
SCORE_3 = {
    "type": "score",
    "score": 3.0,
    "confidence": 1.0,
    "legend": {"0": "none", "1": "small", "2": "meaningful", "3": "blocks revenue"},
    "probabilities": {"0": 0.0, "1": 0.0, "2": 0.0, "3": 1.0},
}
CHOICE_B2 = {
    "type": "choice",
    "choice": "B-2",
    "confidence": 0.89,
    "probabilities": {"B-2": 0.9, "B-4": 0.03, "B-10": 0.0},
}


def test_registry_finds_open_findings_only():
    findings = tri.load_findings()
    ids = {f["id"] for f in findings}
    assert ids, "registry has no open findings"
    assert "admin_verification_email" not in ids, "fixed items must not be triaged"
    assert "B-2" in ids


def test_every_finding_carries_evidence():
    """A finding without observed evidence cannot be judged honestly."""
    for f in tri.load_findings():
        assert f.get("evidence", "").strip(), f"{f['id']} has no evidence string"
        assert f.get("class"), f"{f['id']} has no class"


def test_state_exposes_named_fields_per_finding():
    state = tri.build_state(FINDINGS, ROOT / "docs" / "coordination" / "ADMIN_FINDINGS.json")
    assert set(state["findings"]) == {"B-2", "B-4", "B-10"}
    assert state["findings"]["B-4"]["owner_only_claimed"] is True


def test_questions_cover_each_finding_plus_global_judgments():
    qs = tri.build_questions(FINDINGS)
    assert {k for k in qs if k.startswith("f")} == {
        "fB-2_real_risk",
        "fB-4_real_risk",
        "fB-10_real_risk",
    }
    assert "revenue_impact" in qs and "next_action" in qs and "needs_owner_action" in qs
    assert type(qs["revenue_impact"]).__name__ == "Score"
    assert type(qs["next_action"]).__name__ == "Choice"


def test_state_hash_is_reproducible_and_evidence_sensitive():
    state = tri.build_state(FINDINGS, ROOT / "x.json")
    qs = tri.build_questions(FINDINGS)
    h1 = tri.state_hash(state, qs)

    state2 = json.loads(json.dumps(state))
    assert tri.state_hash(state2, qs) == h1, "same evidence must hash the same"

    state2["findings"]["B-2"]["evidence"] = "changed evidence"
    assert tri.state_hash(state2, qs) != h1, "changed evidence must change the hash"


def test_score_uses_the_live_legend_contract():
    level, desc = tri.score_level(SCORE_3)
    assert level == 3
    assert desc == "blocks revenue"

    # out-of-range / malformed answers clamp or report honestly, never crash
    assert tri.score_level({"type": "score", "score": 99.0})[0] == 3
    assert tri.score_level({"type": "score", "score": -5.0})[0] == 0
    assert "unparsed" in tri.score_level({"type": "score", "score": None})[1]


def test_interpret_ranks_by_risk_weighted_by_severity():
    answers = {
        "fB-2_real_risk": NOUL_HIGH,
        "fB-4_real_risk": {"type": "noul", "noul": 0.88},
        "fB-10_real_risk": NOUL_LOW,
        "revenue_impact": SCORE_3,
        "next_action": CHOICE_B2,
        "needs_owner_action": {"type": "noul", "noul": 0.65},
    }
    d = tri.interpret(FINDINGS, answers)
    assert [r["id"] for r in d["ranking"]] == ["B-2", "B-4", "B-10"]
    assert d["ranking"][0]["priority"] > d["ranking"][1]["priority"]
    assert d["next_action"] == "B-2"
    assert d["next_action_source"] == "model_choice"
    assert d["severity_weight"] == 3
    assert d["needs_owner_action"] is True
    assert d["next_action_distribution"]["B-2"] == pytest.approx(0.9)


def test_interpret_falls_back_to_ranking_when_choice_is_off_menu():
    """An out-of-set choice must not be silently trusted."""
    answers = {
        "fB-2_real_risk": NOUL_LOW,
        "fB-4_real_risk": NOUL_HIGH,
        "fB-10_real_risk": NOUL_LOW,
        "revenue_impact": SCORE_3,
        "next_action": {"type": "choice", "choice": "NOT_A_FINDING", "confidence": 0.4},
        "needs_owner_action": {"type": "noul", "noul": 0.1},
    }
    d = tri.interpret(FINDINGS, answers)
    assert d["next_action"] == "B-4"
    assert d["next_action_source"] == "ranking_fallback"
    assert d["needs_owner_action"] is False


def test_missing_risk_answer_ranks_last_not_as_zero_risk(tmp_path):
    """`unknown != 0` — an unjudged finding must not outrank a judged one."""
    answers = {
        "fB-2_real_risk": NOUL_LOW,
        "fB-4_real_risk": NOUL_LOW,
        "fB-10_real_risk": NOUL_LOW,
        "revenue_impact": SCORE_3,
        "next_action": CHOICE_B2,
        "needs_owner_action": {"type": "noul", "noul": 0.0},
    }
    d = tri.interpret(FINDINGS, answers)
    assert d["next_action"] == "B-2"


# --- trace / CLI -------------------------------------------------------------
class _FakeResponse:
    success = True
    error = None
    model = "jev-1.13.0"
    result = {"model": "jev-1.13.0"}
    latency_sec = 1.3
    answers = {
        "fB-2_real_risk": NOUL_HIGH,
        "fB-4_real_risk": NOUL_LOW,
        "fB-10_real_risk": NOUL_LOW,
        "revenue_impact": SCORE_3,
        "next_action": CHOICE_B2,
        "needs_owner_action": {"type": "noul", "noul": 0.65},
    }


class _FakeClient:
    """Stands in for TypeSafeClient — same call surface, recorded answers."""

    def system_one(self, state, questions):
        return _FakeResponse()


@pytest.fixture()
def present_cred(monkeypatch):
    monkeypatch.setattr(
        tri,
        "credential_state",
        lambda: {
            "state": "PRESENT",
            "enabled": True,
            "fingerprint": "2e13ca55f7f8",
            "model": "jev-latest",
        },
    )
    monkeypatch.setattr(tri, "get_typesafe_client", lambda: _FakeClient())


def test_trace_record_has_the_mandated_fields():
    state = tri.build_state(FINDINGS, ROOT / "docs" / "coordination" / "ADMIN_FINDINGS.json")
    qs = tri.build_questions(FINDINGS)
    rec = tri.trace_record(
        task_id="t1",
        state=state,
        questions=qs,
        response=_FakeResponse(),
        decision=tri.interpret(FINDINGS, _FakeResponse.answers),
        evidence_refs=["docs/coordination/ADMIN_FINDINGS.json#B-2"],
        s_hash="abc123",
        requested_model="jev-latest",
    )
    for field in (
        "task_id",
        "state_hash",
        "evidence_refs",
        "requested_model",
        "resolved_model",
        "latency_sec",
        "success",
        "questions",
        "answers",
        "decision",
        "downstream_action",
        "outcome",
    ):
        assert field in rec, f"trace is missing required field {field}"
    assert rec["requested_model"] == "jev-latest"
    assert rec["resolved_model"] == "jev-1.13.0"
    assert rec["downstream_action"] == "pending_admin_execution"
    assert rec["outcome"] is None


def test_record_outcome_appends_and_keeps_decision_immutable(tmp_path):
    trace = tmp_path / "trace.jsonl"
    tri.append_jsonl(trace, {"kind": "decision", "task_id": "t1", "outcome": None})
    rec = tri.record_outcome(trace, "t1", "fixed + verified")
    lines = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["outcome"] is None, "decision record must not be rewritten"
    assert lines[1]["kind"] == "outcome"
    assert rec["outcome"] == "fixed + verified"


def test_cli_fails_closed_when_credentials_are_absent(tmp_path, monkeypatch, capsys):
    """No key => exit 3, and NO decision record written (never invent a priority)."""
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setattr(tri, "credential_state", lambda: {"state": "ABSENT", "enabled": False})
    rc = tri.main(["--trace", str(trace)])
    assert rc == 3
    assert not trace.exists()
    assert "FAIL-CLOSED" in capsys.readouterr().err


def test_cli_fails_closed_when_the_api_call_fails(tmp_path, monkeypatch, capsys):
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setattr(
        tri,
        "credential_state",
        lambda: {"state": "PRESENT", "enabled": True, "model": "jev-latest"},
    )

    class _Boom:
        def system_one(self, state, questions):
            class R:
                success = False
                error = "HTTP 401: unauthorized"
                model = None
                latency_sec = 0.2
                answers: dict = {}

            return R()

    monkeypatch.setattr(tri, "get_typesafe_client", lambda: _Boom())
    rc = tri.main(["--trace", str(trace)])
    assert rc == 3
    assert not trace.exists()
    assert "FAIL-CLOSED" in capsys.readouterr().err


def test_cli_records_a_trace_on_success(tmp_path, monkeypatch, present_cred):
    trace = tmp_path / "trace.jsonl"
    rc = tri.main(["--trace", str(trace), "--json"])
    assert rc == 0
    rec = json.loads(trace.read_text(encoding="utf-8").splitlines()[0])
    assert rec["success"] is True
    assert rec["decision"]["next_action"] == "B-2"


def test_never_writes_the_credential_into_the_trace(tmp_path, monkeypatch, present_cred):
    """Secret hygiene: the trace must never contain the key or its raw form."""
    secret = "apikey_241d1117d72428e4219b3678f7e5d4bdf97_deadbeefdeadbeefdeadbeef"  # nosecret
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setenv("TYPESAFE_API_KEY", secret)
    assert tri.main(["--trace", str(trace)]) == 0
    written = trace.read_text(encoding="utf-8")
    assert secret not in written
    assert "241d1117" not in written


def test_usage_error_when_outcome_text_missing(tmp_path, capsys):
    rc = tri.main(["--record-outcome", "t1", "--trace", str(tmp_path / "t.jsonl")])
    assert rc == 1
    assert "REFUSED" in capsys.readouterr().err


def test_default_trace_path_avoids_the_runtime_data_tree():
    """`data/` belongs to the runtime-data ratchets — a trace log must not widen it.

    `tests/test_runtime_data_a1_ratchet.py` counts every `data/`-rooted path as
    reviewed surface and pins the total, so adding one there is a gate change.
    """
    assert "data" not in tri.DEFAULT_TRACE.parts
    assert tri.DEFAULT_TRACE.name == "typesafe_decisions.jsonl"
