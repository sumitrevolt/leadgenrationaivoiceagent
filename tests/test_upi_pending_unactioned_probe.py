"""Revenue guard: a paid customer stuck in `pending` must reach the operator.

Manual UPI is the ONLY payment rail. Discovery of a new submission rides on a
single best-effort ntfy push that swallows failures at three nested levels and
has no email fallback. This probe is the durable backstop: it feeds the already
scheduled 08:30 IST `ops_alerts.daily_readiness_digest()`, which pushes only on
`status == "BLOCKER"`.

Each test sets up its own condition (R4) — nothing here asserts an absence that
it did not itself create.

Locked to the current probe contract on `app.api.activation` (store_ok /
stale_pending / alert_hours / UPI_PENDING_ALERT_HOURS override).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.api import activation


def _iso(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


@pytest.fixture
def fake_payments(monkeypatch):
    """Swap the payment store for an in-memory list the test controls.

    Patch the *attribute on the real module*, not `sys.modules` — the probe does
    `from app.platform import upi_payments`, which binds the package attribute
    and ignores a `sys.modules` substitution.
    """

    rows: list[dict] = []

    def _fake_list(status: str | None = None):
        if status:
            return [r for r in rows if r.get("status") == status]
        return list(rows)

    def _fake_actionable():
        return [
            row
            for row in rows
            if row.get("status") == "pending"
            or (
                row.get("status") == "approved"
                and not row.get("activated")
                and not row.get("auto_activated")
            )
        ]

    monkeypatch.setattr("app.platform.upi_payments.list_payments", _fake_list)
    monkeypatch.setattr("app.platform.upi_payments.list_actionable", _fake_actionable)
    return rows


def test_probe_is_registered_in_probes():
    """A probe not in _PROBES never reaches the digest — registration is the gate."""
    assert activation._upi_pending_unactioned in activation._PROBES
    assert (
        activation._PROBE_BY_KEY.get("upi_pending_unactioned") is activation._upi_pending_unactioned
    )


def test_no_pending_is_ok(fake_payments):
    out = activation._upi_pending_unactioned()
    assert out["status"] == activation._OK
    assert out["checks"]["stale_pending"] == 0
    assert out["checks"]["store_ok"] is True
    assert out["action"] == ""


def test_fresh_pending_does_not_page(fake_payments):
    """A submission from 10 minutes ago is normal — paging on it would train the
    operator to ignore the digest."""
    fake_payments.append({"id": "p-fresh", "status": "pending", "created_at": _iso(0.17)})
    out = activation._upi_pending_unactioned()
    assert out["status"] == activation._OK
    assert out["checks"]["pending_total"] == 1
    assert out["checks"]["stale_pending"] == 0


def test_stale_pending_is_a_blocker(fake_payments):
    """The money case: customer paid, nobody acted, ntfy push may have been lost."""
    threshold = activation._upi_pending_alert_hours()
    fake_payments.append(
        {
            "id": "p-stale",
            "status": "pending",
            "created_at": _iso(threshold + 2),
        }
    )
    out = activation._upi_pending_unactioned()
    assert out["status"] == activation._BLOCKER
    assert out["checks"]["stale_pending"] == 1
    assert out["checks"]["alert_hours"] == threshold
    assert "approve" in out["action"].lower() or "upi" in out["action"].lower()


def test_blocker_status_is_what_the_digest_filters_on():
    """Couples this probe to `daily_readiness_digest`, which selects on the exact
    string "BLOCKER". If that contract drifts, the alert silently stops firing."""
    assert activation._BLOCKER == "BLOCKER"


def test_unparseable_timestamp_counts_as_stale(fake_payments):
    """Prefer a false page over a silently swallowed payment."""
    fake_payments.append({"id": "p-bad", "status": "pending", "created_at": "not-a-date"})
    out = activation._upi_pending_unactioned()
    assert out["status"] == activation._BLOCKER
    assert out["checks"]["stale_pending"] == 1


def test_store_failure_is_neutral_not_a_blocker(monkeypatch):
    """An infra hiccup must not manufacture a revenue blocker — that would make
    the digest cry wolf and get muted."""

    def _boom(status=None):
        raise RuntimeError("store unreadable")

    monkeypatch.setattr("app.platform.upi_payments.list_actionable", _boom)
    out = activation._upi_pending_unactioned()
    assert out["status"] == activation._NEUTRAL
    assert out["checks"]["store_ok"] is False


def test_approved_unbound_row_is_still_a_blocker(fake_payments):
    """Bank credit confirmed but identity missing is not done until activation."""
    fake_payments.append(
        {
            "id": "p-unbound",
            "status": "approved",
            "needs_client_bind": True,
            "activation_blocked": "empty_client_id",
            "created_at": _iso(72),
        }
    )
    out = activation._upi_pending_unactioned()
    assert out["status"] == activation._BLOCKER
    assert out["checks"]["pending_total"] == 1
    assert out["checks"]["approved_unbound"] == 1
    assert "bind" in out["action"].lower()


def test_approved_bound_unactivated_row_is_still_a_blocker(fake_payments):
    fake_payments.append(
        {
            "id": "p-bound-unactivated",
            "status": "approved",
            "client_id": "client-1",
            "created_at": _iso(72),
        }
    )
    out = activation._upi_pending_unactioned()
    assert out["status"] == activation._BLOCKER
    assert out["checks"]["approved_unbound"] == 0
    assert out["checks"]["approved_unactivated"] == 1
    assert "re-approve" in out["action"].lower()


def test_approved_activated_row_is_ignored(fake_payments):
    fake_payments.append(
        {
            "id": "p-ok",
            "status": "approved",
            "client_id": "client-1",
            "activated": True,
            "created_at": _iso(72),
        }
    )
    out = activation._upi_pending_unactioned()
    assert out["status"] == activation._OK
    assert out["checks"]["pending_total"] == 0


def test_env_threshold_override(fake_payments, monkeypatch):
    """Operators can tighten/loosen the page window without a code change."""
    monkeypatch.setenv("UPI_PENDING_ALERT_HOURS", "1")
    fake_payments.append({"id": "p-1h", "status": "pending", "created_at": _iso(2)})
    out = activation._upi_pending_unactioned()
    assert out["status"] == activation._BLOCKER
    assert out["checks"]["alert_hours"] == 1.0
