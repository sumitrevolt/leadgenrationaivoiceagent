"""Contracts for the tri-state store authority.

Everything a migrated Tier-0 store depends on lives here, so a defect in this
module would reach the invoice ledger, the consent ledger and the voice kill
switch at once. The three A1 telephony stores exist to shake this out BEFORE
money and compliance move.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.platform import runtime_data as rd
from app.platform import runtime_data_authority as auth
from app.platform import runtime_data_manifest as manifest
from app.platform import runtime_data_marker as mk

STORE = "telephony.voice_kill_switch"
LEGACY = Path("data/voice_launch_kill.json")
TARGET = ("telephony", "voice_launch_kill.json")
OVERRIDE_ENV = "VOICE_LAUNCH_KILL_FILE"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Every test states its own configuration. No ambient inheritance."""
    for key in (rd.ENV_KEY, rd.LEGACY_ENV_KEY, auth.CUTOVER_GATE_ENV, OVERRIDE_ENV):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("APP_ENV", "test")


def _kwargs(**extra):
    base = {
        "store_id": STORE,
        "legacy_path": LEGACY,
        "target_segments": TARGET,
        "override_env": OVERRIDE_ENV,
    }
    base.update(extra)
    return base


def _write_marker(root: Path, store_ids: list[str], monkeypatch) -> Path:
    """A marker the real validator accepts.

    The validator refuses to call a store 'migrated' while the manifest still
    records it as LEGACY_IN_CHECKOUT, so the manifest row is moved here too —
    that transition is commit 3's job, and this test must not depend on the
    order the commits land in.
    """
    for row in manifest.STORES:
        if row["store_id"] in store_ids:
            monkeypatch.setitem(row, "migration_state", manifest.DUAL_READ_PRE_CUTOVER)

    started = datetime.now(timezone.utc) - timedelta(minutes=5)
    marker = {
        "schema_version": mk.SCHEMA_VERSION,
        "manifest_version": manifest.MANIFEST_VERSION,
        "runtime_root_identifier": str(root),
        "source_production_sha": "aa93f3ce",
        "migrated_store_ids": store_ids,
        "source_manifest_reference": "app/platform/runtime_data_manifest.py",
        "verification_reference": "tests/test_runtime_data_authority.py",
        "cutover_started_at": started.isoformat(),
        "cutover_completed_at": datetime.now(timezone.utc).isoformat(),
        "validation_status": mk.VALIDATION_PASSED,
        "rollback_reference": "legacy sources retained at /opt/leadgen/data",
    }
    path = root / "migration" / "cutover.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(marker), encoding="utf-8")
    assert mk.validate_marker(marker) == [], mk.validate_marker(marker)
    return path


# --------------------------------------------------------------------- LEGACY
def test_root_unset_is_legacy_and_uses_the_exact_legacy_path():
    """Merging the migration must change nothing until a root is configured."""
    a = auth.resolve_store_authority(**_kwargs())
    assert a.mode is auth.AuthorityMode.LEGACY
    assert a.active_path == LEGACY
    assert a.canonical_path is None
    assert a.source is auth.AuthoritySource.LEGACY_DEFAULT


def test_legacy_mode_keeps_an_explicit_override(monkeypatch, tmp_path):
    """Production already sets some of these. They must not break on merge day."""
    custom = tmp_path / "elsewhere" / "kill.json"
    monkeypatch.setenv(OVERRIDE_ENV, str(custom))
    a = auth.resolve_store_authority(**_kwargs())
    assert a.mode is auth.AuthorityMode.LEGACY
    assert a.active_path == custom
    assert a.source is auth.AuthoritySource.EXPLICIT_OVERRIDE


# ------------------------------------------------------- MIGRATION_VALIDATION
def test_configured_root_without_cutover_does_not_move_the_writer(monkeypatch, tmp_path):
    """The bulk copy runs in this mode. Live writers must stay where they are."""
    monkeypatch.setenv(rd.ENV_KEY, str(tmp_path))
    a = auth.resolve_store_authority(**_kwargs())
    assert a.mode is auth.AuthorityMode.MIGRATION_VALIDATION
    assert a.active_path == LEGACY, "a configured root alone must not switch the authority"
    assert a.canonical_path == tmp_path / "telephony" / "voice_launch_kill.json"


def test_cutover_gate_without_a_marker_is_not_canonical(monkeypatch, tmp_path):
    monkeypatch.setenv(rd.ENV_KEY, str(tmp_path))
    monkeypatch.setenv(auth.CUTOVER_GATE_ENV, "1")
    a = auth.resolve_store_authority(**_kwargs())
    assert a.mode is auth.AuthorityMode.MIGRATION_VALIDATION
    assert a.active_path == LEGACY


def test_marker_listing_another_store_leaves_this_one_alone(monkeypatch, tmp_path):
    """A partially migrated cutover is normal; per-store granularity makes it safe."""
    monkeypatch.setenv(rd.ENV_KEY, str(tmp_path))
    monkeypatch.setenv(auth.CUTOVER_GATE_ENV, "1")
    _write_marker(tmp_path, ["telephony.dial_suppression"], monkeypatch)
    a = auth.resolve_store_authority(**_kwargs())
    assert a.mode is auth.AuthorityMode.MIGRATION_VALIDATION
    assert a.active_path == LEGACY


