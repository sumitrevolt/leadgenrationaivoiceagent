"""Tests for the Telegram command mirror OCC reader (Wave 7 Gap 2)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.platform.telegram_command_mirror import (
    MirrorRow,
    command_count_by_status,
    latest_for_command,
    read_recent,
    summary,
)


@pytest.fixture(autouse=True)
def _hermetic_mirror(tmp_path, monkeypatch):
    """Point the mirror reader at a tmp file for hermetic tests."""
    mirror = tmp_path / "telegram_command_mirror.jsonl"
    monkeypatch.setenv("TELEGRAM_COMMAND_MIRROR_PATH", str(mirror))
    yield mirror


def _write_rows(mirror: Path, rows: list[dict]) -> None:
    mirror.parent.mkdir(parents=True, exist_ok=True)
    with mirror.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_read_recent_returns_empty_when_file_missing(_hermetic_mirror):
    assert read_recent() == []


def test_summary_reports_not_instrumented_when_empty(_hermetic_mirror):
    s = summary()
    assert s["status"] == "NOT_INSTRUMENTED"
    assert s["total_rows"] == 0
    assert "fabrication" in s["note"].lower()


def test_read_recent_parses_rows(_hermetic_mirror):
    _write_rows(
        _hermetic_mirror,
        [
            {
                "command": "/revenue",
                "status": "OK",
                "fetched_at": "2026-09-22T08:00:00+00:00",
                "elapsed_ms": 12.5,
                "data": {"verified_recurring_mrr_inr": 5999.0},
            },
            {
                "command": "/workers",
                "status": "OK",
                "fetched_at": "2026-09-22T08:01:00+00:00",
                "elapsed_ms": 4.0,
                "data": {"agent_count": 31},
            },
        ],
    )
    rows = read_recent()
    assert len(rows) == 2
    assert rows[0].command == "/revenue"
    assert rows[0].status == "OK"
    assert rows[1].data["agent_count"] == 31


def test_command_count_by_status_aggregates_correctly(_hermetic_mirror):
    _write_rows(
        _hermetic_mirror,
        [
            {"command": "/revenue", "status": "OK", "fetched_at": "t1", "elapsed_ms": 0, "data": {}},
            {"command": "/workers", "status": "OK", "fetched_at": "t2", "elapsed_ms": 0, "data": {}},
            {"command": "/email", "status": "BLOCKED", "fetched_at": "t3", "elapsed_ms": 0, "data": {}},
            {"command": "/ci", "status": "UNAVAILABLE", "fetched_at": "t4", "elapsed_ms": 0, "data": {}},
        ],
    )
    counts = command_count_by_status()
    assert counts.get("OK") == 2
    assert counts.get("BLOCKED") == 1
    assert counts.get("UNAVAILABLE") == 1


def test_latest_for_command_filters_correctly(_hermetic_mirror):
    _write_rows(
        _hermetic_mirror,
        [
            {"command": "/revenue", "status": "OK", "fetched_at": "t1", "elapsed_ms": 0, "data": {}},
            {"command": "/workers", "status": "OK", "fetched_at": "t2", "elapsed_ms": 0, "data": {}},
            {"command": "/revenue", "status": "EMPTY", "fetched_at": "t3", "elapsed_ms": 0, "data": {}},
        ],
    )
    rev = latest_for_command("/revenue", limit=5)
    assert len(rev) == 2
    assert all(r.command == "/revenue" for r in rev)
    assert rev[-1].status == "EMPTY"


def test_summary_ok_with_real_rows(_hermetic_mirror):
    _write_rows(
        _hermetic_mirror,
        [
            {"command": "/revenue", "status": "OK", "fetched_at": "t1", "elapsed_ms": 12, "data": {}},
            {"command": "/workers", "status": "OK", "fetched_at": "t2", "elapsed_ms": 4, "data": {}},
            {"command": "/blockers", "status": "EMPTY", "fetched_at": "t3", "elapsed_ms": 1, "data": {}},
        ],
    )
    s = summary()
    assert s["status"] == "OK"
    assert s["total_rows"] == 3
    assert s["command_count_by_status"]["OK"] == 2
    assert s["command_count_by_status"]["EMPTY"] == 1
    assert len(s["latest_commands"]) == 3
    assert s["latest_fetched_at"] == "t3"
    assert "/revenue" in s["unique_commands"]


def test_summary_includes_unique_commands_sorted(_hermetic_mirror):
    _write_rows(
        _hermetic_mirror,
        [
            {"command": "/smartflo", "status": "OK", "fetched_at": "t1", "elapsed_ms": 0, "data": {}},
            {"command": "/revenue", "status": "OK", "fetched_at": "t2", "elapsed_ms": 0, "data": {}},
            {"command": "/agents", "status": "OK", "fetched_at": "t3", "elapsed_ms": 0, "data": {}},
        ],
    )
    s = summary()
    assert s["unique_commands"] == ["/agents", "/revenue", "/smartflo"]  # sorted


def test_malformed_lines_are_skipped_not_fatal(_hermetic_mirror):
    _hermetic_mirror.parent.mkdir(parents=True, exist_ok=True)
    with _hermetic_mirror.open("w", encoding="utf-8") as fh:
        fh.write("not valid json\n")
        fh.write(json.dumps({"command": "/revenue", "status": "OK", "fetched_at": "t", "elapsed_ms": 0, "data": {}}) + "\n")
        fh.write("\n")  # empty line
    rows = read_recent()
    assert len(rows) == 1
    assert rows[0].command == "/revenue"


def test_mirror_row_dataclass_round_trip():
    r = MirrorRow(
        command="/revenue",
        status="OK",
        fetched_at="2026-09-22",
        elapsed_ms=12.5,
        data={"k": "v"},
    )
    d = r.to_dict()
    assert d["command"] == "/revenue"
    assert d["status"] == "OK"
    assert d["data"] == {"k": "v"}


def test_occ_summary_can_be_ingested_by_dashboard(_hermetic_mirror):
    """The summary structure MUST match what the OCC dashboard expects."""
    _write_rows(
        _hermetic_mirror,
        [
            {"command": "/revenue", "status": "OK", "fetched_at": "t", "elapsed_ms": 1, "data": {}},
        ],
    )
    s = summary()
    # Required fields for the OCC card.
    assert "kind" in s
    assert "status" in s
    assert "fetched_at" in s
    assert "total_rows" in s
    assert "command_count_by_status" in s
    assert "latest_commands" in s