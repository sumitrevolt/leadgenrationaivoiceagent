"""Lineage-aware deploy image retention — regression contracts."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "deploy_vps.sh"

FIVE = {
    "app": "9b09a808",
    "worker": "9b09a808",
    "scheduler": "9b09a808",
    "worker-heavy": "9b09a808",
    "worker-video": "9b09a808",
}


def _load_retention():
    path = ROOT / "scripts" / "deploy_image_retention.py"
    name = "deploy_image_retention"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _img(tag: str, created_at: str):
    mod = _load_retention()
    return mod.ImageTag(tag=tag, created_at=created_at)


def test_current_and_immediate_previous_retained_even_when_keep_images_1():
    mod = _load_retention()
    images = [
        _img("9b09a808", "2026-08-11T02:04:59Z"),
        _img("a3fbc8bb", "2026-08-10T17:06:03Z"),
        _img("olddead01", "2026-08-01T00:00:00Z"),
    ]
    remove = mod.plan_removals(
        images, current_tag="9b09a808", rollback_tag="a3fbc8bb", keep_images=1
    )
    assert "9b09a808" not in remove
    assert "a3fbc8bb" not in remove
    assert remove == ["olddead01"]


def test_rebuilt_older_tag_with_newest_created_at_cannot_displace_previous():
    mod = _load_retention()
    images = [
        _img("a3fbc8bb", "2026-08-11T09:00:00Z"),
        _img("9b09a808", "2026-08-11T02:04:59Z"),
        _img("deadbeef1", "2026-08-11T10:00:00Z"),
    ]
    remove = mod.plan_removals(
        images, current_tag="9b09a808", rollback_tag="a3fbc8bb", keep_images=1
    )
    assert "a3fbc8bb" not in remove
    assert "9b09a808" not in remove
    assert "deadbeef1" in remove


def test_inconsistent_pre_deploy_service_tags_fail_closed():
    mod = _load_retention()
    skewed = dict(FIVE)
    skewed["worker"] = "a3fbc8bb"
    with pytest.raises(ValueError, match="inconsistent"):
        mod.assert_consistent_running_tags(skewed)


def test_one_missing_or_empty_service_tag_fails():
    mod = _load_retention()
    incomplete = dict(FIVE)
    del incomplete["worker-video"]
    with pytest.raises(ValueError, match="incomplete service mapping"):
        mod.assert_consistent_running_tags(incomplete)

    empty = dict(FIVE)
    empty["scheduler"] = ""
    with pytest.raises(ValueError, match="invalid/missing/malformed"):
        mod.assert_consistent_running_tags(empty)

    missing_token = dict(FIVE)
    missing_token["app"] = "MISSING"
    with pytest.raises(ValueError, match="invalid/missing/malformed"):
        mod.assert_consistent_running_tags(missing_token)


def test_latest_or_malformed_previous_tag_fails():
    mod = _load_retention()
    with pytest.raises(ValueError, match="malformed|invalid"):
        mod.protected_tags(current_tag="9b09a808", rollback_tag="latest")
    with pytest.raises(ValueError, match="malformed|invalid"):
        mod.resolve_rollback_tag(
            current_tag="9b09a808",
            running_before_tag="not_a_sha!",
            stored_rollback_tag=None,
        )
    latest_map = dict.fromkeys(FIVE, "latest")
    with pytest.raises(ValueError, match="invalid/missing/malformed"):
        mod.assert_consistent_running_tags(latest_map)


def test_keep_images_1_cannot_remove_sole_rollback_artifact():
    mod = _load_retention()
    images = [
        _img("9b09a808", "2026-08-11T02:04:59Z"),
        _img("a3fbc8bb", "2026-08-10T17:06:03Z"),
    ]
    remove = mod.plan_removals(
        images, current_tag="9b09a808", rollback_tag="a3fbc8bb", keep_images=1
    )
    assert remove == []
    protected = mod.protected_tags(current_tag="9b09a808", rollback_tag="a3fbc8bb")
    assert protected == {"9b09a808", "a3fbc8bb"}


def test_same_sha_redeploy_preserves_existing_rollback():
    mod = _load_retention()
    images = [
        _img("9b09a808", "2026-08-11T02:04:59Z"),
        _img("a3fbc8bb", "2026-08-10T17:06:03Z"),
        _img("deadold01", "2026-07-01T00:00:00Z"),
    ]
    rb = mod.resolve_rollback_tag(
        current_tag="9b09a808",
        running_before_tag="9b09a808",
        stored_rollback_tag="a3fbc8bb",
    )
    assert rb == "a3fbc8bb"
    remove = mod.plan_removals(images, current_tag="9b09a808", rollback_tag=rb, keep_images=1)
    assert "a3fbc8bb" not in remove
    assert remove == ["deadold01"]


def test_same_sha_missing_lineage_state_refuses_pruning():
    mod = _load_retention()
    with pytest.raises(ValueError, match="missing durable rollback lineage"):
        mod.resolve_rollback_tag(
            current_tag="9b09a808",
            running_before_tag="9b09a808",
            stored_rollback_tag=None,
        )


def test_missing_protected_artifact_refuses_before_lineage_write(tmp_path: Path):
    mod = _load_retention()
    lineage = tmp_path / "var" / "lib" / "leadgen" / "deploy_rollback_lineage.json"
    # Pre-existing good state must stay byte-identical on refuse.
    good = mod.LineageState(
        current_tag="9b09a808",
        rollback_tag="a3fbc8bb",
        verified_sha="9b09a808",
        updated_at="2026-08-11T02:00:00Z",
    )
    mod.write_lineage_state(lineage, good)
    before = lineage.read_bytes()

    images_missing_rollback = [
        {"tag": "9b09a808", "created_at": "2026-08-11T02:04:59Z"},
        {"tag": "deadold01", "created_at": "2026-07-01T00:00:00Z"},
    ]
    rc = mod.main(
        [
            "--current",
            "9b09a808",
            "--previous",
            "a3fbc8bb",
            "--images-json",
            json.dumps(images_missing_rollback),
            "--running-json",
            json.dumps(FIVE),
            "--require-running-json",
            "--write-lineage",
            str(lineage),
            "--lineage-state",
            str(lineage),
        ]
    )
    assert rc == 2
    assert lineage.read_bytes() == before

    rc = mod.main(
        [
            "--current",
            "9b09a808",
            "--previous",
            "a3fbc8bb",
            "--images-json",
            json.dumps([{"tag": "a3fbc8bb", "created_at": "2026-08-10T17:06:03Z"}]),
            "--write-lineage",
            str(lineage),
        ]
    )
    assert rc == 2
    assert lineage.read_bytes() == before

    absent = tmp_path / "absent_lineage.json"
    rc = mod.main(
        [
            "--current",
            "9b09a808",
            "--previous",
            "a3fbc8bb",
            "--images-json",
            "[]",
            "--write-lineage",
            str(absent),
        ]
    )
    assert rc == 2
    assert not absent.exists()


def test_stored_but_absent_rollback_refuses_same_sha(tmp_path: Path):
    mod = _load_retention()
    lineage = tmp_path / "lineage.json"
    mod.write_lineage_state(
        lineage,
        mod.LineageState(
            current_tag="9b09a808",
            rollback_tag="a3fbc8bb",
            verified_sha="9b09a808",
            updated_at="2026-08-11T02:00:00Z",
        ),
    )
    before = lineage.read_bytes()
    rc = mod.main(
        [
            "--current",
            "9b09a808",
            "--previous",
            "9b09a808",
            "--images-json",
            json.dumps([{"tag": "9b09a808", "created_at": "2026-08-11T02:04:59Z"}]),
            "--lineage-state",
            str(lineage),
            "--write-lineage",
            str(lineage),
        ]
    )
    assert rc == 2
    assert lineage.read_bytes() == before


def test_successful_path_writes_lineage_and_removes_only_unprotected(tmp_path: Path):
    mod = _load_retention()
    lineage = tmp_path / "var" / "lib" / "leadgen" / "deploy_rollback_lineage.json"
    images = [
        {"tag": "9b09a808", "created_at": "2026-08-11T02:04:59Z"},
        {"tag": "a3fbc8bb", "created_at": "2026-08-10T17:06:03Z"},
        {"tag": "olddead01", "created_at": "2026-08-01T00:00:00Z"},
    ]
    rc = mod.main(
        [
            "--current",
            "9b09a808",
            "--previous",
            "a3fbc8bb",
            "--keep-images",
            "1",
            "--images-json",
            json.dumps(images),
            "--running-json",
            json.dumps(FIVE),
            "--require-running-json",
            "--write-lineage",
            str(lineage),
        ]
    )
    assert rc == 0
    loaded = mod.load_lineage_state(lineage)
    assert loaded is not None
    assert loaded.current_tag == "9b09a808"
    assert loaded.rollback_tag == "a3fbc8bb"
    # Restart persistence: reload after "process" restart (fresh load).
    assert mod.load_lineage_state(lineage).rollback_tag == "a3fbc8bb"


def test_corrupt_lineage_state_refused(tmp_path: Path):
    mod = _load_retention()
    path = tmp_path / "corrupt.json"
    path.write_text("{not-json", encoding="utf-8")
    assert mod.load_lineage_state(path) is None
    path.write_text(
        json.dumps({"current_tag": "9b09a808", "rollback_tag": "9b09a808"}),
        encoding="utf-8",
    )
    assert mod.load_lineage_state(path) is None


def test_lineage_default_path_outside_git_checkout():
    mod = _load_retention()
    assert mod.DEFAULT_LINEAGE_STATE_PATH == "/var/lib/leadgen/deploy_rollback_lineage.json"
    assert not str(mod.DEFAULT_LINEAGE_STATE_PATH).startswith("/opt/leadgen")


def test_failed_deployment_cannot_overwrite_last_known_good_lineage(tmp_path: Path):
    mod = _load_retention()
    path = tmp_path / "lineage.json"
    good = mod.LineageState(
        current_tag="9b09a808",
        rollback_tag="a3fbc8bb",
        verified_sha="9b09a808",
        updated_at="2026-08-11T02:00:00Z",
    )
    mod.write_lineage_state(path, good)
    before = path.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        mod.write_lineage_state(
            path,
            mod.LineageState(
                current_tag="deadbeef",
                rollback_tag="9b09a808",
                verified_sha="9b09a808",
                updated_at="2026-08-11T05:00:00Z",
            ),
        )
    assert path.read_text(encoding="utf-8") == before


def test_deploy_vps_wires_lineage_retention_planner():
    t = SCRIPT.read_text(encoding="utf-8")
    assert "deploy_image_retention.py" in t
    assert "/var/lib/leadgen/deploy_rollback_lineage.json" in t
    assert "$REPO/.deploy_rollback_lineage.json" not in t
    assert "zero destructive cleanup executed" in t
    assert "_CLEANUP_OK" in t
    assert "BUILD CACHE skipped" in t
    assert "--write-lineage" in t
    assert "--require-running-json" in t
    command_lines = [ln for ln in t.splitlines() if not ln.strip().startswith("#")]
    joined = "\n".join(command_lines)
    assert "docker rmi -f" not in joined

    health_ok = t.index('if [ "$LIVE_VER" != "$VER" ]; then')
    write_idx = t.index("--write-lineage")
    up_idx = t.index("_compose_up > /tmp/deploy_up.log")
    assert up_idx < health_ok < write_idx


def test_deploy_vps_refusal_gates_all_destructive_cleanup():
    """Planner refuse / malformed → no rmi, no image prune, no builder prune."""
    t = SCRIPT.read_text(encoding="utf-8")
    retention = t[t.index("=== RETENTION (lineage-aware") : t.index("=== DEPLOYED $VER OK ===")]
    assert "_CLEANUP_OK=1" in retention
    assert "docker image prune -f" in retention
    assert "BUILD CACHE skipped" in retention
    assert 'if [ "$_CLEANUP_OK" -eq 1 ]; then' in retention
    assert "docker builder prune -f --filter" in retention
    assert "zero destructive cleanup executed" in retention
    prune_idx = retention.index("docker image prune -f")
    gate_idx = retention.index('if [ "$_CLEANUP_OK" -eq 1 ]; then')
    assert prune_idx < gate_idx
    builder_idx = retention.index("docker builder prune -f --filter")
    assert gate_idx < builder_idx


def test_no_debug_instrumentation_shipped():
    src = (ROOT / "scripts" / "deploy_image_retention.py").read_text(encoding="utf-8")
    assert "_agent_dbg" not in src
    assert "LEADGEN_" + "DEBUG" not in src
    assert "3b" + "0972" not in src
    assert "debug-" + "3b0972" not in src
    assert "#region agent" not in src
    # Production planner must not import/open a session debug log path.
    assert "debug-" not in src.lower() or "debug-3b" not in src
