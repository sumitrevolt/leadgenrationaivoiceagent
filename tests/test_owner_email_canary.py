"""Owner-inbox email canary — refusal, idempotency, daily cap, API gates."""

from __future__ import annotations

import asyncio
import contextlib

import pytest
from fastapi.testclient import TestClient

from app.api.auth_deps import get_current_user, require_super_admin
from app.main import app
from app.models.user import UserRole
from app.platform import owner_email_canary as canary
from tests.conftest import create_mock_user


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    def _path(*, create: bool = False):
        if create:
            tmp_path.mkdir(parents=True, exist_ok=True)
        return tmp_path / "attempts.jsonl"

    monkeypatch.setattr(canary, "_attempts_path", _path)
    monkeypatch.setattr(canary, "_lock_target", lambda: str(tmp_path / "attempts.jsonl"))
    monkeypatch.setattr(canary, "_TIMEOUT_S", 2.0)
    # Config ready by default so provider-path tests are not short-circuited.
    monkeypatch.setattr(
        canary,
        "_smtp_or_api_configured",
        lambda: {
            "api_available": True,
            "smtp_user_present": True,
            "smtp_password_present": True,
            "send_path_ready": True,
        },
    )
    yield


def test_mask_email():
    assert canary.mask_email("owner@example.com") == "ow***@example.com"
    assert canary.mask_email("a@x.com").endswith("@x.com")
    assert canary.mask_email("nope") == "***"
    assert "@" not in canary.mask_email("").replace("***", "")


def test_preflight_never_requires_bulk_flag(monkeypatch):
    monkeypatch.delenv("AUTO_EMAIL_OUTREACH", raising=False)
    pf = canary.preflight()
    assert pf["ok"] is True
    assert pf["bulk_outreach_required"] is False
    assert pf["auto_email_outreach_enabled"] is False


def test_preflight_read_only_does_not_create_dir(tmp_path, monkeypatch):
    empty = tmp_path / "never_created" / "attempts.jsonl"

    def _path(*, create: bool = False):
        if create:
            empty.parent.mkdir(parents=True, exist_ok=True)
        return empty

    monkeypatch.setattr(canary, "_attempts_path", _path)
    pf = canary.preflight()
    assert pf["ok"] is True
    assert pf["attempt_count"] == 0
    assert not empty.parent.exists()


def test_one_to_one_helper():
    assert canary.is_one_to_one("owner@example.com") is True
    assert canary.is_one_to_one("a@x.com,b@y.com") is False
    assert canary.is_one_to_one("") is False


def test_confirm_required_zero_provider(monkeypatch):
    called = {"n": 0}

    async def _boom(*a, **k):
        called["n"] += 1
        return {"sent": True, "mode": "email_sender", "provider_called": True}

    monkeypatch.setattr(canary, "_provider_send", _boom)
    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com", idempotency_key="idem-key-01", confirm=False
        )
    )
    assert res["outcome"] == canary.BLOCKED
    assert res["provider_called"] is False
    assert called["n"] == 0


