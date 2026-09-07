"""2026-09-06 — body implementation pin for run_whatsapp_automation.

Context: the beat entry was registered in 94439e74 (wiring fix) but the task
BODY was still a stub returning {"status":"ready"}, so auto_sent would have
stayed 0 after deploy. These tests pin the real drain behaviour AND — more
importantly — that every compliance gate fails CLOSED (§5):

    1. WHATSAPP_AUTO_SEND gate + HARD_OFF
    2. genuine DAILY cap (Redis), not a per-run clamp
    3. per-day idempotency (a phone is messaged at most once a day)
    4. fail-closed DND/TRAI scrub — UNVERIFIED == blocked

If any of these tests fail, do NOT "fix" them by loosening an assertion — a
loosened assertion here is a compliance regression, not a flake.
"""

from __future__ import annotations

import importlib

mod = importlib.import_module("app.tasks.whatsapp_automation")

CAND = [
    {"phone": "+919999000001", "status": "new", "name": "A", "niche": "solar"},
    {"phone": "+919999000002", "status": "interested", "name": "B", "niche": "dental"},
]


def _enable(monkeypatch, sent_today=0, done=None, candidates=None, scrub=None, batch=None):
    monkeypatch.setattr(mod, "whatsapp_enabled", lambda: True)
    monkeypatch.setattr(mod, "daily_cap", lambda: 50)
    monkeypatch.setattr(mod, "batch_limit", lambda: 10)
    monkeypatch.setattr(mod, "_budget_state", lambda day: (sent_today, done if done is not None else set()))
    monkeypatch.setattr(mod, "_fetch_candidates", lambda limit: (CAND if candidates is None else candidates))
    if scrub is not None:
        monkeypatch.setattr(mod, "_scrub_dnd", scrub)
    if batch is not None:
        monkeypatch.setattr(mod, "run_whatsapp_batch", batch)


def test_disabled_returns_skipped(monkeypatch):
    monkeypatch.setattr(mod, "whatsapp_enabled", lambda: False)
    result = mod.run_whatsapp_automation()
    assert result["status"] == "skipped"


def test_redis_unavailable_fails_closed(monkeypatch):
    """Cap cannot be enforced -> abort, never send blind."""
    monkeypatch.setattr(mod, "whatsapp_enabled", lambda: True)
    monkeypatch.setattr(mod, "_budget_state", lambda day: (None, None))
    result = mod.run_whatsapp_automation()
    assert result["status"] == "aborted"


def test_daily_cap_is_genuinely_daily(monkeypatch):
    """11 hourly beats must not exceed the DAILY cap."""
    _enable(monkeypatch, sent_today=50)
    result = mod.run_whatsapp_automation()
    assert result["status"] == "skipped"
    assert result["reason"] == "daily cap reached"


def test_no_candidates_is_idle(monkeypatch):
    _enable(monkeypatch, candidates=[])
    result = mod.run_whatsapp_automation()
    assert result["status"] == "idle"


def test_per_day_idempotency_suppresses_repeats(monkeypatch):
    already = {c["phone"] for c in CAND}
    _enable(monkeypatch, done=already)
    result = mod.run_whatsapp_automation()
    assert result["status"] == "idle"
    assert result["skipped_duplicate"] == len(CAND)


def test_dnd_scrub_blocks_everything(monkeypatch):
    async def _scrub(cands):
        return [], len(cands)

    _enable(monkeypatch, scrub=_scrub)
    result = mod.run_whatsapp_automation()
    assert result["status"] == "blocked"
    assert result["skipped_dnd"] == len(CAND)


def test_happy_path_sends_and_records(monkeypatch):
    recorded = {}

    async def _scrub(cands):
        return cands, 0

    async def _batch(leads):
        return {"processed": len(leads), "sent": len(leads), "failed": 0}

    monkeypatch.setattr(mod, "_record_sends", lambda day, phones, sent: recorded.update(
        {"day": day, "phones": phones, "sent": sent}
    ))
    _enable(monkeypatch, scrub=_scrub, batch=_batch)
    result = mod.run_whatsapp_automation()
    assert result["status"] == "ok"
    assert result["sent"] == len(CAND)
    assert result["sent_today"] == len(CAND)
    assert recorded.get("sent") == len(CAND)


def test_scrub_fails_closed_on_unverified_lookup(monkeypatch):
    """UNVERIFIED == DND == BLOCK. This is the §5 TRAI invariant."""
    import app.utils.dnd_checker as dc

    class _Res:
        is_dnd = False
        verified = False  # lookup could not be verified

    class _Checker:
        async def check_single(self, phone, channel=None):
            # OPS-017: the WhatsApp gate must declare the messaging channel so a
            # voice-only carrier-scrub allowance can never clear it.
            assert channel == "messaging", f"expected messaging scrub, got {channel!r}"
            return _Res()

    monkeypatch.setattr(dc, "DNDChecker", _Checker)
    kept, blocked = mod._run_async(mod._scrub_dnd(CAND))
    assert kept == []
    assert blocked == len(CAND)


def test_scrub_fails_closed_when_checker_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _boom(name, *args, **kwargs):
        if name == "app.utils.dnd_checker":
            raise ImportError("no dnd module")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _boom)
    kept, blocked = mod._run_async(mod._scrub_dnd(CAND))
    assert kept == []
    assert blocked == len(CAND)


def test_scrub_keeps_confirmed_non_dnd(monkeypatch):
    import app.utils.dnd_checker as dc

    class _Res:
        is_dnd = False
        verified = True

    class _Checker:
        async def check_single(self, phone, channel=None):
            assert channel == "messaging", f"expected messaging scrub, got {channel!r}"
            return _Res()

    monkeypatch.setattr(dc, "DNDChecker", _Checker)
    kept, blocked = mod._run_async(mod._scrub_dnd(CAND))
    assert len(kept) == len(CAND)
    assert blocked == 0
