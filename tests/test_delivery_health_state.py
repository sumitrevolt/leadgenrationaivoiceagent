"""Delivery-health STATE machine (admin Command Center — At-Risk detection).

Covers (1) each of the 7 reachable states of
`admin_dashboard_builders.delivery_health()` via synthetic client+summary+recent
fixtures; (2) the at-risk 7d-value / 24h-failure branches; (3) the time-window
boundaries of `delivery_ledger.recent_counts()` (the additive windowed helper
that feeds delivery_health) written as temp jsonl through the module's own
`_LEDGER_DIR` call-time resolver (same monkeypatch style as the other ledger tests); (4) the
_build_command_center wiring — new `at_risk_count`/`benefit_this_week` scalars +
per-customer `health` — AND that every pre-existing response field is still
present (frontends depend on them)."""

import json
import os
from datetime import datetime, timedelta, timezone

from app.api.admin_dashboard_builders import delivery_health

_VALID_ACTIONS = {
    "open_setup",
    "generate_campaign",
    "approve_content",
    "investigate_failure",
    "none",
}


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _client(**kw):
    base = {
        "id": "c",
        "business_name": "Biz",
        "plan": "starter",
        "status": "active",
        "setup_done": True,
    }
    base.update(kw)
    return base


def _summary(**kw):
    base = {
        "events_total": 0,
        "posts_created": 0,
        "posts_approved": 0,
        "posts_published": 0,
    }
    base.update(kw)
    return base


def _recent(value=False, failures=0):
    return {"value_events_in_window": value, "failures_24h": failures}


def _assert_shape(h):
    assert set(h.keys()) >= {
        "state",
        "label_hi",
        "reason",
        "next_action",
        "next_action_hint",
        "tone",
    }
    assert h["next_action"] in _VALID_ACTIONS
    assert h["tone"] in {"ok", "warn", "err", "muted"}


# --------------------------------------------------------------------------- #
# the 7 states, in precedence order
# --------------------------------------------------------------------------- #
def test_state_at_risk_when_no_value_in_7d():
    h = delivery_health(
        _client(setup_done=True),
        _summary(events_total=5, posts_created=2, posts_approved=1, posts_published=1),
        0,
        _recent(value=False),
    )
    assert h["state"] == "at_risk"
    assert h["next_action"] == "investigate_failure"
    assert h["tone"] == "err"
    _assert_shape(h)


def test_state_at_risk_when_recent_failure_even_with_value():
    """A failure in the last 24h forces at_risk even if value landed in 7d."""
    h = delivery_health(
        _client(setup_done=True),
        _summary(events_total=5, posts_created=2, posts_approved=1, posts_published=1),
        0,
        _recent(value=True, failures=1),
    )
    assert h["state"] == "at_risk"
    assert "failure" in h["reason"].lower()
    _assert_shape(h)


def test_at_risk_trumps_pending_approval():
    """at_risk precedence: even with pending approvals, no-value-7d wins."""
    h = delivery_health(
        _client(setup_done=True),
        _summary(events_total=5, posts_created=2),
        3,
        _recent(value=False),
    )
    assert h["state"] == "at_risk"


def test_state_not_started_when_zero_events():
    h = delivery_health(_client(setup_done=False), _summary(events_total=0), 0, _recent())
    assert h["state"] == "not_started"
    assert h["next_action"] == "open_setup"
    assert h["tone"] == "warn"
    _assert_shape(h)


def test_state_blocked_when_setup_stuck_over_24h():
    created = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    h = delivery_health(
        _client(setup_done=False, created_at=created),
        _summary(events_total=2),  # has some events, so not "not_started"
        0,
        _recent(),
    )
    assert h["state"] == "blocked"
    assert h["next_action"] == "open_setup"
    assert h["tone"] == "err"
    _assert_shape(h)


def test_state_not_started_early_when_incomplete_but_recent():
    """Not setup_done, has events, but <24h old / no parseable created_at →
    still early-setup (not_started), NOT blocked."""
    h = delivery_health(_client(setup_done=False), _summary(events_total=2), 0, _recent())
    assert h["state"] == "not_started"


def test_state_setup_ready_when_no_posts_yet():
    h = delivery_health(
        _client(setup_done=True), _summary(events_total=1, posts_created=0), 0, _recent()
    )
    assert h["state"] == "setup_ready"
    assert h["next_action"] == "generate_campaign"
    _assert_shape(h)


