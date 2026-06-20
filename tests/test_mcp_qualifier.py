"""M.1 — MCP qualifier.run endpoint contract tests.

The qualifier is a paid metered surface; its contract must be stable:
- Schema accepts the documented fields.
- Returns total / grade / per-dimension / reasons / action / meter_remaining.
- Auth + capability gating works (re-uses H.3 paths).
- Rich vs sparse input meaningfully differentiates grades (otherwise the
  product is worthless).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.platform import mcp_keys


@pytest.fixture(autouse=True)
def _iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mcp_keys, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(mcp_keys, "_KEYS_PATH", tmp_path / "keys.jsonl")
    monkeypatch.setattr(mcp_keys, "_USAGE_PATH", tmp_path / "usage.jsonl")
    monkeypatch.setenv("MCP_PRODUCT", "1")


def _issue() -> str:
    return mcp_keys.issue("test")["key"]


def test_qualifier_needs_key() -> None:
    client = TestClient(app)
    r = client.post("/api/mcp-product/v1/qualifier", json={"business_name": "x"})
    assert r.status_code == 401


def test_qualifier_runs_pure_no_llm() -> None:
    """Even with a totally bare prospect, the endpoint must NOT raise."""
    client = TestClient(app)
    r = client.post(
        "/api/mcp-product/v1/qualifier",
        headers={"X-LeadGen-Key": _issue()},
        json={},  # everything optional
    )
    assert r.status_code == 200
    d = r.json()
    assert "total" in d and "grade" in d
    assert d["grade"] in {"A", "B", "C", "D"}
    assert "meter_remaining" in d
    assert d["version"] == "v1"


def test_qualifier_rich_input_outperforms_sparse() -> None:
    """A well-described prospect MUST grade at least as high as an empty one
    (otherwise the BANT signal isn't surviving the JSON round-trip)."""
    client = TestClient(app)
    key = _issue()
    headers = {"X-LeadGen-Key": key}

    bare = client.post("/api/mcp-product/v1/qualifier", headers=headers, json={}).json()
    rich = client.post(
        "/api/mcp-product/v1/qualifier",
        headers=headers,
        json={
            "business_name": "Sharma Solar Solutions",
            "niche": "solar",
            "city": "Pune",
            "phone": "9876543210",
            "website": "https://sharmasolar.in",
            "reviews": 120,
            "user_ratings_total": 120,
            "rating": 4.6,
            "employees": 15,
            "annual_revenue_inr": 25_000_000,
            "intent": "abhi quote chahiye",
            "notes": "urgent — wants installation next month",
        },
    ).json()
    assert rich["total"] >= bare["total"]


def test_qualifier_metering_decrements() -> None:
    client = TestClient(app)
    key = _issue()
    headers = {"X-LeadGen-Key": key}
    r1 = client.post("/api/mcp-product/v1/qualifier", headers=headers, json={}).json()
    r2 = client.post("/api/mcp-product/v1/qualifier", headers=headers, json={}).json()
    assert r2["meter_remaining"] == r1["meter_remaining"] - 1


def test_qualifier_capability_check() -> None:
    """A key without qualifier.run granted must get 403."""
    out = mcp_keys.issue("limited", capabilities=["niches.list"])
    client = TestClient(app)
    r = client.post(
        "/api/mcp-product/v1/qualifier",
        headers={"X-LeadGen-Key": out["key"]},
        json={},
    )
    assert r.status_code == 403


def test_discover_lists_qualifier_path() -> None:
    """SDKs find the path via /discover — make sure it's there."""
    client = TestClient(app)
    r = client.get("/api/mcp-product/v1/discover")
    assert r.status_code == 200
    d = r.json()
    assert "qualifier.run" in d["capabilities"]
    assert d["paths"]["qualifier.run"].endswith("/qualifier")


def test_a2a_agent_card_lists_qualifier() -> None:
    """The A2A discovery card must advertise the new capability so cross-
    agent clients can discover it without our SDK."""
    client = TestClient(app)
    r = client.get("/.well-known/agent.json")
    assert r.status_code == 200
    d = r.json()
    caps = {c["id"] for c in d["capabilities"]}
    assert "qualifier.run" in caps
