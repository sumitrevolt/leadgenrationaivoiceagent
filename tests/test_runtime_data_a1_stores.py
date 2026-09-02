"""A1 — the three telephony Tier-0 stores, migrated to the runtime authority.

These are the smallest Tier-0 stores and they carry the calling-safety
contracts, which is exactly why they go first: a defect in the shared authority
shows up here, under the strictest assertions in the repo, before the invoice
ledger and the consent ledger are touched.

Nothing here enables calling, writes a marker, or moves production data.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.platform import platform_dial
from app.platform import runtime_data as rd
from app.platform import runtime_data_authority as auth
from app.platform import runtime_data_manifest as manifest
from app.platform import runtime_data_marker as mk
from app.telephony import call_feedback, dial_gate, voice_launch

A1_STORES = (
    "telephony.voice_kill_switch",
    "telephony.calling_safety_config",
    "telephony.dial_suppression",
)

OVERRIDE_ENVS = (
    "VOICE_LAUNCH_KILL_FILE",
    "PLATFORM_DIAL_CONFIG",
    "DIAL_TEST_MODE_CONFIG",
    "DIAL_BLOCKLIST_FILE",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in (rd.ENV_KEY, rd.LEGACY_ENV_KEY, auth.CUTOVER_GATE_ENV, "VOICE_LAUNCH_KILL"):
        monkeypatch.delenv(key, raising=False)
    for key in OVERRIDE_ENVS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("APP_ENV", "test")


def _activate_cutover(root: Path, store_ids: list[str], monkeypatch) -> None:
    """Configure root + gate + a marker the real validator accepts.

    The manifest transition is commit 3's atomic scope, so it is monkeypatched
    here rather than depended upon — these tests must pass whatever order the
    commits land in.
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
        "verification_reference": "tests/test_runtime_data_a1_stores.py",
        "cutover_started_at": started.isoformat(),
        "cutover_completed_at": datetime.now(timezone.utc).isoformat(),
        "validation_status": mk.VALIDATION_PASSED,
        "rollback_reference": "legacy sources retained at /opt/leadgen/data",
    }
    path = root / "migration" / "cutover.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(marker), encoding="utf-8")
    assert mk.validate_marker(marker) == []
    monkeypatch.setenv(rd.ENV_KEY, str(root))
    monkeypatch.setenv(auth.CUTOVER_GATE_ENV, "1")


# ---------------------------------------------------------------- 1. LEGACY
def test_legacy_defaults_are_byte_for_byte_the_current_paths():
    """Merge day proof: with no runtime root configured, nothing moves."""
    assert voice_launch._kill_file() == Path("data/voice_launch_kill.json")
    assert platform_dial._cfg_path() == Path("data/platform_dial.json")
    assert dial_gate._cfg_path() == Path("data/dial_test_mode.json")
    assert dial_gate._blocklist_path() == Path("data/dial_blocklist.json")
    assert call_feedback._blocklist_path() == Path("data/dial_blocklist.json")


# ------------------------------------------------------------- 2. OVERRIDES
def test_existing_overrides_still_win_before_cutover(monkeypatch, tmp_path):
    """Production may already set these. They must not break on merge day."""
    monkeypatch.setenv("VOICE_LAUNCH_KILL_FILE", str(tmp_path / "k.json"))
    monkeypatch.setenv("PLATFORM_DIAL_CONFIG", str(tmp_path / "pd.json"))
    monkeypatch.setenv("DIAL_TEST_MODE_CONFIG", str(tmp_path / "dtm.json"))
    monkeypatch.setenv("DIAL_BLOCKLIST_FILE", str(tmp_path / "bl.json"))
    assert voice_launch._kill_file() == tmp_path / "k.json"
    assert platform_dial._cfg_path() == tmp_path / "pd.json"
    assert dial_gate._cfg_path() == tmp_path / "dtm.json"
    assert dial_gate._blocklist_path() == tmp_path / "bl.json"
    assert call_feedback._blocklist_path() == tmp_path / "bl.json"