def test_state_pending_approval():
    h = delivery_health(
        _client(setup_done=True),
        _summary(events_total=5, posts_created=2, posts_approved=1, posts_published=1),
        1,
        _recent(value=True),  # value present → not at_risk
    )
    assert h["state"] == "pending_approval"
    assert h["next_action"] == "approve_content"
    _assert_shape(h)


def test_state_live_when_approved_not_yet_published():
    h = delivery_health(
        _client(setup_done=True),
        _summary(events_total=5, posts_created=3, posts_approved=2, posts_published=1),
        0,
        _recent(value=True),
    )
    assert h["state"] == "live"
    assert h["next_action"] == "none"
    assert h["tone"] == "ok"
    _assert_shape(h)


def test_state_delivered_when_value_in_7d_and_no_queue():
    h = delivery_health(
        _client(setup_done=True),
        _summary(events_total=5, posts_created=3, posts_approved=1, posts_published=1),
        0,
        _recent(value=True),
    )
    assert h["state"] == "delivered"
    assert h["tone"] == "ok"
    _assert_shape(h)


# --------------------------------------------------------------------------- #
# scoping + safety
# --------------------------------------------------------------------------- #
def test_trial_customer_never_at_risk():
    """at_risk is scoped to paid (plan != trial) so a free-trial account never
    trips the paid-delivery alarm."""
    h = delivery_health(
        _client(plan="trial", setup_done=True),
        _summary(events_total=5, posts_created=2, posts_approved=1, posts_published=1),
        0,
        _recent(value=False),
    )
    assert h["state"] != "at_risk"


def test_paused_customer_never_at_risk():
    h = delivery_health(
        _client(status="paused", setup_done=True),
        _summary(events_total=5, posts_created=2),
        0,
        _recent(value=False),
    )
    assert h["state"] != "at_risk"


def test_delivery_health_never_raises_on_garbage():
    h = delivery_health(None, None, None, None)  # type: ignore[arg-type]
    assert h["state"] == "unknown"
    assert h["next_action"] == "none"
    assert h["tone"] == "muted"


# --------------------------------------------------------------------------- #
# recent_counts() window boundaries (feeds delivery_health's `recent`)
# --------------------------------------------------------------------------- #
def _iso(dt):
    return dt.isoformat(timespec="seconds")


def _write_events(dir_path, cid, events):
    os.makedirs(str(dir_path), exist_ok=True)
    path = os.path.join(str(dir_path), f"{cid}.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for ev, at in events:
            f.write(json.dumps({"at": at, "client_id": cid, "event": ev}) + "\n")


def test_recent_counts_value_window_7d_boundary(monkeypatch, tmp_path):
    from app.marketing import delivery_ledger as dl

    monkeypatch.setattr(dl, "_LEDGER_DIR", lambda: str(tmp_path))
    now = datetime.now(timezone.utc)
    _write_events(tmp_path, "c_in", [("post_published", _iso(now - timedelta(days=6)))])
    _write_events(tmp_path, "c_out", [("post_published", _iso(now - timedelta(days=8)))])
    assert dl.recent_counts("c_in")["value_events_in_window"] is True
    assert dl.recent_counts("c_out")["value_events_in_window"] is False


def test_recent_counts_failures_24h_boundary(monkeypatch, tmp_path):
    from app.marketing import delivery_ledger as dl

    monkeypatch.setattr(dl, "_LEDGER_DIR", lambda: str(tmp_path))
    now = datetime.now(timezone.utc)
    _write_events(tmp_path, "f_in", [("post_failed", _iso(now - timedelta(hours=23)))])
    _write_events(tmp_path, "f_out", [("automation_failed", _iso(now - timedelta(hours=25)))])
    assert dl.recent_counts("f_in")["failures_24h"] == 1
    assert dl.recent_counts("f_out")["failures_24h"] == 0


def test_recent_counts_events_in_window_and_z_suffix(monkeypatch, tmp_path):
    from app.marketing import delivery_ledger as dl

    monkeypatch.setattr(dl, "_LEDGER_DIR", lambda: str(tmp_path))
    now = datetime.now(timezone.utc)
    # trailing-Z stamps must parse too (older backfill / external writers)
    z_stamp = (now - timedelta(days=1)).isoformat(timespec="seconds").replace("+00:00", "Z")
    _write_events(
        tmp_path,
        "c1",
        [
            ("post_published", z_stamp),
            ("lead_captured", _iso(now - timedelta(days=2))),
            ("post_published", _iso(now - timedelta(days=40))),  # out of window
        ],
    )
    r = dl.recent_counts("c1")
    assert r["events_in_window"] == 2
    assert r["value_events_in_window"] is True


def test_recent_counts_missing_file_is_all_zero(monkeypatch, tmp_path):
    from app.marketing import delivery_ledger as dl

    monkeypatch.setattr(dl, "_LEDGER_DIR", lambda: str(tmp_path))
    r = dl.recent_counts("does_not_exist")
    assert r["events_in_window"] == 0
    assert r["value_events_in_window"] is False
    assert r["failures_24h"] == 0


# --------------------------------------------------------------------------- #
# _build_command_center wiring — new scalars + per-customer health, existing
# fields byte-preserved.
# --------------------------------------------------------------------------- #
def _cc_client(cid, **kw):
    base = {
        "id": cid,
        "business_name": f"Biz {cid}",
        "plan": "starter",
        "product": "marketing",
        "status": "active",
        "setup_done": True,
    }
    base.update(kw)
    return base


def _patch_cc(monkeypatch, clients, summaries, recents, approvals):
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None, product=None: clients,
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.delivery_ledger.summary", lambda cid: summaries.get(cid, {}), raising=False
    )
    monkeypatch.setattr(
        "app.marketing.delivery_ledger.recent_counts",
        lambda cid, hours=168: recents.get(cid, {}),
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.delivery_ledger.ensure_backfilled", lambda cid: None, raising=False
    )
    monkeypatch.setattr(
        "app.marketing.content_approval.pending", lambda client_id="": approvals, raising=False
    )


