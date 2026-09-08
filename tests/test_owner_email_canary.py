"""Owner-inbox email canary — refusal, idempotency, daily cap, API gates."""

from __future__ import annotations

import asyncio
import contextlib
import json
import multiprocessing
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.auth_deps import get_current_user, require_super_admin
from app.main import app
from app.models.user import UserRole
from app.platform import owner_email_canary as canary
from app.platform import runtime_data as rd
from app.platform import runtime_data_authority as auth
from app.platform import runtime_data_manifest as manifest
from app.platform import runtime_data_marker as mk
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
    """Provider false must not become SKIPPED — ambiguous for retry safety."""

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


# ---- Release-blocking safety regressions (cloud review @ 086e5c3) ---------- #


def test_timeout_exactly_one_transport_no_cascade(monkeypatch):
    """Ambiguous timeout must not fall through Resend→Brevo→SMTP."""
    calls = {"resend": 0, "brevo": 0, "smtp": 0}

    async def _resend(**_k):
        calls["resend"] += 1
        raise asyncio.TimeoutError()

    async def _brevo(**_k):
        calls["brevo"] += 1
        return True

    async def _smtp(**_k):
        calls["smtp"] += 1
        return True

    monkeypatch.setattr(canary, "_pick_one_transport", lambda: "resend")
    monkeypatch.setattr(canary, "_send_resend_once", _resend)
    monkeypatch.setattr(canary, "_send_brevo_once", _brevo)
    monkeypatch.setattr(canary, "_send_smtp_once", _smtp)
    monkeypatch.setattr(canary, "_suppressed", lambda _e: False)

    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-one-to-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.UNKNOWN_REQUIRES_REVIEW
    assert res["reason"] == "provider_timeout_no_retry"
    assert calls == {"resend": 1, "brevo": 0, "smtp": 0}


def test_provider_error_exactly_one_transport_no_cascade(monkeypatch):
    calls = {"resend": 0, "brevo": 0, "smtp": 0}

    async def _resend(**_k):
        calls["resend"] += 1
        raise RuntimeError("provider_boom")

    async def _brevo(**_k):
        calls["brevo"] += 1
        return True

    async def _smtp(**_k):
        calls["smtp"] += 1
        return True

    monkeypatch.setattr(canary, "_pick_one_transport", lambda: "resend")
    monkeypatch.setattr(canary, "_send_resend_once", _resend)
    monkeypatch.setattr(canary, "_send_brevo_once", _brevo)
    monkeypatch.setattr(canary, "_send_smtp_once", _smtp)
    monkeypatch.setattr(canary, "_suppressed", lambda _e: False)

    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-one-err-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.UNKNOWN_REQUIRES_REVIEW
    assert res["reason"] == "RuntimeError"
    assert calls == {"resend": 1, "brevo": 0, "smtp": 0}


def test_provider_send_never_uses_email_sender(monkeypatch):
    """Canary must not enter EmailSender's multi-provider fallback chain."""
    import inspect

    import app.integrations.email_sender as sender_mod

    src = inspect.getsource(canary._provider_send)
    assert "EmailSender" not in src

    async def _forbid(*_a, **_k):
        raise AssertionError("EmailSender.send_email must not be used by canary")

    monkeypatch.setattr(sender_mod.EmailSender, "send_email", _forbid)
    monkeypatch.setattr(canary, "_pick_one_transport", lambda: "resend")

    async def _ok(**_k):
        return True

    monkeypatch.setattr(canary, "_send_resend_once", _ok)
    monkeypatch.setattr(canary, "_suppressed", lambda _e: False)
    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-no-sender-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.SENT


