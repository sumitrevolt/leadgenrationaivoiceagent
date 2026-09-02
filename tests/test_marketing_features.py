"""Tests for new marketing features (review automation, email drips, appointment reminders, customer health)."""

from __future__ import annotations

import pytest

# ─── Review Automation ──────────────────────────────────────────────


class TestReviewAutomation:
    def test_import(self):
        from app.marketing.review_automation import start_review_sequence

        assert callable(start_review_sequence)

    def test_daily_cap(self):
        from app.marketing.review_automation import _DAILY_CAP

        assert _DAILY_CAP > 0
        assert _DAILY_CAP <= 20  # ban-safety

    def test_sequence_steps_defined(self):
        from app.marketing.review_automation import SEQUENCE_STEPS

        assert len(SEQUENCE_STEPS) >= 3
        steps = [s["step"] for s in SEQUENCE_STEPS]
        assert "initial_request" in steps
        assert "private_feedback" in steps

    def test_list_sequences_empty(self, tmp_path, monkeypatch):
        from app.marketing import review_automation

        monkeypatch.setattr(review_automation, "_STORE", str(tmp_path / "test.jsonl"))
        result = review_automation.list_sequences("test_client")
        assert result == []

    def test_stats_empty(self, tmp_path, monkeypatch):
        from app.marketing import review_automation

        monkeypatch.setattr(review_automation, "_STORE", str(tmp_path / "test.jsonl"))
        stats = review_automation.get_sequence_stats("test_client")
        assert stats["total_sequences"] == 0
        assert stats["sent"] == 0
        assert stats["conversion_rate"] == 0

    @pytest.mark.asyncio
    async def test_start_sequence_no_phone(self, tmp_path, monkeypatch):
        from app.marketing import review_automation

        monkeypatch.setattr(review_automation, "_STORE", str(tmp_path / "test.jsonl"))
        result = await review_automation.start_review_sequence(
            client_id="c1",
            business_name="Sharma Salon",
            customer_name="Ravi",
        )
        assert result["ok"] is True
        assert result["review_type"] == "google"
        assert result["step"] == "initial_request"

    @pytest.mark.asyncio
    async def test_start_sequence_unhappy_customer(self, tmp_path, monkeypatch):
        from app.marketing import review_automation

        monkeypatch.setattr(review_automation, "_STORE", str(tmp_path / "test.jsonl"))
        result = await review_automation.start_review_sequence(
            client_id="c1",
            business_name="Test Biz",
            sentiment_score=2,
        )
        assert result["ok"] is True
        assert result["review_type"] == "private"

    @pytest.mark.asyncio
    async def test_handle_reply_positive(self, tmp_path, monkeypatch):
        from app.marketing import review_automation

        store = str(tmp_path / "test.jsonl")
        monkeypatch.setattr(review_automation, "_STORE", store)
        # Create a sequence first so handle_reply can find it
        await review_automation.start_review_sequence(
            client_id="c1", business_name="Test", customer_name="Ravi"
        )
        seqs = review_automation.list_sequences("c1")
        seq_id = seqs[0]["sequence_id"]
        result = await review_automation.handle_reply(seq_id, "Bahut achha hai!")
        assert result["ok"] is True
        assert result["reply_sentiment"] >= 4


# ─── Email Drips ───────────────────────────────────────────────────


class TestEmailDrips:
    def test_import(self):
        from app.marketing.email_drips import create_drip

        assert callable(create_drip)

    def test_templates_exist(self):
        from app.marketing.email_drips import get_templates

        templates = get_templates()
        assert len(templates) >= 3
        ids = [t["id"] for t in templates]
        assert "welcome_5day" in ids
        assert "winback_3step" in ids

    def test_list_drips_empty(self, tmp_path, monkeypatch):
        from app.marketing import email_drips

        monkeypatch.setattr(email_drips, "_DRIPS_STORE", str(tmp_path / "drips.jsonl"))
        monkeypatch.setattr(email_drips, "_RUNS_STORE", str(tmp_path / "runs.jsonl"))
        result = email_drips.list_drips("test_client")
        assert result == []

    def test_stats_empty(self, tmp_path, monkeypatch):
        from app.marketing import email_drips

        monkeypatch.setattr(email_drips, "_DRIPS_STORE", str(tmp_path / "drips.jsonl"))
        monkeypatch.setattr(email_drips, "_RUNS_STORE", str(tmp_path / "runs.jsonl"))
        stats = email_drips.get_drip_stats("test_client")
        assert stats["total_drips"] == 0
        assert stats["open_rate"] == 0

    @pytest.mark.asyncio
    async def test_create_drip(self, tmp_path, monkeypatch):
        from app.marketing import email_drips

        monkeypatch.setattr(email_drips, "_DRIPS_STORE", str(tmp_path / "drips.jsonl"))
        monkeypatch.setattr(email_drips, "_RUNS_STORE", str(tmp_path / "runs.jsonl"))
        result = await email_drips.create_drip(
            client_id="c1",
            name="Test Drip",
            steps=[
                {"delay_hours": 0, "subject": "Hello", "body": "Welcome!"},
                {"delay_hours": 24, "subject": "Follow up", "body": "How are you?"},
            ],
        )
        assert result["ok"] is True
        assert result["total_steps"] == 2

    @pytest.mark.asyncio
    async def test_start_drip_not_found(self, tmp_path, monkeypatch):
        from app.marketing import email_drips

        monkeypatch.setattr(email_drips, "_DRIPS_STORE", str(tmp_path / "drips.jsonl"))
        monkeypatch.setattr(email_drips, "_RUNS_STORE", str(tmp_path / "runs.jsonl"))
        result = await email_drips.start_drip_for_customer(
            drip_id="nonexistent",
            client_id="c1",
            customer_email="test@test.com",
        )
        assert result["ok"] is False


