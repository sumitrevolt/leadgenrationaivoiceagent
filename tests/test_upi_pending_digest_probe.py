"""UPI pending unactioned probe — backup page when submit-time ntfy misses.

Uses setattr on ``upi_payments.list_actionable`` (not ``sys.modules`` stub): a
``from app.platform import upi_payments`` inside the probe binds the real
module, so ``monkeypatch.setitem(sys.modules, ...)`` never intercepts it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.api import activation as ax


def _iso_hours_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def test_probe_registered_in_digest_path() -> None:
    assert ax._upi_pending_unactioned in ax._PROBES
    assert "upi_pending_unactioned" in ax._PROBE_BY_KEY
    phase1_keys = ax._PHASES[0][2]
    assert "upi_pending_unactioned" in phase1_keys


def test_no_pending_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.platform import upi_payments

    monkeypatch.setattr(upi_payments, "list_actionable", lambda: [])
    r = ax._upi_pending_unactioned()
    assert r["status"] == "OK"
    assert r["checks"]["pending_total"] == 0
    assert r["checks"]["stale_pending"] == 0


def test_fresh_pending_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.platform import upi_payments

    monkeypatch.setattr(
        upi_payments,
        "list_actionable",
        lambda: [
            {
                "id": "upi_fresh",
                "status": "pending",
                "created_at": _iso_hours_ago(1),
            }
        ],
    )
    r = ax._upi_pending_unactioned()
    assert r["status"] == "OK"
    assert r["checks"]["pending_total"] == 1
    assert r["checks"]["stale_pending"] == 0


def test_stale_pending_is_blocker(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.platform import upi_payments

    monkeypatch.delenv("UPI_PENDING_ALERT_HOURS", raising=False)
    monkeypatch.setattr(
        upi_payments,
        "list_actionable",
        lambda: [
            {
                "id": "upi_stale",
                "status": "pending",
                "created_at": _iso_hours_ago(ax._UPI_PENDING_ALERT_HOURS_DEFAULT + 1),
            }
        ],
    )
    r = ax._upi_pending_unactioned()
    assert r["status"] == "BLOCKER"
    assert r["checks"]["stale_pending"] == 1
    assert "UPI pending" in r["action"] or "approve" in r["action"].lower()


def test_env_threshold_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """2h-old pending is OK at default 6h, BLOCKER when threshold=1."""
    from app.platform import upi_payments

    monkeypatch.setattr(
        upi_payments,
        "list_actionable",
        lambda: [
            {
                "id": "upi_mid",
                "status": "pending",
                "created_at": _iso_hours_ago(2),
            }
        ],
    )
    monkeypatch.delenv("UPI_PENDING_ALERT_HOURS", raising=False)
    assert ax._upi_pending_unactioned()["status"] == "OK"
    monkeypatch.setenv("UPI_PENDING_ALERT_HOURS", "1")
    assert ax._upi_pending_unactioned()["status"] == "BLOCKER"
    assert ax._upi_pending_unactioned()["checks"]["alert_hours"] == 1.0


def test_bad_env_threshold_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPI_PENDING_ALERT_HOURS", "nope")
    assert ax._upi_pending_alert_hours() == float(ax._UPI_PENDING_ALERT_HOURS_DEFAULT)
    monkeypatch.setenv("UPI_PENDING_ALERT_HOURS", "0")
    assert ax._upi_pending_alert_hours() == float(ax._UPI_PENDING_ALERT_HOURS_DEFAULT)


def test_corrupt_timestamp_counts_as_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.platform import upi_payments

    monkeypatch.setattr(
        upi_payments,
        "list_actionable",
        lambda: [
            {"id": "upi_bad_ts", "status": "pending", "created_at": "not-a-date"},
            {"id": "upi_empty_ts", "status": "pending", "created_at": ""},
        ],
    )
    r = ax._upi_pending_unactioned()
    assert r["status"] == "BLOCKER"
    assert r["checks"]["stale_pending"] == 2


def test_store_failure_is_neutral_not_blocker(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.platform import upi_payments

    def _boom():
        raise RuntimeError("store down")

    monkeypatch.setattr(upi_payments, "list_actionable", _boom)
    r = ax._upi_pending_unactioned()
    assert r["status"] == "NEUTRAL"
    assert r["checks"].get("store_ok") is False