def test_attempt_ledger_unreadable_blocks_before_provider(tmp_path, monkeypatch):
    ledger = tmp_path / "attempts.jsonl"
    ledger.write_text('{"event":"attempt"}\n', encoding="utf-8")

    real_read = Path.read_text

    def _deny_read(self, *a, **k):
        if self == ledger:
            raise PermissionError("ledger locked for test")
        return real_read(self, *a, **k)

    called = {"n": 0}

    async def _prov(*_a, **_k):
        called["n"] += 1
        return {"sent": True, "provider_called": True}

    monkeypatch.setattr(canary, "_attempts_path", lambda *, create=False: ledger)
    monkeypatch.setattr(canary, "_lock_target", lambda: str(ledger))
    monkeypatch.setattr(canary, "_provider_send", _prov)
    monkeypatch.setattr(canary, "_suppressed", lambda _e: False)
    monkeypatch.setattr(Path, "read_text", _deny_read)

    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-ledger-unreadable-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.BLOCKED
    assert res["reason"] == "attempt_ledger_unreadable"
    assert res["provider_called"] is False
    assert called["n"] == 0

    pf = canary.preflight()
    assert pf["ok"] is False
    assert pf["reason"] == "attempt_ledger_unreadable"


def test_attempt_ledger_corrupt_blocks_before_provider(tmp_path, monkeypatch):
    ledger = tmp_path / "attempts.jsonl"
    ledger.write_text("{not-json\n", encoding="utf-8")

    called = {"n": 0}

    async def _prov(*_a, **_k):
        called["n"] += 1
        return {"sent": True, "provider_called": True}

    monkeypatch.setattr(canary, "_attempts_path", lambda *, create=False: ledger)
    monkeypatch.setattr(canary, "_lock_target", lambda: str(ledger))
    monkeypatch.setattr(canary, "_provider_send", _prov)
    monkeypatch.setattr(canary, "_suppressed", lambda _e: False)

    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-ledger-corrupt-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.BLOCKED
    assert res["reason"] == "attempt_ledger_corrupt"
    assert called["n"] == 0
    assert res["provider_called"] is False

    pf = canary.preflight()
    assert pf["ok"] is False
    assert pf["reason"] == "attempt_ledger_corrupt"


def test_suppression_read_error_fail_closed_canary_only(monkeypatch, tmp_path):
    """Ordinary suppression I/O errors must block the canary (no provider I/O)."""
    from app.platform import email_unsub

    ledger = tmp_path / "email_suppression.jsonl"
    ledger.write_text("", encoding="utf-8")
    monkeypatch.setattr(email_unsub, "_store_or_none", lambda: ledger)
    monkeypatch.setattr(email_unsub, "_store_path", lambda: ledger)

    real_read = Path.read_text

    def _deny_read(self, *a, **k):
        if self == ledger:
            raise PermissionError("suppression locked for test")
        return real_read(self, *a, **k)

    called = {"n": 0}

    async def _prov(*_a, **_k):
        called["n"] += 1
        return {"sent": True, "provider_called": True}

    monkeypatch.setattr(Path, "read_text", _deny_read)
    monkeypatch.setattr(canary, "_provider_send", _prov)

    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-sup-io-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.BLOCKED
    assert res["reason"] == "suppression_ledger_untrusted"
    assert called["n"] == 0


def test_suppression_corrupt_ledger_fail_closed(monkeypatch, tmp_path):
    from app.platform import email_unsub

    bad = tmp_path / "email_suppression.jsonl"
    bad.write_text("{broken\n", encoding="utf-8")
    monkeypatch.setattr(email_unsub, "_store_or_none", lambda: bad)
    monkeypatch.setattr(email_unsub, "_store_path", lambda: bad)

    called = {"n": 0}

    async def _prov(*_a, **_k):
        called["n"] += 1
        return {"sent": True, "provider_called": True}

    monkeypatch.setattr(canary, "_provider_send", _prov)
    # Do NOT stub _suppressed — exercise canary-local strict snapshot.
    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-sup-corrupt-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.BLOCKED
    assert res["reason"] == "suppression_ledger_untrusted"
    assert called["n"] == 0


