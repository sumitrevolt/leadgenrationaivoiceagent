"""Headless Jarvis ingress — loop/posture tests (no network; seams mocked).

Pins the single-consumer contract:
- fail-closed posture (flag off / token missing => honest reason, zero I/O)
- dedupe: a replayed update_id executes exactly once (memory + redis seams)
- watermark persistence across passes
- 409 conflict => honest status + one-shot egress alert hook (never a race)
"""

from __future__ import annotations

import json
import os
import types

import pytest

from app.platform import telegram_ingress as ti


@pytest.fixture()
def off_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_INGRESS_ENABLED", "0")
    monkeypatch.delenv("TELEGRAM_JARVIS_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_INGRESS_BOT_TOKEN", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)


@pytest.fixture()
def on_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_INGRESS_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_JARVIS_BOT_TOKEN", "test-token-" + "x" * 24)
    monkeypatch.delenv("REDIS_URL", raising=False)


def test_disabled_flag_fails_closed_no_network(off_env, monkeypatch):
    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("network seam touched while disabled")

    monkeypatch.setattr(ti, "_get_updates", _boom)
    status = ti.run_ingress_once()
    assert status == {"ok": False, "enabled": False, "reason": "disabled"}
    assert called["n"] == 0
    assert ti.readiness() == {"ok": False, "enabled": False, "reason": "disabled"}


def test_enabled_but_token_missing(off_env, monkeypatch):
    monkeypatch.setenv("TELEGRAM_INGRESS_ENABLED", "1")

    def _boom(*a, **k):
        raise AssertionError("network seam touched without a token")

    monkeypatch.setattr(ti, "_get_updates", _boom)
    status = ti.run_ingress_once()
    assert status["ok"] is False
    assert status["reason"] == "token_unconfigured"
    assert status["ingested"] == 0


def _make_update(update_id: int, text: str = "/status") -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "chat": {"id": 1},
            "from": {"id": 2},
            "text": text,
        },
    }


def test_dedupe_executes_update_once_and_persists_watermark(on_env, monkeypatch):
    """Same update_id replayed across two passes must dispatch once; the
    offset watermark must advance (so a restart resumes, not re-runs)."""
    dispatches = {"n": 0}
    watermark = {"v": 0}

    class FakeDedupe:
        def is_new(self, update_id):
            # simulate redis NX semantics
            if update_id in seen:
                return False
            seen.add(update_id)
            return True

        def watermark_get(self, key):
            return watermark["v"]

        def watermark_set(self, key, val):
            watermark["v"] = val

    seen = set()

    def fake_poll(token, offset, timeout):
        # first pass: two updates; second pass: replay of the older one + new
        if offset <= 100:
            return [_make_update(100), _make_update(101)]
        return [_make_update(100), _make_update(102)]

    monkeypatch.setattr(ti, "_get_updates", fake_poll)
    monkeypatch.setattr(ti, "_dedupe", lambda: FakeDedupe())

    def fake_dispatch(update, send_reply=True):
        dispatches["n"] += 1
        r = types.SimpleNamespace()
        r.success = True
        r.intent = "status_check"
        return r

    import app.integrations.telegram_bot as tb

    monkeypatch.setattr(tb, "get_telegram_bot", lambda: types.SimpleNamespace(
        process_update=fake_dispatch
    ))

    # pass 1: 100 + 101 both new
    s1 = ti.run_ingress_once()
    assert s1["ok"] is True and s1["ingested"] == 2 and s1["watermark"] == 101
    assert dispatches["n"] == 2

    # pass 2: 100 replayed (suppressed), 102 new
    s2 = ti.run_ingress_once()
    assert s2["ok"] is True and s2["ingested"] == 1 and s2["watermark"] == 102
    assert dispatches["n"] == 3  # exactly-once across the replay
    assert watermark["v"] == 102


def test_409_conflict_honest_status_and_one_shot_alert(on_env, monkeypatch):
    alerts = {"n": 0}
    monkeypatch.setattr(
        ti,
        "_alert_conflict",
        lambda fp: alerts.__setitem__("n", alerts["n"] + 1),
    )

    def fake_poll(token, offset, timeout):
        raise ti.IngressError("http_409", "conflicting getUpdates call")

    monkeypatch.setattr(ti, "_get_updates", fake_poll)
    s = ti.run_ingress_once()
    assert s["ok"] is False
    assert s["reason"] == "conflict_another_consumer"
    assert alerts["n"] == 1  # alert hook fired exactly once for this pass


def test_loop_noops_when_disabled(off_env, monkeypatch):
    import threading

    ev = threading.Event()
    ev.set()
    assert ti.run_ingress_loop(stop_event=ev) == 0


def test_loop_refuses_without_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_INGRESS_ENABLED", "1")
    monkeypatch.delenv("TELEGRAM_JARVIS_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_INGRESS_BOT_TOKEN", raising=False)
    import threading

    assert ti.run_ingress_loop(stop_event=threading.Event()) == 1