def test_bulk_refused_zero_provider(monkeypatch):
    called = {"n": 0}

    async def _boom(*a, **k):
        called["n"] += 1
        return {"sent": True}

    monkeypatch.setattr(canary, "_provider_send", _boom)
    res = asyncio.run(
        canary.send_canary(
            to_email="a@x.com,b@y.com",
            idempotency_key="idem-bulk-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.SKIPPED
    assert res["reason"] == "bulk_or_invalid_email_refused"
    assert called["n"] == 0


def test_suppressed_zero_provider(monkeypatch):
    called = {"n": 0}

    async def _boom(*a, **k):
        called["n"] += 1
        return {"sent": True}

    monkeypatch.setattr(canary, "_provider_send", _boom)
    monkeypatch.setattr(canary, "_suppressed", lambda e: True)
    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-sup-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.SKIPPED
    assert res["reason"] == "suppressed"
    assert called["n"] == 0


def test_missing_smtp_fails_closed_no_cap_consume(monkeypatch):
    called = {"n": 0}

    async def _boom(*a, **k):
        called["n"] += 1
        return {"sent": True, "provider_called": True}

    monkeypatch.setattr(canary, "_provider_send", _boom)
    monkeypatch.setattr(canary, "_suppressed", lambda e: False)
    monkeypatch.setattr(
        canary,
        "_smtp_or_api_configured",
        lambda: {
            "api_available": False,
            "smtp_user_present": False,
            "smtp_password_present": False,
            "send_path_ready": False,
        },
    )
    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-smtp-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.FAILED
    assert res["reason"] == "smtp_not_configured"
    assert res["provider_called"] is False
    assert called["n"] == 0
    # Cap not consumed — a later configured send with a new key may proceed.
    monkeypatch.setattr(
        canary,
        "_smtp_or_api_configured",
        lambda: {
            "api_available": True,
            "smtp_user_present": True,
            "smtp_password_present": True,
            "send_path_ready": True,
        },
    )

    async def _ok(*a, **k):
        called["n"] += 1
        return {
            "sent": True,
            "mode": "email_sender",
            "provider_called": True,
            "list_unsubscribe_attached": True,
        }

    monkeypatch.setattr(canary, "_provider_send", _ok)
    res2 = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-smtp-retry-02",
            confirm=True,
        )
    )
    assert res2["outcome"] == canary.SENT
    assert called["n"] == 1


def test_timeout_unknown_no_retry(monkeypatch):
    async def _to(*a, **k):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(canary, "_provider_send", _to)
    monkeypatch.setattr(canary, "_suppressed", lambda e: False)
    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-to-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.UNKNOWN_REQUIRES_REVIEW
    assert res["reason"] == "provider_timeout_no_retry"
    assert res["provider_called"] is True


def test_provider_false_maps_to_unknown_not_skipped(monkeypatch):
    """EmailSender collapses errors to False — must not become SKIPPED."""

    async def _false(*a, **k):
        return {
            "sent": False,
            "mode": "provider_refused",
            "provider_called": True,
            "list_unsubscribe_attached": True,
        }

    monkeypatch.setattr(canary, "_provider_send", _false)
    monkeypatch.setattr(canary, "_suppressed", lambda e: False)
    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-false-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.UNKNOWN_REQUIRES_REVIEW
    assert res["outcome"] != canary.SKIPPED
    assert res["provider_called"] is True
    # Same key must not re-send.
    res2 = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-false-01",
            confirm=True,
        )
    )
    assert res2["outcome"] == canary.DUPLICATE


def test_duplicate_idempotency_sends_once(monkeypatch):
    sent = {"n": 0}

    async def _ok(*a, **k):
        sent["n"] += 1
        return {
            "sent": True,
            "mode": "email_sender",
            "provider_called": True,
            "list_unsubscribe_attached": True,
        }

    monkeypatch.setattr(canary, "_provider_send", _ok)
    monkeypatch.setattr(canary, "_suppressed", lambda e: False)
    r1 = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-once-01",
            confirm=True,
        )
    )
    r2 = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-once-01",
            confirm=True,
        )
    )
    assert r1["outcome"] == canary.SENT
    assert r2["outcome"] == canary.DUPLICATE
    assert sent["n"] == 1
    assert "owner@example.com" not in str(r1)


def test_concurrent_same_key_sends_once(monkeypatch):
    sent = {"n": 0}
    gate = asyncio.Event()

    async def _ok(*a, **k):
        sent["n"] += 1
        await gate.wait()
        return {
            "sent": True,
            "mode": "email_sender",
            "provider_called": True,
            "list_unsubscribe_attached": True,
        }

    monkeypatch.setattr(canary, "_provider_send", _ok)
    monkeypatch.setattr(canary, "_suppressed", lambda e: False)

    async def _run():
        t1 = asyncio.create_task(
            canary.send_canary(
                to_email="owner@example.com",
                idempotency_key="idem-race-01",
                confirm=True,
            )
        )
        await asyncio.sleep(0.05)  # let first claim pending under lock
        t2 = asyncio.create_task(
            canary.send_canary(
                to_email="owner@example.com",
                idempotency_key="idem-race-01",
                confirm=True,
            )
        )
        await asyncio.sleep(0.05)
        gate.set()
        return await asyncio.gather(t1, t2)

    r1, r2 = asyncio.run(_run())
    outcomes = {r1["outcome"], r2["outcome"]}
    assert canary.SENT in outcomes
    assert canary.DUPLICATE in outcomes
    assert sent["n"] == 1


