"""Tests — clientops batch (speed_to_lead, content_approval, client_snapshots,
lead_distribution, proposal_tracking).

Pure-python: saare store paths tmp_path pe monkeypatch — NO network, NO DB.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest


def _write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


# --------------------------------------------------------------------------- #
# F1: speed_to_lead
# --------------------------------------------------------------------------- #
def test_speed_to_lead_summary(tmp_path, monkeypatch):
    from app.platform import speed_to_lead as stl

    inq = str(tmp_path / "inquiries.jsonl")
    alerts = str(tmp_path / "lead_alerts.jsonl")
    dialer = str(tmp_path / "dialer_logs.jsonl")
    monkeypatch.setattr(stl, "_INQUIRIES_FILE", inq)
    monkeypatch.setattr(stl, "_ALERTS_FILE", alerts)
    monkeypatch.setattr(stl, "_DIALER_FILE", dialer)
    # Hermetic: callback-file bhi isolate karo — real data/ai_callbacks.jsonl me
    # test-phone (9876543210) ka record avg ko pollute karta tha (CI: avg 0.0).
    monkeypatch.setattr(stl, "_CALLBACK_FILE", str(tmp_path / "callbacks.jsonl"))

    now = datetime.now(timezone.utc)
    now_ep = now.timestamp()
    iso = now.replace(tzinfo=None).isoformat() + "Z"
    _write_jsonl(
        inq,
        [
            {"phone": "9876543210", "at": iso, "source": "website"},
            {"phone": "9000000001", "at": iso, "source": "website"},  # untouched
        ],
    )
    # alert 60s baad — under-2-min touch
    _write_jsonl(alerts, [{"phone": "919876543210", "epoch": now_ep + 60}])

    s = stl.summary(days=30)
    assert s["ok"] is True
    assert s["total_inquiries"] == 2
    assert s["touched"] == 1 and s["untouched"] == 1
    assert s["avg_seconds"] == pytest.approx(60, abs=2)
    assert s["under_2min_pct"] == 100.0
    assert isinstance(s["verdict"], str) and len(s["verdict"]) > 10


def test_speed_to_lead_empty_store(tmp_path, monkeypatch):
    from app.platform import speed_to_lead as stl

    monkeypatch.setattr(stl, "_INQUIRIES_FILE", str(tmp_path / "none1.jsonl"))
    monkeypatch.setattr(stl, "_ALERTS_FILE", str(tmp_path / "none2.jsonl"))
    monkeypatch.setattr(stl, "_DIALER_FILE", str(tmp_path / "none3.jsonl"))
    monkeypatch.setattr(stl, "_CALLBACK_FILE", str(tmp_path / "none4.jsonl"))
    s = stl.summary()
    assert s["ok"] is True and s["total_inquiries"] == 0
    assert "2 min" in s["verdict"] or "2 minute" in s["verdict"]


# --------------------------------------------------------------------------- #
# F2: content_approval
# --------------------------------------------------------------------------- #
def test_content_approval_flow(tmp_path, monkeypatch):
    from app.marketing import content_approval as ca

    monkeypatch.setattr(ca, "_FILE", lambda: str(tmp_path / "approvals.jsonl"))

    res = ca.submit("client-1", {"caption": "Diwali offer 20% off", "title": "Diwali post"})
    assert res["ok"] is True
    token = res["approval"]["token"]
    assert res["approval"]["status"] == "pending"
    assert token in res["approve_url"]
    assert "wa.me" in res["wa_link"]

    assert len(ca.pending("client-1")) == 1

    ok = ca.approve(token)
    assert ok["ok"] is True and ok["approval"]["status"] == "approved"
    assert ca.pending("client-1") == []

    # idempotent — dubara approve = already_decided
    again = ca.approve(token)
    assert again["ok"] is True and again.get("already_decided") is True


def test_content_approval_reject_and_unknown(tmp_path, monkeypatch):
    from app.marketing import content_approval as ca

    monkeypatch.setattr(ca, "_FILE", lambda: str(tmp_path / "approvals.jsonl"))

    res = ca.submit("client-2", {"caption": "post"})
    rej = ca.reject(res["approval"]["token"], note="Logo bada karo")
    assert rej["ok"] is True
    assert rej["approval"]["status"] == "rejected"
    assert rej["approval"]["note"] == "Logo bada karo"

    bad = ca.approve("not-a-real-token")
    assert bad["ok"] is False

    # public HTML Hinglish
    html = ca.decision_html({"ok": True, "approval": {"status": "approved"}}, "approve")
    assert "Approve ho gaya" in html


def test_content_approval_decide_by_id(tmp_path, monkeypatch):
    from app.marketing import content_approval as ca

    monkeypatch.setattr(ca, "_FILE", lambda: str(tmp_path / "approvals.jsonl"))

    res = ca.submit("client-admin", {"caption": "Admin decide test", "title": "Post"})
    aid = res["approval"]["id"]
    assert len(ca.pending("client-admin")) == 1

    ok = ca.decide_by_id(aid, "approve")
    assert ok["ok"] is True and ok["approval"]["status"] == "approved"
    assert ca.pending("client-admin") == []

    res2 = ca.submit("client-admin", {"caption": "Reject me"})
    rej = ca.decide_by_id(res2["approval"]["id"], "reject", "change logo")
    assert rej["ok"] is True and rej["approval"]["status"] == "rejected"


# --------------------------------------------------------------------------- #
# F3: client_snapshots
# --------------------------------------------------------------------------- #
def test_snapshot_capture_and_apply(tmp_path, monkeypatch):
    from app.marketing import content_schedule, journeys
    from app.platform import client_snapshots as snaps

    snap_dir = str(tmp_path / "snapshots")
    monkeypatch.setattr(snaps, "_SNAP_DIR", snap_dir)
    monkeypatch.setattr(snaps, "_INDEX_FILE", os.path.join(snap_dir, "index.jsonl"))
    monkeypatch.setattr(journeys, "_JOURNEYS", str(tmp_path / "journeys.jsonl"))
    monkeypatch.setattr(content_schedule, "_FILE", str(tmp_path / "schedule.jsonl"))

    clients = {
        "src-1": {
            "id": "src-1",
            "business_name": "Sharma Solar",
            "slug": "sharma-solar",
            "niche": "solar",
            "city": "Pune",
        },
        "tgt-2": {
            "id": "tgt-2",
            "business_name": "Verma Gym",
            "slug": "verma-gym",
            "niche": "gym",
            "city": "Nashik",
        },
    }
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda cid: clients.get(cid))

    # source data: ek journey rule (client-linked) + ek FUTURE scheduled item
    journeys.add_journey(
        "Inquiry pe WA draft",
        "inquiry_received",
        [{"type": "draft_whatsapp", "params": {"client_id": "src-1"}}],
        condition={"client_id": "src-1"},
    )
    content_schedule.schedule(
        "Sharma Solar",
        niche="solar",
        date_iso="2099-01-01",
        occasion="New Year",
        offer="10% off",
        channel="instagram",
        client_id="src-1",
    )

    cap = snaps.capture("src-1", "Solar starter setup")
    assert cap["ok"] is True
    assert "journeys" in cap["sections"]
    assert "content_schedule" in cap["sections"]
    assert "cadence_template" in cap["sections"]
    sid = cap["snapshot_id"]
    assert snaps.get_snapshot(sid) is not None
    assert any(s["id"] == sid for s in snaps.list_snapshots())

    before_rules = len(journeys.list_journeys())
    res = snaps.apply(sid, "tgt-2")
    assert res["ok"] is True
    assert "applied" in str(res["results"].get("journeys", ""))
    assert "applied" in str(res["results"].get("content_schedule", ""))

    # naye records APPEND hue — source mutate nahi
    rules = journeys.list_journeys()
    assert len(rules) == before_rules + 1
    new_rule = rules[-1]
    assert new_rule["enabled"] is False  # snapshot rules disabled aate
    assert "tgt-2" in json.dumps(new_rule)  # client_id swap hua
    # source rule untouched
    assert "src-1" in json.dumps(rules[0])

    sched = content_schedule.list_scheduled()
    tgt_items = [i for i in sched if i.get("client_id") == "tgt-2"]
    assert len(tgt_items) == 1 and tgt_items[0]["occasion"] == "New Year"


def test_snapshot_missing(tmp_path, monkeypatch):
    from app.platform import client_snapshots as snaps

    monkeypatch.setattr(snaps, "_SNAP_DIR", str(tmp_path / "s2"))
    monkeypatch.setattr(snaps, "_INDEX_FILE", str(tmp_path / "s2" / "index.jsonl"))
    assert snaps.apply("doesnotexist", "x")["ok"] is False
    assert snaps.capture("", "")["ok"] is False


def test_niche_snapshot_capture_and_apply(tmp_path, monkeypatch):
    from app.marketing import content_schedule, journeys
    from app.platform import client_snapshots as snaps

    snap_dir = str(tmp_path / "snapshots")
    monkeypatch.setattr(snaps, "_SNAP_DIR", snap_dir)
    monkeypatch.setattr(snaps, "_INDEX_FILE", os.path.join(snap_dir, "index.jsonl"))
    monkeypatch.setattr(journeys, "_JOURNEYS", str(tmp_path / "journeys.jsonl"))
    monkeypatch.setattr(content_schedule, "_FILE", str(tmp_path / "schedule.jsonl"))

    clients = {
        "tgt-3": {
            "id": "tgt-3",
            "business_name": "Sharma Coaching",
            "slug": "sharma-coaching",
            "niche": "coaching",
            "city": "Surat",
        },
    }
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda cid: clients.get(cid))

    cap = snaps.capture_from_niche("coaching", "Coaching starter")
    assert cap["ok"] is True
    assert cap.get("niche_key") == "coaching"
    assert "journeys" in cap["sections"]
    assert "mini_site" in cap["sections"]
    sid = cap["snapshot_id"]
    assert snaps.find_niche_snapshot("coaching") == sid

    before = len(journeys.list_journeys())
    res = snaps.apply_niche_to_client("tgt-3", "coaching")
    assert res["ok"] is True
    assert len(journeys.list_journeys()) == before + 2
    assert res.get("auto_captured") is False

    res2 = snaps.apply_niche_to_client("tgt-3", "coaching")
    assert res2["ok"] is True


def test_niche_snapshot_unknown_niche(tmp_path, monkeypatch):
    from app.platform import client_snapshots as snaps

    monkeypatch.setattr(snaps, "_SNAP_DIR", str(tmp_path / "s3"))
    monkeypatch.setattr(snaps, "_INDEX_FILE", str(tmp_path / "s3" / "index.jsonl"))
    assert snaps.capture_from_niche("not_a_real_niche_xyz")["ok"] is False


# --------------------------------------------------------------------------- #
# F4: lead_distribution
# --------------------------------------------------------------------------- #
def test_round_robin_assignment(tmp_path, monkeypatch):
    from app.platform import lead_distribution as ld

    monkeypatch.setattr(ld, "_ROUTING_FILE", str(tmp_path / "routing.jsonl"))
    monkeypatch.setattr(ld, "_ASSIGN_FILE", str(tmp_path / "assigns.jsonl"))

    cfg = ld.set_config(
        "client-1",
        [{"name": "Amit", "phone": "9876543210"}, {"name": "Priya", "phone": "9123456780"}],
    )
    assert cfg["ok"] is True and len(cfg["config"]["members"]) == 2

    a1 = ld.assign("client-1", {"name": "Lead One", "phone": "9000000001"})
    a2 = ld.assign("client-1", {"name": "Lead Two", "phone": "9000000002"})
    a3 = ld.assign("client-1", {"name": "Lead Three", "phone": "9000000003"})
    assert a1["assigned_to"]["name"] == "Amit"
    assert a2["assigned_to"]["name"] == "Priya"
    assert a3["assigned_to"]["name"] == "Amit"  # wrap-around
    assert "wa.me/919876543210" in a1["wa_link"]
    assert "Lead One" in a1["message"]

    rows = ld.assignments("client-1")
    assert len(rows) == 3
    assert rows[0]["lead"]["name"] == "Lead Three"  # newest first


def test_assignment_without_config(tmp_path, monkeypatch):
    from app.platform import lead_distribution as ld

    monkeypatch.setattr(ld, "_ROUTING_FILE", str(tmp_path / "r2.jsonl"))
    monkeypatch.setattr(ld, "_ASSIGN_FILE", str(tmp_path / "a2.jsonl"))
    res = ld.assign("no-config-client", {"name": "x", "phone": "9000000000"})
    assert res["ok"] is False and "routing" in res["error"]
    assert ld.maybe_assign("no-config-client", {"name": "x"}) is None
    # invalid members reject
    bad = ld.set_config("c", [{"name": "NoPhone", "phone": "12"}])
    assert bad["ok"] is False


def test_maybe_assign_when_configured(tmp_path, monkeypatch):
    from app.platform import lead_distribution as ld

    monkeypatch.setattr(ld, "_ROUTING_FILE", str(tmp_path / "r3.jsonl"))
    monkeypatch.setattr(ld, "_ASSIGN_FILE", str(tmp_path / "a3.jsonl"))
    ld.set_config("c1", [{"name": "A", "phone": "9876543210"}])
    out = ld.maybe_assign("c1", {"name": "Lead", "phone": "9000000001"})
    assert out and out.get("ok") is True
    assert out["assigned_to"]["name"] == "A"


def test_list_approvals_enriches_business_name(tmp_path, monkeypatch):
    """ADR-104 (2026-07-15, Priority 3): GET /api/clientops/approvals now adds
    business_name (+ client_status) to each row so the admin Approvals table
    can show a readable name instead of the raw client id. Known client ->
    business_name populated, client_status='ok'. Deleted/unknown client ->
    business_name=None, client_status='unknown', client_id untouched (never
    dropped) so the approve/reject buttons still work."""
    import asyncio

    from app.api import clientops
    from app.marketing import clients_store
    from app.marketing import content_approval as ca

    monkeypatch.setattr(ca, "_FILE", lambda: str(tmp_path / "approvals.jsonl"))
    ca.submit("known-1", {"title": "Diwali post", "caption": "20% off"})
    ca.submit("deleted-99", {"title": "Old post", "caption": "gone client"})

    monkeypatch.setattr(
        clients_store,
        "list_clients",
        lambda status=None, product=None: [
            {"id": "known-1", "business_name": "Sharma Solar"},
            {"id": "other-client", "business_name": "Verma Gym"},
        ],
    )

    result = asyncio.get_event_loop().run_until_complete(
        clientops.list_approvals(client_id="", status="pending")
    )
    assert result["ok"] is True
    by_client = {r["client_id"]: r for r in result["approvals"]}

    assert by_client["known-1"]["business_name"] == "Sharma Solar"
    assert by_client["known-1"]["client_status"] == "ok"

    assert by_client["deleted-99"]["business_name"] is None
    assert by_client["deleted-99"]["client_status"] == "unknown"
    # client_id itself must survive untouched -- decide buttons need it
    assert by_client["deleted-99"]["client_id"] == "deleted-99"


def test_list_approvals_enrichment_never_raises_on_store_failure(tmp_path, monkeypatch):
    """If clients_store.list_clients() itself errors, the approvals list must
    still return successfully (fail-open enrichment, per project convention:
    external/secondary lookups never crash the primary response)."""
    import asyncio

    from app.api import clientops
    from app.marketing import clients_store
    from app.marketing import content_approval as ca

    monkeypatch.setattr(ca, "_FILE", lambda: str(tmp_path / "approvals2.jsonl"))
    ca.submit("client-z", {"title": "Post", "caption": "x"})

    def _boom(status=None, product=None):
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(clients_store, "list_clients", _boom)

    result = asyncio.get_event_loop().run_until_complete(
        clientops.list_approvals(client_id="", status="pending")
    )
    assert result["ok"] is True
    assert result["approvals"][0]["client_id"] == "client-z"
    assert result["approvals"][0]["business_name"] is None


def test_approval_decide_for_client(tmp_path, monkeypatch):
    from app.marketing import content_approval as ca

    monkeypatch.setattr(ca, "_FILE", lambda: str(tmp_path / "ap.jsonl"))
    sub = ca.submit("client-x", {"title": "Test", "caption": "Hello"})
    assert sub["ok"] is True
    aid = sub["approval"]["id"]
    bad = ca.decide_for_client("other", aid, "approve")
    assert bad["ok"] is False
    ok = ca.decide_for_client("client-x", aid, "approve")
    assert ok["ok"] is True
    assert ok["approval"]["status"] == "approved"


# --------------------------------------------------------------------------- #
# F5: proposal_tracking
# --------------------------------------------------------------------------- #
def test_proposal_tracking_url(tmp_path, monkeypatch):
    from app.platform import proposal_tracking as pt

    monkeypatch.setattr(pt, "_LINKS_FILE", str(tmp_path / "props.jsonl"))
    monkeypatch.setattr(pt, "_VIEWS_FILE", str(tmp_path / "views.jsonl"))
    monkeypatch.setattr(pt, "_HTML_DIR", str(tmp_path / "html"))

    res = pt.make_tracked(
        url="https://example.com/proposal.pdf", phone="9876543210", label="Sharma proposal"
    )
    assert res["ok"] is True
    token = res["token"]
    assert f"/api/clientops/p/{token}" in res["tracking_url"]

    assert pt.views(token)["opened"] is False
    pt.record_view(token, ua="Mozilla/5.0", ip="49.36.12.99")
    v = pt.views(token)
    assert v["opened"] is True and v["view_count"] == 1
    assert v["views"][0]["ip"] == "49.36.12.x"  # coarse IP — privacy

    assert pt.resolve(token) == {"url": "https://example.com/proposal.pdf"}
    listed = pt.list_tracked()
    assert listed[0]["token"] == token and listed[0]["opened"] is True


def test_proposal_tracking_html_and_invalid(tmp_path, monkeypatch):
    from app.platform import proposal_tracking as pt

    monkeypatch.setattr(pt, "_LINKS_FILE", str(tmp_path / "p2.jsonl"))
    monkeypatch.setattr(pt, "_VIEWS_FILE", str(tmp_path / "v2.jsonl"))
    monkeypatch.setattr(pt, "_HTML_DIR", str(tmp_path / "h2"))

    res = pt.make_tracked(html="<h1>Proposal: Verma Gym</h1>")
    assert res["ok"] is True
    out = pt.resolve(res["token"])
    assert "Verma Gym" in out["html"]

    assert pt.resolve("unknown-token-xyz") is None
    assert pt.make_tracked()["ok"] is False  # na url na html
    assert pt.make_tracked(url="ftp://bad")["ok"] is False


# --------------------------------------------------------------------------- #
# Router import sanity (mount main session karega)
# --------------------------------------------------------------------------- #
def test_router_imports_and_routes():
    from app.api.clientops import router

    paths = {r.path for r in router.routes}
    assert "/clientops/speed-to-lead" in paths
    assert "/clientops/approve/{token}" in paths
    assert "/clientops/snapshots/capture" in paths
    assert "/clientops/snapshots/capture-niche" in paths
    assert "/clientops/snapshots/apply-niche" in paths
    assert "/clientops/snapshots/{snapshot_id}" in paths
    assert "/clientops/routing/assign" in paths
    assert "/clientops/p/{token}" in paths
