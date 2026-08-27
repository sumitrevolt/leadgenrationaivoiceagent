"""Smoke test for hot_queue_owner_pack module.

ADR-OWNER-1: ensures the new build_owner_pack engine is importable + idempotent
+ safe when reply_agent.hot_queue() returns empty (no flakes) and never raises.
"""
import asyncio
import os
import sys
import tempfile
import pytest

# Allow running from repo root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_module_imports():
    from app.platform import hot_queue_owner_pack

    assert hasattr(hot_queue_owner_pack, "build_owner_pack")
    assert callable(hot_queue_owner_pack.build_owner_pack)
    assert hasattr(hot_queue_owner_pack, "_push_ntfy")


def test_build_owner_pack_empty_rows_is_ok(tmp_path, monkeypatch):
    """Empty hot_queue must still return ok + write empty CSV (not crash)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    from app.platform import reply_agent
    from app.platform import hot_queue_owner_pack

    def fake_empty(limit=200, scope="boss"):
        return []

    monkeypatch.setattr(reply_agent, "hot_queue", fake_empty)

    r = asyncio.run(hot_queue_owner_pack.build_owner_pack(limit=200, push_ntfy=False))
    assert r.get("ok") is True, r
    assert r.get("rows") == 0
    assert os.path.exists(r.get("csv"))


def test_build_owner_pack_with_rows_writes_csv_and_md(tmp_path, monkeypatch):
    """3 fake rows → 3 CSV lines + a non-empty MD file."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    from app.platform import reply_agent
    from app.platform import hot_queue_owner_pack

    sample = [
        {
            "hq_id": "x1",
            "channel": "calling_flagged",
            "intent": "interested",
            "from": "a@x.com",
            "phone": "+919999999999",
            "business_name": "AFM SOLAR",
            "niche": "solar_residential",
            "city": "Pune",
            "text": "interested",
            "draft": "Namaste",
            "wa_link": "https://wa.me/919999999999?text=Namaste",
            "owner_action": "reply_or_call_then_done",
            "sla_state": "n/a",
            "at": "2026-08-27T00:00:00+00:00",
            "prospect_id": "p1",
        },
        {
            "hq_id": "x2",
            "channel": "calling_flagged",
            "intent": "interested",
            "from": "b@x.com",
            "phone": "+919888888888",
            "business_name": "SAVEMAX",
            "niche": "solar_residential",
            "city": "Mumbai",
            "text": "interested",
            "draft": "Hello",
            "wa_link": "https://wa.me/919888888888?text=Hello",
            "owner_action": "reply_or_call_then_done",
            "sla_state": "n/a",
            "at": "2026-08-26T00:00:00+00:00",
            "prospect_id": "p2",
        },
        {
            "hq_id": "x3",
            "channel": "calling_flagged",
            "intent": "interested",
            "from": "c@x.com",
            "phone": "",
            "business_name": "GLOBAL",
            "niche": "real_estate",
            "city": "Nagpur",
            "text": "interested",
            "draft": "",
            "wa_link": "",
            "owner_action": "reply_or_call_then_done",
            "sla_state": "n/a",
            "at": "2026-08-25T00:00:00+00:00",
            "prospect_id": "p3",
        },
    ]

    def fake_rows(limit=200, scope="boss"):
        return sample

    monkeypatch.setattr(reply_agent, "hot_queue", fake_rows)

    r = asyncio.run(hot_queue_owner_pack.build_owner_pack(limit=200, push_ntfy=False))
    assert r.get("ok") is True
    assert r.get("rows") == 3
    csv_path = r.get("csv")
    md_path = r.get("md")
    assert os.path.exists(csv_path)
    assert os.path.exists(md_path)
    # CSV should have 3 data rows + 1 header
    with open(csv_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 4
    # First data row must have wa_link + phone parsed
    assert "wa.me/919999999999" in lines[1]
    assert "919999999999" in lines[1]


def test_build_owner_pack_never_raises_on_hot_queue_error(tmp_path, monkeypatch):
    """If reply_agent.hot_queue() raises, build_owner_pack returns ok:False, never crashes."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    from app.platform import reply_agent
    from app.platform import hot_queue_owner_pack

    def boom(*a, **kw):
        raise RuntimeError("redis down")

    monkeypatch.setattr(reply_agent, "hot_queue", boom)

    r = asyncio.run(hot_queue_owner_pack.build_owner_pack(limit=200, push_ntfy=False))
    assert r.get("ok") is False
    assert "hot_queue_unavailable" in r.get("error", "")