# ─── Appointment Reminders ─────────────────────────────────────────


class TestAppointmentReminders:
    def test_import(self):
        from app.marketing.appointment_reminders import schedule_reminders

        assert callable(schedule_reminders)

    def test_templates_defined(self):
        from app.marketing.appointment_reminders import TEMPLATES

        assert "24h_before" in TEMPLATES
        assert "1h_before" in TEMPLATES
        assert "post_appointment" in TEMPLATES
        assert "no_show_recovery" in TEMPLATES

    def test_list_empty(self, tmp_path, monkeypatch):
        from app.marketing import appointment_reminders

        monkeypatch.setattr(appointment_reminders, "_STORE", str(tmp_path / "test.jsonl"))
        result = appointment_reminders.list_reminders("c1")
        assert result == []

    def test_stats_empty(self, tmp_path, monkeypatch):
        from app.marketing import appointment_reminders

        monkeypatch.setattr(appointment_reminders, "_STORE", str(tmp_path / "test.jsonl"))
        stats = appointment_reminders.get_reminder_stats("c1")
        assert stats["total_reminders"] == 0

    @pytest.mark.asyncio
    async def test_schedule_reminders(self, tmp_path, monkeypatch):
        from datetime import datetime, timedelta, timezone

        from app.marketing import appointment_reminders

        monkeypatch.setattr(appointment_reminders, "_STORE", str(tmp_path / "test.jsonl"))
        future = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
        result = await appointment_reminders.schedule_reminders(
            client_id="c1",
            business_name="Test Biz",
            customer_name="Ravi",
            customer_phone="919876543210",
            appointment_time=future,
        )
        assert result["ok"] is True
        assert result["reminders_scheduled"] >= 2


# ─── Customer Health ───────────────────────────────────────────────


class TestCustomerHealth:
    def test_import(self):
        from app.marketing.customer_health import calculate_health_score

        assert callable(calculate_health_score)

    def test_weights_sum_to_100(self):
        from app.marketing.customer_health import WEIGHTS

        assert sum(WEIGHTS.values()) == 100

    def test_healthy_customer(self):
        from app.marketing.customer_health import calculate_health_score

        result = calculate_health_score(
            "c1",
            engagement_data={
                "dashboard_logins_30d": 10,
                "content_approvals_30d": 8,
                "last_login_days_ago": 1,
            },
            usage_data={"posts_created_30d": 15, "leads_handled_30d": 20, "features_used": 5},
            payment_data={"subscription_status": "active", "on_time_payments_pct": 100},
            satisfaction_data={"nps_score": 9, "support_tickets_open": 0, "review_sentiment": 5},
            growth_data={
                "leads_trend": "up",
                "content_performance": "up",
                "month_over_month_growth": 15,
            },
        )
        assert result["total_score"] >= 70
        assert result["classification"] == "healthy"

    def test_critical_customer(self):
        from app.marketing.customer_health import calculate_health_score

        result = calculate_health_score(
            "c1",
            engagement_data={"dashboard_logins_30d": 0, "last_login_days_ago": 30},
            usage_data={"posts_created_30d": 0},
            payment_data={"subscription_status": "cancelled"},
            satisfaction_data={"nps_score": 1, "support_tickets_open": 5},
            growth_data={"leads_trend": "down"},
        )
        assert result["total_score"] < 40
        assert result["classification"] == "critical"

    def test_at_risk_customer(self):
        from app.marketing.customer_health import calculate_health_score

        result = calculate_health_score(
            "c1",
            engagement_data={"dashboard_logins_30d": 3, "last_login_days_ago": 10},
            usage_data={"posts_created_30d": 2},
            payment_data={"subscription_status": "active"},
            satisfaction_data={"nps_score": 5},
            growth_data={"leads_trend": "flat"},
        )
        assert 40 <= result["total_score"] < 70
        assert result["classification"] == "at_risk"

    def test_health_summary_empty(self, tmp_path, monkeypatch):
        from app.marketing import customer_health

        monkeypatch.setattr(customer_health, "_STORE", str(tmp_path / "test.jsonl"))
        summary = customer_health.get_health_summary()
        assert summary["total_clients"] == 0

    @pytest.mark.asyncio
    async def test_record_health(self, tmp_path, monkeypatch):
        from app.marketing import customer_health

        monkeypatch.setattr(customer_health, "_STORE", str(tmp_path / "test.jsonl"))
        result = await customer_health.record_health(
            client_id="c1",
            engagement_data={"dashboard_logins_30d": 5},
            payment_data={"subscription_status": "active"},
        )
        assert "total_score" in result
        assert "classification" in result
        assert result["client_id"] == "c1"


