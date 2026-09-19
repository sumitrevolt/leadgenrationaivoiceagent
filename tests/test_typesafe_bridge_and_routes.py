"""Tests for TypeSafe Bridge, Schemas, and Dedicated REST Routes (2026-09-19).

Verifies end-to-end type safety:
- Pydantic v2 schema validations (strict enum adherence, boundary checks)
- TypeSafeBridge coordination layer (connecting leads, QA, triage, calls)
- FastAPI route contract tests for /api/v1/typesafe/*
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.auth_deps import require_admin
from app.main import app
from app.platform.typesafe_bridge import TypeSafeBridge, get_typesafe_bridge
from app.platform.typesafe_integration import TypeSafeResponse
from app.platform.typesafe_schemas import (
    CallDispositionEnum,
    CallEvaluationRequest,
    CallEvaluationResponse,
    ContentAuditRequest,
    ContentAuditResponse,
    FitLevelEnum,
    LeadQualifyRequest,
    LeadQualifyResponse,
    ProductOfferingEnum,
    ReplyIntentEnum,
    ReplyTriageRequest,
    ReplyTriageResponse,
    TypeSafeSystemStatusResponse,
    ValueExtractionRequest,
    ValueExtractionResponse,
)


@pytest.fixture
def bridge():
    return TypeSafeBridge()


class TestTypeSafeSchemasAndBridge:
    def test_qualify_lead_schema_and_bridge(self, bridge):
        req = LeadQualifyRequest(
            name="Apex Dental Clinic",
            niche="dental",
            city="Bengaluru",
            phone="9876543210",
            website="https://apexdental.in",
            notes="Looking for patient appointment automated telecalling",
        )
        assert req.name == "Apex Dental Clinic"
        assert req.niche == "dental"

        # Bridge call with fallback
        resp = bridge.qualify_lead(req)
        assert isinstance(resp, LeadQualifyResponse)
        assert resp.fit_level in (FitLevelEnum.LOW, FitLevelEnum.MEDIUM, FitLevelEnum.HIGH, FitLevelEnum.EXCEPTIONAL)
        assert resp.recommended_product in (
            ProductOfferingEnum.MARKETING_SUITE,
            ProductOfferingEnum.VOICE_AGENT,
            ProductOfferingEnum.COMBO,
            ProductOfferingEnum.UNQUALIFIED,
        )
        assert 0 <= resp.score <= 100

    def test_content_audit_schema_and_bridge(self, bridge):
        req = ContentAuditRequest(
            subject="Special Festival Offer for Clinics",
            body="Get 50 new patient leads this Diwali with zero upfront fee.",
            channel="email",
            recipient_email="doctor@apex.in",
        )
        resp = bridge.audit_outbound_content(req)
        assert isinstance(resp, ContentAuditResponse)
        assert isinstance(resp.approved, bool)
        assert resp.tone in ("professional", "friendly", "aggressive", "passive")

    def test_reply_triage_schema_and_bridge(self, bridge):
        req = ReplyTriageRequest(
            message_body="Can you please call me back tomorrow around 3 PM?",
            channel="whatsapp",
            lead_id="L-101",
        )
        resp = bridge.triage_reply(req)
        assert isinstance(resp, ReplyTriageResponse)
        assert resp.intent in (
            ReplyIntentEnum.DEMO_REQUEST,
            ReplyIntentEnum.PRICING_QUERY,
            ReplyIntentEnum.CALLBACK_REQUESTED,
            ReplyIntentEnum.QUESTION,
            ReplyIntentEnum.NOT_INTERESTED,
            ReplyIntentEnum.UNSUBSCRIBE,
            ReplyIntentEnum.OTHER,
        )

    def test_call_evaluation_schema_and_bridge(self, bridge):
        req = CallEvaluationRequest(
            transcript_or_summary="Owner said they are interested in the ₹1,999 marketing package. Send payment details.",
            call_duration_seconds=145,
            telephony_provider="tata_smartflo",
        )
        resp = bridge.evaluate_call(req)
        assert isinstance(resp, CallEvaluationResponse)
        assert resp.disposition in (
            CallDispositionEnum.HOT_LEAD,
            CallDispositionEnum.CALLBACK_SCHEDULED,
            CallDispositionEnum.FOLLOW_UP_NEEDED,
            CallDispositionEnum.NOT_INTERESTED,
            CallDispositionEnum.DND_REQUESTED,
        )

    def test_value_extraction_schema_and_bridge(self, bridge):
        req = ValueExtractionRequest(
            source_text="Our business operates strictly in Mumbai and Thane.",
            field_name="primary_city",
            candidates=["Delhi", "Mumbai", "Kolkata"],
        )
        resp = bridge.extract_value(req)
        assert isinstance(resp, ValueExtractionResponse)
        assert resp.field_name == "primary_city"


class TestTypeSafeRoutes:
    @pytest.fixture
    def client(self):
        # Override require_admin for testing endpoints
        app.dependency_overrides[require_admin] = lambda: {"user_id": "test-admin", "role": "admin"}
        yield TestClient(app)
        app.dependency_overrides.pop(require_admin, None)

    def test_status_endpoint(self, client):
        res = client.get("/api/v1/typesafe/status")
        assert res.status_code == 200
        data = res.json()
        assert "enabled" in data
        assert "credential_present" in data
        assert "model" in data
        assert data["services_ready"] is True

    def test_qualify_lead_route(self, client):
        payload = {
            "name": "Jiya Makeover Studio",
            "niche": "salon_makeup",
            "city": "Mumbai",
            "phone": "9876543210",
        }
        res = client.post("/api/v1/typesafe/qualify-lead", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "score" in data
        assert "fit_level" in data
        assert "pitch_angle" in data

    def test_audit_message_route(self, client):
        payload = {
            "subject": "Quick question regarding your Google rating",
            "body": "Hi, we noticed your rating has room for improvement. Can we help?",
            "channel": "email",
        }
        res = client.post("/api/v1/typesafe/audit-message", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "approved" in data
        assert "persuasion_score" in data

    def test_triage_reply_route(self, client):
        payload = {
            "message_body": "Interested! How much does it cost?",
            "channel": "email",
        }
        res = client.post("/api/v1/typesafe/triage-reply", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "intent" in data
        assert "suggested_action" in data

    def test_evaluate_call_route(self, client):
        payload = {
            "transcript_or_summary": "Customer confirmed booking appointment for Saturday 11 AM.",
            "call_duration_seconds": 180,
            "telephony_provider": "tata_smartflo",
        }
        res = client.post("/api/v1/typesafe/evaluate-call", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "disposition" in data
        assert "explicit_consent_given" in data

    def test_extract_value_route(self, client):
        payload = {
            "source_text": "We are looking for the ₹5,999 combo plan.",
            "field_name": "requested_plan",
            "candidates": ["₹1,999 Starter", "₹4,999 Voice", "₹5,999 Combo"],
        }
        res = client.post("/api/v1/typesafe/extract-value", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "field_name" in data
