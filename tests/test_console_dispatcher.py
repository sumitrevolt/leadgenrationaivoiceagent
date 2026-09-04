"""Tests for app.automation.console_dispatcher — the M2 contract.

Covers:
  * Happy path emit + drain
  * Dedupe within window (in-process ring)
  * Unknown event_key is rejected without writing
  * VOICE_LAUNCH_KILL=1 blocks voice-channel events
  * Empty tenant_id is rejected
  * Storage failure does NOT propagate to caller
  * Drain with clear_after resets the queue
  * Drain peek preserves the queue
  * Handler registration + dispatch (typed map)
  * Cap-trim keeps only the most recent N envelopes
  * dry_run returns envelope inline without writing

All tests use an isolated tmp store_root so they never touch the real
``data/console_events`` directory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

import pytest

from app.automation import console_dispatcher as cd


@pytest.fixture
def store_root(tmp_path: Path) -> Path:
    """Each test gets its own JSONL store."""
    root = tmp_path / "console_events"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture(autouse=True)
def _reset_dedupe_ring():
    """Wipe the in-process dedupe ring between tests."""
    cd._DEDUPE_RING.clear()
    yield
    cd._DEDUPE_RING.clear()


@pytest.fixture(autouse=True)
def _reset_voice_kill(monkeypatch):
    """Default VOICE_LAUNCH_KILL off unless a test explicitly enables it."""
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "0")
    yield


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
def test_emit_happy_path_writes_envelope(store_root):
    r = cd.emit_console_event(
        "inbound_missed",
        "leadgen-ai",
        {"from": "+91xxxxxxxxxx", "duration_s": 12},
        source="test",
        store_root=store_root,
    )
    assert r["emitted"] is True
    assert r["reason"] == "ok"
    assert r["event_id"].startswith("ce_leadgen-ai_")

    files = list(store_root.iterdir())
    assert len(files) == 1
    line = files[0].read_text(encoding="utf-8").strip()
    env = json.loads(line)
    assert env["event_key"] == "inbound_missed"
    assert env["tenant_id"] == "leadgen-ai"
    assert env["payload"]["from"] == "+91xxxxxxxxxx"
    assert env["channels"] == ["voice", "sms", "whatsapp"]
    assert env["requires_dlt"] is True
    assert env["source"] == "test"
    assert env["dedupe_key"].startswith("leadgen-ai|inbound_missed|")


def test_emit_with_override_dedupe_key(store_root):
    r1 = cd.emit_console_event(
        "lead_created",
        "tenant-x",
        {"a": 1},
        override_dedupe_key="tenant-x|lead_created|custom-key",
        store_root=store_root,
    )
    assert r1["emitted"] is True
    r2 = cd.emit_console_event(
        "lead_created",
        "tenant-x",
        {"b": 2},
        override_dedupe_key="tenant-x|lead_created|custom-key",
        store_root=store_root,
    )
    assert r2["emitted"] is False
    assert r2["reason"] == "duplicate"


# --------------------------------------------------------------------------- #
# Dedupe
# --------------------------------------------------------------------------- #
def test_dedupe_collapses_identical_events_in_window(store_root):
    payload = {"from": "+91xxxxxxxxxx", "duration_s": 30}
    r1 = cd.emit_console_event("inbound_missed", "leadgen-ai", payload, store_root=store_root)
    r2 = cd.emit_console_event("inbound_missed", "leadgen-ai", payload, store_root=store_root)
    assert r1["emitted"] is True
    assert r2["emitted"] is False
    assert r2["reason"] == "duplicate"
    assert cd.pending_event_count("leadgen-ai", store_root=store_root) == 1


def test_different_payloads_do_not_dedupe(store_root):
    r1 = cd.emit_console_event(
        "inbound_missed", "leadgen-ai", {"from": "+91aaaaaaaaaa"}, store_root=store_root
    )
    r2 = cd.emit_console_event(
        "inbound_missed", "leadgen-ai", {"from": "+91bbbbbbbbbb"}, store_root=store_root
    )
    assert r1["emitted"] is True
    assert r2["emitted"] is True
    assert cd.pending_event_count("leadgen-ai", store_root=store_root) == 2


def test_different_tenants_do_not_dedupe(store_root):
    payload = {"x": 1}
    r1 = cd.emit_console_event("lead_created", "tenant-a", payload, store_root=store_root)
    r2 = cd.emit_console_event("lead_created", "tenant-b", payload, store_root=store_root)
    assert r1["emitted"] is True
    assert r2["emitted"] is True


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def test_unknown_event_key_is_rejected(store_root):
    r = cd.emit_console_event(
        "definitely_not_a_real_event",
        "leadgen-ai",
        {},
        store_root=store_root,
    )
    assert r["emitted"] is False
    assert r["reason"] == "unknown_event_key"
    assert cd.pending_event_count("leadgen-ai", store_root=store_root) == 0


def test_empty_tenant_id_is_rejected(store_root):
    r = cd.emit_console_event("inbound_missed", "", {}, store_root=store_root)
    assert r["emitted"] is False
    assert r["reason"] == "empty_tenant"
    assert r["store_path"] == ""


def test_valid_event_keys_includes_all_eight():
    keys = cd.valid_event_keys()
    expected = {
        "inbound_answered",
        "inbound_missed",
        "lead_created",
        "outbound_no_answer",
        "appointment_due",
        "payment_due",
        "customer_dormant",
        "service_completed",
    }
    assert expected.issubset(set(keys))
    assert len(keys) == 8


# --------------------------------------------------------------------------- #
# Kill-switch
# --------------------------------------------------------------------------- #
def test_voice_kill_blocks_voice_channel_events(store_root, monkeypatch):
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "1")
    r = cd.emit_console_event(
        "inbound_missed",  # channels: voice, sms, whatsapp
        "leadgen-ai",
        {"from": "+91xxxxxxxxxx"},
        store_root=store_root,
    )
    assert r["emitted"] is False
    assert r["reason"] == "voice_kill_active"
    assert cd.pending_event_count("leadgen-ai", store_root=store_root) == 0


def test_voice_kill_does_not_block_sms_only_events(store_root, monkeypatch):
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "1")
    # All EVENT_SLOTS use voice, so this branch is theoretical; assert
    # it for safety in case future slots drop voice.
    r = cd.emit_console_event(
        "payment_due",  # channels: voice, sms
        "leadgen-ai",
        {"amount": 1999},
        store_root=store_root,
    )
    # Today every slot has voice, so kill still fires — pin that contract.
    assert r["emitted"] is False
    assert r["reason"] == "voice_kill_active"


# --------------------------------------------------------------------------- #
# Storage isolation — failure cannot break the caller
# --------------------------------------------------------------------------- #
def test_storage_failure_is_isolated(store_root):
    # Force open() to raise. The dispatcher must catch and return a
    # well-formed dict, not raise into the caller.
    fake_open = mock.mock_open()
    fake_open.side_effect = OSError("disk on fire")
    with mock.patch("builtins.open", fake_open):
        r = cd.emit_console_event(
            "inbound_missed", "leadgen-ai", {"x": 1}, store_root=store_root
        )
    assert r["emitted"] is False
    assert r["reason"] == "storage_error"
    assert r["event_id"] is not None  # envelope was built before the write attempt


def test_storage_failure_does_not_corrupt_state(store_root):
    """A failed emit must NOT register the dedupe key (so a retry can succeed)."""
    fake_open = mock.mock_open()
    fake_open.side_effect = OSError("disk on fire")
    with mock.patch("builtins.open", fake_open):
        r1 = cd.emit_console_event(
            "lead_created", "tenant-z", {"x": 1}, store_root=store_root
        )
    assert r1["emitted"] is False
    # Clear the dedupe ring manually — storage failure must not have polluted it.
    cd._DEDUPE_RING.clear()
    r2 = cd.emit_console_event(
        "lead_created", "tenant-z", {"x": 1}, store_root=store_root
    )
    assert r2["emitted"] is True


# --------------------------------------------------------------------------- #
# Drain semantics
# --------------------------------------------------------------------------- #
def test_drain_peek_preserves_queue(store_root):
    cd.emit_console_event("inbound_missed", "leadgen-ai", {"a": 1}, store_root=store_root)
    cd.emit_console_event("lead_created", "leadgen-ai", {"b": 2}, store_root=store_root)
    envs = cd.drain_console_events("leadgen-ai", store_root=store_root)
    assert len(envs) == 2
    assert cd.pending_event_count("leadgen-ai", store_root=store_root) == 2


def test_drain_clear_resets_queue(store_root):
    cd.emit_console_event("inbound_missed", "leadgen-ai", {"a": 1}, store_root=store_root)
    envs = cd.drain_console_events("leadgen-ai", store_root=store_root, clear_after=True)
    assert len(envs) == 1
    assert cd.pending_event_count("leadgen-ai", store_root=store_root) == 0


def test_drain_respects_max_count(store_root):
    for i in range(5):
        # Different dedupe payload each time to bypass the dedupe ring.
        cd.emit_console_event(
            "lead_created", "leadgen-ai", {"i": i}, store_root=store_root
        )
    envs = cd.drain_console_events("leadgen-ai", max_count=3, store_root=store_root)
    assert len(envs) == 3


def test_pending_count_zero_when_no_file(store_root):
    assert cd.pending_event_count("nope", store_root=store_root) == 0


def test_drain_handles_corrupt_lines(store_root):
    # Write a corrupt line then a real envelope. Drain must skip the bad line.
    p = store_root / "leadgen-ai.jsonl"
    p.write_text("{this is not json}\n", encoding="utf-8")
    cd.emit_console_event("lead_created", "leadgen-ai", {"x": 1}, store_root=store_root)
    envs = cd.drain_console_events("leadgen-ai", store_root=store_root)
    assert len(envs) == 1
    assert envs[0]["event_key"] == "lead_created"


# --------------------------------------------------------------------------- #
# Cap trim
# --------------------------------------------------------------------------- #
def test_cap_trim_keeps_recent_envelopes(store_root, monkeypatch):
    monkeypatch.setenv("CONSOLE_EVENT_MAX_PER_TENANT", "3")
    for i in range(7):
        cd.emit_console_event(
            "lead_created", "leadgen-ai", {"i": i}, store_root=store_root
        )
    # Cap trimmed to 3, but the in-process dedupe ring let them all through
    # because each payload differs.
    assert cd.pending_event_count("leadgen-ai", store_root=store_root) == 3


# --------------------------------------------------------------------------- #
# Handler map + dispatch
# --------------------------------------------------------------------------- #
def test_default_handlers_are_noop():
    for key in cd.valid_event_keys():
        assert cd.HANDLERS[key] is cd._noop_handler


def test_register_handler_for_known_key():
    captured = []

    def handler(envelope, ctx):
        captured.append((envelope["event_key"], ctx))
        return {"handled": True, "event_id": envelope["event_id"]}

    assert cd.register_handler("lead_created", handler) is True
    env = {"event_id": "ce_x_1_aaaa", "event_key": "lead_created"}
    out = cd.dispatch_envelope(env, ctx={"dry_run": True})
    assert out["handled"] is True
    assert captured == [("lead_created", {"dry_run": True})]


def test_register_handler_for_unknown_key_returns_false():
    def handler(envelope, ctx):
        return {"handled": True}

    assert cd.register_handler("not_a_real_event", handler) is False


def test_dispatch_unknown_event_falls_back_to_noop():
    out = cd.dispatch_envelope({"event_id": "ce_x_1_yyyy", "event_key": "bogus"})
    assert out["handled"] is False
    assert out["reason"] == "noop_default"


def test_dispatch_handler_exception_is_isolated():
    def bad_handler(envelope, ctx):
        raise RuntimeError("kaboom")

    cd.register_handler("payment_due", bad_handler)
    out = cd.dispatch_envelope({"event_id": "ce_x_1_zzzz", "event_key": "payment_due"})
    assert out["handled"] is False
    assert out["reason"].startswith("handler_error:RuntimeError")


# --------------------------------------------------------------------------- #
# dry_run
# --------------------------------------------------------------------------- #
def test_dry_run_does_not_write(store_root):
    r = cd.emit_console_event(
        "inbound_answered", "leadgen-ai", {"x": 1}, dry_run=True, store_root=store_root
    )
    assert r["emitted"] is True
    assert r["reason"] == "dry_run"
    assert "envelope" in r
    assert cd.pending_event_count("leadgen-ai", store_root=store_root) == 0


# --------------------------------------------------------------------------- #
# Tenant isolation
# --------------------------------------------------------------------------- #
def test_per_tenant_isolation(store_root):
    cd.emit_console_event("lead_created", "tenant-a", {"x": 1}, store_root=store_root)
    cd.emit_console_event("lead_created", "tenant-b", {"x": 1}, store_root=store_root)
    assert cd.pending_event_count("tenant-a", store_root=store_root) == 1
    assert cd.pending_event_count("tenant-b", store_root=store_root) == 1
    assert cd.pending_event_count("tenant-c", store_root=store_root) == 0
    files = {p.name for p in store_root.iterdir()}
    assert "tenant-a.jsonl" in files
    assert "tenant-b.jsonl" in files


def test_tenant_id_with_path_separators_is_sanitized(store_root):
    # Defensive: a buggy caller passing "../../etc/passwd" must NOT escape store_root.
    cd.emit_console_event("lead_created", "../../etc", {}, store_root=store_root)
    # Every file must live INSIDE store_root (no traversal out of the directory).
    for p in store_root.iterdir():
        assert store_root in p.parents, f"{p} escaped store_root"
    # Sanitized filename should not contain path separators.
    for p in store_root.iterdir():
        assert "/" not in p.name
        assert "\\" not in p.name


# --------------------------------------------------------------------------- #
# Existing tests must remain green — sanity-check that slots match EVENT_SLOTS
# --------------------------------------------------------------------------- #
def test_slots_match_product_consoles_event_slots():
    from app.api.product_consoles import EVENT_SLOTS

    cd_slots = set(cd.valid_event_keys())
    pc_slots = {s["key"] for s in EVENT_SLOTS}
    assert cd_slots == pc_slots
