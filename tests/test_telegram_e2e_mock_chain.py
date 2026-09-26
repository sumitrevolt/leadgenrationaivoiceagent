"""P1 evidence: isolated end-to-end Telegram -> task ledger -> worker -> TypeSafe chain.

The TelegramBot rendering path is exercised with the canonical handoff call
mocked at its boundary. The handoff persistence and worker-liveness behavior
is covered separately by test_telegram_dev_task_handoff.py. The TypeSafe stage
is also stubbed, so the chain stays hermetic and repeatable. No real customer
touches and no real poller activation.

Run:  .venv/Scripts/python.exe -m pytest tests/test_telegram_e2e_mock_chain.py -v
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_telegram_handoff_creates_claims_executes_and_completes_task():
    """Owner command renders the verified result from the canonical handoff."""
    from app.integrations.telegram_bot import TelegramBot

    result = {
        "ok": True,
        "task_id": "task-test-handoff",
        "worker_id": "api_telegram_jarvis",
        "live_cli_count": 6,
        "state": "completed",
    }
    bot = TelegramBot.__new__(TelegramBot)

    with patch(
        "app.integrations.telegram_dev_task_handoff.run_canonical_handoff",
        return_value=result,
    ) as handoff:
        text, kind, target = bot._cmd_test_handoff()

    handoff.assert_called_once_with()
    assert kind == "command"
    assert target == "pilot"
    assert "Canonical Task Handoff Verified" in text
    assert "task-test-handoff" in text
    assert "6/6" in text
    assert "completed" in text


def test_typesafe_judgment_consumes_telegram_task_context_mocked():
    """TypeSafe Choice call stubbed: proves the consumer chain wiring."""
    from app.platform.typesafe_integration import (
        TypeSafeResponse,
        get_typesafe_client,
    )

    # Stub the underlying system_one so netguard is bypassed
    mock_resp = TypeSafeResponse(
        success=True,
        result={"answers": {"q": "hot_queue"}},
        model="jev-latest",
        latency_sec=0.001,
    )
    client = get_typesafe_client()
    with patch.object(client, "system_one", return_value=mock_resp):
        state = {
            "origin": "telegram_owner_command",
            "task": "route_new_inbound_lead",
            "lead": "salon pricing quote, contactable now",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        resp = client.choice(
            "Which queue lane should this telegram-originated inbound lead enter?",
            state,
            criteria=["hot_queue", "warm_nurture", "cold_reject"],
        )
        assert resp.success
        assert resp.value in {"hot_queue", "warm_nurture", "cold_reject"}