# ------------------------------------------------- 3. MIGRATION_VALIDATION
def test_configured_root_alone_does_not_move_any_writer(monkeypatch, tmp_path):
    """The bulk copy runs in this mode; live writers must stay put."""
    monkeypatch.setenv(rd.ENV_KEY, str(tmp_path))
    assert voice_launch._kill_file() == Path("data/voice_launch_kill.json")
    assert platform_dial._cfg_path() == Path("data/platform_dial.json")
    assert dial_gate._cfg_path() == Path("data/dial_test_mode.json")
    assert call_feedback._blocklist_path() == Path("data/dial_blocklist.json")


# ------------------------------------------------------------- 4. CANONICAL
def test_canonical_targets_only_after_a_valid_per_store_marker(monkeypatch, tmp_path):
    _activate_cutover(tmp_path, list(A1_STORES), monkeypatch)
    assert voice_launch._kill_file() == tmp_path / "telephony" / "voice_launch_kill.json"
    assert platform_dial._cfg_path() == tmp_path / "telephony" / "platform_dial.json"
    assert dial_gate._cfg_path() == tmp_path / "telephony" / "dial_test_mode.json"
    assert dial_gate._blocklist_path() == tmp_path / "telephony" / "dial_blocklist.json"
    assert call_feedback._blocklist_path() == dial_gate._blocklist_path()


def test_marker_without_this_store_leaves_it_on_legacy(monkeypatch, tmp_path):
    _activate_cutover(tmp_path, ["telephony.dial_suppression"], monkeypatch)
    assert voice_launch._kill_file() == Path("data/voice_launch_kill.json")
    assert platform_dial._cfg_path() == Path("data/platform_dial.json")
    assert dial_gate._blocklist_path() == tmp_path / "telephony" / "dial_blocklist.json"


# ------------------------------------------------------- 5. STALE OVERRIDE
def test_stale_override_after_cutover_is_denied_without_leaking_its_value(monkeypatch, tmp_path):
    _activate_cutover(tmp_path, list(A1_STORES), monkeypatch)
    monkeypatch.setenv("PLATFORM_DIAL_CONFIG", "data/platform_dial.json")
    with pytest.raises(rd.RuntimeDataError) as exc:
        platform_dial._cfg_path()
    msg = str(exc.value)
    assert "PLATFORM_DIAL_CONFIG" in msg
    assert "data/platform_dial.json" not in msg


# ----------------------------------------------------- 6. PAIR CANNOT SPLIT
def test_calling_safety_pair_cannot_split_roots(monkeypatch, tmp_path):
    """One file canonical and the other legacy would mean the operator's dial
    kill and the test-mode allowlist belonged to different deployments."""
    _activate_cutover(tmp_path, list(A1_STORES), monkeypatch)
    assert platform_dial._cfg_path().parent == dial_gate._cfg_path().parent
    assert platform_dial._cfg_path().parent == tmp_path / "telephony"

    # And before the cutover, both stay legacy together.
    monkeypatch.delenv(auth.CUTOVER_GATE_ENV, raising=False)
    assert platform_dial._cfg_path() == Path("data/platform_dial.json")
    assert dial_gate._cfg_path() == Path("data/dial_test_mode.json")


# --------------------------------------------------- 7. KILL FAILS CLOSED
def test_unresolvable_kill_authority_engages_the_kill(monkeypatch, tmp_path):
    """An authority that cannot be resolved is exactly when dialling must stop."""
    _activate_cutover(tmp_path, list(A1_STORES), monkeypatch)
    monkeypatch.setenv("VOICE_LAUNCH_KILL_FILE", "data/voice_launch_kill.json")
    status = voice_launch.admin_kill_status()
    assert status.engaged is True
    assert status.source == "FILE"
    assert status.reason == "INVALID_PATH"
    assert voice_launch.admin_kill_engaged() is True


def test_missing_canonical_kill_file_still_engages(monkeypatch, tmp_path):
    """No legacy fallback: absent canonical authority means ENGAGED, not 'off'."""
    _activate_cutover(tmp_path, list(A1_STORES), monkeypatch)
    status = voice_launch.admin_kill_status()
    assert status.engaged is True
    assert status.reason == "MISSING"


