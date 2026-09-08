"""wiring_gaps() — "flag ON but backend/creds missing" detection.

A config gap (armed automation that silently no-ops) is a different failure
mode from a runtime outage: the dead-man sees a green heartbeat while the job
does nothing. These tests pin that:

1. Unarmed (all flags off) → no gaps.
2. GSC_ENABLED=1 without usable creds → a GSC gap.
3. GSC_ENABLED=1 WITH creds (via the canonical `gsc.enabled()` gate, which
   honours the `google_sheets_credentials` fallback + file-exists check) →
   NO gap. Regression guard for the re-implemented-check false-alarm.
4. CRM_SYNC=1 with no provider → a CRM gap.
5. A provider module that raises must NOT crash wiring_gaps() — the signal is
   best-effort and must degrade to "no gap for that check", never to an
   exception in the health()/watchdog path.
6. health() carries the `wiring_gaps` field.
"""

from __future__ import annotations

import json

from app.platform import automation_health as ah

_ARMED_FLAGS = ("GSC_ENABLED", "CRM_SYNC", "CRM_SYNC_PULL", "SOCIAL_ENGINE", "WHATSAPP_AUTO_SEND")


def _all_off(monkeypatch) -> None:
    for flag in _ARMED_FLAGS:
        monkeypatch.setenv(flag, "0")


def test_no_gaps_when_nothing_armed(monkeypatch):
    _all_off(monkeypatch)
    assert ah.wiring_gaps() == []


def test_gsc_armed_but_no_creds(monkeypatch):
    _all_off(monkeypatch)
    monkeypatch.setenv("GSC_ENABLED", "1")
    monkeypatch.setattr("app.integrations.gsc.enabled", lambda: False)
    keys = [g["key"] for g in ah.wiring_gaps()]
    assert "GSC_ENABLED" in keys


def test_gsc_armed_with_creds_no_false_alarm(monkeypatch):
    # wiring_gaps must NOT re-implement a narrower cred check than the canonical
    # gsc.enabled() — otherwise the google_sheets_credentials fallback alarms.
    _all_off(monkeypatch)
    monkeypatch.setenv("GSC_ENABLED", "1")
    monkeypatch.setattr("app.integrations.gsc.enabled", lambda: True)
    assert not any(g["key"] == "GSC_ENABLED" for g in ah.wiring_gaps())


def test_crm_sync_armed_but_no_provider(monkeypatch):
    _all_off(monkeypatch)
    monkeypatch.setenv("CRM_SYNC", "1")
    monkeypatch.setattr(
        "app.platform.crm_sync.status",
        lambda client_id="": {"provider": "none", "auto_sync": True},
    )
    assert any(g["key"] == "CRM_SYNC" for g in ah.wiring_gaps())


def test_provider_raise_does_not_crash(monkeypatch):
    _all_off(monkeypatch)
    for flag in _ARMED_FLAGS:
        monkeypatch.setenv(flag, "1")

    def _boom(*_a, **_k):
        raise RuntimeError("provider module exploded")

    monkeypatch.setattr("app.platform.crm_sync.status", _boom)
    monkeypatch.setattr("app.integrations.gsc.enabled", _boom)
    monkeypatch.setattr("app.marketing.postiz_publish.enabled", _boom)
    monkeypatch.setattr("app.integrations.whatsapp_selfhost.is_active_provider", _boom)
    # Best-effort: must return a list and never raise.
    assert isinstance(ah.wiring_gaps(), list)


def test_health_includes_wiring_gaps(tmp_path, monkeypatch):
    monkeypatch.setattr(ah, "_BEATS", lambda: str(tmp_path / "beats.json"))
    with open(ah._BEATS(), "w", encoding="utf-8") as f:
        json.dump({}, f)
    monkeypatch.setattr(
        ah,
        "engine_skip_summary",
        lambda hours=48: {"total": 0, "by_engine": {}, "by_job": {}, "latest": []},
    )
    monkeypatch.setattr(ah, "stale_outputs", lambda: [])
    monkeypatch.setattr(ah, "queue_depth", lambda: {"celery": 0, "heavy": 0, "dlq": 0, "dead": 0})
    _all_off(monkeypatch)
    h = ah.health()
    assert "wiring_gaps" in h
    assert h["wiring_gaps"] == []
