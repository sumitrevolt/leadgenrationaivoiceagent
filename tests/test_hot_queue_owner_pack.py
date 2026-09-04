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
    from app.platform import hot_queue_owner_pack, reply_agent

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
    from app.platform import hot_queue_owner_pack, reply_agent

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
    with open(csv_path, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 4
    # First data row must have wa_link + phone parsed
    assert "wa.me/919999999999" in lines[1]
    assert "919999999999" in lines[1]


def _row(hq_id, phone, wa_link=None, name="BIZ"):
    return {
        "hq_id": hq_id,
        "channel": "calling_flagged",
        "intent": "interested",
        "from": f"{hq_id}@x.com",
        "phone": phone,
        "business_name": name,
        "niche": "solar_residential",
        "city": "Pune",
        "text": "interested",
        "draft": "",
        "wa_link": wa_link or "",
        "owner_action": "reply_or_call_then_done",
        "sla_state": "n/a",
        "at": "2026-08-27T00:00:00+00:00",
        "prospect_id": hq_id,
    }


def test_existing_customer_phone_is_excluded_from_pack(tmp_path, monkeypatch):
    """A row whose phone belongs to a paying customer must never reach the pack."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    from app.platform import hot_queue_owner_pack, reply_agent

    rows = [
        _row("p1", "+919876543210", name="JIYA-CUSTOMER"),   # Jiya Makeover
        _row("p2", "919888888888", name="REAL-PROSPECT"),
        _row("p3", "9876543210", name="SAME-CUSTOMER-BARE"),  # same number, bare form
    ]
    monkeypatch.setattr(reply_agent, "hot_queue", lambda limit=200, scope="boss": rows)
    monkeypatch.setattr(
        hot_queue_owner_pack,
        "_existing_customer_phones",
        lambda: ({"9876543210"}, True),
    )

    r = asyncio.run(hot_queue_owner_pack.build_owner_pack(limit=200, push_ntfy=False))
    assert r.get("ok") is True
    assert r.get("rows") == 1, r
    assert r.get("excluded_existing_customers") == 2, r
    assert r.get("customer_suppression") == "active"

    with open(r["csv"], encoding="utf-8") as f:
        body = f.read()
    assert "9876543210" not in body          # excluded in both +91 and bare form
    assert "919888888888" in body            # the real prospect survives


def test_suppression_matches_wa_link_only_row(tmp_path, monkeypatch):
    """A row with no `phone` but a customer wa.me link must also be excluded."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    from app.platform import hot_queue_owner_pack, reply_agent

    rows = [_row("p1", "", wa_link="https://wa.me/919876543210?text=hi")]
    monkeypatch.setattr(reply_agent, "hot_queue", lambda limit=200, scope="boss": rows)
    monkeypatch.setattr(
        hot_queue_owner_pack,
        "_existing_customer_phones",
        lambda: ({"9876543210"}, True),
    )

    r = asyncio.run(hot_queue_owner_pack.build_owner_pack(limit=200, push_ntfy=False))
    assert r.get("rows") == 0, r
    assert r.get("excluded_existing_customers") == 1, r


def test_unverified_suppression_is_reported_not_silent(tmp_path, monkeypatch):
    """Unreadable client store must surface `unverified`, never pretend it is clean."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    from app.platform import hot_queue_owner_pack, reply_agent

    rows = [_row("p1", "919888888888")]
    monkeypatch.setattr(reply_agent, "hot_queue", lambda limit=200, scope="boss": rows)
    monkeypatch.setattr(
        hot_queue_owner_pack, "_existing_customer_phones", lambda: (set(), False)
    )

    r = asyncio.run(hot_queue_owner_pack.build_owner_pack(limit=200, push_ntfy=False))
    assert r.get("customer_suppression") == "unverified", r
    assert r.get("rows") == 1, r  # fail-visible: rows pass through, state is flagged
    with open(r["md"], encoding="utf-8") as f:
        assert "UNVERIFIED" in f.read()


def test_suppression_lookup_never_raises(tmp_path, monkeypatch):
    """A exploding suppression lookup must not take the daily pack down with it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    from app.platform import hot_queue_owner_pack, reply_agent

    monkeypatch.setattr(
        reply_agent, "hot_queue", lambda limit=200, scope="boss": [_row("p1", "919888888888")]
    )

    def boom():
        raise RuntimeError("store locked")

    monkeypatch.setattr(hot_queue_owner_pack, "_existing_customer_phones", boom)

    r = asyncio.run(hot_queue_owner_pack.build_owner_pack(limit=200, push_ntfy=False))
    assert r.get("ok") is True, r
    assert r.get("customer_suppression") == "unverified", r
    assert r.get("rows") == 1, r


def test_last10_normalisation():
    from app.platform import hot_queue_owner_pack

    assert hot_queue_owner_pack._last10("+919876543210") == "9876543210"
    assert hot_queue_owner_pack._last10("919876543210") == "9876543210"
    assert hot_queue_owner_pack._last10("+91 98765-43210") == "9876543210"
    assert hot_queue_owner_pack._last10("") == ""
    assert hot_queue_owner_pack._last10("12345") == ""  # too short to be a phone


def test_build_owner_pack_never_raises_on_hot_queue_error(tmp_path, monkeypatch):
    """If reply_agent.hot_queue() raises, build_owner_pack returns ok:False, never crashes."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    from app.platform import hot_queue_owner_pack, reply_agent

    def boom(*a, **kw):
        raise RuntimeError("redis down")

    monkeypatch.setattr(reply_agent, "hot_queue", boom)

    r = asyncio.run(hot_queue_owner_pack.build_owner_pack(limit=200, push_ntfy=False))
    assert r.get("ok") is False
    assert "hot_queue_unavailable" in r.get("error", "")
