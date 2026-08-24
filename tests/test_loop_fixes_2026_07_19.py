"""2026-07-19 loop fixes — 3 regression tests for the 72h-verdict open concerns.

Fix 1: self_improve_tick must stop (without requeue) when tick_slot is denied
       but flag is ON — denied duplicates must not multiply the queue. The slot
       owner already schedules the next tick; watchdog revival is single-locked.

Fix 2: VobizClient.get_balance uses split httpx.Timeout (connect=5s, read=10s)
       and downgrades recurring transport errors to WARNING (was ERROR spam).

Fix 3: Sentry startup diagnostic warns when SENTRY_AUTH_TOKEN/ORG/PROJECT are
       missing while DSN is armed (issue-level API review gap surfaced).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest


# ============================================================ Fix 1
class TestSelfImproveTickSlotDenial:
    """Denied duplicate ticks must terminate instead of multiplying the queue."""

    def test_no_requeue_when_slot_denied_and_flag_on(self, monkeypatch):
        from app.agents import self_improve as si
        from app.tasks import staff_jobs

        queued: list[dict] = []

        async def fake_run_once():
            return {"enabled": True, "skipped": "tick_slot"}

        monkeypatch.setenv("SELF_IMPROVE_LOOP", "1")
        monkeypatch.setattr(si, "run_once", fake_run_once)
        monkeypatch.setattr(si, "enabled", lambda: True)
        monkeypatch.setattr(si, "acquire_tick_slot", lambda: "")  # slot DENIED
        monkeypatch.setattr(si, "release_tick_slot", lambda token: None)
        monkeypatch.setattr(si, "note_tick_requeue", lambda c: None)
        monkeypatch.setattr(si, "gap_seconds", lambda: 180)
        monkeypatch.setattr(
            staff_jobs.self_improve_tick, "apply_async", lambda **kw: queued.append(kw)
        )

        staff_jobs.self_improve_tick.run()

        assert not queued, "Denied duplicate must stop; only slot owner may requeue"

    def test_no_requeue_when_flag_off(self, monkeypatch):
        from app.agents import self_improve as si
        from app.tasks import staff_jobs

        queued: list[dict] = []

        monkeypatch.delenv("SELF_IMPROVE_LOOP", raising=False)
        monkeypatch.setattr(si, "enabled", lambda: False)
        monkeypatch.setattr(si, "acquire_tick_slot", lambda: "")
        monkeypatch.setattr(si, "release_tick_slot", lambda token: None)
        monkeypatch.setattr(
            staff_jobs.self_improve_tick, "apply_async", lambda **kw: queued.append(kw)
        )

        staff_jobs.self_improve_tick.run()
        assert not queued, "Flag OFF = chain must stop, no requeue"

    def test_requeue_still_works_when_slot_acquired(self, monkeypatch):
        from app.agents import self_improve as si
        from app.tasks import staff_jobs

        queued: list[dict] = []

        async def fake_run_once():
            return {"enabled": True, "ok": True, "action": "scrape_leads"}

        monkeypatch.setenv("SELF_IMPROVE_LOOP", "1")
        monkeypatch.setattr(si, "run_once", fake_run_once)
        monkeypatch.setattr(si, "enabled", lambda: True)
        monkeypatch.setattr(si, "acquire_tick_slot", lambda: "tok123")
        monkeypatch.setattr(si, "release_tick_slot", lambda token: None)
        monkeypatch.setattr(si, "note_tick_requeue", lambda c: None)
        monkeypatch.setattr(si, "gap_seconds", lambda: 180)
        monkeypatch.setattr(
            staff_jobs.self_improve_tick, "apply_async", lambda **kw: queued.append(kw)
        )

        staff_jobs.self_improve_tick.run()
        assert queued == [{"countdown": 180}], f"Normal requeue with gap, got {queued}"


# ============================================================ Fix 2
class TestVobizGetBalanceTimeoutHardening:
    """get_balance must use split timeout (connect=5s, read=10s) and downgrade
    recurring transport errors (ConnectTimeout/ConnectError/NetworkError) to
    WARNING level. Was: 15s total timeout + ERROR log every watchdog run."""

    def test_uses_split_timeout_with_short_connect(self, monkeypatch):
        import httpx as _httpx_mod

        from app.telephony import vobiz_handler

        captured: dict[str, Any] = {}

        class _FakeAsyncClient:
            def __init__(self, *args, timeout=None, **kwargs):
                captured["timeout"] = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, *a, **kw):
                class _Resp:
                    status_code = 200

                    def json(self):
                        return {"balance": "25.00"}

                    @property
                    def text(self):
                        return ""

                return _Resp()

        monkeypatch.setattr(_httpx_mod, "AsyncClient", _FakeAsyncClient, raising=False)

        client = vobiz_handler.VobizClient()
        client.auth_id = "AUTH"
        client.auth_token = "TOK"
        client.base_url = "https://api.vobiz.ai/api/v1/Account/AUTH"

        asyncio.run(client.get_balance())

        to = captured.get("timeout")
        assert to is not None, "timeout must be passed"
        assert getattr(to, "connect", None) == 5.0, (
            f"connect timeout must be 5s, got {getattr(to, 'connect', None)}"
        )
        assert getattr(to, "read", None) == 10.0, (
            f"read timeout must be 10s, got {getattr(to, 'read', None)}"
        )

    def test_transport_error_logged_as_warning_not_error(self, monkeypatch):
        import logging

        import httpx as _httpx_mod

        from app.telephony import vobiz_handler

        class _BoomClient:
            def __init__(self, *a, timeout=None, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, *a, **kw):
                raise _httpx_mod.ConnectTimeout("connection timed out")

        monkeypatch.setattr(_httpx_mod, "AsyncClient", _BoomClient, raising=False)

        client = vobiz_handler.VobizClient()
        client.auth_id = "AUTH"
        client.auth_token = "TOK"
        client.base_url = "https://api.vobiz.ai/api/v1/Account/AUTH"

        records: list[logging.LogRecord] = []

        class _H(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = _H()
        logger = vobiz_handler.logger
        prev = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            res = asyncio.run(client.get_balance())
        finally:
            logger.removeHandler(handler)
            logger.setLevel(prev)

        assert res["status_code"] == 0
        assert "ConnectTimeout" in str(res["body"].get("error", ""))

        error_records = [r for r in records if r.levelno >= logging.ERROR]
        warning_records = [
            r
            for r in records
            if r.levelno == logging.WARNING and "transport error" in r.getMessage().lower()
        ]
        assert not error_records, "ConnectTimeout must NOT log as ERROR (recurring noise)"
        assert warning_records, "ConnectTimeout must log as WARNING"


# ============================================================ Fix 3
class TestSentryIssueApiDiagnostic:
    """Startup must warn when SENTRY_DSN is armed but SENTRY_AUTH_TOKEN/ORG/PROJECT
    are missing — surfaces the issue-level API review gap (operator-action)."""

    def test_warning_when_dsn_set_but_api_creds_missing(self, monkeypatch):
        from app.config import settings

        monkeypatch.setenv("SENTRY_DSN", "https://example.com")
        monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("SENTRY_ORG", raising=False)
        monkeypatch.delenv("SENTRY_PROJECT", raising=False)

        missing = settings.missing_sentry_api_creds()
        assert missing == ["SENTRY_AUTH_TOKEN", "SENTRY_ORG", "SENTRY_PROJECT"]

    def test_no_warning_when_all_creds_set(self, monkeypatch):
        from app.config import settings

        monkeypatch.setenv("SENTRY_AUTH_TOKEN", "tok")
        monkeypatch.setenv("SENTRY_ORG", "myorg")
        monkeypatch.setenv("SENTRY_PROJECT", "myproject")

        missing = settings.missing_sentry_api_creds()
        assert missing == [], "All creds set = no missing"