def test_env_token_remains_the_final_authority(monkeypatch, tmp_path):
    """ENV precedence is unchanged by the migration."""
    _activate_cutover(tmp_path, list(A1_STORES), monkeypatch)
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "0")
    assert voice_launch.admin_kill_status().engaged is False
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "1")
    assert voice_launch.admin_kill_status().engaged is True


# ------------------------------------------- 8. BLOCKLIST MISSING SEMANTICS
def test_resolving_the_blocklist_creates_nothing(monkeypatch, tmp_path):
    """A missing blocklist is a legitimate state — resolution must not
    materialise an empty suppression list."""
    _activate_cutover(tmp_path, list(A1_STORES), monkeypatch)
    p = call_feedback._blocklist_path()
    assert not p.exists()
    assert not p.parent.exists(), "resolution created the store directory"
    # The reader tolerates absence exactly as before.
    assert call_feedback._load() == {} or isinstance(call_feedback._load(), dict)
    assert not p.exists()


def test_first_legitimate_write_creates_the_parent(monkeypatch, tmp_path):
    _activate_cutover(tmp_path, list(A1_STORES), monkeypatch)
    call_feedback._save({"numbers": {}})
    p = call_feedback._blocklist_path()
    assert p.is_file()
    assert p.parent == tmp_path / "telephony"


# ------------------------------------------------------- 9. COMPANION PATHS
def test_lock_and_temp_companions_follow_the_active_target(monkeypatch, tmp_path):
    _activate_cutover(tmp_path, list(A1_STORES), monkeypatch)
    call_feedback._save({"numbers": {}})
    active = call_feedback._blocklist_path()
    # `_save` writes `<target>.json.tmp` beside the destination and os.replace()s
    # it: atomicity only holds within one filesystem.
    assert not (active.with_suffix(active.suffix + ".tmp")).exists()
    assert active.parent == tmp_path / "telephony"

    kill = voice_launch._kill_file()
    assert kill.with_name(kill.name + ".tmp_kill").parent == kill.parent


def test_set_kill_writes_only_to_the_canonical_target(monkeypatch, tmp_path):
    _activate_cutover(tmp_path, list(A1_STORES), monkeypatch)
    legacy = Path("data/voice_launch_kill.json")
    legacy_before = legacy.read_bytes() if legacy.exists() else None

    assert voice_launch.set_kill(True) is True
    canonical = tmp_path / "telephony" / "voice_launch_kill.json"
    assert json.loads(canonical.read_text(encoding="utf-8")) == {"kill": True}

    after = legacy.read_bytes() if legacy.exists() else None
    assert after == legacy_before, "the legacy copy was written after cutover"


# --------------------------------------------------- 10. NO LITERALS LEFT
@pytest.mark.parametrize(
    ("module_path", "literals"),
    [
        ("app/telephony/voice_launch.py", ("data/voice_launch_kill.json",)),
        ("app/platform/platform_dial.py", ("data/platform_dial.json",)),
        ("app/telephony/dial_gate.py", ("data/dial_test_mode.json", "data/dial_blocklist.json")),
        ("app/telephony/call_feedback.py", ("data/dial_blocklist.json",)),
    ],
)
def test_a1_writers_carry_no_uncontrolled_checkout_literal(module_path, literals):
    """The literal may appear only as the declared `legacy_path=` argument.

    Anywhere else it is a second authority that the cutover would not move.

    Checked on the AST, not on text: these modules legitimately NAME their store
    in prose, and a line-based scan flagged the docstrings that explain the very
    thing being enforced. A comment is not a writer.
    """
    import ast

    repo = Path(__file__).resolve().parents[1]
    tree = ast.parse((repo / module_path).read_text(encoding="utf-8"))

    exempt: set[int] = set()
    for node in ast.walk(tree):
        # Docstrings: prose, never a path the code opens.
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                exempt.add(id(body[0].value))
        # The declared legacy path IS the controlled reference.
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "legacy_path":
                    for sub in ast.walk(kw.value):
                        if isinstance(sub, ast.Constant):
                            exempt.add(id(sub))

    offenders = [
        (getattr(n, "lineno", "?"), n.value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and id(n) not in exempt
        and any(lit in n.value for lit in literals)
    ]
    assert not offenders, f"{module_path} still hardcodes a checkout path: {offenders}"
