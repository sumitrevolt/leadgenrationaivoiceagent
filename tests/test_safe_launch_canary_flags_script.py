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


def _load_automation_max():
    path = SCRIPTS / "vps_enable_automation_max_flags.py"
    spec = importlib.util.spec_from_file_location("vps_enable_automation_max_flags", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_automation_max_self_improve_not_clobbered_by_default():
    """ADR-172: the default run must leave a live SELF_IMPROVE_LOOP posture alone."""
    mod = _load_automation_max()
    assert "SELF_IMPROVE_LOOP" not in mod.WANT_SAFE


def test_automation_max_self_improve_containment(tmp_path, monkeypatch, capsys):
    """Containment is still reachable — deliberately, via --force-self-improve-off."""
    env_file = tmp_path / ".env"
    env_file.write_text("SELF_IMPROVE_LOOP=1\n", encoding="utf-8")
    monkeypatch.setenv("LEADGEN_ENV", str(env_file))
    mod = _load_automation_max()
    monkeypatch.setattr(
        sys, "argv", ["vps_enable_automation_max_flags.py", "--dry-run", "--force-self-improve-off"]
    )
    assert mod.main() == 0
    assert "SET SELF_IMPROVE_LOOP=0" in capsys.readouterr().out
    # --dry-run must not have written the containment value through to disk.
    assert env_file.read_text(encoding="utf-8") == "SELF_IMPROVE_LOOP=1\n"
