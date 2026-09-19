"""Typed-contract guards for the TypeSafe surface.

Each test here pins a defect that was found by live probing on 2026-09-19 and
that would otherwise be able to return silently:

1. `credential_state()` returns a MAPPING. Comparing that mapping to the bare
   label "PRESENT" is always False, so an armed integration was reported as
   absent. Guarded at both the behaviour level and the source level.
2. A `Noul` probability of exactly 0.0 is falsy. Writing
   `x.get("noul") or x.get("probability") or default` collapses a confident NO
   into `default`. Guarded directly against `_noul_prob`.
3. The `Score` bucket maps are keyed by int; an un-narrowed leaf silently
   misses the key. Guarded against `_score_index`.
4. The outbound content gate asked one vague triple-barrelled question, which
   flagged ~100% of compliant outreach as spam and — because
   `EmailSender.send_email` hard-blocks on `approved=False` — silently killed
   the entire outbound email funnel. Guarded by asserting the question
   enumerates concrete signals.
5. `budget_likelihood` was passed through raw behind a `# type: ignore`, so an
   unexpected bucket reached pydantic and raised ValidationError (HTTP 500).

All tests are hermetic: no network, no credential, no real API call.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.api import typesafe_routes
from app.platform.typesafe_bridge import get_typesafe_bridge
from app.platform.typesafe_integration import TypeSafeResponse, credential_state
from app.platform.typesafe_schemas import (
    BudgetLikelihoodEnum,
    LeadQualifyRequest,
)
from app.platform.typesafe_services import (
    LeadQualificationResult,
    _noul_prob,
    _score_index,
    get_typesafe_content_qa,
)

ROOT = Path(__file__).resolve().parents[1]

_CREDENTIAL_KEYS = {"state", "enabled", "source", "fingerprint", "model"}
_STATE_LABELS = {"PRESENT", "ABSENT", "INVALID", "ROTATION_REQUIRED"}


# --------------------------------------------------------------------------- #
# 1. credential_state() is a mapping, not a label
# --------------------------------------------------------------------------- #


def test_credential_state_is_a_mapping_not_a_label():
    """The contract is a CredentialState mapping; callers must read ["state"]."""
    state = credential_state()
    assert isinstance(state, dict), "credential_state() must return a mapping"
    assert _CREDENTIAL_KEYS <= set(state), f"missing keys: {_CREDENTIAL_KEYS - set(state)}"
    assert state["state"] in _STATE_LABELS
    assert isinstance(state["enabled"], bool)


def test_status_compares_the_state_key_not_the_whole_mapping():
    """Source guard: `cred == "PRESENT"` is always False and hides an armed key."""
    src = (ROOT / "app/api/typesafe_routes.py").read_text(encoding="utf-8")
    assert 'cred == "PRESENT"' not in src, (
        "regression: comparing the credential mapping to a bare string is always "
        "False, so an armed integration is reported as absent"
    )
    assert 'state == "PRESENT"' in src


def test_status_reports_an_armed_credential_as_present(monkeypatch):
    """Behaviour guard: an armed credential must surface as credential_present=True."""
    armed: dict[str, Any] = {
        "state": "PRESENT",
        "enabled": True,
        "source": "env:TYPESAFE_API_KEY",
        "fingerprint": "deadbeef1234",
        "model": "jev-latest",
    }
    monkeypatch.setattr(typesafe_routes, "credential_state", lambda: dict(armed))

    resp = asyncio.run(typesafe_routes.get_status(_user=None))

    assert resp.credential_present is True
    assert resp.enabled is True
    assert resp.credential_source == "env:TYPESAFE_API_KEY"
    assert resp.fingerprint == "deadbeef1234"


def test_status_reports_an_absent_credential_as_absent(monkeypatch):
    absent: dict[str, Any] = {
        "state": "ABSENT",
        "enabled": False,
        "source": "none",
        "fingerprint": "",
        "model": "jev-latest",
    }
    monkeypatch.setattr(typesafe_routes, "credential_state", lambda: dict(absent))

    resp = asyncio.run(typesafe_routes.get_status(_user=None))

    assert resp.credential_present is False
    assert resp.enabled is False
    # an empty fingerprint must not leak through as "" — it is normalised to "none"
    assert resp.fingerprint == "none"


# --------------------------------------------------------------------------- #
# 2. _noul_prob must not collapse a genuine 0.0
# --------------------------------------------------------------------------- #


def test_noul_prob_preserves_a_genuine_zero():
    """0.0 is a confident NO, not "missing". The `or` chain got this wrong."""
    assert _noul_prob({"type": "noul", "noul": 0.0}, 0.5) == 0.0
    assert _noul_prob({"type": "noul", "noul": 0.0}, 0.0) == 0.0


def test_noul_prob_reads_the_noul_leaf():
    assert _noul_prob({"type": "noul", "noul": 0.87}, 0.5) == 0.87


def test_noul_prob_falls_back_to_probability_when_noul_absent():
    assert _noul_prob({"type": "noul", "probability": 0.31}, 0.5) == 0.31


def test_noul_prob_prefers_noul_over_probability():
    assert _noul_prob({"noul": 0.9, "probability": 0.1}, 0.5) == 0.9


def test_noul_prob_degrades_on_malformed_leaf():
    assert _noul_prob({"noul": "not-a-number"}, 0.5) == 0.5
    assert _noul_prob({"noul": None}, 0.5) == 0.5
    assert _noul_prob({}, 0.5) == 0.5
    assert _noul_prob(None, 0.5) == 0.5
    # bool must not be treated as a score
    assert _noul_prob({"noul": True}, 0.5) == 0.5
    # a bare numeric leaf (not wrapped in a dict) still coerces
    assert _noul_prob(0.42, 0.5) == 0.42
    assert _noul_prob("0.42", 0.5) == 0.42


# --------------------------------------------------------------------------- #
# 3. _score_index narrows to an int bucket
# --------------------------------------------------------------------------- #


def test_score_index_narrows_numeric_leaves():
    assert _score_index(0) == 0
    assert _score_index(2) == 2
    assert _score_index(2.0) == 2
    assert _score_index("3") == 3


def test_score_index_returns_none_on_malformed_leaves():
    assert _score_index(None) is None
    assert _score_index("high") is None
    assert _score_index(True) is None
    assert _score_index({"score": 1}) is None


def test_score_bucket_maps_are_int_keyed():
    """The maps are keyed by int, which is why the leaf must be narrowed first."""
    bucket_map = {0: "cold", 1: "lukewarm", 2: "warm", 3: "hot"}
    assert bucket_map.get(_score_index(2.0), "lukewarm") == "warm"
    # an un-narrowed 1.9 would miss the key and fall through to the default
    assert bucket_map.get(_score_index(1.9), "lukewarm") == "lukewarm"


# --------------------------------------------------------------------------- #
# 4. The content gate must ask a decidable question
# --------------------------------------------------------------------------- #


def _capture_content_questions() -> dict[str, Any]:
    """Intercept the questions the content gate sends, without calling the API."""
    qa = get_typesafe_content_qa()
    captured: dict[str, Any] = {}

    def fake_system_one(state: dict[str, Any], questions: dict[str, Any]) -> TypeSafeResponse:
        captured.update(questions)
        return TypeSafeResponse(success=False, error="INERT: test double")

    original = qa.client.system_one
    qa.client.system_one = fake_system_one  # type: ignore[method-assign]
    try:
        qa.audit_outbound_message("subject", "body", "email")
    finally:
        qa.client.system_one = original  # type: ignore[method-assign]
    return captured


def test_content_gate_asks_all_four_questions():
    captured = _capture_content_questions()
    assert set(captured) >= {"spam", "compliance", "persuasion", "tone"}


def test_spam_question_enumerates_concrete_signals():
    """A vague question flagged compliant outreach as spam and blocked the funnel."""
    spam = _capture_content_questions()["spam"].to_dict("spam")["instructions"]
    lowered = spam.lower()
    assert "guaranteed" in lowered, "spam criteria must name guaranteed-result claims"
    assert "clickbait" in lowered
    assert "opt-out" in lowered or "opt out" in lowered, (
        "the question must tell the model that a compliant opt-out is NOT spam"
    )
    assert "look like spam, use deceptive clickbait, or violate commercial guidelines" not in spam, (
        "the old undecidable triple-barrelled question must not return — it flagged "
        "every compliant email and silently blocked the outbound funnel"
    )


def test_compliance_question_enumerates_concrete_signals():
    compliance = _capture_content_questions()["compliance"].to_dict("compliance")["instructions"]
    lowered = compliance.lower()
    assert "guarantee" in lowered
    assert "sender identification" in lowered
    assert "opt out" in lowered or "opt-out" in lowered


# --------------------------------------------------------------------------- #
# 5. budget_likelihood must be mapped, never passed through raw
# --------------------------------------------------------------------------- #


def test_bridge_does_not_pass_budget_likelihood_through_raw():
    src = (ROOT / "app/platform/typesafe_bridge.py").read_text(encoding="utf-8")
    assert "budget_likelihood=result.budget_likelihood" not in src, (
        "regression: a raw str reaches a BudgetLikelihoodEnum field and pydantic "
        "raises ValidationError (HTTP 500) on an unexpected bucket"
    )
    assert "budget_map" in src


def test_bridge_softens_an_unknown_budget_bucket_instead_of_raising(monkeypatch):
    bridge = get_typesafe_bridge()
    bogus = LeadQualificationResult(
        score=70,
        fit_level="high",
        buying_intent=True,
        intent_confidence=0.9,
        budget_likelihood="ginormous",  # hallucinated bucket
        recommended_product="combo",
        pitch_angle="x",
        is_hot_lead=True,
    )
    monkeypatch.setattr(bridge.lead_scorer, "qualify_lead", lambda lead: bogus)

    resp = bridge.qualify_lead(LeadQualifyRequest(name="Apex Dental"))

    assert resp.budget_likelihood == BudgetLikelihoodEnum.STANDARD
    assert resp.score == 70


def test_bridge_maps_every_declared_budget_bucket():
    """Each bucket the scorer can emit must round-trip through the bridge map."""
    bridge = get_typesafe_bridge()
    for bucket, expected in (
        ("shoestring", BudgetLikelihoodEnum.SHOESTRING),
        ("modest", BudgetLikelihoodEnum.MODEST),
        ("standard", BudgetLikelihoodEnum.STANDARD),
        ("enterprise", BudgetLikelihoodEnum.ENTERPRISE),
    ):
        result = LeadQualificationResult(
            score=50,
            fit_level="medium",
            buying_intent=False,
            intent_confidence=0.5,
            budget_likelihood=bucket,
            recommended_product="marketing_suite",
            pitch_angle="x",
            is_hot_lead=False,
        )
        bridge.lead_scorer.qualify_lead = lambda lead, _r=result: _r  # type: ignore[method-assign]
        resp = bridge.qualify_lead(LeadQualifyRequest(name="X"))
        assert resp.budget_likelihood == expected, f"bucket {bucket!r} not mapped"
