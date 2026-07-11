"""Test the delivery-outcome probe `_first_paid_delivery`.

Closes the '`production_ready:true` = tautology' gap (2026-07-11 audit): before
this probe, no probe in `activation._PROBES` ever returned `_BLOCKER` — every
one returned `_OK`/`_WARN`/`_NEUTRAL` — so `blocker_count` in
`/api/activation/summary` was structurally guaranteed to be 0 regardless of
whether any real paid customer had actually received a single deliverable.

This test suite proves the probe answers three cases correctly:
  1. No paid customers → _NEUTRAL (not-yet-selling, not a bug).
  2. Paid customer with progress → _OK.
  3. Paid customer, 0% delivery, 24h+ post-activation → _WARN with actionable
     admin next step (Delivery Cockpit → Generate Content).

Plus wiring guardrails:
  - The probe must be in `_PROBES` (flows into `/summary` + `/readiness`).
  - The probe must never raise (fail-open → _NEUTRAL) if the store is offline.
  - The probe result must be cached across calls within `_FIRST_PAID_TTL_S`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.api import activation


def _dt_iso(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _install_stubs(monkeypatch, clients, pcts_by_id):
    """Patch `clients_store.list_clients` + `product_one_delivery` calls the
    probe makes. Also bust the module-level cache so each test is fresh."""
    import app.marketing.clients_store as real_store
    import app.marketing.product_one_delivery as real_p1

    def _list_clients(status=None, product=None):
        rows = list(clients)
        if status:
            rows = [r for r in rows if str(r.get("status") or "").lower() == status.lower()]
        return rows

    def _plan_paid(client):
        plan = str(client.get("plan") or "").strip().lower()
        return plan not in ("", "trial", "free", "none", "pending")

    def _status(cid, client=None):
        return {"deliverable_completion_pct": pcts_by_id.get(str(cid), 0)}

    monkeypatch.setattr(real_store, "list_clients", _list_clients)
    monkeypatch.setattr(real_p1, "_client_plan_paid", _plan_paid)
    monkeypatch.setattr(real_p1, "customer_delivery_status", _status)

    activation._FIRST_PAID_CACHE.clear()
    activation._FIRST_PAID_CACHE.update({"at": 0.0, "result": None})


def test_no_paid_customers_returns_neutral(monkeypatch):
    _install_stubs(monkeypatch, clients=[], pcts_by_id={})
    r = activation._first_paid_delivery()
    assert r["status"] == activation._NEUTRAL
    assert r["checks"]["paid_customers"] == 0
    assert r["checks"]["with_zero_deliverables_24h_plus"] == 0


def test_paid_customer_with_progress_returns_ok(monkeypatch):
    _install_stubs(
        monkeypatch,
        clients=[{"id": "c1", "status": "active", "plan": "starter", "created_at": _dt_iso(48)}],
        pcts_by_id={"c1": 30},
    )
    r = activation._first_paid_delivery()
    assert r["status"] == activation._OK
    assert r["checks"]["paid_customers"] == 1
    assert r["checks"]["with_progress"] == 1
    assert r["checks"]["with_zero_deliverables_24h_plus"] == 0


def test_stale_paid_customer_returns_warn(monkeypatch):
    """The core outcome: a paid customer 48h post-activation with 0/10
    deliverables flips the readiness gate to WARN with actionable copy —
    but WITHOUT exposing the customer's client_id (PII discipline)."""
    _install_stubs(
        monkeypatch,
        clients=[{"id": "jiya-test", "status": "active", "plan": "starter", "created_at": _dt_iso(48)}],
        pcts_by_id={"jiya-test": 0},
    )
    r = activation._first_paid_delivery()
    assert r["status"] == activation._WARN
    assert r["checks"]["with_zero_deliverables_24h_plus"] == 1
    # PII discipline: client_id must NEVER appear in the probe result (public
    # /summary + admin /readiness both surface this verbatim).
    assert "jiya-test" not in r["action"]
    assert "jiya-test" not in str(r["checks"])
    # Aggregate + bucketed severity instead of per-customer identifiers.
    assert r["checks"]["oldest_pending_hours"] in ("24-48h", "48-72h", "72h+")
    assert "Delivery Cockpit" in r["action"]


def test_probe_result_never_contains_pii(monkeypatch):
    """Guardrail — even with multiple stale customers with distinctive-looking
    identifiers, the probe result must remain PII-free."""
    _install_stubs(
        monkeypatch,
        clients=[
            {"id": "cust-alpha-9876543210", "status": "active", "plan": "starter", "created_at": _dt_iso(48)},
            {"id": "user_bravo@example.com", "status": "active", "plan": "starter", "created_at": _dt_iso(72)},
            {"id": "9999888877776666", "status": "active", "plan": "starter", "created_at": _dt_iso(96)},
        ],
        pcts_by_id={"cust-alpha-9876543210": 0, "user_bravo@example.com": 0, "9999888877776666": 0},
    )
    r = activation._first_paid_delivery()
    blob = str(r)  # concat everything the probe surfaces
    for identifier in ("cust-alpha-9876543210", "user_bravo@example.com", "9999888877776666", "@example.com"):
        assert identifier not in blob, f"PII leak: {identifier!r} found in probe result"
    assert r["checks"]["with_zero_deliverables_24h_plus"] == 3
    assert r["checks"]["oldest_pending_hours"] == "72h+"


