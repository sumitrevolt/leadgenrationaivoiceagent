"""Reseller / Agency program — store + program_info (pure python, no network)."""

from __future__ import annotations

import pytest


@pytest.fixture
def rs(tmp_path, monkeypatch):
    """Fresh reseller module pointed at an isolated tmp store; notify is a no-op."""
    from app.platform import reseller as _rs

    monkeypatch.setattr(_rs, "_STORE", str(tmp_path / "reseller_applications.json"))
    monkeypatch.setattr(_rs, "_notify_admin", lambda *_a, **_k: None)
    return _rs


def test_submit_creates_pending(rs):
    out = rs.submit_application(
        name="Sumit",
        agency="GrowthCo",
        email="sumit@growthco.in",
        phone="9876543210",
        city="Indore",
        clients_estimate=8,
        message="serve restaurants",
    )
    assert out["ok"] is True
    assert out["status"] == "pending"
    assert out["decided_at"] is None
    assert out["id"].startswith("rs-")
    assert out["clients_estimate"] == 8
    assert out["agency"] == "GrowthCo"


def test_submit_rejects_missing_name(rs):
    out = rs.submit_application(name="", agency="X", email="a@b.com")
    assert out["ok"] is False
    assert "error" in out


def test_submit_rejects_bad_email(rs):
    out = rs.submit_application(name="A", agency="X", email="not-an-email")
    assert out["ok"] is False
    assert "error" in out


def test_list_filter_by_status(rs):
    rs.submit_application(name="A", agency="A1", email="a@b.com")
    rs.submit_application(name="B", agency="B1", email="b@c.com")
    pending = rs.list_applications(status="pending")
    assert len(pending) == 2
    assert all(r["status"] == "pending" for r in pending)
    assert rs.list_applications(status="approved") == []


def test_list_all_no_filter(rs):
    rs.submit_application(name="A", agency="A1", email="a@b.com")
    rs.submit_application(name="B", agency="B1", email="b@c.com")
    assert len(rs.list_applications()) == 2


def test_decide_approve_flips_status(rs):
    sub = rs.submit_application(name="A", agency="A1", email="a@b.com")
    aid = sub["id"]
    rec = rs.decide(aid, approve=True)
    assert rec["status"] == "approved"
    assert rec["decided_at"] is not None
    assert rec["decided_by"] == "admin"
    # persisted
    assert rs.list_applications(status="approved")[0]["id"] == aid
    assert rs.list_applications(status="pending") == []


def test_decide_reject_flips_status(rs):
    sub = rs.submit_application(name="A", agency="A1", email="a@b.com")
    rec = rs.decide(sub["id"], approve=False)
    assert rec["status"] == "rejected"
    assert rec["decided_at"] is not None


def test_decide_not_found(rs):
    out = rs.decide("rs-999-deadbe", approve=True)
    assert out == {"ok": False, "error": "not_found"}


def test_ids_unique_across_submissions(rs):
    a = rs.submit_application(name="A", agency="A1", email="a@b.com")
    b = rs.submit_application(name="B", agency="B1", email="b@c.com")
    assert a["id"] != b["id"]


def test_program_info_shape(rs):
    info = rs.program_info()
    assert isinstance(info, dict)
    assert "commission_tiers" in info
    tiers = info["commission_tiers"]
    assert isinstance(tiers, list) and len(tiers) >= 3
    assert all("rate_pct" in t for t in tiers)
    assert {t["rate_pct"] for t in tiers} == {20, 25, 30}
    assert "whats_included" in info


def test_clients_estimate_coerces_bad_input(rs):
    out = rs.submit_application(
        name="A",
        agency="A1",
        email="a@b.com",
        clients_estimate="not-int",  # type: ignore[arg-type]
    )
    assert out["ok"] is True
    assert out["clients_estimate"] == 0