def test_daily_provider_cap_blocks_second_key(monkeypatch):
    sent = {"n": 0}

    async def _ok(*a, **k):
        sent["n"] += 1
        return {
            "sent": True,
            "mode": "email_sender",
            "provider_called": True,
            "list_unsubscribe_attached": True,
        }

    monkeypatch.setattr(canary, "_provider_send", _ok)
    monkeypatch.setattr(canary, "_suppressed", lambda e: False)
    r1 = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-cap-01",
            confirm=True,
        )
    )
    r2 = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-cap-02",
            confirm=True,
        )
    )
    assert r1["outcome"] == canary.SENT
    assert r2["outcome"] == canary.BLOCKED
    assert r2["reason"] == "daily_provider_attempt_cap"
    assert r2["provider_called"] is False
    assert sent["n"] == 1


def test_lock_unavailable_blocks_provider(monkeypatch):
    """Exactly-once claim must fail closed when the sidecar lock is unavailable."""
    from app.utils import file_lock as locks

    called = {"n": 0}

    @contextlib.contextmanager
    def _unlocked(*_args, **_kwargs):
        yield False

    async def _provider(*_args, **_kwargs):
        called["n"] += 1
        return {"sent": True, "mode": "email_sender", "provider_called": True}

    monkeypatch.setattr(locks, "file_lock", _unlocked)
    monkeypatch.setattr(canary, "_provider_send", _provider)
    monkeypatch.setattr(canary, "_suppressed", lambda _email: False)

    result = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-lock-fail-01",
            confirm=True,
        )
    )

    assert result["outcome"] == canary.BLOCKED
    assert result["reason"] == "idempotency_lock_unavailable"
    assert result["provider_called"] is False
    assert called["n"] == 0
    assert canary.find_by_idempotency("idem-lock-fail-01") is None


def test_persist_before_provider(monkeypatch):
    seen_pending = {"ok": False}

    async def _check(*a, **k):
        row = canary.find_by_idempotency("idem-persist-01")
        seen_pending["ok"] = bool(row) and row.get("outcome") == "pending"
        return {
            "sent": True,
            "mode": "email_sender",
            "provider_called": True,
            "list_unsubscribe_attached": True,
        }

    monkeypatch.setattr(canary, "_provider_send", _check)
    monkeypatch.setattr(canary, "_suppressed", lambda e: False)
    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-persist-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.SENT
    assert seen_pending["ok"] is True


def test_authority_refusal_no_checkout_fallback(monkeypatch):
    from app.platform import runtime_data as rd

    def _boom(*, create: bool = False):
        raise rd.RuntimeDataError("canonical authority refused (test)")

    monkeypatch.setattr(canary, "_attempts_path", _boom)
    monkeypatch.setattr(
        canary,
        "_lock_target",
        lambda: (_ for _ in ()).throw(rd.RuntimeDataError("canonical authority refused (test)")),
    )
    monkeypatch.setattr(canary, "_suppressed", lambda e: False)
    called = {"n": 0}

    async def _prov(*a, **k):
        called["n"] += 1
        return {"sent": True, "provider_called": True}

    monkeypatch.setattr(canary, "_provider_send", _prov)
    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-auth-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.BLOCKED
    assert res["reason"] == "runtime_data_authority_refused"
    assert called["n"] == 0
    assert res["provider_called"] is False

    pf = canary.preflight()
    assert pf["ok"] is False
    assert pf["reason"] == "runtime_data_authority_refused"


