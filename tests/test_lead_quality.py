"""Tests for the read-only leads/CRM quality-assurance aggregator
(app/marketing/lead_quality.py).

Hermetic: every external primitive is monkeypatched (prospect store reader, lead
scorer, tenant resolver, team activity feed), so NO live production lead data is
read or mutated. Covers duplicate detection, missing-contact detection, the
read-only guarantee (write functions raise if called), never-raises resilience on
a bad record, and the AgentRunResult-shaped record.
"""

# ruff: noqa: I001
from __future__ import annotations

from datetime import datetime, timezone

from app.marketing import clients_store
from app.marketing import lead_quality as lq
from app.platform import lead_scoring, prospector, team


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _install(monkeypatch, leads, *, forbid_writes=True, score_fn=None):
    """Wire hermetic stubs and return the captured team.log_event calls list."""
    monkeypatch.setattr(prospector, "list_prospects", lambda status=None, limit=100: list(leads))
    # tenant resolver → identity (no file I/O); empty handled by module -> 'platform'
    monkeypatch.setattr(clients_store, "canonical_client_id", lambda cid: str(cid or "").strip())
    if score_fn is not None:
        monkeypatch.setattr(lead_scoring, "score_lead", score_fn)

    events = []
    monkeypatch.setattr(team, "log_event", lambda *a, **k: events.append((a, k)))

    if forbid_writes:

        def _boom(*a, **k):
            raise AssertionError("WRITE called from read-only lead-quality scan")

        monkeypatch.setattr(prospector, "set_prospect_fields", _boom)
        monkeypatch.setattr(prospector, "set_prospect_fields_bulk", _boom)
        monkeypatch.setattr(prospector, "mark_prospect", _boom)
        monkeypatch.setattr(clients_store, "update_client", _boom)
        monkeypatch.setattr(clients_store, "delete_client", _boom)
        monkeypatch.setattr(clients_store, "dedupe_clients", _boom)
    return events


def _issue(res, kind):
    for i in res["issues"]:
        if i["type"] == kind:
            return i
    raise AssertionError(f"issue {kind!r} not present in {[i['type'] for i in res['issues']]}")


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_detects_duplicate_leads_same_phone(monkeypatch):
    """Two leads with the same normalised phone (same tenant) = one duplicate."""
    leads = [
        {"id": "a", "business_name": "Alpha", "phone": "+91 98765 43210", "lead_score": 70},
        {"id": "b", "business_name": "Beta", "phone": "098765-43210", "lead_score": 70},
    ]
    events = _install(monkeypatch, leads)
    res = lq.scan_lead_quality()
    assert res["status"] == "success"
    dup = _issue(res, "duplicate_leads")
    assert dup["count"] >= 1
    assert res["counts"]["duplicate_leads"] >= 1
    assert dup["sample"] and dup["sample"][0]["key"] == "9876543210"
    # exactly one observability event, under the leads-manager owner
    assert events and events[0][0][0] == "rohan"


def test_cross_tenant_same_phone_is_not_a_duplicate(monkeypatch):
    """Same phone under two different tenants must NOT be flagged (tenant-safe)."""
    leads = [
        {
            "id": "a",
            "business_name": "A",
            "phone": "9876543210",
            "client_id": "t1",
            "lead_score": 70,
        },
        {
            "id": "b",
            "business_name": "B",
            "phone": "9876543210",
            "client_id": "t2",
            "lead_score": 70,
        },
    ]
    _install(monkeypatch, leads)
    res = lq.scan_lead_quality()
    assert _issue(res, "duplicate_leads")["count"] == 0


def test_detects_missing_contact(monkeypatch):
    leads = [
        {"id": "c", "business_name": "NoContact", "phone": "", "email": "", "lead_score": 10},
        {"id": "d", "business_name": "HasPhone", "phone": "9812345678", "lead_score": 10},
    ]
    _install(monkeypatch, leads)
    res = lq.scan_lead_quality()
    miss = _issue(res, "missing_contact")
    assert miss["count"] == 1
    assert miss["sample"][0]["id"] == "c"


