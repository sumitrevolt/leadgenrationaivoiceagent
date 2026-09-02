"""L-track tests — pause-toggles, dead-letter alert, baseline reset.

The L-track is a set of small ops-capability additions on top of stable
modules; tests focus on the new contracts (toggle persists / dead-letter
counts / reset clears the right rows) rather than re-asserting prior shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents import eval_gate
from app.platform import customer_webhooks as cw
from app.platform import mcp_keys, ops_alerts


# --------------------------------------------------------------------------- #
# L.1 customer-webhook pause toggle
# --------------------------------------------------------------------------- #
@pytest.fixture
def _cw_iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cw, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(cw, "_REG_PATH", tmp_path / "regs.jsonl")
    monkeypatch.setattr(cw, "_DEL_PATH", tmp_path / "dels.jsonl")
    monkeypatch.setenv("CUSTOMER_WEBHOOKS", "1")
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")


def test_set_enabled_persists(_cw_iso) -> None:
    reg = cw.register("client_a", "https://example.com/h", ["lead.qualified"])
    assert cw.set_enabled(reg["id"], "client_a", False)["ok"] is True
    rows = cw._read_registrations()
    assert rows[0]["enabled"] is False
    assert "enabled_toggled_at" in rows[0]


def test_set_enabled_cross_tenant_rejected(_cw_iso) -> None:
    reg = cw.register("client_a", "https://example.com/h", ["lead.qualified"])
    out = cw.set_enabled(reg["id"], "client_b", False)
    assert out["ok"] is False
    assert out["error"] == "not_found"


async def test_disabled_webhook_skips_emit(_cw_iso, monkeypatch: pytest.MonkeyPatch) -> None:
    reg = cw.register("client_a", "https://example.com/h", ["lead.qualified"])
    cw.set_enabled(reg["id"], "client_a", False)

    fired: list = []

    async def _stub(row, event_type, payload, delivery_id=None, schedule=None):
        fired.append(row["id"])
        return {"delivered": True}

    monkeypatch.setattr(cw, "_deliver_one", _stub)
    out = await cw.emit("client_a", "lead.qualified", {})
    assert out["emitted"] == 0
    assert fired == []


# --------------------------------------------------------------------------- #
# L.2 MCP key pause toggle
# --------------------------------------------------------------------------- #
@pytest.fixture
def _mck_iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mcp_keys, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(mcp_keys, "_KEYS_PATH", tmp_path / "keys.jsonl")
    monkeypatch.setattr(mcp_keys, "_USAGE_PATH", tmp_path / "usage.jsonl")
    monkeypatch.setenv("MCP_PRODUCT", "1")


def test_set_enabled_pauses_authentication(_mck_iso) -> None:
    out = mcp_keys.issue("test")
    assert mcp_keys.set_enabled(out["id"], False) is True
    # Authenticate now rejects the (still-valid-secret) key
    assert mcp_keys.authenticate(out["key"]) is None


def test_set_enabled_resumes_authentication(_mck_iso) -> None:
    out = mcp_keys.issue("test")
    mcp_keys.set_enabled(out["id"], False)
    assert mcp_keys.authenticate(out["key"]) is None
    mcp_keys.set_enabled(out["id"], True)
    assert mcp_keys.authenticate(out["key"]) is not None


def test_set_enabled_unknown_key_returns_false(_mck_iso) -> None:
    assert mcp_keys.set_enabled("mck_nope", False) is False


# --------------------------------------------------------------------------- #
# L.3 dead-letter alert
# --------------------------------------------------------------------------- #
def test_consecutive_failure_count_resets_on_success(_cw_iso) -> None:
    reg = cw.register("client_a", "https://example.com/h", ["lead.qualified"])
    wh_id = reg["id"]
    # Seed: failed, failed, succeeded, failed, failed
    for delivered in (False, False, True, False, False):
        cw._append_delivery(
            {
                "id": f"del_{delivered}",
                "webhook_id": wh_id,
                "client_id": "client_a",
                "event_type": "lead.qualified",
                "url": reg["url"],
                "attempts": 3,
                "last_status": 200 if delivered else 500,
                "delivered": delivered,
                "at": 1700000000,
            }
        )
    # Only the trailing 2 failures count (the success in the middle resets)
    assert cw.consecutive_failure_count(wh_id) == 2


def test_dead_letter_alert_threshold(
    _cw_iso, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """3 consecutive failures should page; 2 should not."""
    monkeypatch.setenv("OPS_ALERTS", "1")
    monkeypatch.setattr(ops_alerts, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(ops_alerts, "_STATE_PATH", tmp_path / "alerts.jsonl")

    pushes: list = []
    monkeypatch.setattr(ops_alerts, "_ntfy", lambda *a, **kw: pushes.append(a))

    reg = cw.register("client_a", "https://example.com/h", ["lead.qualified"])
    for i in range(2):
        cw._append_delivery(
            {
                "id": f"d{i}",
                "webhook_id": reg["id"],
                "client_id": "client_a",
                "event_type": "lead.qualified",
                "url": reg["url"],
                "attempts": 3,
                "last_status": 500,
                "delivered": False,
                "at": 1700000000,
            }
        )
    out = ops_alerts.maybe_alert_webhook_dead_letter(reg["id"], "client_a", reg["url"])
    assert out["alerted"] is False
    assert out["consecutive_failures"] == 2

    # 3rd failure -> page
    cw._append_delivery(
        {
            "id": "d2",
            "webhook_id": reg["id"],
            "client_id": "client_a",
            "event_type": "lead.qualified",
            "url": reg["url"],
            "attempts": 3,
            "last_status": 500,
            "delivered": False,
            "at": 1700000000,
        }
    )
    out = ops_alerts.maybe_alert_webhook_dead_letter(reg["id"], "client_a", reg["url"])
    assert out["alerted"] is True
    assert out["consecutive_failures"] == 3
    assert len(pushes) == 1


# --------------------------------------------------------------------------- #
# L.4 eval_gate reset_baseline
# --------------------------------------------------------------------------- #
def test_reset_baseline_clears_only_targeted_combo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(eval_gate, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(eval_gate, "_HISTORY_PATH", tmp_path / "hist.jsonl")
    monkeypatch.setenv("EVAL_GATE", "1")

    for s in (0.5, 0.6, 0.7):
        eval_gate.record_score("rag", "faithfulness", s)
        eval_gate.record_score("rag", "answer_relevancy", s)
        eval_gate.record_score("self_improve", "harvest_leads", s)

    out = eval_gate.reset_baseline("rag", "faithfulness")
    assert out["ok"] is True
    assert out["removed"] == 3
    # Other combos preserved
    assert len(eval_gate.recent_scores("rag", "answer_relevancy", n=10)) == 3
    assert len(eval_gate.recent_scores("self_improve", "harvest_leads", n=10)) == 3
    assert len(eval_gate.recent_scores("rag", "faithfulness", n=10)) == 0


def test_reset_baseline_no_history_safe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(eval_gate, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(eval_gate, "_HISTORY_PATH", tmp_path / "hist.jsonl")
    out = eval_gate.reset_baseline("rag", "faithfulness")
    assert out["ok"] is True
    assert out["removed"] == 0
