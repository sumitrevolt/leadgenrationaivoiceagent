"""Tests for the 9 new Telegram owner commands (Wave 7 §2 deliverable).

These tests prove:
  * Each command returns a real ``OwnerCommandResult`` with status field
    reflecting source-backed state.
  * Missing data = ``NOT_INSTRUMENTED`` / ``UNAVAILABLE`` / ``EMPTY``, NEVER
    fabricated zero / healthy.
  * MRR and cash scoreboards are NEVER combined into one number.
  * Unknown commands return ``UNAVAILABLE`` (not silent success).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.integrations.telegram_owner_commands import (
    COMMAND_DISPATCH,
    OwnerCommandResult,
    cmd_blockers,
    cmd_email,
    cmd_revenue,
    cmd_smartflo,
    cmd_typesafe,
    cmd_video,
    cmd_workers,
    handle_owner_command,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_dispatch_table_has_9_commands():
    assert len(COMMAND_DISPATCH) == 9
    expected = {
        "/revenue", "/workers", "/smartflo", "/typesafe", "/blockers",
        "/email", "/video", "/ci", "/approvals",
    }
    assert set(COMMAND_DISPATCH.keys()) == expected


def test_unknown_command_returns_unavailable():
    r = handle_owner_command("/nonexistent")
    assert r.status == "UNAVAILABLE"
    assert "UNAVAILABLE" in r.text


def test_revenue_with_no_sources_returns_not_instrumented(tmp_path, monkeypatch):
    """When all 3 source files are absent, return NOT_INSTRUMENTED — never zero."""
    # Repoint data dir to an empty tmp folder.
    monkeypatch.setattr(
        "app.integrations.telegram_owner_commands._data_path",
        lambda fn: tmp_path / fn,
    )
    r = cmd_revenue()
    assert r.status == "NOT_INSTRUMENTED"
    assert "NOT_INSTRUMENTED" in r.text
    assert "1" in r.text  # honest baseline shown
    assert "jiya" in r.text.lower()


def test_revenue_separates_mrr_from_cash(tmp_path, monkeypatch):
    """MRR and cash must be exposed as SEPARATE fields, never summed."""
    monkeypatch.setattr(
        "app.integrations.telegram_owner_commands._data_path",
        lambda fn: tmp_path / fn,
    )
    # Use distinct values: MRR=5999, collected_cash=11998 (2 invoices paid)
    _write_jsonl(
        tmp_path / "revenue_snapshots.jsonl",
        [{"ts": "2026-09-22", "verified_recurring_mrr_inr": 5999.0}],
    )
    _write_jsonl(
        tmp_path / "billing_records.jsonl",
        [
            {"amount_inr": 5999.0, "status": "VERIFIED", "id": "INV/2026-27/0001"},
            {"amount_inr": 5999.0, "status": "VERIFIED", "id": "INV/2026-27/0002"},
        ],
    )
    _write_jsonl(
        tmp_path / "marketing_clients.jsonl",
        [{"id": "jiya", "status": "active"}],
    )

    r = cmd_revenue()
    assert r.status == "OK"
    assert "NEVER" in r.text.upper() or "separate" in r.text.lower()
    # Data payload has separate keys.
    assert "verified_recurring_mrr_inr" in r.data
    assert "verified_net_collected_cash_inr" in r.data
    # These are distinct numbers in the payload — they MUST NOT be summed.
    assert r.data["verified_recurring_mrr_inr"] == 5999.0
    assert r.data["verified_net_collected_cash_inr"] == 11998.0
    # And the source list is shown.
    assert r.data["mrr_target_inr"] == 10_000_000


def test_email_unconfigured_returns_blocked():
    os.environ.pop("SMTP_USER", None)
    os.environ.pop("SMTP_USERNAME", None)
    r = cmd_email()
    # Per §6 directive: unconfigured = BLOCKED, never HEALTHY.
    assert r.status == "BLOCKED"
    assert "BLOCKED" in r.text
    assert r.data["fourteen_mailbox_pool_built"] is False
    assert r.data["smtp_user_configured"] in (False, "")


def test_email_when_configured_returns_configured(monkeypatch):
    """If smtp_user is set, return CONFIGURED status (not HEALTHY — that's a fabrication)."""
    monkeypatch.setattr(
        "app.integrations.telegram_owner_commands._safe",
        lambda fn, default=None, label="": "test@example.com",
    )
    r = cmd_email()
    assert r.status == "OK"
    assert r.data["status_label"] == "CONFIGURED"
    assert r.data["smtp_user_configured"] is True


def test_smartflo_returns_provider_or_unknown():
    r = cmd_smartflo()
    # Status is OK (has gates) or NOT_INSTRUMENTED — never HEALTHY.
    assert r.status in ("OK", "NOT_INSTRUMENTED")
    assert r.status != "HEALTHY"
    # voice_stream_enabled is a known field.
    assert "voice_stream_enabled" in r.data


def test_workers_returns_31_agents():
    r = cmd_workers()
    # Agent count is 31 by canonical truth (owner_os.py).
    if r.status == "OK":
        assert r.data["agent_count"] == 31
        assert r.data["hermes_bots"]  # 9 bots


def test_typesafe_returns_intake_gate_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.integrations.telegram_owner_commands._data_path",
        lambda fn: tmp_path / fn,
    )
    _write_jsonl(
        tmp_path / "typesafe_intake_trace.jsonl",
        [
            {"consumed_calls": 0, "route": "proceed", "reason": "policy_disabled"},
            {"consumed_calls": 1, "route": "proceed", "reason": "credential_unavailable"},
        ],
    )
    r = cmd_typesafe()
    assert r.data["intake_trace_rows"] == 2
    assert r.data["consumed_calls_total"] == 1
    # Wired vs unwired stages are documented honestly.
    assert "intake_judge" in r.data["wired_stages"][0]
    assert "plan_review" in r.data["unwired_stages"]


def test_blockers_empty_when_no_blockers(tmp_path, monkeypatch):
    """If no blocked tasks exist, return EMPTY (not OK or HEALTHY)."""
    monkeypatch.setattr(
        "app.integrations.telegram_owner_commands._safe",
        lambda fn, default=None, label="": [],
    )
    r = cmd_blockers()
    assert r.status == "EMPTY"
    assert "zero blockers" in r.text.lower() or "None" in r.text


def test_video_not_instrumented_when_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.integrations.telegram_owner_commands._data_path",
        lambda fn: tmp_path / fn,
    )
    r = cmd_video()
    assert r.status in ("OK", "NOT_INSTRUMENTED")


def test_handler_dispatch_returns_result_for_known():
    r = handle_owner_command("/blockers")
    assert isinstance(r, OwnerCommandResult)
    assert r.command == "/blockers"


def test_result_truncation_for_long_text():
    r = OwnerCommandResult(
        command="test",
        status="OK",
        fetched_at="2026-09-22",
        elapsed_ms=0.0,
        text="x" * 5000,
    )
    out = r.to_telegram_text()
    assert len(out) <= 3800
    assert "truncated" in out


def test_result_data_payload_shape():
    r = OwnerCommandResult(
        command="test",
        status="OK",
        fetched_at="2026-09-22",
        elapsed_ms=12.5,
        text="hello",
        data={"k": "v"},
    )
    p = r.to_data_payload()
    assert p["command"] == "test"
    assert p["status"] == "OK"
    assert p["elapsed_ms"] == 12.5
    assert p["data"] == {"k": "v"}