def test_suppression_toctou_no_second_fail_open_reader(monkeypatch, tmp_path):
    """Mutate/break ledger after first strict read — must still use snapshot.

    Old bug: trustworthy() validated, then is_contact_suppressed reopened via
    fail-open reader which skipped corrupt lines ⇒ empty ⇒ send. Fixed path
    decides from the same validated snapshot and never calls the fail-open API.
    """
    from app.platform import email_unsub

    ledger = tmp_path / "email_suppression.jsonl"
    good = (
        json.dumps(
            {
                "email": "owner@example.com",
                "scope": "email_address",
                "channel": "email",
                "ts": int(time.time()),
            }
        )
        + "\n"
    )
    ledger.write_text(good, encoding="utf-8")
    monkeypatch.setattr(email_unsub, "_store_or_none", lambda: ledger)
    monkeypatch.setattr(email_unsub, "_store_path", lambda: ledger)

    reads = {"n": 0}
    real_read = Path.read_text

    def _read_then_break(self, *a, **k):
        if self == ledger:
            reads["n"] += 1
            if reads["n"] == 1:
                text = real_read(self, *a, **k)
                # Poison on-disk AFTER the snapshot bytes are in hand.
                ledger.write_text("{broken-after-snapshot\n", encoding="utf-8")
                return text
            raise AssertionError("second suppression ledger read must not happen")
        return real_read(self, *a, **k)

    def _fail_open_must_not_run(**_k):
        raise AssertionError("email_unsub.is_contact_suppressed must not be used")

    called = {"n": 0}

    async def _prov(*_a, **_k):
        called["n"] += 1
        return {"sent": True, "provider_called": True}

    monkeypatch.setattr(Path, "read_text", _read_then_break)
    monkeypatch.setattr(email_unsub, "is_contact_suppressed", _fail_open_must_not_run)
    monkeypatch.setattr(canary, "_provider_send", _prov)

    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-sup-toctou-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.SKIPPED
    assert res["reason"] == "suppressed"
    assert res["provider_called"] is False
    assert called["n"] == 0
    assert reads["n"] == 1


def test_suppression_structural_corruption_blocks(monkeypatch, tmp_path):
    """Identity-less / partial suppression objects must block, not look empty."""
    from app.platform import email_unsub

    called = {"n": 0}

    async def _prov(*_a, **_k):
        called["n"] += 1
        return {"sent": True, "provider_called": True}

    monkeypatch.setattr(canary, "_provider_send", _prov)

    for idx, payload in enumerate(("{}", '{"event":"attempt"}', '{"email":""}')):
        bad = tmp_path / f"email_suppression_struct_{idx}.jsonl"
        bad.write_text(payload + "\n", encoding="utf-8")
        monkeypatch.setattr(email_unsub, "_store_or_none", lambda p=bad: p)
        monkeypatch.setattr(email_unsub, "_store_path", lambda p=bad: p)
        res = asyncio.run(
            canary.send_canary(
                to_email="owner@example.com",
                idempotency_key=f"idem-sup-struct-{idx:02d}",
                confirm=True,
            )
        )
        assert res["outcome"] == canary.BLOCKED, payload
        assert res["reason"] == "suppression_ledger_untrusted", payload
        assert called["n"] == 0


