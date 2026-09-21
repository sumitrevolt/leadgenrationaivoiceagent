"""wiring_gaps(): TypeSafe credential gap (silent-INERT class, 2026-09-18).

Why this exists: TypeSafe judgments ("lead scoring / outreach variants / reply
triage") sit behind a client that FAILS SOFT — no key means every call site
silently returns its fallback. Nothing turns red: the job runs, the heartbeat is
green, the judgment never happened. The owner hit exactly this on 2026-09-18
("kal ho rahi thi, aaj nahi") after a leaked key was correctly removed from
source (979c2229).

So the credential state must be visible where "armed but unwired" already shows
up. Pinned properties:
  1. ABSENT key -> a TypeSafe gap (default ON, because call sites are unconditional)
  2. PRESENT key -> no gap (no false alarm)
  3. ROTATION_REQUIRED (exposed fingerprint) -> a gap, with the fingerprint but
     NEVER the credential value
  4. TYPESAFE_ENABLED=0 -> opted out, no gap
  5. the check is config-only: no network call, and a raising provider cannot
     break wiring_gaps()/health()

All keys below are OBVIOUSLY-SYNTHETIC dummies, never real credentials.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.platform import automation_health as ah  # noqa: E402
from app.platform import typesafe_integration as tsi  # noqa: E402

DUMMY_KEY = "apikey_dummy_0000000000000000000000000000000000000000000000000000000000"

_OTHER_FLAGS = ("GSC_ENABLED", "CRM_SYNC", "CRM_SYNC_PULL", "SOCIAL_ENGINE", "WHATSAPP_AUTO_SEND")


def _isolate(monkeypatch, tmp_path: Path) -> None:
    """Neutralise every other gap source + the beat-registration sweep."""
    for flag in _OTHER_FLAGS:
        monkeypatch.setenv(flag, "0")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("TYPEsafe_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_ENABLED", raising=False)
    monkeypatch.setattr(ah, "_beat_registration_gaps", lambda: [])
    monkeypatch.setenv("AUTOMATION_HEALTH_ALERTS", "0")

    # This checkout can have live TS_A..TS_D vault slots. These tests exercise
    # env-state transitions, so isolate every non-env key source explicitly.
    def _env_only_keys():
        raw = []
        for name in ("TYPESAFE_API_KEYS", "TYPESAFE_API_KEY", "TYPEsafe_API_KEY"):
            raw.extend(tsi._split_keys(os.getenv(name, "")))
        for i in range(1, 5):
            raw.extend(tsi._split_keys(os.getenv(f"TYPESAFE_API_KEY_{i}", "")))
        return [
            key
            for key in dict.fromkeys(raw)
            if tsi.fingerprint(key) not in tsi.COMPROMISED_FINGERPRINTS
        ]

    monkeypatch.setattr(tsi, "_load_all_keys", _env_only_keys)


def _typesafe_gaps() -> list[dict]:
    return [g for g in ah.wiring_gaps() if g.get("key") == "TYPESAFE_API_KEY"]


def test_absent_credential_reports_gap(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    gaps = _typesafe_gaps()
    assert len(gaps) == 1
    assert "INERT" in gaps[0]["note"]
    assert gaps[0]["missing"] == "TYPESAFE_API_KEY"


def test_present_credential_no_false_alarm(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("TYPESAFE_API_KEY", DUMMY_KEY)
    assert _typesafe_gaps() == []


def test_legacy_env_name_also_counts_as_present(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("TYPEsafe_API_KEY", DUMMY_KEY)
    assert _typesafe_gaps() == []


def test_exposed_fingerprint_reports_rotation_gap(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("TYPESAFE_API_KEY", DUMMY_KEY)
    monkeypatch.setitem(tsi.COMPROMISED_FINGERPRINTS, tsi.fingerprint(DUMMY_KEY), "test fixture")
    gaps = _typesafe_gaps()
    assert len(gaps) == 1
    assert "EXPOSED" in gaps[0]["note"]
    assert tsi.fingerprint(DUMMY_KEY) in gaps[0]["note"]


def test_opt_out_suppresses_the_gap(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("TYPESAFE_ENABLED", "0")
    assert _typesafe_gaps() == []


def test_gap_payload_never_leaks_the_key(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("TYPESAFE_API_KEY", DUMMY_KEY)
    monkeypatch.setitem(tsi.COMPROMISED_FINGERPRINTS, tsi.fingerprint(DUMMY_KEY), "test fixture")
    assert DUMMY_KEY not in str(ah.wiring_gaps())


def test_credential_state_is_config_only_and_never_raises(monkeypatch, tmp_path):
    """No network: credential_state() must answer from env alone."""
    _isolate(monkeypatch, tmp_path)
    st = tsi.credential_state()
    assert st["state"] == "ABSENT" and st["enabled"] is False
    assert st["fingerprint"] == "" and "key" not in st

    monkeypatch.setenv("TYPESAFE_API_KEY", DUMMY_KEY)
    st2 = tsi.credential_state()
    assert st2["state"] == "PRESENT" and st2["enabled"] is True
    assert st2["source"] == "env:TYPESAFE_API_KEY"
    assert st2["fingerprint"] == tsi.fingerprint(DUMMY_KEY)
    assert DUMMY_KEY not in str(st2)


def test_broken_credential_provider_cannot_break_wiring_gaps(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    def _boom():
        raise RuntimeError("credential_state exploded")

    monkeypatch.setattr(tsi, "credential_state", _boom)
    assert isinstance(ah.wiring_gaps(), list)


def test_module_tripwire_is_not_empty_and_hashes_are_short(monkeypatch):
    """The trip-wire is a hash list — a fingerprint, never a credential."""
    assert tsi.COMPROMISED_FINGERPRINTS, "trip-wire emptied — exposed keys could be re-armed"
    for fp in tsi.COMPROMISED_FINGERPRINTS:
        assert len(fp) == 12 and all(c in "0123456789abcdef" for c in fp)


def test_script_and_module_do_not_drift_on_the_tripwire(tmp_path):
    """scripts/typesafe_status.py must consume the module's list, not fork one."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "typesafe_status_drift_check", ROOT / "scripts" / "typesafe_status.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["typesafe_status_drift_check"] = mod
    spec.loader.exec_module(mod)

    assert mod._TRIPWIRE_LOADED is True, "script fell back to degraded mode (app import failed)"
    assert set(mod.COMPROMISED_FINGERPRINTS) == set(tsi.COMPROMISED_FINGERPRINTS)
    assert mod.fingerprint(DUMMY_KEY) == tsi.fingerprint(DUMMY_KEY)


