"""Tests for the Telegram owner-command dispatcher (Task #80).

Naming: T1–T4 are Agnes's required scenarios. T5–T10 cover the rest of the
owner directive (compliance, kill switch, egress failure, replay safety).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _status_helpers import _task_status_value  # noqa: E402

# Ensure worktree root is importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Lightweight stand-ins for Orchestrator / TaskStore / TelegramBot so the
# dispatcher can be exercised without spinning up the FastAPI / DB stack.
# ---------------------------------------------------------------------------
class _FakeStatus:
    READY = "READY"
    RUNNING = "RUNNING"
    REVIEW = "REVIEW"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    DONE = "DONE"


def _status_enum(name: str) -> SimpleNamespace:
    """Build a TaskStatus-like SimpleNamespace whose str() and .value both
    reflect the supplied name, and whose attributes expose all enum names
    for attribute-style comparisons (TaskStatus.REVIEW etc.)."""
    ns = SimpleNamespace(
        name=name, value=name,
        READY=_FakeStatus.READY, RUNNING=_FakeStatus.RUNNING,
        REVIEW=_FakeStatus.REVIEW, FAILED=_FakeStatus.FAILED,
        BLOCKED=_FakeStatus.BLOCKED, DONE=_FakeStatus.DONE,
    )
    return ns


class _FakeTask:
    def __init__(
        self,
        task_id: str,
        status: str = "READY",
        assigned_agent: str = "hermes",
        version: int = 1,
        fencing_token: str | None = None,
        idempotency_key: str | None = None,
        evidence: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self.id = task_id
        self.status = _status_enum(status)
        self.assigned_agent = assigned_agent
        self.version = version
        self.fencing_token = fencing_token
        self.idempotency_key = idempotency_key
        self.evidence = evidence
        self.error_message = error_message
        self.input_payload = "{}"
        self.outgoing_message_id = None
        self.updated_at = 0.0


class _FakeStore:
    """In-memory store. One task per id; supports update_cas + save."""

    def __init__(self, tasks: dict[str, _FakeTask] | None = None) -> None:
        self._tasks: dict[str, _FakeTask] = tasks or {}
        self.TaskStatus = SimpleNamespace(
            READY="READY",
            RUNNING="RUNNING",
            REVIEW="REVIEW",
            FAILED="FAILED",
            BLOCKED="BLOCKED",
            DONE="DONE",
        )

    def get(self, task_id: str) -> _FakeTask | None:
        return self._tasks.get(task_id)

    def get_by_idempotency_key(self, key: str) -> _FakeTask | None:
        for t in self._tasks.values():
            if t.idempotency_key == key:
                return t
        return None

    def update_cas(self, *, task_id: str, expected_version: int, new_status, new_fencing_token: str | None) -> bool:
        t = self._tasks.get(task_id)
        if not t or t.version != expected_version:
            return False
        if isinstance(new_status, str):
            t.status = _status_enum(new_status)
        else:
            t.status = new_status
        if new_fencing_token is not None:
            t.fencing_token = new_fencing_token
        t.version += 1
        return True

    def save(self, task) -> None:
        task.updated_at = __import__("time").time()
        self._tasks[task.id] = task


class _FakeOrchestrator:
    def __init__(self, store: _FakeStore, *, kill: bool = False, dispatch_returns: bool = True) -> None:
        self.store = store
        self._kill = kill
        self._dispatch_returns = dispatch_returns
        self.dispatch_calls = 0

    def is_kill_switch_active(self) -> bool:
        return self._kill

    def dispatch_task(self, task_id: str) -> bool:
        self.dispatch_calls += 1
        # Simulate Orchestrator: transition READY → RUNNING + generate fence
        if not self._dispatch_returns:
            return False
        t = self.store.get(task_id)
        if not t:
            return False
        t.status = _status_enum("RUNNING")
        t.fencing_token = f"fence_{task_id}_{t.version}"
        t.version += 1
        return True


class _FakeBot:
    """Mimics the extended TelegramBot — supports both old and new send API."""

    def __init__(self, *, ok: bool = True, message_id: int = 99999) -> None:
        self.ok = ok
        self.message_id = message_id
        self.sent: list[dict] = []

    # New API used by dispatcher
    def send_message_with_message_id(self, chat_id, text, parse_mode=None):
        self.sent.append({"chat_id": chat_id, "text": text[:200] + ("..." if len(text) > 200 else "")})
        return self.ok, (self.message_id if self.ok else None)

    # Legacy boolean API — backward compat path
    def send_message(self, chat_id, text, parse_mode=None) -> bool:
        ok, _msg_id = self.send_message_with_message_id(chat_id, text, parse_mode)
        return ok


# ---------------------------------------------------------------------------
# Common fixture: a task in the store + owner chat id
# ---------------------------------------------------------------------------
@pytest.fixture
def owner_chat_id() -> int:
    os.environ["TELEGRAM_OWNER_CHAT_IDS"] = "1621120182"
    return 1621120182


@pytest.fixture
def ready_task() -> _FakeTask:
    return _FakeTask(task_id="task_79406871", status="READY", assigned_agent="hermes")


@pytest.fixture
def env(ready_task):
    store = _FakeStore(tasks={ready_task.id: ready_task})
    orch = _FakeOrchestrator(store)
    bot = _FakeBot(ok=True, message_id=424242)
    return SimpleNamespace(store=store, orch=orch, bot=bot, task=ready_task)


# ---------------------------------------------------------------------------
# T1 — Agnes: Happy path E2E
# ---------------------------------------------------------------------------
def test_T1_happy_path_owner_status_dispatched(owner_chat_id, env):
    """Owner sends /status bound to task_79406871. Handler runs, reply sent,
    result + fencing token + outgoing message_id all persisted."""
    from app.platform.telegram_owner_command_dispatcher import dispatch_owner_command

    res = dispatch_owner_command(
        update_id=555_001,
        chat_id=owner_chat_id,
        command="/status",
        task_id="task_79406871",
        orchestrator=env.orch,
        telegram_bot=env.bot,
    )

    assert res.status == "DISPATCHED"
    assert res.task_id == "task_79406871"
    assert res.fencing_token is not None
    assert res.fencing_token.startswith("fence_")
    assert res.reply_message_id == 424242

    # Persisted evidence on the task
    t = env.store.get("task_79406871")
    assert t.evidence is not None
    payload = json.loads(t.evidence)
    assert payload["handler_executed"] is True
    assert payload["command"] == "/status"
    assert payload["fencing_token"] == res.fencing_token

    # Idempotency key bound to update_id
    assert t.idempotency_key == "tg:owner_command:555001"

    # Reply actually sent exactly once
    assert len(env.bot.sent) == 1
    assert env.bot.sent[0]["chat_id"] == owner_chat_id

    # Orchestrator's dispatch_task was called exactly once (the legitimate
    # READY → RUNNING transition — NOT a self-written verified=True shortcut).
    assert env.orch.dispatch_calls == 1


# ---------------------------------------------------------------------------
# T2 — Agnes: Idempotency on replay
# ---------------------------------------------------------------------------
def test_T2_idempotent_replay_returns_same_message_id_without_resending(owner_chat_id, env):
    from app.platform.telegram_owner_command_dispatcher import dispatch_owner_command

    # First call — real dispatch
    r1 = dispatch_owner_command(
        update_id=555_002,
        chat_id=owner_chat_id,
        command="/status",
        task_id="task_79406871",
        orchestrator=env.orch,
        telegram_bot=env.bot,
    )
    assert r1.status == "DISPATCHED"
    assert r1.reply_message_id == 424242
    assert env.orch.dispatch_calls == 1
    assert len(env.bot.sent) == 1

    # Replay — same update_id. Same task. Should NOT re-send, NOT re-dispatch.
    r2 = dispatch_owner_command(
        update_id=555_002,
        chat_id=owner_chat_id,
        command="/status",
        task_id="task_79406871",
        orchestrator=env.orch,
        telegram_bot=env.bot,
    )
    assert r2.status == "IDEMPOTENT_REPLAY"
    assert r2.reply_message_id == 424242
    assert env.orch.dispatch_calls == 1  # not re-dispatched
    assert len(env.bot.sent) == 1  # not re-sent


# ---------------------------------------------------------------------------
# T3 — Agnes: Unauthorized sender
# ---------------------------------------------------------------------------
def test_T3_unauthorized_sender_rejected_without_writing(owner_chat_id, env):
    from app.platform.telegram_owner_command_dispatcher import dispatch_owner_command

    res = dispatch_owner_command(
        update_id=555_003,
        chat_id=999999999,  # NOT an owner
        command="/status",
        task_id="task_79406871",
        orchestrator=env.orch,
        telegram_bot=env.bot,
    )

    assert res.status == "UNAUTHORIZED"
    assert res.reason == "chat_not_owner"

    # Task NOT mutated
    t = env.store.get("task_79406871")
    assert t.idempotency_key is None  # never bound
    assert t.evidence is None  # no handler ran
    assert env.orch.dispatch_calls == 0
    assert len(env.bot.sent) == 0


# ---------------------------------------------------------------------------
# T4 — Agnes: Worker / handler failure
# ---------------------------------------------------------------------------
def test_T4_handler_failure_marks_task_FAILED_with_truthful_reason(owner_chat_id, env, monkeypatch):
    from app.platform.telegram_owner_command_dispatcher import dispatch_owner_command

    # Force handler import to raise (simulating a missing / crashing module).
    import app.platform.telegram_owner_command_dispatcher as disp_mod

    def _boom(_command):
        raise RuntimeError("simulated handler crash")

    monkeypatch.setattr(
        disp_mod, "_resolve_handler", lambda _cmd: _boom
    )

    res = dispatch_owner_command(
        update_id=555_004,
        chat_id=owner_chat_id,
        command="/status",
        task_id="task_79406871",
        orchestrator=env.orch,
        telegram_bot=env.bot,
    )

    assert res.status == "HANDLER_FAILED"
    assert "simulated handler crash" in (res.reason or "")

    # Task marked FAILED with truthful reason
    t = env.store.get("task_79406871")
    assert _task_status_value(t) == "FAILED"
    assert t.error_message is not None
    assert "simulated handler crash" in t.error_message

    # Handler crashed → no reply was sent (NOT a fake success)
    assert len(env.bot.sent) == 0


# ---------------------------------------------------------------------------
# T5 — Kill switch
# ---------------------------------------------------------------------------
def test_T5_kill_switch_blocks_dispatch_with_truthful_BLOCKED(owner_chat_id, env):
    from app.platform.telegram_owner_command_dispatcher import dispatch_owner_command

    env.orch._kill = True

    res = dispatch_owner_command(
        update_id=555_005,
        chat_id=owner_chat_id,
        command="/status",
        task_id="task_79406871",
        orchestrator=env.orch,
        telegram_bot=env.bot,
    )

    assert res.status == "KILLED"
    assert "Kill switch" in (res.reason or "")

    t = env.store.get("task_79406871")
    assert _task_status_value(t) == "BLOCKED"
    assert "Kill switch" in (t.error_message or "")
    assert env.orch.dispatch_calls == 0
    assert len(env.bot.sent) == 0


# ---------------------------------------------------------------------------
# T6 — Egress failure: handler ran but reply send failed
# ---------------------------------------------------------------------------
def test_T6_egress_failure_persists_handler_result_but_marks_FAILED(owner_chat_id, env):
    from app.platform.telegram_owner_command_dispatcher import dispatch_owner_command

    env.bot = _FakeBot(ok=False, message_id=0)
    env.orch.bot = env.bot  # not needed but consistent

    res = dispatch_owner_command(
        update_id=555_006,
        chat_id=owner_chat_id,
        command="/status",
        task_id="task_79406871",
        orchestrator=env.orch,
        telegram_bot=env.bot,
    )

    assert res.status == "DISPATCHED_NO_REPLY"
    assert res.reply_message_id is None

    # Handler result STILL persisted (handler_executed=True), but task marked FAILED
    t = env.store.get("task_79406871")
    assert t.evidence is not None
    assert json.loads(t.evidence)["handler_executed"] is True
    assert _task_status_value(t) == "FAILED"
    assert "egress_failure" in (t.error_message or "")


# ---------------------------------------------------------------------------
# T7 — Handler missing (no callable for this command)
# ---------------------------------------------------------------------------
def test_T7_handler_missing_marks_REVIEW_with_truthful_reason(owner_chat_id, env, monkeypatch):
    from app.platform.telegram_owner_command_dispatcher import dispatch_owner_command
    import app.platform.telegram_owner_command_dispatcher as disp_mod

    monkeypatch.setattr(disp_mod, "_resolve_handler", lambda _cmd: None)

    res = dispatch_owner_command(
        update_id=555_007,
        chat_id=owner_chat_id,
        command="/some-unknown-cmd",
        task_id="task_79406871",
        orchestrator=env.orch,
        telegram_bot=env.bot,
    )

    assert res.status == "HANDLER_MISSING"
    assert "handler_missing" in (res.reason or "")
    t = env.store.get("task_79406871")
    assert _task_status_value(t) == "REVIEW"
    assert "handler_missing" in (t.error_message or "")


# ---------------------------------------------------------------------------
# T8 — Boolean send_message() still works for legacy callers
# ---------------------------------------------------------------------------
def test_T8_legacy_boolean_send_message_compatible():
    """Pre-existing boolean-only send_message(...) must keep its signature and
    return True/False exactly as before (no breaking change for callers)."""
    from app.integrations.telegram_bot import TelegramBot

    bot = TelegramBot(token="dummy-test-token")
    # New method exists
    assert callable(getattr(bot, "send_message_with_message_id", None))
    # Legacy method exists, returns bool, accepts the same kwargs
    import inspect
    sig = inspect.signature(bot.send_message)
    assert "chat_id" in sig.parameters
    assert "text" in sig.parameters
    assert "parse_mode" in sig.parameters

    # Stub requests so we don't hit the network
    class _Resp:
        status_code = 200
        def json(self):
            return {"ok": True, "result": {"message_id": 12345}}

    with patch("app.integrations.telegram_bot.requests.post", return_value=_Resp()):
        result = bot.send_message("123", "hello")
        assert isinstance(result, bool)
        assert result is True


# ---------------------------------------------------------------------------
# T9 — dispatch_task_79406871 actually resolves the existing READY task
# ---------------------------------------------------------------------------
def test_T9_dispatch_existing_ready_task_79406871(owner_chat_id, env):
    from app.platform.telegram_owner_command_dispatcher import dispatch_owner_command

    # Confirm pre-state from the real orchestrator_ledger.db (sanity check
    # against the task this whole dispatcher was built around).
    ledger_db = ROOT.parent / "data" / "orchestrator_ledger.db"
    if ledger_db.exists():
        con = sqlite3.connect(str(ledger_db))
        cur = con.execute(
            "SELECT task_id, status, owner_bot, assigned_agent, idempotency_key "
            "FROM task_records WHERE task_id='task_79406871'"
        )
        row = cur.fetchone()
        con.close()
        if row:
            # Real row must be READY (the canonical contract)
            assert row[1] == "READY", (
                f"task_79406871 status changed away from READY: {row[1]}"
            )
            assert row[2] == "guardian"
            assert row[3] == "hermes"
            # Idempotency key must NOT yet be the dispatcher's tg: prefix
            assert not (row[4] or "").startswith("tg:owner_command:"), (
                "task_79406871 already bound to a telegram owner command "
                f"update_id (idempotency_key={row[4]!r})"
            )

    res = dispatch_owner_command(
        update_id=555_009,
        chat_id=owner_chat_id,
        command="/status",
        task_id="task_79406871",
        orchestrator=env.orch,
        telegram_bot=env.bot,
    )
    assert res.status == "DISPATCHED"
    assert res.task_id == "task_79406871"
    assert res.fencing_token is not None


# ---------------------------------------------------------------------------
# T10 — No double reply on cross-task replay (different task_id, same update_id)
# ---------------------------------------------------------------------------
def test_T10_idempotent_replay_across_tasks_returns_existing_owner(owner_chat_id, env):
    """If update_id was previously bound to task A, a new attempt pointing at
    task B for the SAME update_id must NOT silently bind task B — it returns
    IDEMPOTENT_REPLAY with the original task id."""
    from app.platform.telegram_owner_command_dispatcher import dispatch_owner_command

    # First dispatch binds update_id → task_79406871
    r1 = dispatch_owner_command(
        update_id=555_010,
        chat_id=owner_chat_id,
        command="/status",
        task_id="task_79406871",
        orchestrator=env.orch,
        telegram_bot=env.bot,
    )
    assert r1.status == "DISPATCHED"

    # Add a second task the malicious caller might try to bind
    second = _FakeTask(task_id="task_OTHER", status="READY", assigned_agent="hermes")
    env.store._tasks["task_OTHER"] = second

    # Same update_id, different task_id — must NOT silently rebind
    r2 = dispatch_owner_command(
        update_id=555_010,
        chat_id=owner_chat_id,
        command="/status",
        task_id="task_OTHER",
        orchestrator=env.orch,
        telegram_bot=env.bot,
    )
    assert r2.status == "IDEMPOTENT_REPLAY"
    assert r2.task_id == "task_79406871"
    # second task must remain untouched
    assert env.store.get("task_OTHER").idempotency_key is None
    # Only one reply sent (for the first task)
    assert len(env.bot.sent) == 1