def test_command_center_adds_at_risk_and_benefit_scalars(monkeypatch):
    from app.api.admin_dashboard_builders import _build_command_center

    clients = [_cc_client("risk1"), _cc_client("ok1")]
    summaries = {
        "risk1": {
            "events_total": 5,
            "posts_created": 3,
            "posts_approved": 1,
            "posts_published": 1,
            "value_delivered": True,
            "automation_failures": 0,
        },
        "ok1": {
            "events_total": 5,
            "posts_created": 3,
            "posts_approved": 1,
            "posts_published": 1,
            "value_delivered": True,
            "automation_failures": 0,
        },
    }
    recents = {
        "risk1": {"value_events_in_window": False, "failures_24h": 0},  # no value 7d → at_risk
        "ok1": {"value_events_in_window": True, "failures_24h": 0},  # value 7d → delivered
    }
    _patch_cc(monkeypatch, clients, summaries, recents, [])

    out = _build_command_center()
    s = out["summary"]
    assert s["at_risk_count"] == 1
    assert s["benefit_this_week"] == 1

    by_id = {c["id"]: c for c in out["per_customer"]}
    assert by_id["risk1"]["health"]["state"] == "at_risk"
    assert by_id["ok1"]["health"]["state"] == "delivered"
    # every per-customer row carries the full health dict
    assert by_id["risk1"]["health"]["next_action"] in _VALID_ACTIONS


def test_command_center_existing_fields_unchanged(monkeypatch):
    """Additive contract: all pre-existing summary + per_customer keys must still
    be present (the frontend + other tests depend on them)."""
    from app.api.admin_dashboard_builders import _build_command_center

    clients = [_cc_client("x")]
    summaries = {"x": {"value_delivered": True, "automation_failures": 0}}
    recents = {"x": {"value_events_in_window": True, "failures_24h": 0}}
    _patch_cc(monkeypatch, clients, summaries, recents, [])

    out = _build_command_center()

    # top-level shape unchanged
    for key in ("ok", "generated_at", "summary", "revenue", "by_product", "per_customer"):
        assert key in out, f"missing top-level {key}"

    # all original summary scalars still present
    for key in (
        "total_customers",
        "paying_customers",
        "stuck_in_setup",
        "receiving_value",
        "failed_automation_count",
        "pending_approvals_total",
    ):
        assert key in out["summary"], f"missing summary.{key}"
    # new scalars added
    assert "at_risk_count" in out["summary"]
    assert "benefit_this_week" in out["summary"]

    # all original per_customer keys still present
    row = out["per_customer"][0]
    for key in (
        "id",
        "business_name",
        "plan",
        "product",
        "mrr",
        "setup_done",
        "value_delivered",
        "automation_failures",
        "pending_approvals",
    ):
        assert key in row, f"missing per_customer.{key}"
    assert "health" in row  # new additive field
