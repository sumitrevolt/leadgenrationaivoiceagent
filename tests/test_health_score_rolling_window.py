"""Health-score rolling window + gate-vs-failure split (2026-07-12 fix).

Covers:
1. `_record_stuck` with gate reasons (auto_delivery_off, sweep_auto_off, no_phone)
   logs `delivery_gated` NOT `automation_failed`.
2. `_record_stuck` with real failures (send_failed, send_error:*) still logs
   `automation_failed`.
3. `_customer_health` uses 24h rolling `failures_24h` — old failures don't
   permanently tank the score.
4. With zero recent failures + gate-only events, health score has NO red
   `automation_failed` flag.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


# --------------------------------------------------------------------------- #
# 1. Gate reasons → delivery_gated, NOT automation_failed
# --------------------------------------------------------------------------- #
class TestRecordStuckEventType:
    """_record_stuck should log delivery_gated for gate reasons, automation_failed for real failures."""

    def _capture_event(self, reason, tmp_path):
        """Call _record_stuck and return the event type that was logged."""
        from app.marketing.customer_delivery import _GATE_REASONS, _record_stuck

        captured = {}

        def fake_log_event(cid, event, **kw):
            captured["event"] = event
            captured["detail"] = kw.get("detail", "")
            return True

        client = {"id": "test-c", "business_name": "TestBiz", "phone": "9999"}
        with patch("app.marketing.delivery_ledger.log_event", side_effect=fake_log_event):
            with patch("app.marketing.customer_delivery._STUCK_LOG", str(tmp_path / "stuck.jsonl")):
                with patch("app.platform.ops_alerts.alert_paid_customer_stuck"):
                    _record_stuck(client, reason)
        return captured

    def test_auto_delivery_off_is_gated(self, tmp_path):
        r = self._capture_event("auto_delivery_off", tmp_path)
        assert r["event"] == "delivery_gated"

    def test_sweep_auto_off_is_gated(self, tmp_path):
        r = self._capture_event("sweep_auto_off", tmp_path)
        assert r["event"] == "delivery_gated"

    def test_no_phone_is_gated(self, tmp_path):
        r = self._capture_event("no_phone", tmp_path)
        assert r["event"] == "delivery_gated"

    def test_send_failed_is_automation_failed(self, tmp_path):
        r = self._capture_event("send_failed", tmp_path)
        assert r["event"] == "automation_failed"

    def test_send_error_is_automation_failed(self, tmp_path):
        r = self._capture_event("send_error:ConnectionError", tmp_path)
        assert r["event"] == "automation_failed"


# --------------------------------------------------------------------------- #
# 2. delivery_gated is a valid ledger event type
# --------------------------------------------------------------------------- #
def test_delivery_gated_in_event_types():
    from app.marketing.delivery_ledger import EVENT_TYPES

    assert "delivery_gated" in EVENT_TYPES


# --------------------------------------------------------------------------- #
# 3. _customer_health: zero recent failures → no automation_failed RED flag
# --------------------------------------------------------------------------- #
def test_health_no_red_with_zero_recent_failures():
    """Even if all-time summary has automation_failures, health uses 24h
    rolling window. With 0 recent failures → no RED automation_failed."""
    from app.marketing.product_one_delivery import _customer_health

    client = {
        "id": "c1",
        "business_name": "Test",
        "plan": "starter",
        "socials": {"instagram": "ig"},
        "whatsapp_phone": "999",
    }
    setup = {"business": True, "offer": True, "brand": True, "social": True, "approval": True}

    # No failures at all → should be green (no red, no yellow from these paths)
    h = _customer_health(
        client=client,
        stage="content_ready",
        risk_flag="ok",
        setup_pct=100,
        setup=setup,
        failed_count=0,
        led_events=[
            {
                "event": "post_published",
                "at": datetime.now(timezone.utc).isoformat(),
                "customer_visible": True,
            }
        ],
        approvals_escalated=[],
        actions=[],
    )
    assert "automation_failed" not in h["reasons"]
    assert h["score"] >= 88  # No red, no yellow


def test_health_red_with_recent_failures():
    """If failed_count > 0, RED automation_failed flag must appear."""
    from app.marketing.product_one_delivery import _customer_health

    client = {
        "id": "c1",
        "business_name": "Test",
        "plan": "starter",
        "socials": {"instagram": "ig"},
        "whatsapp_phone": "999",
    }
    setup = {"business": True, "offer": True, "brand": True, "social": True, "approval": True}

    h = _customer_health(
        client=client,
        stage="content_ready",
        risk_flag="automation_failed",
        setup_pct=100,
        setup=setup,
        failed_count=3,
        led_events=[
            {
                "event": "post_published",
                "at": datetime.now(timezone.utc).isoformat(),
                "customer_visible": True,
            }
        ],
        approvals_escalated=[],
        actions=[],
    )
    assert "automation_failed" in h["reasons"]
    assert h["score"] <= 65  # At least -35


# --------------------------------------------------------------------------- #
# 4. _ledger_recent_failures reads failures_24h
# --------------------------------------------------------------------------- #
def test_ledger_recent_failures_reads_24h(tmp_path, monkeypatch):
    """_ledger_recent_failures should return failures_24h from recent_counts."""
    from app.marketing import delivery_ledger
    from app.marketing.product_one_delivery import _ledger_recent_failures

    ledger_dir = str(tmp_path / "ledger")
    os.makedirs(ledger_dir, exist_ok=True)
    monkeypatch.setattr(delivery_ledger, "_LEDGER_DIR", lambda: ledger_dir)

    cid = "test-client"
    now = datetime.now(timezone.utc)

    # Write 2 automation_failed events in the last hour (within 24h window)
    path = os.path.join(ledger_dir, f"{cid}.jsonl")
    for i in range(2):
        ev = {
            "event": "automation_failed",
            "at": (now - timedelta(minutes=30 + i)).isoformat(),
            "detail": "send_failed",
            "actor": "system",
        }
        with open(path, "a") as f:
            f.write(json.dumps(ev) + "\n")

    # Write 5 old automation_failed events (outside 24h window — should NOT count)
    for i in range(5):
        ev = {
            "event": "automation_failed",
            "at": (now - timedelta(hours=48 + i)).isoformat(),
            "detail": "send_failed",
            "actor": "system",
        }
        with open(path, "a") as f:
            f.write(json.dumps(ev) + "\n")

    result = _ledger_recent_failures(cid)
    assert result == 2, f"Expected 2 recent failures, got {result}"


def test_ledger_recent_failures_ignores_gated(tmp_path, monkeypatch):
    """delivery_gated events should NOT count as failures_24h."""
    from app.marketing import delivery_ledger
    from app.marketing.product_one_delivery import _ledger_recent_failures

    ledger_dir = str(tmp_path / "ledger")
    os.makedirs(ledger_dir, exist_ok=True)
    monkeypatch.setattr(delivery_ledger, "_LEDGER_DIR", lambda: ledger_dir)

    cid = "gated-client"
    now = datetime.now(timezone.utc)
    path = os.path.join(ledger_dir, f"{cid}.jsonl")

    # Write delivery_gated events (recent but should NOT count as failures)
    for i in range(10):
        ev = {
            "event": "delivery_gated",
            "at": (now - timedelta(minutes=10 + i)).isoformat(),
            "detail": "auto_delivery_off",
            "actor": "system",
        }
        with open(path, "a") as f:
            f.write(json.dumps(ev) + "\n")

    result = _ledger_recent_failures(cid)
    assert result == 0, f"delivery_gated events should not count as failures, got {result}"