def test_detects_stale_hot_lead(monkeypatch):
    """A hot lead with no follow-up touch is stale; a recently-emailed one is not."""
    leads = [
        {"id": "h1", "business_name": "StaleHot", "phone": "9111111111", "lead_score": 85},
        {
            "id": "h2",
            "business_name": "FreshHot",
            "phone": "9222222222",
            "lead_score": 85,
            "emailed_at": _now_iso(),
        },
    ]
    _install(monkeypatch, leads)
    res = lq.scan_lead_quality()
    stale = _issue(res, "stale_hot_leads")
    assert stale["count"] == 1
    assert stale["sample"][0]["id"] == "h1"
    assert res["counts"]["hot_leads"] == 2


def test_detects_unqualified_and_unscored(monkeypatch):
    """Below-threshold leads = unqualified; leads the scorer can't score = unscored."""
    leads = [
        {"id": "u1", "business_name": "Cold", "phone": "9333333333", "lead_score": 20},
        {"id": "u2", "business_name": "NoScore", "phone": "9444444444"},
    ]

    def _boom_score(_rec):
        raise RuntimeError("scorer down")

    _install(monkeypatch, leads, score_fn=_boom_score)
    res = lq.scan_lead_quality()
    assert res["status"] == "success"
    assert res["counts"]["unqualified"] == 1  # u1 (stored score 20 < threshold)
    assert res["counts"]["unscored"] == 1  # u2 (scorer raised → None)
    assert _issue(res, "unqualified_leads")["count"] == 2


def test_scan_is_read_only_no_writes(monkeypatch):
    """If any write primitive is invoked the stub raises — scan must still succeed."""
    leads = [
        {"id": "a", "business_name": "A", "phone": "9876543210", "lead_score": 70},
        {"id": "b", "business_name": "B", "phone": "9876543210", "lead_score": 70},
        {"id": "c", "business_name": "C", "phone": "", "email": ""},
    ]
    _install(monkeypatch, leads, forbid_writes=True)
    res = lq.scan_lead_quality()
    assert res["status"] == "success"  # proves no write path was hit


def test_never_raises_on_bad_record(monkeypatch):
    """A malformed record can't sink the scan (never-raises contract)."""
    leads = [
        {"id": "ok", "business_name": "Good", "phone": "9812345678", "lead_score": 65},
        {"id": "bad", "phone": {"weird": 1}, "email": 123, "lead_score": "not-a-number"},
    ]

    def _boom_score(_rec):
        raise RuntimeError("scorer blew up")

    _install(monkeypatch, leads, score_fn=_boom_score)
    res = lq.scan_lead_quality()
    assert res["status"] == "success"
    assert res["checked"] == 2
    # bad record has no reachable contact and could not be scored
    assert res["counts"]["missing_contact"] >= 1
    assert res["counts"]["unscored"] >= 1


def test_run_result_shape_and_summary(monkeypatch):
    leads = [
        {"id": "a", "business_name": "A", "phone": "9876543210", "lead_score": 70},
        {"id": "b", "business_name": "B", "phone": "", "email": "", "lead_score": 10},
    ]
    _install(monkeypatch, leads)
    res = lq.scan_lead_quality()
    for key in (
        "run_id",
        "agent_id",
        "domain",
        "lane",
        "status",
        "started_at",
        "completed_at",
        "latency_ms",
        "checked",
        "issues",
        "counts",
        "error",
    ):
        assert key in res, key
    assert res["agent_id"] == "lead_quality"
    assert res["domain"] == "leads_crm"
    assert res["lane"] == "GREEN"
    assert isinstance(res["latency_ms"], int)
    assert isinstance(res["issues"], list)
    types = {i["type"] for i in res["issues"]}
    assert types == {
        "duplicate_leads",
        "missing_contact",
        "unqualified_leads",
        "stale_hot_leads",
    }
    assert res["counts"]["total_leads"] == 2

    summ = lq.lead_quality_summary()
    assert summ["checked"] == 2
    assert "total_issues" in summ
    assert isinstance(summ["issue_totals"], list)


def test_empty_store_is_clean_ok_event(monkeypatch):
    events = _install(monkeypatch, [])
    res = lq.scan_lead_quality()
    assert res["status"] == "success"
    assert res["checked"] == 0
    assert all(i["count"] == 0 for i in res["issues"])
    # no issues → status 'ok' on the emitted event
    assert events and events[0][1].get("status") == "ok"