# ---- API layer ------------------------------------------------------------- #


@pytest.fixture
def api_client(monkeypatch, tmp_path):
    def _path(*, create: bool = False):
        if create:
            tmp_path.mkdir(parents=True, exist_ok=True)
        return tmp_path / "attempts.jsonl"

    monkeypatch.setattr(canary, "_attempts_path", _path)
    monkeypatch.setattr(canary, "_lock_target", lambda: str(tmp_path / "attempts.jsonl"))
    monkeypatch.setattr(canary, "_suppressed", lambda e: False)
    monkeypatch.setattr(
        canary,
        "_smtp_or_api_configured",
        lambda: {
            "api_available": True,
            "smtp_user_present": True,
            "smtp_password_present": True,
            "send_path_ready": True,
        },
    )
    before = dict(app.dependency_overrides)
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
    app.dependency_overrides.update(before)


def test_api_requires_super_admin(api_client):
    app.dependency_overrides.pop(require_super_admin, None)
    app.dependency_overrides.pop(get_current_user, None)
    # Non-super admin
    app.dependency_overrides[get_current_user] = lambda: create_mock_user(role=UserRole.ADMIN)
    r = api_client.get("/api/admin/owner-email-canary/preflight")
    assert r.status_code == 403
    r2 = api_client.post(
        "/api/admin/owner-email-canary/send",
        json={
            "to_email": "owner@example.com",
            "idempotency_key": "idem-api-auth-01",
            "confirm": True,
            "confirm_owner_inbox": True,
        },
    )
    assert r2.status_code == 403


def test_api_super_admin_preflight_ok(api_client):
    app.dependency_overrides[require_super_admin] = lambda: create_mock_user(
        role=UserRole.SUPER_ADMIN
    )
    r = api_client.get("/api/admin/owner-email-canary/preflight")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["bulk_outreach_required"] is False


def test_api_both_confirm_booleans_required(api_client, monkeypatch):
    app.dependency_overrides[require_super_admin] = lambda: create_mock_user(
        role=UserRole.SUPER_ADMIN
    )
    called = {"n": 0}

    async def _boom(*a, **k):
        called["n"] += 1
        return {"sent": True, "provider_called": True}

    monkeypatch.setattr(canary, "_provider_send", _boom)

    r1 = api_client.post(
        "/api/admin/owner-email-canary/send",
        json={
            "to_email": "owner@example.com",
            "idempotency_key": "idem-api-conf-01",
            "confirm": True,
            "confirm_owner_inbox": False,
        },
    )
    assert r1.status_code == 200
    assert r1.json()["outcome"] == canary.BLOCKED
    assert r1.json()["reason"] == "confirm_and_owner_inbox_required"
    assert called["n"] == 0

    r2 = api_client.post(
        "/api/admin/owner-email-canary/send",
        json={
            "to_email": "owner@example.com",
            "idempotency_key": "idem-api-conf-02",
            "confirm": False,
            "confirm_owner_inbox": True,
        },
    )
    assert r2.status_code == 200
    assert r2.json()["outcome"] == canary.BLOCKED
    assert called["n"] == 0


def test_api_send_happy_path_masks_recipient(api_client, monkeypatch):
    app.dependency_overrides[require_super_admin] = lambda: create_mock_user(
        role=UserRole.SUPER_ADMIN, user_id="sa-1"
    )

    async def _ok(*a, **k):
        return {
            "sent": True,
            "mode": "email_sender",
            "provider_called": True,
            "list_unsubscribe_attached": True,
        }

    monkeypatch.setattr(canary, "_provider_send", _ok)
    r = api_client.post(
        "/api/admin/owner-email-canary/send",
        json={
            "to_email": "owner@example.com",
            "idempotency_key": "idem-api-send-01",
            "confirm": True,
            "confirm_owner_inbox": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"] == canary.SENT
    assert "owner@example.com" not in r.text
    assert body["to_masked"].startswith("ow")