def test_fresh_paid_customer_within_24h_is_ok(monkeypatch):
    """5h post-activation with 0% is inside the grace window — do NOT warn."""
    _install_stubs(
        monkeypatch,
        clients=[{"id": "c1", "status": "active", "plan": "starter", "created_at": _dt_iso(5)}],
        pcts_by_id={"c1": 0},
    )
    r = activation._first_paid_delivery()
    assert r["status"] == activation._OK
    assert r["checks"]["with_zero_deliverables_24h_plus"] == 0


def test_trial_customer_never_counts(monkeypatch):
    """`_client_plan_paid` excludes trial/free/pending — the probe must too."""
    _install_stubs(
        monkeypatch,
        clients=[{"id": "trial1", "status": "active", "plan": "trial", "created_at": _dt_iso(48)}],
        pcts_by_id={"trial1": 0},
    )
    r = activation._first_paid_delivery()
    assert r["status"] == activation._NEUTRAL
    assert r["checks"]["paid_customers"] == 0


def test_probe_wired_into_probes_tuple():
    """Guardrail: without this wiring the probe would exist but never affect
    `/api/activation/summary` / `/readiness` output."""
    assert activation._first_paid_delivery in activation._PROBES
    assert "first_paid_delivery" in activation._PROBE_BY_KEY
    survival_keys = activation._PHASES[0][2]
    assert "first_paid_delivery" in survival_keys


def test_probe_fails_closed_to_warn_on_store_error(monkeypatch):
    """Wholesale store failure must return WARN — NOT a silent NEUTRAL.

    Rationale (2026-07-11 hardening): a silent NEUTRAL would let a broken
    clients_store hide the exact 'audit passed but not delivering' signal this
    probe exists to surface. WARN with a sanitized reason is the honest state.

    Also verify the raw exception message NEVER leaks (would expose DB connect
    strings, host IPs, or SQL fragments) — only the exception type name is
    surfaced in a bounded `eval_error_type` field.
    """
    import app.marketing.clients_store as real_store

    class _CustomStoreError(RuntimeError):
        pass

    def _boom(*a, **kw):
        # sensitive-looking message we must confirm never leaves the process
        raise _CustomStoreError("postgres://leadgen:s3cret@172.17.0.2:5432/leadgen_db offline")

    monkeypatch.setattr(real_store, "list_clients", _boom)
    activation._FIRST_PAID_CACHE.clear()
    activation._FIRST_PAID_CACHE.update({"at": 0.0, "result": None})

    r = activation._first_paid_delivery()
    assert r["status"] == activation._WARN, "must fail-closed to WARN, not silent NEUTRAL"
    assert r["checks"]["eval_error"] is True
    assert r["checks"]["eval_error_type"] == "_CustomStoreError"
    # Exception MESSAGE must never leak — check for the sensitive fragments.
    blob = str(r)
    for leak in ("postgres://", "s3cret", "172.17.0.2", "5432", "leadgen_db"):
        assert leak not in blob, f"raw exception message leaked: {leak!r}"
    # Action must direct admin to Delivery Cockpit (not a stack trace).
    assert "Delivery Cockpit" in r["action"]


def test_probe_result_is_cached_within_ttl(monkeypatch):
    """Within `_FIRST_PAID_TTL_S`, subsequent calls MUST return the cached
    result without hitting the store again — keeps public /summary cheap."""
    call_count = {"n": 0}

    import app.marketing.clients_store as real_store
    import app.marketing.product_one_delivery as real_p1

    def _list_clients(status=None, product=None):
        call_count["n"] += 1
        return []

    monkeypatch.setattr(real_store, "list_clients", _list_clients)
    monkeypatch.setattr(real_p1, "_client_plan_paid", lambda c: False)
    monkeypatch.setattr(real_p1, "customer_delivery_status", lambda cid, c=None: {})

    activation._FIRST_PAID_CACHE.clear()
    activation._FIRST_PAID_CACHE.update({"at": 0.0, "result": None})

    activation._first_paid_delivery()
    activation._first_paid_delivery()
    activation._first_paid_delivery()

    assert call_count["n"] == 1


def test_readiness_shape_still_valid_with_new_probe(monkeypatch):
    """Sanity: `_PROBES` still yields dicts with the expected shape when the
    new probe runs alongside the existing ones. (Read-only shape check.)"""
    activation._FIRST_PAID_CACHE.clear()
    activation._FIRST_PAID_CACHE.update({"at": 0.0, "result": None})

    import app.marketing.clients_store as real_store
    monkeypatch.setattr(real_store, "list_clients", lambda *a, **kw: [])

    items = [p() for p in activation._PROBES]
    for it in items:
        assert set(it.keys()) >= {"key", "label", "status", "env_vars", "checks", "action"}
        assert it["status"] in (activation._OK, activation._WARN, activation._NEUTRAL, activation._BLOCKER)
