"""A social DRY-RUN must never be indistinguishable from real publishing.

WHY (2026-07-14): the 2026-07-11 canary gate `data/social_engine.json
{"dry_run": true}` was left ON for three days. The engine drained the queue,
FABRICATED PublishResult(ok=True) and marked jobs `published` — while never
calling Postiz. Six self-brand jobs read "published" (post_id empty) and not a
single post ever reached social. The founder only found out by noticing the
silence. Nothing in logs or the drain result said "this is a dry run".

Same class as ADR-095/096 (synthetic/fake state polluting a real status
surface) and the same fix as ADR-097: make the silent state LOUD.

Offline/pure — no providers, no network.
"""

from __future__ import annotations

import asyncio

from app.social_engine import engine


def _drain(monkeypatch, *, dry: bool):
    monkeypatch.setattr(engine, "enabled", lambda: True)
    monkeypatch.setattr(engine, "_dry_run_enabled", lambda: dry)
    # No jobs: we are asserting on the drain's self-report, not on dispatch.
    monkeypatch.setattr(engine.store, "claim_pending", lambda limit: [])
    return asyncio.run(engine.process_queue())


def test_drain_result_reports_dry_run_true(monkeypatch):
    out = _drain(monkeypatch, dry=True)
    assert out["ran"] is True
    # The flag callers/dashboards need in order to badge instead of guess.
    assert out["dry_run"] is True


def test_drain_result_reports_dry_run_false_on_real_publish(monkeypatch):
    out = _drain(monkeypatch, dry=False)
    assert out["ran"] is True
    assert out["dry_run"] is False


def test_dry_run_drain_logs_a_loud_warning(monkeypatch):
    """Three days of silent fake-publishing is what this warning prevents."""
    import logging
    from contextlib import contextmanager

    records: list[str] = []

    class _H(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = _H()
    logger = logging.getLogger("app.social_engine.engine")
    prev = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    try:
        _drain(monkeypatch, dry=True)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)

    blob = " ".join(records).lower()
    assert "dry-run" in blob or "dry run" in blob
    assert "nothing" in blob  # must say nothing is actually posted


def test_real_drain_is_quiet(monkeypatch, caplog):
    """No warning when publishing for real — the alarm must stay meaningful."""
    import logging

    caplog.set_level(logging.WARNING, logger="app.social_engine.engine")
    _drain(monkeypatch, dry=False)
    blob = " ".join(r.getMessage() for r in caplog.records).lower()
    assert "dry-run" not in blob


def test_engine_off_is_still_inert(monkeypatch):
    """The master gate keeps precedence over everything above."""
    monkeypatch.setattr(engine, "enabled", lambda: False)
    out = asyncio.run(engine.process_queue())
    assert out["ran"] is False
    assert out["reason"] == "SOCIAL_ENGINE off"