def test_suppression_valid_match_from_same_snapshot(monkeypatch, tmp_path):
    """Valid suppression row blocks send from the strict snapshot (no fail-open)."""
    from app.platform import email_unsub

    ledger = tmp_path / "email_suppression.jsonl"
    ledger.write_text(
        json.dumps(
            {
                "email": "Owner@Example.com",
                "scope": "email_address",
                "channel": "email",
                "ts": int(time.time()),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(email_unsub, "_store_or_none", lambda: ledger)
    monkeypatch.setattr(email_unsub, "_store_path", lambda: ledger)

    def _fail_open_must_not_run(**_k):
        raise AssertionError("fail-open is_contact_suppressed must not run")

    called = {"n": 0}

    async def _prov(*_a, **_k):
        called["n"] += 1
        return {"sent": True, "provider_called": True}

    monkeypatch.setattr(email_unsub, "is_contact_suppressed", _fail_open_must_not_run)
    monkeypatch.setattr(canary, "_provider_send", _prov)

    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-sup-match-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.SKIPPED
    assert res["reason"] == "suppressed"
    assert called["n"] == 0


def test_attempt_ledger_structural_corruption_blocks(tmp_path, monkeypatch):
    """Structurally invalid but JSON-valid attempt rows must block before I/O."""
    called = {"n": 0}

    async def _prov(*_a, **_k):
        called["n"] += 1
        return {"sent": True, "provider_called": True}

    monkeypatch.setattr(canary, "_provider_send", _prov)
    monkeypatch.setattr(canary, "_suppressed", lambda _e: False)

    for idx, payload in enumerate(
        (
            "{}",
            '{"event":"attempt"}',
            json.dumps({"event": "attempt", "idempotency_key": "k", "ts": 1.0}),
        )
    ):
        ledger = tmp_path / f"attempts_struct_{idx}.jsonl"
        ledger.write_text(payload + "\n", encoding="utf-8")
        monkeypatch.setattr(canary, "_attempts_path", lambda *, create=False, p=ledger: p)
        monkeypatch.setattr(canary, "_lock_target", lambda p=ledger: str(p))
        res = asyncio.run(
            canary.send_canary(
                to_email="owner@example.com",
                idempotency_key=f"idem-attempt-struct-{idx:02d}",
                confirm=True,
            )
        )
        assert res["outcome"] == canary.BLOCKED, payload
        assert res["reason"] == "attempt_ledger_corrupt", payload
        assert res["provider_called"] is False
        assert called["n"] == 0
        pf = canary.preflight()
        assert pf["ok"] is False
        assert pf["reason"] == "attempt_ledger_corrupt"


def test_definite_pre_network_failure_does_not_consume_cap(monkeypatch):
    """A local dependency/config failure is not a provider attempt."""
    monkeypatch.setattr(canary, "_suppressed", lambda _e: False)
    monkeypatch.setattr(
        canary,
        "_smtp_or_api_configured",
        lambda: {
            "api_available": True,
            "smtp_user_present": False,
            "smtp_password_present": False,
            "send_path_ready": True,
        },
    )
    calls = {"n": 0}

    async def _local_failure(*_a, **_k):
        calls["n"] += 1
        raise canary.ProviderNotCalledError("httpx_missing")

    monkeypatch.setattr(canary, "_provider_send", _local_failure)
    first = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-pre-network-a-01",
            confirm=True,
        )
    )
    assert first["outcome"] == canary.FAILED
    assert first["reason"] == "httpx_missing"
    assert first["provider_called"] is False

    async def _sent(*_a, **_k):
        calls["n"] += 1
        return {"sent": True, "mode": "resend", "provider_called": True}

    monkeypatch.setattr(canary, "_provider_send", _sent)
    second = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-pre-network-b-02",
            confirm=True,
        )
    )
    assert second["outcome"] == canary.SENT
    assert calls["n"] == 2


def test_no_provider_io_while_file_lock_held(monkeypatch):
    from app.utils import file_lock as locks

    holding = {"lock": False}
    orig = locks.file_lock

    @contextlib.contextmanager
    def _tracked(path, timeout_s=5.0):
        with orig(path, timeout_s=timeout_s) as locked:
            holding["lock"] = True
            try:
                yield locked
            finally:
                holding["lock"] = False

    async def _prov(*_a, **_k):
        assert holding["lock"] is False, "provider I/O must run outside the claim lock"
        return {
            "sent": True,
            "mode": "resend",
            "provider_called": True,
            "list_unsubscribe_attached": True,
        }

    monkeypatch.setattr(locks, "file_lock", _tracked)
    monkeypatch.setattr(canary, "_provider_send", _prov)
    monkeypatch.setattr(canary, "_suppressed", lambda _e: False)
    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-lock-scope-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.SENT
    assert holding["lock"] is False


def _child_hold_canary_lock(lock_target: str, ready_file: str, hold_s: float) -> None:
    """Separate OS process — holds the sidecar lock so the parent cannot claim."""
    import time as _t
    from pathlib import Path as _P

    from app.utils.file_lock import file_lock

    with file_lock(lock_target, timeout_s=2.0) as locked:
        if not locked:
            _P(ready_file).write_text("lock_failed", encoding="utf-8")
            return
        _P(ready_file).write_text("ready", encoding="utf-8")
        _t.sleep(hold_s)


