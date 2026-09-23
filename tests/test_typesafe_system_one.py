"""Unit tests for TypeSafe System One API integration (app/platform/typesafe_integration.py).

Verifies:
- TypeSafeClient initialization and INERT state when no API key
- System One question serialization: Choice, Noul, Score
- Score criteria list vs dict normalization
- Response parsing for choice, noul, and score values
- Error handling and HTTP fallback behavior
"""

from unittest.mock import MagicMock, patch

import pytest

from app.platform.typesafe_integration import (
    Choice,
    Noul,
    Score,
    TypeSafeClient,
    TypeSafeResponse,
    typesafe_choice,
    typesafe_noul,
    typesafe_score,
    typesafe_system_one,
)


def test_inert_client_when_no_api_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("TYPEsafe_API_KEY", raising=False)

    client = TypeSafeClient(api_key="")
    resp = client.initialize()
    assert resp.success is False
    assert "INERT" in (resp.error or "")
    assert client.enabled is False

    call_resp = client.system_one({"query": "test"}, {"q": Noul("Is this a test?")})
    assert call_resp.success is False
    assert "INERT" in (call_resp.error or "")


def test_question_serialization():
    choice = Choice("Pick an option", criteria={"a": "Option A", "b": "Option B"})
    c_dict = choice.to_dict("choice_q")
    assert c_dict["type"] == "choice"
    assert c_dict["instructions"] == "Pick an option"
    assert c_dict["criteria"] == {"a": "Option A", "b": "Option B"}

    noul = Noul("Is this valid?")
    n_dict = noul.to_dict("noul_q")
    assert n_dict["type"] == "noul"
    assert n_dict["instructions"] == "Is this valid?"

    score = Score("Rate relevance", criteria=["low", "medium", "high"])
    s_dict = score.to_dict("score_q")
    assert s_dict["type"] == "score"
    assert s_dict["instructions"] == "Rate relevance"
    assert s_dict["criteria"] == ["low", "medium", "high"]


def test_score_dict_to_list_normalization():
    score = Score("Rate relevance", criteria={"1": "low", "2": "high"})
    client = TypeSafeClient(api_key="test-key")
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "model": "jev-latest",
            "answers": {"q": {"score": 2.5, "confidence": 0.85}},
        }
        mock_post.return_value = mock_resp

        resp = client.score("Rate relevance", {"state": "sample"}, {"1": "low", "2": "high"})
        assert resp.success is True
        assert resp.value == 2.5
        assert resp.confidence == 0.85

        # Check posted payload structure
        payload = mock_post.call_args[1]["json"]
        assert payload["model"] == "jev-latest"
        assert payload["questions"]["q"]["criteria"] == ["low", "high"]


def test_typesafe_response_parsing():
    # Choice parsing
    r_choice = TypeSafeResponse(
        success=True,
        result={"answers": {"ans1": {"choice": "option_a", "confidence": 0.92}}},
    )
    assert r_choice.value == "option_a"
    assert r_choice.confidence == 0.92

    # Noul parsing (noul field carries probability, no explicit confidence)
    r_noul = TypeSafeResponse(
        success=True,
        result={"answers": {"ans1": {"noul": 0.88}}},
    )
    assert r_noul.value == 0.88
    assert r_noul.confidence == 0.88

    # Out-of-range / malformed answers clamp or report honestly, never crash
    r_oob = TypeSafeResponse(
        success=True,
        result={"answers": {"q": {"score": 1.02, "confidence": 1.5}}},
    )
    assert r_oob.value == 1.0, f"1.02 should clamp to 1.0, got {r_oob.value}"
    assert r_oob.confidence == 1.0, f"1.5 should clamp to 1.0, got {r_oob.confidence}"
    assert r_oob.score == 1.0, f"1.02 should clamp to 1.0 (score prop), got {r_oob.score}"

    # High out-of-range score (2.4 from real production judgment) also clamps
    r_high = TypeSafeResponse(
        success=True,
        result={"answers": {"q": {"score": 2.4, "confidence": 0.0}}},
    )
    assert r_high.score == 1.0, f"2.4 should clamp to 1.0 (score prop), got {r_high.score}"

    # Normal score passes through
    r_ok = TypeSafeResponse(
        success=True,
        result={"answers": {"q": {"score": 0.74, "confidence": 0.85}}},
    )
    assert r_ok.score == 0.74, f"0.74 should pass through, got {r_ok.score}"

    # Empty/error parsing
    r_err = TypeSafeResponse(success=False, error="timeout")
    assert r_err.value is None
    assert r_err.confidence == 0.5
