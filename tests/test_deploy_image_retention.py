"""Lineage-aware deploy image retention — regression contracts."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "deploy_vps.sh"

# Enable session NDJSON evidence for lineage vs legacy comparisons.
os.environ.setdefault("LEADGEN_DEBUG_SESSION", "3b0972")
os.environ.setdefault("LEADGEN_DEBUG_LOG_PATH", str(ROOT / "debug-3b0972.log"))


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
        images, current_tag="9b09a808", previous_tag="a3fbc8bb", keep_images=1
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
        images, current_tag="9b09a808", previous_tag="a3fbc8bb", keep_images=1
    )
    assert "a3fbc8bb" not in remove
    assert "9b09a808" not in remove
    assert "deadbeef1" in remove


def test_inconsistent_pre_deploy_service_tags_fail_closed():
    mod = _load_retention()
    with pytest.raises(ValueError, match="inconsistent"):
        mod.assert_consistent_running_tags(
            {"app": "9b09a808", "worker": "a3fbc8bb", "scheduler": "9b09a808"}
        )


def test_keep_images_1_cannot_remove_sole_rollback_artifact():
    mod = _load_retention()
    images = [
        _img("9b09a808", "2026-08-11T02:04:59Z"),
        _img("a3fbc8bb", "2026-08-10T17:06:03Z"),
    ]
    remove = mod.plan_removals(
        images, current_tag="9b09a808", previous_tag="a3fbc8bb", keep_images=1
    )
    assert remove == []
    protected = mod.protected_tags(current_tag="9b09a808", previous_tag="a3fbc8bb")
    assert protected == {"9b09a808", "a3fbc8bb"}


def test_deploy_vps_wires_lineage_retention_planner():
    t = SCRIPT.read_text(encoding="utf-8")
    assert "deploy_image_retention.py" in t
    assert "PREV_PROD_TAG" in t
    assert "=== PRE-DEPLOY production tag capture (lineage) ===" in t
    assert "=== RETENTION (lineage-aware" in t
    assert "inconsistent pre-deploy app-image tags" in t
    # never force-delete
    command_lines = [ln for ln in t.splitlines() if not ln.strip().startswith("#")]
    joined = "\n".join(command_lines)
    assert "docker rmi -f" not in joined