def test_cross_process_os_lock_blocks_second_claim(tmp_path, monkeypatch):
    ledger = tmp_path / "attempts.jsonl"
    ready = tmp_path / "ready.txt"
    monkeypatch.setattr(canary, "_attempts_path", lambda *, create=False: ledger)
    monkeypatch.setattr(canary, "_lock_target", lambda: str(ledger))
    monkeypatch.setattr(canary, "_suppressed", lambda _e: False)

    called = {"n": 0}

    async def _prov(*_a, **_k):
        called["n"] += 1
        return {"sent": True, "mode": "resend", "provider_called": True}

    monkeypatch.setattr(canary, "_provider_send", _prov)

    import app.utils.file_lock as fl

    real = fl.file_lock

    @contextlib.contextmanager
    def _short_lock(path, timeout_s=5.0):
        with real(path, timeout_s=0.3) as locked:
            yield locked

    monkeypatch.setattr(fl, "file_lock", _short_lock)

    # "spawn" starts a FRESH interpreter, so the child pays the full `app`
    # import cost before it can take the lock. Alone that is a couple of
    # seconds; inside a batch run on a loaded Windows box it repeatedly
    # exceeded a 10s budget, so this test failed for machine speed rather than
    # for lock behaviour. Budget the startup generously and hold the lock for
    # longer than the parent can possibly need, so the assertions below still
    # measure contention and nothing here is weakened.
    ctx = multiprocessing.get_context("spawn")
    child = ctx.Process(
        target=_child_hold_canary_lock,
        args=(str(ledger), str(ready), 60.0),
    )
    child.start()
    try:
        deadline = time.time() + 120
        while time.time() < deadline and not ready.exists() and child.is_alive():
            time.sleep(0.05)
        assert ready.exists(), (
            "lock-holding child never signalled ready "
            f"(alive={child.is_alive()}, exitcode={child.exitcode}) — "
            "child startup budget exceeded, not a locking failure"
        )
        assert ready.read_text(encoding="utf-8") == "ready", (
            "child could not acquire the sidecar lock; contention below would "
            "not be measuring what this test claims"
        )

        res = asyncio.run(
            canary.send_canary(
                to_email="owner@example.com",
                idempotency_key="idem-xproc-01",
                confirm=True,
            )
        )
        assert res["outcome"] == canary.BLOCKED
        assert res["reason"] == "idempotency_lock_unavailable"
        assert res["provider_called"] is False
        assert called["n"] == 0
    finally:
        # The child now deliberately outlives the assertions, so reclaim it
        # directly instead of waiting out its hold.
        if child.is_alive():
            child.terminate()
        child.join(timeout=15)
        if child.is_alive():  # pragma: no cover - terminate did not take
            child.kill()
            child.join(timeout=5)


