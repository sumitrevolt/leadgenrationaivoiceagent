"""Tests for Safe Launch canary flag script (zero real outbound)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    path = SCRIPTS / "vps_enable_safe_launch_canary.py"
    spec = importlib.util.spec_from_file_location("vps_enable_safe_launch_canary", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_canary_sets_sales_autopilot_dry_run():
    mod = _load()
    assert mod.WANT_CANARY["SALES_AUTOPILOT_ENABLED"] == "1"
    assert mod.WANT_CANARY["SALES_AUTOPILOT_DRY_RUN"] == "1"
    assert mod.WANT_CANARY["SALES_AUTOPILOT_WHATSAPP_ENABLED"] == "0"
    assert mod.WANT_CANARY["SALES_AUTOPILOT_EMAIL_ENABLED"] == "0"


def test_canary_creative_lab_not_gpu():
    mod = _load()
    assert mod.WANT_CANARY["CREATIVE_OS_ENABLED"] == "1"
    assert mod.WANT_CANARY["CREATIVE_GPU_LAB_ENABLED"] == "0"
    assert mod.WANT_CANARY["CREATIVE_COMFYUI_ENABLED"] == "0"


def test_canary_self_improve_forced_off():
    mod = _load()
    assert mod.WANT_CANARY["SELF_IMPROVE_LOOP"] == "0"
    assert mod.WANT_CANARY["AGENT_RUNTIME"] == "1"


def test_canary_refuses_live_whatsapp():
    mod = _load()
    with __import__("pytest").raises(SystemExit, match="REFUSED"):
        mod.set_kv("", "WHATSAPP_AUTO_SEND", "1")


def test_canary_refuses_live_dial():
    mod = _load()
    with __import__("pytest").raises(SystemExit, match="REFUSED"):
        mod.set_kv("", "PLATFORM_DIAL_DAILY", "1")


def test_canary_allows_hard_off_writes():
    mod = _load()
    text, ch = mod.set_kv("", "PLATFORM_DIAL_DAILY", "0")
    assert ch is True
    assert "PLATFORM_DIAL_DAILY=0" in text


def test_canary_want_never_live_overlap_are_off():
    mod = _load()
    for k in set(mod.WANT_CANARY) & mod.NEVER_LIVE:
        assert mod.WANT_CANARY[k] not in ("1", "true", "yes", "on")


def test_automation_max_self_improve_containment():
    path = SCRIPTS / "vps_enable_automation_max_flags.py"
    spec = importlib.util.spec_from_file_location("vps_enable_automation_max_flags", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.WANT_SAFE.get("SELF_IMPROVE_LOOP") == "0"
