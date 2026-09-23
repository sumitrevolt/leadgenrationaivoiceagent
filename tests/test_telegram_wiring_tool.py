"""
Tests for the Telegram coordination-group wiring tool
=====================================================
The wiring tool is the only code path that writes
``config/telegram/setup_spec.yaml`` (the single source of truth for every
Telegram surface). These tests pin the guards that keep that write safe:

1. bindings refuse to overwrite an existing chat_id unless forced;
2. the writer keeps a timestamped backup;
3. the YAML round-trip cannot silently reshape the document;
4. the required coordination groups are reported as unwired when they are.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_tool():
    path = ROOT / "scripts" / "telegram_wire_coordination_groups.py"
    spec = importlib.util.spec_from_file_location("telegram_wire_coordination_groups", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tool(tmp_path, monkeypatch):
    """A writable copy of the real spec, isolated in tmp_path.

    The live spec legitimately has the three coordination groups bound to real
    chat_ids (and agents_coordination may carry previously created topic_ids),
    so the test copy is normalised first: the coordination groups start empty
    with no topic_ids. Tests that need a bound group bind it explicitly.
    """
    module = _load_tool()
    source = yaml.safe_load((ROOT / "config" / "telegram" / "setup_spec.yaml").read_text(encoding="utf-8"))
    for group in source.get("cross_product") or []:
        if group.get("key") in module.COORDINATION_KEYS:
            group["chat_id"] = ""
            group.pop("topic_ids", None)
    tmp_spec = tmp_path / "setup_spec.yaml"
    tmp_spec.write_text(yaml.safe_dump(source, sort_keys=False, allow_unicode=True, width=4096), encoding="utf-8")
    monkeypatch.setattr(module, "SPEC_PATH", tmp_spec)
    return module


def test_spec_round_trip_is_lossless(tool):
    before = yaml.safe_load(tool.SPEC_PATH.read_text(encoding="utf-8"))
    tool.save_spec(tool.load_spec(), backup=False)
    assert tool.load_spec() == before


def test_save_spec_writes_a_backup(tool):
    spec = tool.load_spec()
    tool.save_spec(spec, backup=True)
    backups = list(tool.SPEC_PATH.parent.glob("setup_spec.yaml.bak-*"))
    assert backups, "a write to the SSOT must leave a timestamped backup"


def test_bind_chat_id_updates_only_the_target_group(tool):
    before = dict(tool.group_refs(tool.load_spec()))
    assert tool.bind_chat_id("workers_coordination", "-1001234567890") == 0

    after = dict(tool.group_refs(tool.load_spec()))
    assert after["workers_coordination"]["chat_id"] == "-1001234567890"
    for ref, group in after.items():
        if ref != "workers_coordination":
            assert group == before[ref], f"unrelated group '{ref}' was modified"


def test_product_group_keys_are_addressed_with_scope(tool):
    """Both products define 'announcements' — a bare key must never be guessed."""
    ambiguous, error = tool.resolve_group(tool.load_spec(), "announcements")
    assert ambiguous is None
    assert "marketing.announcements" in error and "voice.announcements" in error

    marketing, error = tool.resolve_group(tool.load_spec(), "marketing.announcements")
    assert error == ""
    assert marketing["handle"] == "LeadGenAIMarketingNews"

    voice, error = tool.resolve_group(tool.load_spec(), "voice.announcements")
    assert error == ""
    assert voice["handle"] == "LeadGenAIVoiceNews"


def test_bind_rejects_ambiguous_key(tool):
    assert tool.bind_chat_id("announcements", "-1001") == 1
    assert tool.find_group(tool.load_spec(), "marketing.announcements")["chat_id"] != "-1001"


def test_bind_chat_id_refuses_silent_replacement(tool):
    assert tool.bind_chat_id("owner_alerts", "-1009999999999") == 1  # already bound
    assert tool.find_group(tool.load_spec(), "owner_alerts")["chat_id"] != "-1009999999999"

    assert tool.bind_chat_id("owner_alerts", "-1009999999999", force=True) == 0
    assert tool.find_group(tool.load_spec(), "owner_alerts")["chat_id"] == "-1009999999999"


def test_bind_unknown_key_fails(tool):
    assert tool.bind_chat_id("does_not_exist", "-100") == 1


def test_required_coordination_groups_are_tracked(tool):
    """The three coordination groups the owner asked for are first-class."""
    assert set(tool.COORDINATION_KEYS) == {
        "workers_coordination",
        "agents_coordination",
        "admin_command_center",
    }
    for key in tool.COORDINATION_KEYS:
        assert tool.find_group(tool.load_spec(), key) is not None


def test_verify_shallow_reports_unwired_required_groups(tool, monkeypatch):
    spec = tool.load_spec()
    for key in tool.COORDINATION_KEYS:
        group, error = tool.resolve_group(spec, key)
        assert error == ""
        group["chat_id"] = ""
        group.pop("topic_ids", None)
    tool.save_spec(tool.load_spec(), backup=False)
    monkeypatch.setattr(tool, "_tokens", lambda: {"jarvis": "J" * 30})
    monkeypatch.setattr(tool, "_get_me", lambda token: {"ok": True, "username": "test_bot", "id": 1})

    assert tool.verify(deep=False) == 1

    for key in tool.COORDINATION_KEYS:
        tool.bind_chat_id(key, "-1001111111111")
    assert tool.verify(deep=False) == 0


def test_create_topics_requires_binding(tool, monkeypatch):
    group = tool.find_group(tool.load_spec(), "agents_coordination")
    group["chat_id"] = ""
    group.pop("topic_ids", None)
    tool.save_spec(tool.load_spec(), backup=False)

    assert tool.create_topics("agents_coordination", "J" * 30) == 1
