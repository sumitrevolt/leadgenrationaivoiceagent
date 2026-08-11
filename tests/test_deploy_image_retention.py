"""Lineage-aware deploy image retention — regression contracts."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "deploy_vps.sh"

# Enable session NDJSON evidence for lineage vs legacy comparisons.
os.environ.setdefault("LEADGEN_DEBUG_SESSION", "3b0972")
os.environ.setdefault("LEADGEN_DEBUG_LOG_PATH", str(ROOT / "debug-3b0972.log"))

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
    # dataclass needs the module registered before @dataclass runs
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
    """Rebuilt a3fbc8bb can have CreatedAt newer than current — still protected."""
    mod = _load_retention()
    images = [
        _img("a3fbc8bb", "2026-08-11T09:00:00Z"),  # rebuilt, newest CreatedAt
        _img("9b09a808", "2026-08-11T02:04:59Z"),
        _img("deadbeef1", "2026-08-11T10:00:00Z"),  # even newer junk
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
    latest_map = dict(FIVE)
    latest_map["app"] = "latest"
    latest_map["worker"] = "latest"
    latest_map["scheduler"] = "latest"
    latest_map["worker-heavy"] = "latest"
    latest_map["worker-video"] = "latest"
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
    # PREV == VER (same-SHA): use durable stored rollback.
    rb = mod.resolve_rollback_tag(
        current_tag="9b09a808",
        running_before_tag="9b09a808",
        stored_rollback_tag="a3fbc8bb",
    )
    assert rb == "a3fbc8bb"
    remove = mod.plan_removals(images, current_tag="9b09a808", rollback_tag=rb, keep_images=1)
    assert "a3fbc8bb" not in remove
    assert "9b09a808" not in remove
    assert remove == ["deadold01"]


def test_same_sha_missing_lineage_state_refuses_pruning():
    mod = _load_retention()
    with pytest.raises(ValueError, match="missing durable rollback lineage"):
        mod.resolve_rollback_tag(
            current_tag="9b09a808",
            running_before_tag="9b09a808",
            stored_rollback_tag=None,
        )
    with pytest.raises(ValueError, match="missing durable rollback lineage"):
        mod.resolve_rollback_tag(
            current_tag="9b09a808",
            running_before_tag="9b09a808",
            stored_rollback_tag="",
        )


def test_lineage_state_written_only_via_post_verify_helpers(tmp_path: Path):
    mod = _load_retention()
    path = tmp_path / "lineage.json"
    # Simulate failed deploy: no write call → file absent.
    assert not path.exists()
    assert mod.load_lineage_state(path) is None

    # Post exact-SHA health: write next state.
    state = mod.next_lineage_state(
        verified_sha="9b09a808",
        running_before_tag="a3fbc8bb",
        previous=None,
        now_iso="2026-08-11T03:00:00Z",
    )
    mod.write_lineage_state(path, state)
    loaded = mod.load_lineage_state(path)
    assert loaded is not None
    assert loaded.current_tag == "9b09a808"
    assert loaded.rollback_tag == "a3fbc8bb"
    assert loaded.verified_sha == "9b09a808"

    # Same-SHA retry keeps stored rollback (does not invent CreatedAt lineage).
    again = mod.next_lineage_state(
        verified_sha="9b09a808",
        running_before_tag="9b09a808",
        previous=loaded,
        now_iso="2026-08-11T04:00:00Z",
    )
    assert again.rollback_tag == "a3fbc8bb"


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

    # Failed deploy must not call write_lineage_state — simulate by refusing
    # invalid verified_sha write (health mismatch path).
    with pytest.raises(ValueError):
        mod.write_lineage_state(
            path,
            mod.LineageState(
                current_tag="deadbeef",
                rollback_tag="9b09a808",
                verified_sha="9b09a808",  # mismatch → refuse
                updated_at="2026-08-11T05:00:00Z",
            ),
        )
    assert path.read_text(encoding="utf-8") == before


def test_deploy_vps_wires_lineage_retention_planner():
    t = SCRIPT.read_text(encoding="utf-8")
    assert "deploy_image_retention.py" in t
    assert "PREV_PROD_TAG" in t
    assert "ROLLBACK_TAG" in t
    assert "LINEAGE_STATE" in t
    assert "--write-lineage" in t
    assert "--require-running-json" in t
    assert "--assert-running-only" in t
    assert "=== PRE-DEPLOY production tag capture (lineage) ===" in t
    assert "=== RETENTION (lineage-aware" in t
    # never force-delete
    command_lines = [ln for ln in t.splitlines() if not ln.strip().startswith("#")]
    joined = "\n".join(command_lines)
    assert "docker rmi -f" not in joined

    # State write only after health verification (not before UP).
    health_ok = t.index('if [ "$LIVE_VER" != "$VER" ]; then')
    write_idx = t.index("--write-lineage")
    up_idx = t.index("_compose_up > /tmp/deploy_up.log")
    assert up_idx < health_ok < write_idx


def test_cli_assert_running_and_same_sha_refuse(tmp_path: Path):
    mod = _load_retention()
    rc = mod.main(
        [
            "--assert-running-only",
            "--running-json",
            json.dumps(FIVE),
        ]
    )
    assert rc == 0

    rc = mod.main(
        [
            "--current",
            "9b09a808",
            "--previous",
            "9b09a808",
            "--images-json",
            "[]",
            "--require-running-json",
        ]
    )
    assert rc == 2
