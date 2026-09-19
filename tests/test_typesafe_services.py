"""Tests for TypeSafe Platform Services Suite (2026-09-19).

Verifies all 5 operational patterns:
1. Composite Lead Qualification (Score + Noul + Choice)
2. Pre-flight Content QA & Compliance Guardrail (Noul + Score + Choice)
3. Inbound Reply Triage (Choice + Noul + Score)
4. Candidate Value Extraction ("Select Instead of Generate")
5. Post-Call Telephony Disposition (Choice + Noul + Score)
6. Fail-safe degradation on Inert / offline states
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.platform.lead_scoring import score_lead_typesafe
from app.platform.typesafe_integration import TypeSafeClient, TypeSafeResponse
from app.platform.typesafe_services import (
    CallDispositionResult,
    ContentQAResult,
    LeadQualificationResult,
    ReplyTriageResult,
    TypeSafeCallEvaluator,
    TypeSafeContentQA,
    TypeSafeLeadScorer,
    TypeSafeReplyTriage,
    TypeSafeValueExtractor,
)


class TestTypeSafeLeadScorer:
    def test_lead_scorer_mock_success(self):
        client = MagicMock(spec=TypeSafeClient)
        client.enabled = True
        client.system_one.return_value = TypeSafeResponse(
            success=True,
            model="jev-latest",
            latency_sec=0.12,
            result={
                "answers": {
                    "fit": {"score": 3, "confidence": 0.9},
                    "intent": {"noul": 0.85, "confidence": 0.85},
                    "budget": {"score": 2, "confidence": 0.8},
                    "product": {"choice": "combo", "confidence": 0.95},
                }
            },
        )

        scorer = TypeSafeLeadScorer(client=client)
        res = scorer.qualify_lead({"name": "Dr. Sharma Dental", "niche": "dental", "city": "Mumbai"})

        assert isinstance(res, LeadQualificationResult)
        assert res.fit_level == "exceptional"
        assert res.buying_intent is True
        assert res.recommended_product == "combo"
        assert res.budget_likelihood == "standard"
        assert res.is_hot_lead is True
        assert res.score >= 75

    def test_lead_scorer_inert_fallback(self):
        client = MagicMock(spec=TypeSafeClient)
        client.enabled = False
        client.system_one.return_value = TypeSafeResponse(success=False, error="INERT")

        scorer = TypeSafeLeadScorer(client=client)
        res = scorer.qualify_lead({"name": "Kirana Store", "niche": "general"})

        assert isinstance(res, LeadQualificationResult)
        assert res.fit_level == "medium"
        assert res.buying_intent is False
        assert res.recommended_product == "marketing_suite"

    def test_score_lead_typesafe_integration(self):
        with patch("app.platform.lead_scoring.score_lead", return_value=60):
            res = score_lead_typesafe({"name": "Jiya Makeover", "phone": "9876543210"})
            assert "base_score" in res
            assert "composite_score" in res
            assert "is_hot_lead" in res


class TestTypeSafeContentQA:
    def test_content_qa_approved(self):
        client = MagicMock(spec=TypeSafeClient)
        client.enabled = True
        client.system_one.return_value = TypeSafeResponse(
            success=True,
            model="jev-latest",
            latency_sec=0.15,
            result={
                "answers": {
                    "spam": {"noul": 0.05},
                    "compliance": {"noul": 0.02},
                    "persuasion": {"score": 2},
                    "tone": {"choice": "professional"},
                }
            },
        )

        qa = TypeSafeContentQA(client=client)
        res = qa.audit_outbound_message(
            subject="Grow your clinic bookings",
            body="Hi, we help local dental clinics automate patient review collection.",
        )

        assert isinstance(res, ContentQAResult)
        assert res.approved is True
        assert res.is_spammy is False
        assert res.compliance_violation is False
        assert res.tone == "professional"
        assert res.persuasion_score == "strong"

    def test_content_qa_blocks_compliance_violation(self):
        client = MagicMock(spec=TypeSafeClient)
        client.enabled = True
        client.system_one.return_value = TypeSafeResponse(
            success=True,
            model="jev-latest",
            latency_sec=0.15,
            result={
                "answers": {
                    "spam": {"noul": 0.1},
                    "compliance": {"noul": 0.85},
                    "persuasion": {"score": 1},
                    "tone": {"choice": "aggressive"},
                }
            },
        )

        qa = TypeSafeContentQA(client=client)
        res = qa.audit_outbound_message(
            subject="Guaranteed ₹10 Lakh Profit in 7 Days!",
            body="Pay now or your competitors will destroy your business.",
        )

        assert res.approved is False
        assert res.compliance_violation is True
        assert res.tone == "aggressive"
        assert len(res.reasons) >= 1


class TestTypeSafeReplyTriage:
    def test_triage_hot_demo_request(self):
        client = MagicMock(spec=TypeSafeClient)
        client.enabled = True
        client.system_one.return_value = TypeSafeResponse(
            success=True,
            model="jev-latest",
            latency_sec=0.10,
            result={
                "answers": {
                    "intent": {"choice": "demo_request"},
                    "is_hot": {"noul": 0.95},
                    "sentiment": {"choice": "positive"},
                    "urgency": {"score": 3},
                }
            },
        )

        triage = TypeSafeReplyTriage(client=client)
        res = triage.triage_reply("Yes! Can we see a demo today at 4 PM?")

        assert isinstance(res, ReplyTriageResult)
        assert res.intent == "demo_request"
        assert res.is_hot is True
        assert res.sentiment == "positive"
        assert res.urgency == "immediate"
        assert res.suggested_action == "schedule_call"

    def test_triage_unsubscribe_request(self):
        client = MagicMock(spec=TypeSafeClient)
        client.enabled = True
        client.system_one.return_value = TypeSafeResponse(
            success=True,
            model="jev-latest",
            latency_sec=0.10,
            result={
                "answers": {
                    "intent": {"choice": "unsubscribe"},
                    "is_hot": {"noul": 0.0},
                    "sentiment": {"choice": "negative"},
                    "urgency": {"score": 0},
                }
            },
        )

        triage = TypeSafeReplyTriage(client=client)
        res = triage.triage_reply("STOP emailing me. Remove from list.")

        assert res.intent == "unsubscribe"
        assert res.suggested_action == "suppress_dnd"


class TestTypeSafeValueExtractor:
    def test_extract_exact_candidate(self):
        client = MagicMock(spec=TypeSafeClient)
        client.enabled = True
        client.choice.return_value = TypeSafeResponse(
            success=True,
            result={"answers": {"q": {"choice": "opt_1"}}},
            latency_sec=0.08,
        )

        extractor = TypeSafeValueExtractor(client=client)
        selected = extractor.select_best_candidate(
            context_text="We have branches in Pune, Hyderabad, and Bangalore. Our HQ is Pune.",
            field_name="headquarters_city",
            candidates=["Hyderabad", "Pune", "Bangalore"],
        )

        assert selected == "Pune"

    def test_extract_single_candidate_instant(self):
        client = MagicMock(spec=TypeSafeClient)
        extractor = TypeSafeValueExtractor(client=client)
        selected = extractor.select_best_candidate("Text", "field", ["OnlyOption"])
        assert selected == "OnlyOption"
        client.choice.assert_not_called()


class TestTypeSafeCallEvaluator:
    def test_call_evaluation_callback_scheduled(self):
        client = MagicMock(spec=TypeSafeClient)
        client.enabled = True
        client.system_one.return_value = TypeSafeResponse(
            success=True,
            model="jev-latest",
            latency_sec=0.11,
            result={
                "answers": {
                    "disposition": {"choice": "callback_scheduled"},
                    "consent": {"noul": 0.88},
                    "warmth": {"score": 2},
                }
            },
        )

        evaluator = TypeSafeCallEvaluator(client=client)
        res = evaluator.evaluate_call(
            transcript_or_summary="Owner said he is driving right now, please call back tomorrow at 11 AM."
        )

        assert isinstance(res, CallDispositionResult)
        assert res.disposition == "callback_scheduled"
        assert res.explicit_consent_given is True
        assert res.lead_warmth == "warm"
        assert res.next_action == "schedule_calendar"
