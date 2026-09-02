"""mcp_keys — issuance, auth, metering, quota, revoke.

The product surface monetizes on quota — quota MUST be enforced.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.platform import mcp_keys


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mcp_keys, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(mcp_keys, "_KEYS_PATH", tmp_path / "keys.jsonl")
    monkeypatch.setattr(mcp_keys, "_USAGE_PATH", tmp_path / "usage.jsonl")
    monkeypatch.setenv("MCP_PRODUCT", "1")


# --------------------------------------------------------------------------- #
# Issuance
# --------------------------------------------------------------------------- #
def test_issue_returns_plaintext_once() -> None:
    out = mcp_keys.issue("test-key", daily_limit=10)
    assert out["ok"] is True
    assert out["key"].startswith("lgmcp_")
    assert "key_preview" in out
    # list_all redacts
    listed = mcp_keys.list_all()
    assert len(listed) == 1
    assert "key" not in listed[0]
    assert "key_hash" not in listed[0]


def test_issue_rejects_unknown_capability() -> None:
    out = mcp_keys.issue("bad", capabilities=["foo.bar"])
    assert out["ok"] is False


def test_issue_default_grants_all_capabilities() -> None:
    out = mcp_keys.issue("default")
    # The persisted row holds the capabilities
    rows = mcp_keys._read_keys()
    assert set(rows[0]["capabilities"]) == set(mcp_keys.SUPPORTED_CAPABILITIES)


# --------------------------------------------------------------------------- #
# Authenticate
# --------------------------------------------------------------------------- #
def test_authenticate_resolves_valid_key() -> None:
    out = mcp_keys.issue("x")
    row = mcp_keys.authenticate(out["key"])
    assert row is not None
    assert row["id"] == out["id"]


def test_authenticate_rejects_wrong_key() -> None:
    mcp_keys.issue("x")
    assert mcp_keys.authenticate("lgmcp_totallybogusvalue") is None


def test_authenticate_rejects_bad_prefix() -> None:
    out = mcp_keys.issue("x")
    # Strip the prefix
    bad = out["key"][6:]
    assert mcp_keys.authenticate(bad) is None


def test_authenticate_rejects_revoked() -> None:
    out = mcp_keys.issue("x")
    mcp_keys.revoke(out["id"])
    assert mcp_keys.authenticate(out["key"]) is None


# --------------------------------------------------------------------------- #
# Meter — the revenue-critical contract
# --------------------------------------------------------------------------- #
def test_check_and_meter_allows_under_quota() -> None:
    out = mcp_keys.issue("x", daily_limit=3)
    row = mcp_keys.authenticate(out["key"])
    for i in range(3):
        v = mcp_keys.check_and_meter(row, "niches.list")
        assert v["ok"] is True


def test_check_and_meter_429s_over_quota() -> None:
    out = mcp_keys.issue("x", daily_limit=2)
    row = mcp_keys.authenticate(out["key"])
    assert mcp_keys.check_and_meter(row, "niches.list")["ok"] is True
    assert mcp_keys.check_and_meter(row, "niches.list")["ok"] is True
    # 3rd call: should be denied with 429
    v = mcp_keys.check_and_meter(row, "niches.list")
    assert v["ok"] is False
    assert v["code"] == 429
    assert v["retry_after_s"] > 0


def test_check_and_meter_403s_capability_not_granted() -> None:
    out = mcp_keys.issue("limited", capabilities=["niches.list"])
    row = mcp_keys.authenticate(out["key"])
    v = mcp_keys.check_and_meter(row, "lead.score")
    assert v["ok"] is False
    assert v["code"] == 403


def test_check_and_meter_tracks_per_key_independently() -> None:
    """A burnt-out key MUST NOT affect a fresh one (revenue isolation)."""
    a = mcp_keys.issue("a", daily_limit=1)
    b = mcp_keys.issue("b", daily_limit=5)
    row_a, row_b = mcp_keys.authenticate(a["key"]), mcp_keys.authenticate(b["key"])
    assert mcp_keys.check_and_meter(row_a, "niches.list")["ok"] is True
    # Key A now at quota
    assert mcp_keys.check_and_meter(row_a, "niches.list")["ok"] is False
    # Key B is unaffected
    for _ in range(5):
        assert mcp_keys.check_and_meter(row_b, "niches.list")["ok"] is True


# --------------------------------------------------------------------------- #
# Revoke
# --------------------------------------------------------------------------- #
def test_revoke_unknown_returns_false() -> None:
    assert mcp_keys.revoke("mck_nope") is False


def test_revoke_then_re_revoke_idempotent() -> None:
    out = mcp_keys.issue("x")
    assert mcp_keys.revoke(out["id"]) is True
    assert mcp_keys.revoke(out["id"]) is False


# --------------------------------------------------------------------------- #
# Usage summary
# --------------------------------------------------------------------------- #
def test_usage_summary_reflects_calls() -> None:
    out = mcp_keys.issue("x", daily_limit=10)
    row = mcp_keys.authenticate(out["key"])
    mcp_keys.check_and_meter(row, "niches.list")
    mcp_keys.check_and_meter(row, "niches.list")
    s = mcp_keys.usage_summary()
    assert s["total_keys"] == 1
    assert s["keys"][0]["calls_today"] == 2
    assert s["keys"][0]["remaining_today"] == 8