# ------------------------------------------------------------------ CANONICAL
def test_canonical_mode_uses_only_the_external_target(monkeypatch, tmp_path):
    monkeypatch.setenv(rd.ENV_KEY, str(tmp_path))
    monkeypatch.setenv(auth.CUTOVER_GATE_ENV, "1")
    _write_marker(tmp_path, [STORE], monkeypatch)
    a = auth.resolve_store_authority(**_kwargs())
    assert a.mode is auth.AuthorityMode.CANONICAL
    assert a.active_path == tmp_path / "telephony" / "voice_launch_kill.json"
    assert a.source is auth.AuthoritySource.CANONICAL_TARGET
    assert a.is_canonical


def test_canonical_mode_refuses_a_stale_override(monkeypatch, tmp_path):
    """A forgotten VOICE_LAUNCH_KILL_FILE=data/... must not survive the cutover."""
    monkeypatch.setenv(rd.ENV_KEY, str(tmp_path))
    monkeypatch.setenv(auth.CUTOVER_GATE_ENV, "1")
    monkeypatch.setenv(OVERRIDE_ENV, "data/voice_launch_kill.json")
    _write_marker(tmp_path, [STORE], monkeypatch)
    with pytest.raises(rd.RuntimeDataError) as exc:
        auth.resolve_store_authority(**_kwargs())
    message = str(exc.value)
    assert STORE in message and OVERRIDE_ENV in message
    # Non-secret: the reason names the VARIABLE, never its value.
    assert "data/voice_launch_kill.json" not in message


def test_canonical_mode_accepts_an_override_pointing_at_the_canonical_target(monkeypatch, tmp_path):
    monkeypatch.setenv(rd.ENV_KEY, str(tmp_path))
    monkeypatch.setenv(auth.CUTOVER_GATE_ENV, "1")
    target = tmp_path / "telephony" / "voice_launch_kill.json"
    monkeypatch.setenv(OVERRIDE_ENV, str(target))
    _write_marker(tmp_path, [STORE], monkeypatch)
    a = auth.resolve_store_authority(**_kwargs())
    assert a.mode is auth.AuthorityMode.CANONICAL
    assert a.active_path == target


def test_canonical_mode_has_no_legacy_read_fallback(monkeypatch, tmp_path):
    """The canonical file is absent — the answer is still the canonical path.

    Falling back here would answer a suppression or consent question from a
    checkout copy that is no longer authoritative.
    """
    monkeypatch.setenv(rd.ENV_KEY, str(tmp_path))
    monkeypatch.setenv(auth.CUTOVER_GATE_ENV, "1")
    _write_marker(tmp_path, [STORE], monkeypatch)
    a = auth.resolve_store_authority(**_kwargs())
    assert not a.active_path.exists()
    assert a.active_path != LEGACY


# -------------------------------------------------------- companions + policy
@pytest.mark.parametrize("canonical", [False, True])
def test_lock_and_temp_sit_beside_the_active_target(monkeypatch, tmp_path, canonical):
    if canonical:
        monkeypatch.setenv(rd.ENV_KEY, str(tmp_path))
        monkeypatch.setenv(auth.CUTOVER_GATE_ENV, "1")
        _write_marker(tmp_path, [STORE], monkeypatch)
    active = auth.resolve_store_authority(**_kwargs()).active_path
    assert auth.resolve_lock_path(**_kwargs()).parent == active.parent
    assert auth.resolve_temp_path(suffix=".tmp_kill", **_kwargs()).parent == active.parent
    assert auth.resolve_lock_path(**_kwargs()).name.endswith(".lock")


def test_resolution_is_not_cached_at_import(monkeypatch, tmp_path):
    """A path frozen at import is what makes a store impossible to redirect."""
    first = auth.resolve_store_authority(**_kwargs())
    monkeypatch.setenv(rd.ENV_KEY, str(tmp_path))
    second = auth.resolve_store_authority(**_kwargs())
    assert first.mode is auth.AuthorityMode.LEGACY
    assert second.mode is auth.AuthorityMode.MIGRATION_VALIDATION


def test_traversal_in_target_segments_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv(rd.ENV_KEY, str(tmp_path))
    with pytest.raises(rd.RuntimeDataError):
        auth.resolve_store_authority(**_kwargs(target_segments=("..", "escape.json")))


def test_cutover_gate_name_matches_the_deployment_preflight():
    """Two names for one gate would let the deploy and the app disagree."""
    text = (
        Path(__file__).resolve().parents[1] / "scripts" / "runtime_data_preflight.py"
    ).read_text(encoding="utf-8")
    assert f'CUTOVER_GATE_ENV = "{auth.CUTOVER_GATE_ENV}"' in text


def test_describe_store_leaks_no_values(monkeypatch, tmp_path):
    monkeypatch.setenv(rd.ENV_KEY, str(tmp_path))
    d = auth.describe_store(**_kwargs())
    assert d["mode"] == auth.AuthorityMode.MIGRATION_VALIDATION.value
    assert d["store_id"] == STORE
    assert set(d) <= {"store_id", "mode", "source", "active_path", "canonical_path", "error"}
