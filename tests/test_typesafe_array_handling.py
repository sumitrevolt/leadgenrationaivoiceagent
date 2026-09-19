"""Tests for TypeSafe array/dict criteria normalization and resilient response parsing.

Validates that passing lists or arrays to Choice/Score does not cause array type errors,
and that TypeSafeResponse gracefully parses both dict and array (list) answers without
raising AttributeError: 'list' object has no attribute 'values'.
"""

from __future__ import annotations

from app.platform.typesafe_integration import Choice, Noul, Score, TypeSafeResponse


def test_choice_criteria_array_coercion():
    """Passing a list of options to Choice must auto-normalize to a dictionary mapping."""
    options = ["proceed", "retry", "escalate"]
    c = Choice("What is the next step?", options)
    assert isinstance(c.criteria, dict)
    assert c.criteria == {
        "proceed": "proceed",
        "retry": "retry",
        "escalate": "escalate",
    }
    wire_payload = c.to_dict("q1")
    assert wire_payload["type"] == "choice"
    assert wire_payload["criteria"] == {
        "proceed": "proceed",
        "retry": "retry",
        "escalate": "escalate",
    }


def test_choice_criteria_dict_preservation():
    """Passing a dictionary to Choice must be preserved as expected."""
    criteria = {"opt_a": "Option A description", "opt_b": "Option B description"}
    c = Choice("Choose an option", criteria)
    assert c.criteria == criteria
    assert c.to_dict("q2")["criteria"] == criteria


def test_score_criteria_dict_coercion():
    """Passing a dictionary to Score must auto-normalize to a list."""
    criteria = {"1": "low", "2": "medium", "3": "high"}
    s = Score("Rate severity", criteria)
    assert isinstance(s.criteria, list)
    assert s.criteria == ["low", "medium", "high"]


def test_score_criteria_list_preservation():
    """Passing a list to Score must be preserved."""
    levels = ["poor", "fair", "good", "excellent"]
    s = Score("Rate quality", levels)
    assert s.criteria == levels


def test_typesafe_response_handles_dict_answers():
    """TypeSafeResponse parses standard dictionary answers."""
    data = {
        "answers": {
            "q1": {"choice": "proceed", "confidence": 0.95},
            "q2": {"score": 3, "confidence": 0.8},
        }
    }
    resp = TypeSafeResponse(success=True, result=data)
    assert resp.value == "proceed"
    assert resp.confidence == 0.95
    assert len(resp.answers) == 2


def test_typesafe_response_handles_array_answers_without_crash():
    """TypeSafeResponse parses array (list) answers without raising AttributeError."""
    data = {
        "answers": [
            {"choice": "auto_approve", "confidence": 0.99},
            {"score": 5, "confidence": 0.9},
        ]
    }
    resp = TypeSafeResponse(success=True, result=data)
    # Must NOT crash with 'list' object has no attribute 'values'
    assert resp.value == "auto_approve"
    assert resp.confidence == 0.99
    assert "ans_0" in resp.answers
    assert "ans_1" in resp.answers


def test_typesafe_response_handles_scalar_and_malformed_answers():
    """Defensively handles scalar or non-dict items in answers."""
    data = {
        "answers": ["yes", "approved"]
    }
    resp = TypeSafeResponse(success=True, result=data)
    assert resp.value == "yes"