def test_canonical_cutover_refuses_hostile_checkout_ledger(monkeypatch, tmp_path):
    """After cutover, poisoned checkout ledger must not be authoritative."""
    root = tmp_path / "runtime_root"
    root.mkdir()
    checkout = tmp_path / "checkout" / "data" / "owner_email_canary"
    checkout.mkdir(parents=True)
    hostile = checkout / "attempts.jsonl"
    # Hostile checkout claims today's slot already taken — must be ignored.
    hostile.write_text(
        json.dumps(
            {
                "event": "attempt",
                "ts": time.time(),
                "idempotency_key": "hostile-key-xxxxxxxx",
                "outcome": "pending",
                "provider_called": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    for row in manifest.STORES:
        if row["store_id"] == "ops.owner_email_canary":
            monkeypatch.setitem(row, "migration_state", manifest.DUAL_READ_PRE_CUTOVER)

    started = datetime.now(timezone.utc) - timedelta(minutes=5)
    marker = {
        "schema_version": mk.SCHEMA_VERSION,
        "manifest_version": manifest.MANIFEST_VERSION,
        "runtime_root_identifier": str(root),
        "source_production_sha": "aaaaaaaa",
        "migrated_store_ids": ["ops.owner_email_canary"],
        "source_manifest_reference": "app/platform/runtime_data_manifest.py",
        "verification_reference": "tests/test_owner_email_canary.py",
        "cutover_started_at": started.isoformat(),
        "cutover_completed_at": datetime.now(timezone.utc).isoformat(),
        "validation_status": mk.VALIDATION_PASSED,
        "rollback_reference": "legacy retained",
    }
    assert mk.validate_marker(marker) == [], mk.validate_marker(marker)
    (root / "migration").mkdir(parents=True, exist_ok=True)
    (root / "migration" / "cutover.json").write_text(json.dumps(marker), encoding="utf-8")
    monkeypatch.setenv(rd.ENV_KEY, str(root))
    monkeypatch.setenv(auth.CUTOVER_GATE_ENV, "1")
    monkeypatch.delenv(rd.LEGACY_ENV_KEY, raising=False)

    # Pass the poisoned checkout path as legacy — CANONICAL must still ignore it.
    def _real_path(*, create: bool = False):
        path = auth.resolve_store_path(
            store_id="ops.owner_email_canary",
            legacy_path=hostile,
            target_segments=("ops", "owner_email_canary", "attempts.jsonl"),
        )
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr(canary, "_attempts_path", _real_path)
    monkeypatch.setattr(canary, "_lock_target", lambda: str(_real_path(create=False)))
    monkeypatch.setattr(canary, "_suppressed", lambda _e: False)

    active = _real_path(create=False)
    assert auth.authority_mode("ops.owner_email_canary") is auth.AuthorityMode.CANONICAL
    assert active.resolve() != hostile.resolve()
    assert str(root) in str(active.resolve())
    assert canary._iter_attempts() == []  # empty canonical, not poison

    called = {"n": 0}

    async def _ok(*_a, **_k):
        called["n"] += 1
        return {
            "sent": True,
            "mode": "resend",
            "provider_called": True,
            "list_unsubscribe_attached": True,
        }

    monkeypatch.setattr(canary, "_provider_send", _ok)
    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-canonical-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.SENT
    assert called["n"] == 1
    # Write landed on canonical, not hostile checkout.
    assert active.exists()
    assert "idem-canonical-01" in active.read_text(encoding="utf-8")
    assert "idem-canonical-01" not in hostile.read_text(encoding="utf-8")
    assert "hostile-key-xxxxxxxx" in hostile.read_text(encoding="utf-8")


def test_api_last_exposes_preflight_failure_not_fake_ok(api_client, monkeypatch):
    app.dependency_overrides[require_super_admin] = lambda: create_mock_user(
        role=UserRole.SUPER_ADMIN
    )

    def _boom_iter():
        raise canary.AttemptLedgerError("attempt_ledger_corrupt", detail="JSONDecodeError")

    monkeypatch.setattr(canary, "_iter_attempts", _boom_iter)
    r = api_client.get("/api/admin/owner-email-canary/last")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["reason"] == "attempt_ledger_corrupt"
    assert body["outcome"] == canary.BLOCKED


def test_api_last_requires_super_admin(api_client):
    app.dependency_overrides.pop(require_super_admin, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_current_user] = lambda: create_mock_user(role=UserRole.ADMIN)
    r = api_client.get("/api/admin/owner-email-canary/last")
    assert r.status_code == 403


def test_api_send_requires_super_admin_not_viewer(api_client):
    app.dependency_overrides.pop(require_super_admin, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_current_user] = lambda: create_mock_user(role=UserRole.VIEWER)
    r = api_client.post(
        "/api/admin/owner-email-canary/send",
        json={
            "to_email": "owner@example.com",
            "idempotency_key": "idem-viewer-rbac-01",
            "confirm": True,
            "confirm_owner_inbox": True,
        },
    )
    assert r.status_code == 403


def test_pre_network_failure_allows_key_rotation(monkeypatch):
    """smtp_not_configured must not consume daily cap — new key may proceed."""
    called = {"n": 0}
    monkeypatch.setattr(canary, "_suppressed", lambda _e: False)
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

    async def _boom(*_a, **_k):
        called["n"] += 1
        return {"sent": True, "provider_called": True}

    monkeypatch.setattr(canary, "_provider_send", _boom)
    r1 = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-rotate-a-01",
            confirm=True,
        )
    )
    assert r1["outcome"] == canary.FAILED
    assert r1["provider_called"] is False
    assert called["n"] == 0

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

    async def _ok(*_a, **_k):
        called["n"] += 1
        return {
            "sent": True,
            "mode": "resend",
            "provider_called": True,
            "list_unsubscribe_attached": True,
        }

    monkeypatch.setattr(canary, "_provider_send", _ok)
    r2 = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-rotate-b-02",
            confirm=True,
        )
    )
    assert r2["outcome"] == canary.SENT
    assert called["n"] == 1
