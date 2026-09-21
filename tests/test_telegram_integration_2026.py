"""
Telegram Bot & TypeSafe Integration Contract Tests (2026)
=========================================================
Verifies:
1. Token configuration & health
2. Owner authentication & allowlisting
3. Unauthorized access rejection
4. Duplicate update deduplication
5. Live orchestrator state retrieval (/status, /tasks, /agents)
6. Kill-switch toggle (/pause, /resume)
7. TypeSafe System One message classification (jev-latest)
8. TypeSafe 9-bot supervisory routing
9. TypeSafe response quality validation
10. End-to-end non-destructive agent task handoff
11. FastAPI REST API endpoints
"""

import os
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.integrations.telegram_bot import TelegramBot, get_telegram_bot
from app.integrations.telegram_typesafe import (
    TelegramBotCoordinator,
    TelegramIntentClassifier,
    TelegramResponseValidator,
)
from app.platform.automation_orchestrator import (
    AutomationOrchestrator,
    StructuredEvidence,
    TaskPriority,
    TaskStatus,
)
from app.platform.typesafe_integration import TypeSafeResponse


@pytest.fixture
def bot_instance(monkeypatch):
    """Create a fresh TelegramBot instance for testing."""
    monkeypatch.setenv("TELEGRAM_JARVIS_BOT_TOKEN", "123456789012345678901234567890")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789012345678901234567890")
    bot = TelegramBot()
    # Mock bot info for test isolation
    bot._bot_info = {"id": 8363810880, "username": "Sumits_jarvis_bot", "first_name": "Jarvis"}
    bot._initialized = True
    return bot


def test_telegram_bot_configuration(bot_instance):
    """Bot must be configured with a valid token."""
    info = bot_instance.get_info()
    assert info["configured"] is True
    assert info["initialized"] is True
    assert info["bot_username"] == "Sumits_jarvis_bot"
    assert "sumitrevolt" in info["owner_usernames"]


def test_owner_authentication(bot_instance):
    """Only allowlisted owners must be accepted."""
    assert bot_instance.is_owner(user_id=123, username="sumitrevolt") is True
    assert bot_instance.is_owner(user_id=123, username="@sumitrevolt") is True
    assert bot_instance.is_owner(user_id=456, username="random_user") is False
    assert bot_instance.is_owner(user_id=789, username="") is False


def test_unauthorized_chat_rejected(bot_instance):
    """Messages from non-owners must be rejected with unauthorized response."""
    update = {
        "update_id": 9001,
        "message": {
            "message_id": 9001,
            "text": "/status",
            "from": {"id": 8888, "username": "unknown_intruder"},
            "chat": {"id": 8888},
        },
    }
    res = bot_instance.process_update(update, send_reply=False)
    assert res.success is False
    assert res.is_owner is False
    assert res.error == "unauthorized"
    assert "Access Restricted" in res.response_text


def test_duplicate_update_protection(bot_instance):
    """Identical update_id or message_id must be suppressed on repeated delivery."""
    update = {
        "update_id": 9002,
        "message": {
            "message_id": 9002,
            "text": "/status",
            "from": {"id": 1234, "username": "sumitrevolt"},
            "chat": {"id": 1234},
        },
    }
    # First delivery
    res1 = bot_instance.process_update(update, send_reply=False)
    assert res1.success is True
    assert res1.deduplicated is False

    # Second delivery with same update_id
    res2 = bot_instance.process_update(update, send_reply=False)
    assert res2.success is True
    assert res2.deduplicated is True
    assert "Duplicate update ignored" in res2.response_text


def test_status_command_live_orchestrator(bot_instance):
    """The /status command must query real orchestrator state, not hardcoded strings."""
    update = {
        "update_id": 9003,
        "message": {
            "message_id": 9003,
            "text": "/status",
            "from": {"id": 1234, "username": "sumitrevolt"},
            "chat": {"id": 1234},
        },
    }
    res = bot_instance.process_update(update, send_reply=False)
    assert res.success is True
    assert res.intent == "status_check"
    assert "LeadGen AI Orchestrator Status" in res.response_text
    assert "9 Hermes bots active" in res.response_text
    assert "Specialist Workforce:" in res.response_text
    assert "31 agents registered" in res.response_text
    assert "Kill Switch (`AUTOMATION_STOP_NEW_CLAIMS`):" in res.response_text


