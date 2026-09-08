"""Activation readiness — advisory compliance section (2026-07 audit fix).

Adds a `compliance` block to GET /api/activation/readiness that surfaces
recording-retention arming, a DND fail-open (TRAI) risk warning, and the
effective (post-clamp) promotional calling window — WITHOUT changing the
existing `ready_for_first_paid_customer` boolean for existing consumers.
"""

from __future__ import annotations

import pytest

from app.api import activation as ax


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        "DND_FAIL_OPEN",
        "RECORDING_RETENTION",
        "COMPLIANCE_PROMO_START",
        "COMPLIANCE_PROMO_END",
    ):
        monkeypatch.delenv(k, raising=False)


def _probe(compliance: dict, key: str) -> dict:
    for p in compliance.get("probes", []):
        if p.get("key") == key:
            return p
    raise AssertionError(f"probe {key!r} missing from compliance section")


async def test_readiness_has_compliance_section() -> None:
    out = await ax.activation_readiness(_user=None)  # type: ignore[arg-type]
    assert "compliance" in out
    comp = out["compliance"]
    # required probes present
    _probe(comp, "recording_retention_armed")
    _probe(comp, "dnd_fail_closed")
    # effective promo window surfaced
    win = comp["promo_calling_window"]
    assert set(win) == {"start", "end", "tz"}
    assert win["tz"] == "IST"


async def test_existing_boolean_shape_unchanged() -> None:
    """The pre-existing readiness contract keys/types are untouched."""
    out = await ax.activation_readiness(_user=None)  # type: ignore[arg-type]
    assert isinstance(out["ready_for_first_paid_customer"], bool)
    assert isinstance(out["blocker_count"], int)
    assert "items" in out and isinstance(out["items"], list)


async def test_dnd_fail_open_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DND_FAIL_OPEN", "1")
    out = await ax.activation_readiness(_user=None)  # type: ignore[arg-type]
    probe = _probe(out["compliance"], "dnd_fail_closed")
    assert probe["status"] == "WARN"
    assert probe["checks"]["dnd_fail_open"] is True
    assert "TRAI" in probe["action"]


async def test_dnd_fail_closed_ok_when_unset() -> None:
    out = await ax.activation_readiness(_user=None)  # type: ignore[arg-type]
    probe = _probe(out["compliance"], "dnd_fail_closed")
    assert probe["status"] == "OK"


async def test_recording_retention_ok_when_armed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RECORDING_RETENTION", "1")
    out = await ax.activation_readiness(_user=None)  # type: ignore[arg-type]
    probe = _probe(out["compliance"], "recording_retention_armed")
    assert probe["status"] == "OK"


async def test_recording_retention_warn_when_unset() -> None:
    out = await ax.activation_readiness(_user=None)  # type: ignore[arg-type]
    probe = _probe(out["compliance"], "recording_retention_armed")
    assert probe["status"] == "WARN"


async def test_promo_window_clamped_in_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bad promo-END override is surfaced already clamped to the 21:00 ceiling."""
    monkeypatch.setenv("COMPLIANCE_PROMO_END", "23:00")
    out = await ax.activation_readiness(_user=None)  # type: ignore[arg-type]
    win = out["compliance"]["promo_calling_window"]
    assert win["start"] == "09:00"
    assert win["end"] == "21:00"
