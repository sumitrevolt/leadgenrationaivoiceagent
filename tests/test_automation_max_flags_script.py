"""Tests for ADR-097 APP_VERSION pin + Automation-Max NEVER list."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from app_version_pin import resolve_app_version_pin  # noqa: E402


def _load_automation_max():
    path = SCRIPTS / "vps_enable_automation_max_flags.py"
    spec = importlib.util.spec_from_file_location("vps_enable_automation_max_flags", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_resolve_pin_from_env_override():
    assert resolve_app_version_pin(env={"LEADGEN_APP_VERSION": "441cf37a"}) == "441cf37a"


def test_resolve_pin_refuses_latest_env():
    with pytest.raises(SystemExit, match="REFUSED recreate"):
        resolve_app_version_pin(env={"LEADGEN_APP_VERSION": "latest"}, inspect_image="")


def test_resolve_pin_from_inspect_image():
    img = "ghcr.io/sumitrevolt/leadgenrationaivoiceagent:441cf37a"
    assert resolve_app_version_pin(env={}, inspect_image=img) == "441cf37a"


def test_resolve_pin_refuses_latest_image():
    with pytest.raises(SystemExit, match="REFUSED recreate"):
        resolve_app_version_pin(
            env={},
            inspect_image="ghcr.io/sumitrevolt/leadgenrationaivoiceagent:latest",
        )


def test_automation_max_never_blocks_whatsapp():
    mod = _load_automation_max()
    with pytest.raises(SystemExit, match="NEVER"):
        mod.set_kv("", "WHATSAPP_AUTO_SEND", "1")


def test_automation_max_set_kv_idempotent():
    mod = _load_automation_max()
    text, ch = mod.set_kv("", "OPS_WATCHDOG", "1")
    assert ch is True
    assert "OPS_WATCHDOG=1" in text
    text2, ch2 = mod.set_kv(text, "OPS_WATCHDOG", "1")
    assert ch2 is False
    assert text2 == text


def test_automation_max_safe_keys_exclude_never():
    mod = _load_automation_max()
    overlap = set(mod.WANT_SAFE) & mod.NEVER
    assert overlap == set()


def test_stale_canary_pause_matcher():
    path = SCRIPTS / "vps_clear_stale_canary_pauses.py"
    spec = importlib.util.spec_from_file_location("vps_clear_stale_canary_pauses", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._is_stale_canary(
        {"scheduled_pause": True, "reason": "clear sticky", "by": "prod-kavya-canary"}
    )
    assert not mod._is_stale_canary(
        {"scheduled_pause": True, "reason": "owner asked", "by": "sumit"}
    )
    assert not mod._is_stale_canary(
        {"scheduled_pause": False, "reason": "clear sticky", "by": "prod-kavya-canary"}
    )