def test_tasks_command(bot_instance):
    """The /tasks command must query tasks from the durable ledger."""
    update = {
        "update_id": 9004,
        "message": {
            "message_id": 9004,
            "text": "/tasks",
            "from": {"id": 1234, "username": "sumitrevolt"},
            "chat": {"id": 1234},
        },
    }
    res = bot_instance.process_update(update, send_reply=False)
    assert res.success is True
    assert res.intent == "task_query"
    assert "Recent Tasks" in res.response_text or "No tasks found" in res.response_text


def test_agents_command(bot_instance):
    """The /agents command must list the 31 specialist agents."""
    update = {
        "update_id": 9005,
        "message": {
            "message_id": 9005,
            "text": "/agents",
            "from": {"id": 1234, "username": "sumitrevolt"},
            "chat": {"id": 1234},
        },
    }
    res = bot_instance.process_update(update, send_reply=False)
    assert res.success is True
    assert res.intent == "agent_query"
    assert "Specialist Execution Workforce (31 Agents)" in res.response_text
    assert "swara (FROZEN)" in res.response_text


def test_pause_and_resume_kill_switch(bot_instance):
    """The /pause and /resume commands must toggle the kill switch."""
    # Pause
    up_pause = {
        "update_id": 9006,
        "message": {
            "message_id": 9006,
            "text": "/pause",
            "from": {"id": 1234, "username": "sumitrevolt"},
            "chat": {"id": 1234},
        },
    }
    res_pause = bot_instance.process_update(up_pause, send_reply=False)
    assert res_pause.success is True
    assert os.environ.get("AUTOMATION_STOP_NEW_CLAIMS") == "1"
    assert "Automation Paused" in res_pause.response_text

    # Resume
    up_resume = {
        "update_id": 9007,
        "message": {
            "message_id": 9007,
            "text": "/resume",
            "from": {"id": 1234, "username": "sumitrevolt"},
            "chat": {"id": 1234},
        },
    }
    res_resume = bot_instance.process_update(up_resume, send_reply=False)
    assert res_resume.success is True
    assert os.environ.get("AUTOMATION_STOP_NEW_CLAIMS") == "0"
    assert "Automation Resumed" in res_resume.response_text


def test_typesafe_intent_classification():
    """TypeSafe intent classifier parses System One response correctly and falls back cleanly."""
    classifier = TelegramIntentClassifier()

    # 1. Deterministic command shortcut
    res_cmd = classifier.classify_intent("/status", "123", is_owner=True)
    assert res_cmd["success"] is True
    assert res_cmd["intent"] == "status_check"

    # 2. System One call with mock
    fake_resp = TypeSafeResponse(
        success=True,
        result={
            "answers": {
                "intent": {"choice": "status_check", "confidence": 0.95},
                "priority": {"choice": "high", "score": 3.0},
                "is_actionable": {"noul": 0.8},
            }
        },
        model="jev-latest",
    )
    # Patch `enabled=True` so the fail-closed guard (client.enabled) is bypassed
    # and the mocked System One judgment is actually consumed — without this the
    # offline env short-circuits to the deterministic fallback and never reaches
    # system_one, so the mock would be ignored and the test would be meaningless.
    with patch.object(classifier.client, "enabled", True), patch.object(
        classifier.client, "system_one", return_value=fake_resp
    ):
        res = classifier.classify_intent("Is the platform healthy right now?", "123", is_owner=True)
        assert res["success"] is True
        assert res["intent"] == "status_check"
        assert res["priority"] == "high"
        assert res["is_actionable"] is True
        assert res["confidence"] == 0.95


def test_typesafe_bot_routing():
    """TypeSafe coordinator routes to one of the 9 Hermes bots."""
    coordinator = TelegramBotCoordinator()

    # Keyword shortcut
    res_kw = coordinator.route_to_hermes_bot("Fix the db server on vps", "123", is_owner=True)
    assert res_kw["success"] is True
    assert res_kw["handler"] == "platform"

    # System One routing with mock
    fake_resp = TypeSafeResponse(
        success=True,
        result={
            "answers": {
                "target_bot": {"choice": "sales"},
                "confidence": {"choice": "very_high"},
            }
        },
        model="jev-latest",
    )
    with patch.object(coordinator.client, "system_one", return_value=fake_resp):
        res = coordinator.route_to_hermes_bot(
            "Follow up on warm enterprise leads", "123", is_owner=True
        )
        assert res["success"] is True
        assert res["handler"] == "sales"
        assert res["confidence"] >= 0.75


