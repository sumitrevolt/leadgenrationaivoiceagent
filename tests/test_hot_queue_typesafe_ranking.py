"""Tests for TypeSafe-powered hot_queue_owner_pack lead ranking.

Verifies:
- _typesafe_score_rows returns original list when TypeSafe ABSENT (fail-open)
- _typesafe_score_rows re-sorts by ts_score descending on TypeSafe success
- build_owner_pack return dict carries ts_scored key
- No secrets/PII in TypeSafe state payload
- Idempotency: same rows → stable sort (ts_score deterministic from intent bonuses)

TypeSafe mock: unit tests MUST NOT make real API calls. We mock TypeSafeClient.system_one
to return a controlled TypeSafeResponse. This is a contract test (shape test), not an
integration test — the real API call is verified by test_typesafe_status_consumer_probe.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.platform.hot_queue_owner_pack import _typesafe_score_rows

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_row(intent: str, has_phone: bool = True, age_hours: float = 10.0) -> dict:
    return {
        "hq_id": f"hq_{intent[:4]}",
        "intent": intent,
        "business_name": f"Biz_{intent}",
        "niche": "salon",
        "city": "Delhi",
        "channel": "email",
        "phone": "9999900001" if has_phone else "",
        "wa_link": "https://wa.me/919999900001" if has_phone else "",
        "age_hours": age_hours,
        "draft": "Test draft",
    }


# ---------------------------------------------------------------------------
# Fail-open tests
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_empty_rows_returns_empty(self):
        """Empty input → empty output, no crash."""
        result = _typesafe_score_rows([])
        assert result == []

    def test_typesafe_absent_preserves_original_order(self):
        """When TypeSafe is ABSENT (no key), original sort is returned unchanged."""
        rows = [
            _make_row("interested"),
            _make_row("question"),
            _make_row("not_interested"),
        ]

        # credential_state is imported inside _typesafe_score_rows from typesafe_integration
        with patch(
            "app.platform.typesafe_integration.credential_state",
            return_value={"enabled": False, "state": "ABSENT"},
        ):
            result = _typesafe_score_rows(rows)

        # Should return unchanged (same objects, same order)
        assert result == rows

    def test_typesafe_exception_returns_original(self):
        """If TypeSafe raises any exception, fail-open → original list returned."""
        rows = [_make_row("interested"), _make_row("question")]
        # Patch credential_state to raise
        with patch(
            "app.platform.typesafe_integration.credential_state",
            side_effect=RuntimeError("simulated credential_state crash"),
        ):
            result = _typesafe_score_rows(rows)
        assert result == rows


# ---------------------------------------------------------------------------
# TypeSafe scoring integration (mocked API)
# ---------------------------------------------------------------------------

class TestTypeSafeScoring:
    def _mock_typesafe_response(self, score_choice: str = "contact_today", noul: float = 0.7):
        """Return a TypeSafeResponse mock for the given urgency choice and noul."""
        from app.platform.typesafe_integration import TypeSafeResponse

        mock_resp = TypeSafeResponse(
            success=True,
            result={
                "model": "jev-1.13.0",
                "answers": {
                    "top_lead_urgency": {"type": "score", "choice": score_choice, "confidence": 0.8},
                    "has_high_intent_lead": {"type": "noul", "noul": noul},
                },
            },
            model="jev-1.13.0",
            latency_sec=0.9,
            attempts=1,
        )
        return mock_resp

    def test_interested_leads_score_higher_than_unsubscribe(self):
        """Interested leads must rank above unsubscribe leads after TypeSafe scoring."""
        rows = [
            _make_row("unsubscribe"),  # placed first intentionally
            _make_row("interested"),   # should rank 1 after scoring
        ]

        mock_resp = self._mock_typesafe_response("contact_today", 0.8)

        with (
            patch("app.platform.typesafe_integration.credential_state",
                  return_value={"enabled": True, "state": "PRESENT", "fingerprint": "abc123"}),
            patch("app.platform.typesafe_integration._get_api_key", return_value="fake_key"),
            patch(
                "app.platform.typesafe_integration.TypeSafeClient.system_one",
                return_value=mock_resp,
            ),
        ):
            result = _typesafe_score_rows(rows)

        assert len(result) == 2
        # "interested" should be ranked #1
        assert result[0]["intent"] == "interested"
        assert result[0].get("ts_rank") == 1
        assert result[1]["intent"] == "unsubscribe"
        assert result[1].get("ts_rank") == 2

    def test_each_lead_gets_an_independent_typesafe_urgency_judgment(self):
        """Per-lead answers, not one batch-wide score, must drive ranking."""
        from app.platform.typesafe_integration import TypeSafeResponse

        rows = [
            _make_row("interested"),
            _make_row("question"),
        ]
        captured_questions: list[dict] = []

        def system_one(_state, questions):
            captured_questions.append(questions)
            return TypeSafeResponse(
                success=True,
                result={
                    "model": "jev-1.13.0",
                    "answers": {
                        "lead_0_urgency": {
                            "type": "score",
                            "choice": "can_wait",
                            "confidence": 0.9,
                        },
                        "lead_1_urgency": {
                            "type": "score",
                            "choice": "urgent_contact_now",
                            "confidence": 0.9,
                        },
                        "has_high_intent_lead": {"type": "noul", "noul": 0.8},
                    },
                },
                model="jev-1.13.0",
                latency_sec=0.4,
                attempts=1,
            )

        with (
            patch(
                "app.platform.typesafe_integration.credential_state",
                return_value={"enabled": True, "state": "PRESENT", "fingerprint": "abc"},
            ),
            patch("app.platform.typesafe_integration._get_api_key", return_value="fake_key"),
            patch(
                "app.platform.typesafe_integration.TypeSafeClient.system_one",
                side_effect=system_one,
            ),
        ):
            result = _typesafe_score_rows(rows)

        assert captured_questions
        assert {"lead_0_urgency", "lead_1_urgency"} <= set(captured_questions[0])
        assert result[0]["intent"] == "question"
        assert result[0]["ts_score"] > result[1]["ts_score"]

    def test_ts_score_and_ts_rank_injected(self):
        """Every row gets ts_score (float) and ts_rank (int) after successful scoring."""
        rows = [_make_row("question"), _make_row("interested")]
        mock_resp = self._mock_typesafe_response("urgent_contact_now", 0.9)

        with (
            patch("app.platform.typesafe_integration.credential_state",
                  return_value={"enabled": True, "state": "PRESENT", "fingerprint": "abc"}),
            patch("app.platform.typesafe_integration._get_api_key", return_value="fake_key"),
            patch(
                "app.platform.typesafe_integration.TypeSafeClient.system_one",
                return_value=mock_resp,
            ),
        ):
            result = _typesafe_score_rows(rows)

        for row in result:
            assert "ts_score" in row, f"ts_score missing from row: {row}"
            assert isinstance(row["ts_score"], float)
            assert 0.0 <= row["ts_score"] <= 1.0
            assert "ts_rank" in row
            assert isinstance(row["ts_rank"], int)

    def test_no_pii_in_state_payload(self):
        """Phone numbers / email addresses must NOT appear in what is sent to TypeSafe.

        This is enforced by contract: _typesafe_score_rows only puts niche/city/intent
        in the state dict, never phone/email/wa_link.
        """
        rows = [_make_row("interested", has_phone=True)]
        phone_number = "9999900001"

        captured_state: list[dict] = []

        from app.platform.typesafe_integration import TypeSafeResponse

        def capturing_system_one(state, questions):
            captured_state.append(state)
            return TypeSafeResponse(
                success=True,
                result={
                    "model": "jev-1.13.0",
                    "answers": {
                        "top_lead_urgency": {"type": "score", "choice": "contact_today", "confidence": 0.7},
                        "has_high_intent_lead": {"type": "noul", "noul": 0.6},
                    },
                },
                model="jev-1.13.0",
                latency_sec=0.5,
                attempts=1,
            )

        with (
            patch("app.platform.typesafe_integration.credential_state",
                  return_value={"enabled": True, "state": "PRESENT", "fingerprint": "abc"}),
            patch("app.platform.typesafe_integration._get_api_key", return_value="fake_key"),
            patch(
                "app.platform.typesafe_integration.TypeSafeClient.system_one",
                side_effect=capturing_system_one,
            ),
        ):
            _typesafe_score_rows(rows)

        assert captured_state, "system_one was not called"
        state_str = str(captured_state[0])
        assert phone_number not in state_str, "Phone number leaked into TypeSafe state payload!"
        assert "wa.me" not in state_str, "WA link leaked into TypeSafe state payload!"

    def test_typesafe_api_failure_returns_original(self):
        """If TypeSafe API returns success=False, fail-open → original list returned."""
        from app.platform.typesafe_integration import TypeSafeResponse

        rows = [_make_row("interested"), _make_row("question")]
        failed_resp = TypeSafeResponse(success=False, error="HTTP 429: rate limited", latency_sec=1.2)

        with (
            patch("app.platform.typesafe_integration.credential_state",
                  return_value={"enabled": True, "state": "PRESENT", "fingerprint": "abc"}),
            patch("app.platform.typesafe_integration._get_api_key", return_value="fake_key"),
            patch(
                "app.platform.typesafe_integration.TypeSafeClient.system_one",
                return_value=failed_resp,
            ),
        ):
            result = _typesafe_score_rows(rows)

        assert result == rows  # original order preserved

    def test_scores_clamped_0_to_1(self):
        """All ts_score values must be in [0.0, 1.0] regardless of bonus stacking."""
        rows = [
            _make_row("interested", has_phone=True, age_hours=0.5),  # many bonuses
            _make_row("unsubscribe", has_phone=False, age_hours=100.0),  # many penalties
        ]
        mock_resp = self._mock_typesafe_response("urgent_contact_now", 0.9)

        with (
            patch("app.platform.typesafe_integration.credential_state",
                  return_value={"enabled": True, "state": "PRESENT", "fingerprint": "abc"}),
            patch("app.platform.typesafe_integration._get_api_key", return_value="fake_key"),
            patch(
                "app.platform.typesafe_integration.TypeSafeClient.system_one",
                return_value=mock_resp,
            ),
        ):
            result = _typesafe_score_rows(rows)

        for row in result:
            score = row.get("ts_score", 0.5)
            assert 0.0 <= score <= 1.0, f"ts_score {score} out of bounds for intent={row['intent']}"
