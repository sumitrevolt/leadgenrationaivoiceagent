"""Sales Autopilot — admin observability API + handoff adapters."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.platform.sales_autopilot import handoff as handoff
from app.platform.sales_autopilot import policy as policy_mod
from app.platform.sales_autopilot import store as store


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_PROSPECTS_FILE", str(tmp_path / "prospects.json"))
    monkeypatch.setattr(store, "_ATTEMPTS_FILE", str(tmp_path / "attempts.jsonl"))
    monkeypatch.setattr(policy_mod, "_POLICY_DIR", str(tmp_path))
    monkeypatch.setattr(policy_mod, "_POLICY_FILE", str(tmp_path / "policy.json"))
    monkeypatch.delenv("SALES_AUTOPILOT_ENABLED", raising=False)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def test_summary_default_off_calling_hard_off(client):
    r = client.get("/api/sales-autopilot/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is False
    assert data["dry_run"] is True
    assert data["calling"] == "HARD_OFF"
    assert data["channels"]["whatsapp_enabled"] is False


def test_seed_estique_endpoint(client):
    r = client.post("/api/sales-autopilot/seed-estique")
    assert r.status_code == 200
    assert r.json()["prospect"]["status"] == store.STATUS_MANUAL_OWNER_CONFIRMED


def test_eligibility_preview_estique_blocked(client):
    client.post("/api/sales-autopilot/seed-estique")
    # engine still off ⇒ engine_disabled, but the endpoint responds structurally.
    body = {"prospect_id": store.ESTIQUE_ID, "channel": "whatsapp", "step": "initial"}
    r = client.post("/api/sales-autopilot/eligibility/preview", json=body)
    assert r.status_code == 200
    assert "eligibility" in r.json()


def test_run_canary_is_dry_run(client, monkeypatch):
    # Even with engine armed, run-canary forces dry-run for a single prospect.
    monkeypatch.setenv("SALES_AUTOPILOT_ENABLED", "1")
    store.upsert_prospect(
        {
            "id": "c1",
            "phone": "+919812345678",
            "niche": "beauty_makeover",
            "consent_basis": "inquiry",
            "status": store.STATUS_NEW,
        }
    )
    r = client.post("/api/sales-autopilot/run-canary", json={"prospect_id": "c1"})
    assert r.status_code == 200
    res = r.json()["result"]
    # SIMULATED (forced dry-run) or BLOCKED (outside hours) — never SENT.
    assert res["outcome"] in ("SIMULATED", "BLOCKED")


def test_inbound_classify_endpoint(client):
    r = client.post("/api/sales-autopilot/inbound/classify", json={"text": "STOP"})
    assert r.status_code == 200
    assert r.json()["category"] == "OPT_OUT"


# ---- handoff adapters -------------------------------------------- #
def test_payment_reminder_blocked_by_kill(monkeypatch):
    policy_mod.save_policy({"kill_switches": {"payment_reminders": True}})
    monkeypatch.setenv("SALES_AUTOPILOT_PAYMENT_REMINDER_KILL", "1")
    out = handoff.payment_reminder("c1")
    assert out["action"] == "blocked"


def test_payment_reminder_records_intent():
    out = handoff.payment_reminder("c2")
    assert out["action"] == "handoff_recorded"
    assert out["target_path"] == "/start"


def test_to_onboarding_marks_converted():
    store.upsert_prospect({"id": "c3", "status": store.STATUS_CONTACTED})
    out = handoff.to_onboarding("c3", client_id="client-9")
    assert out["action"] == "handoff_recorded"
    assert store.get_prospect("c3")["status"] == store.STATUS_CONVERTED


def test_first_value_handoff():
    out = handoff.first_value("c4")
    assert out["action"] == "handoff_recorded"
    assert "seed_first_week" in out["target"]