def test_typesafe_response_validation():
    """TypeSafe validator scores response quality."""
    validator = TelegramResponseValidator()

    fake_resp = TypeSafeResponse(
        success=True,
        result={
            "answers": {
                "quality": {"choice": "excellent"},
                "appropriate": {"noul": 0.99},
                "complete": {"noul": 0.95},
            }
        },
        model="jev-latest",
    )
    # Patch `enabled=True` so the fail-closed guard (client.enabled) is bypassed
    # and the mocked System One judgment is actually consumed.
    with patch.object(validator.client, "enabled", True), patch.object(
        validator.client, "system_one", return_value=fake_resp
    ):
        res = validator.validate_response(
            response_text="Platform is online. All 31 agents are registered and healthy.",
            intent="status_check",
        )
        assert res["success"] is True
        assert res["quality"] == "excellent"
        assert res["quality_score"] == 4.0
        assert res["appropriate"] is True


def test_end_to_end_agent_task_handoff():
    """Submit, claim/dispatch, verify, and complete a task in AutomationOrchestrator."""
    orch = AutomationOrchestrator()
    owner_bot = "pilot"
    assigned_agent = "lekha"  # green lane observer agent

    # 1. Submit
    record, created = orch.submit_task(
        owner_bot=owner_bot,
        assigned_agent=assigned_agent,
        priority=TaskPriority.LOW,
        input_payload={"test": True},
        idempotency_key=f"test_e2e:{time.time()}",
    )
    assert record is not None
    assert record.status == TaskStatus.READY

    # 2. Dispatch
    dispatched = orch.dispatch_task(record.task_id)
    assert dispatched is True
    assert orch.store.get(record.task_id).status == TaskStatus.RUNNING

    # 3. Verify and Complete
    evidence = StructuredEvidence(
        type="test_result",
        uri_or_path="tests/test_telegram_integration_2026.py",
        producer=assigned_agent,
        checksum_or_result={"status": "pass"},
    )
    completed = orch.verify_and_complete(
        record.task_id,
        execution_evidence=evidence,
        is_success=True,
    )
    assert completed.status == TaskStatus.DONE
    assert orch.store.get(record.task_id).status == TaskStatus.DONE


def test_api_endpoints(monkeypatch):
    """FastAPI REST endpoints under /api/telegram/bot must return correct schemas."""
    monkeypatch.setenv("TELEGRAM_JARVIS_BOT_TOKEN", "123456789012345678901234567890")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789012345678901234567890")
    from app.main import app

    client = TestClient(app)

    # Health
    resp = client.get("/api/telegram/bot/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert data["typesafe_model"] == "jev-latest"

    # Status
    resp = client.get("/api/telegram/bot/status")
    assert resp.status_code == 200
    status_data = resp.json()
    assert status_data["status"] == "online"
    assert "task_counts" in status_data

    # Classify
    resp = client.post(
        "/api/telegram/bot/classify",
        json={"message": "/status", "user_id": "123", "is_owner": True},
    )
    assert resp.status_code == 200
    assert resp.json()["intent"] == "status_check"

    # Route
    resp = client.post(
        "/api/telegram/bot/route",
        json={"message": "We need to fix an index on postgres", "user_id": "123", "is_owner": True},
    )
    assert resp.status_code == 200
    assert resp.json()["handler"] in (
        "board",
        "pilot",
        "guardian",
        "engineering",
        "platform",
        "sales",
        "hunter",
        "operations",
        "success",
    )

    # Webhook
    resp = client.post(
        "/api/telegram/bot/webhook",
        json={
            "update_id": 99999,
            "message": {
                "message_id": 99999,
                "text": "/status",
                "from": {"id": 1234, "username": "sumitrevolt"},
                "chat": {"id": 1234},
            },
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["is_owner"] is True