def test_wiring_gap_does_not_degrade_health_status(monkeypatch, tmp_path):
    """A config gap is informational: it must not flip health().status/ok.

    blast-radius guard: wiring_gaps() feeds Mission Control + the daily brief,
    and a new gap source must never repaint a running system as "degraded".
    """
    import json

    monkeypatch.setattr(ah, "_RUNS", lambda: str(tmp_path / "runs.jsonl"))
    monkeypatch.setattr(ah, "_BEATS", lambda: str(tmp_path / "beats.json"))
    Path(ah._BEATS()).write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(ah, "stale_outputs", lambda: [])
    monkeypatch.setattr(ah, "queue_depth", lambda: {"celery": 0, "heavy": 0, "dlq": 0, "dead": 0})
    monkeypatch.setattr(
        ah,
        "engine_skip_summary",
        lambda hours=48: {"total": 0, "by_engine": {}, "by_job": {}, "latest": []},
    )
    _isolate(monkeypatch, tmp_path)  # no key -> gap is reported
    h = ah.health()
    assert [g["key"] for g in h["wiring_gaps"]] == ["TYPESAFE_API_KEY"]
    assert h["status"] in ("warming_up", "healthy")
    assert h["ok"] is True


@pytest.mark.parametrize("value", ["0", "false", "no", "FALSE"])
def test_opt_out_values_are_honoured(monkeypatch, tmp_path, value):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("TYPESAFE_ENABLED", value)
    assert _typesafe_gaps() == []