# ─── API Endpoints ─────────────────────────────────────────────────


class TestMarketingFeaturesAPI:
    def test_router_import(self):
        from app.api.marketing_features import router

        assert router.prefix == "/api/marketing-features"

    def test_router_has_routes(self):
        from app.api.marketing_features import router

        route_paths = [r.path for r in router.routes]
        assert any("review-automation/start" in p for p in route_paths)
        assert any("email-drips/create" in p for p in route_paths)
        assert any("appointments/schedule" in p for p in route_paths)
        assert any("health/score" in p for p in route_paths)
        assert any("forms/templates" in p for p in route_paths)
        assert any("proposals/templates" in p for p in route_paths)

    def test_form_and_proposal_routes_are_inert_when_flag_off(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.auth_deps import require_admin
        from app.api.marketing_features import router

        monkeypatch.delenv("FORM_BUILDER", raising=False)
        monkeypatch.delenv("PROPOSAL_BUILDER", raising=False)
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_admin] = lambda: "admin"
        client = TestClient(app)
        assert client.get("/api/marketing-features/forms/templates").status_code == 503
        assert client.get("/api/marketing-features/proposals/templates").status_code == 503

    def test_form_templates_open_when_flag_on(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.auth_deps import require_admin
        from app.api.marketing_features import router

        monkeypatch.setenv("FORM_BUILDER", "1")
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_admin] = lambda: "admin"
        client = TestClient(app)
        r = client.get("/api/marketing-features/forms/templates")
        assert r.status_code == 200
        assert "templates" in r.json()


# ─── Form/Survey Builder ──────────────────────────────────────────


class TestFormBuilder:
    def test_import(self):
        from app.marketing.form_builder import create_form

        assert callable(create_form)

    def test_templates_exist(self):
        from app.marketing.form_builder import get_templates

        templates = get_templates()
        assert len(templates) >= 3
        ids = [t["id"] for t in templates]
        assert "contact_us" in ids
        assert "lead_qualification" in ids

    def test_field_types(self):
        from app.marketing.form_builder import FIELD_TYPES

        assert "text" in FIELD_TYPES
        assert "email" in FIELD_TYPES
        assert "phone" in FIELD_TYPES
        assert "rating" in FIELD_TYPES

    def test_list_forms_empty(self, tmp_path, monkeypatch):
        from app.marketing import form_builder

        monkeypatch.setattr(form_builder, "_FORMS_STORE", str(tmp_path / "forms.jsonl"))
        monkeypatch.setattr(form_builder, "_RESPONSES_STORE", str(tmp_path / "responses.jsonl"))
        result = form_builder.list_forms("c1")
        assert result == []

    def test_stats_empty(self, tmp_path, monkeypatch):
        from app.marketing import form_builder

        monkeypatch.setattr(form_builder, "_FORMS_STORE", str(tmp_path / "forms.jsonl"))
        monkeypatch.setattr(form_builder, "_RESPONSES_STORE", str(tmp_path / "responses.jsonl"))
        stats = form_builder.get_form_stats("c1")
        assert stats["total_forms"] == 0

    @pytest.mark.asyncio
    async def test_create_form(self, tmp_path, monkeypatch):
        from app.marketing import form_builder

        monkeypatch.setattr(form_builder, "_FORMS_STORE", str(tmp_path / "forms.jsonl"))
        monkeypatch.setattr(form_builder, "_RESPONSES_STORE", str(tmp_path / "responses.jsonl"))
        result = await form_builder.create_form(
            client_id="c1",
            name="Test Form",
            steps=[
                {
                    "title": "Step 1",
                    "fields": [{"id": "name", "type": "text", "label": "Name", "required": True}],
                }
            ],
        )
        assert result["ok"] is True
        assert result["total_fields"] == 1

    @pytest.mark.asyncio
    async def test_create_from_template(self, tmp_path, monkeypatch):
        from app.marketing import form_builder

        monkeypatch.setattr(form_builder, "_FORMS_STORE", str(tmp_path / "forms.jsonl"))
        monkeypatch.setattr(form_builder, "_RESPONSES_STORE", str(tmp_path / "responses.jsonl"))
        result = await form_builder.create_from_template("c1", "contact_us")
        assert result["ok"] is True
        assert result["total_steps"] >= 2

    @pytest.mark.asyncio
    async def test_submit_response(self, tmp_path, monkeypatch):
        from app.marketing import form_builder

        monkeypatch.setattr(form_builder, "_FORMS_STORE", str(tmp_path / "forms.jsonl"))
        monkeypatch.setattr(form_builder, "_RESPONSES_STORE", str(tmp_path / "responses.jsonl"))
        create_result = await form_builder.create_form(
            client_id="c1",
            name="Test",
            steps=[{"title": "S1", "fields": [{"id": "q1", "type": "text"}]}],
        )
        result = await form_builder.submit_response(
            form_id=create_result["form_id"],
            client_id="c1",
            answers={"q1": "Answer"},
            submitter_name="Ravi",
        )
        assert result["ok"] is True
        assert result["answers_count"] == 1


# ─── Proposal/Quote Builder ───────────────────────────────────────


class TestProposalBuilder:
    def test_import(self):
        from app.marketing.proposal_builder import generate_proposal

        assert callable(generate_proposal)

    def test_templates_exist(self):
        from app.marketing.proposal_builder import get_templates

        templates = get_templates()
        assert len(templates) >= 3
        ids = [t["id"] for t in templates]
        assert "marketing_starter" in ids
        assert "marketing_advanced" in ids
        assert "voice_only" in ids

    def test_list_proposals_empty(self, tmp_path, monkeypatch):
        from app.marketing import proposal_builder

        monkeypatch.setattr(proposal_builder, "_STORE", str(tmp_path / "proposals.jsonl"))
        result = proposal_builder.list_proposals("c1")
        assert result == []

    def test_stats_empty(self, tmp_path, monkeypatch):
        from app.marketing import proposal_builder

        monkeypatch.setattr(proposal_builder, "_STORE", str(tmp_path / "proposals.jsonl"))
        stats = proposal_builder.get_proposal_stats("c1")
        assert stats["total_proposals"] == 0

    @pytest.mark.asyncio
    async def test_generate_proposal(self, tmp_path, monkeypatch):
        from app.marketing import proposal_builder

        monkeypatch.setattr(proposal_builder, "_STORE", str(tmp_path / "proposals.jsonl"))
        result = await proposal_builder.generate_proposal(
            client_id="c1",
            business_name="Sharma Salon",
            client_name="Ravi",
            template_id="marketing_starter",
        )
        assert result["ok"] is True
        assert result["total_sections"] >= 4
        assert result["status"] == "draft"

    @pytest.mark.asyncio
    async def test_update_proposal_status(self, tmp_path, monkeypatch):
        from app.marketing import proposal_builder

        monkeypatch.setattr(proposal_builder, "_STORE", str(tmp_path / "proposals.jsonl"))
        gen = await proposal_builder.generate_proposal(
            client_id="c1",
            business_name="Test",
            client_name="Ravi",
        )
        result = await proposal_builder.update_proposal_status(gen["proposal_id"], "sent")
        assert result["ok"] is True
        assert result["status"] == "sent"

    @pytest.mark.asyncio
    async def test_invalid_status(self, tmp_path, monkeypatch):
        from app.marketing import proposal_builder

        monkeypatch.setattr(proposal_builder, "_STORE", str(tmp_path / "proposals.jsonl"))
        result = await proposal_builder.update_proposal_status("fake", "invalid_status")
        assert result["ok"] is False

    def test_render_html(self):
        from app.marketing.proposal_builder import render_proposal_html

        html = render_proposal_html(
            {
                "business_name": "Sharma Salon",
                "client_name": "Ravi",
                "created_at": "2026-08-16T00:00:00",
                "valid_until": "2026-09-16T00:00:00",
                "sections": [{"title": "Test", "content": "Hello World"}],
            }
        )
        assert "Sharma Salon" in html
        assert "Hello World" in html
        assert "<html" in html
