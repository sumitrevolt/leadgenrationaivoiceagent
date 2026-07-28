"""Regression tests for the age-gated 4-tier delivery-outcome probe.

Refined semantics (2026-07-11 P0 loop): the probe distinguishes SETUP progress
(business_profile / brand_kit) from GENERATED artifacts (content_queue drafts)
from CUSTOMER-VISIBLE artifacts (approved / scheduled in customer dashboard)
from EVIDENCE-BACKED completed delivery (posts_published or evidence_url).

Age-based SLA:
  <24h    : any state OK (grace)
  ≥24h    : require ≥1 generated
  ≥72h    : require ≥1 customer-visible
  ≥7d     : require ≥1 evidence-backed completed

Test cases lock:
  1. No paid customers → _NEUTRAL
  2. <24h grace with setup only → _OK
  3. ≥24h with setup only (jiya-shape before draft) → _WARN
  4. ≥24h with generated draft (jiya-shape after draft) → still WARN on visible/completed
     (because customer_visible remains false — draft only in admin queue)
  5. ≥72h with admin-only draft → _WARN on visible SLA
  6. ≥72h with customer-visible artifact → _OK for visible tier
  7. ≥7d without evidence-backed → _WARN on completed SLA
  8. ≥7d with evidence_url populated → _OK
  9. business_profile + brand_kit alone NEVER count as customer-value
 10. Stage change alone NEVER counts as delivery
 11. Percentage change alone NEVER counts as delivery
 12. Trial customer never counts (not paid)
 13. Wholesale eval failure → sanitized _WARN (never _NEUTRAL)
 14. Exception with credentials/SQL/IP/customer_id/email leaks NONE of them
 15. Result exposes only aggregate counts + bucket strings
 16. Exact timestamps NEVER appear in the result
 17. Cache TTL doesn't preserve stale probe results beyond documented window
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.api import activation


def _dt_iso(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _install_stubs(monkeypatch, clients, state_by_id, ledger_summary_by_id=None):
    """Patch clients_store + product_one_delivery + delivery_ledger to
    hermetic fixtures. Also bust the probe cache so each test starts fresh."""
    ledger_summary_by_id = ledger_summary_by_id or {}
    import app.marketing.clients_store as real_store
    import app.marketing.product_one_delivery as real_p1

    def _list(status=None, product=None):
        rows = list(clients)
        if status:
            rows = [r for r in rows if str(r.get("status") or "").lower() == status.lower()]
        return rows

    def _plan_paid(c):
        return str(c.get("plan") or "").strip().lower() not in (
            "",
            "trial",
            "free",
            "none",
            "pending",
        )

    def _status(cid, client=None):
        return state_by_id.get(str(cid), {}) or {}

    monkeypatch.setattr(real_store, "list_clients", _list)
    monkeypatch.setattr(real_p1, "_client_plan_paid", _plan_paid)
    monkeypatch.setattr(real_p1, "customer_delivery_status", _status)
    monkeypatch.setattr(activation, "_client_has_payment_evidence", _plan_paid, raising=False)

    # delivery_ledger is imported lazily inside _customer_outcome_class; stub it.
    try:
        import app.marketing.delivery_ledger as real_ledger

        monkeypatch.setattr(
            real_ledger, "summary", lambda cid: ledger_summary_by_id.get(str(cid), {}) or {}
        )
    except ImportError:
        pass

    activation._FIRST_PAID_CACHE.clear()
    activation._FIRST_PAID_CACHE.update({"at": 0.0, "result": None})


def _customer(cid, hours_ago, plan="starter"):
    return {"id": cid, "status": "active", "plan": plan, "created_at": _dt_iso(hours_ago)}


def _state(
    *,
    setup=False,
    generated=0,
    waiting=0,
    scheduled=0,
    published=0,
    deliverables=None,
    deliverable_pct=0,
):
    """Compose a customer_delivery_status shape."""
    return {
        "setup_checks": {"business": setup, "brand": setup},
        "content_generated": generated,
        "posts_waiting_for_approval": waiting,
        "posts_scheduled": scheduled,
        "posts_published": published,
        "deliverables": deliverables or [],
        "deliverable_completion_pct": deliverable_pct,
    }


# --------------------------------------------------------------------------- #
# 1. NEUTRAL when no paid customers exist
# --------------------------------------------------------------------------- #


def test_1_no_paid_customers_returns_neutral(monkeypatch):
    _install_stubs(monkeypatch, clients=[], state_by_id={})
    r = activation._first_paid_delivery()
    assert r["status"] == activation._NEUTRAL
    assert r["checks"]["paid_customers"] == 0


# --------------------------------------------------------------------------- #
# 2. <24h grace: setup only → OK
# --------------------------------------------------------------------------- #


def test_2_fresh_customer_with_setup_only_is_ok_within_grace(monkeypatch):
    _install_stubs(
        monkeypatch,
        clients=[_customer("c1", hours_ago=5)],
        state_by_id={"c1": _state(setup=True)},
    )
    r = activation._first_paid_delivery()
    assert r["status"] == activation._OK
    assert r["checks"]["with_setup_progress"] == 1
    assert r["checks"]["with_generated_artifacts"] == 0
    assert r["checks"]["zero_generated_after_grace"] == 0


# --------------------------------------------------------------------------- #
# 3. ≥24h with setup only → WARN on generated SLA
# --------------------------------------------------------------------------- #


def test_3_stale_customer_with_setup_only_warns_on_generated_sla(monkeypatch):
    """Jiya-shape BEFORE the live draft was generated: 4 days old, setup done,
    zero generated. Previous probe reported _OK — false positive. New probe
    must return _WARN."""
    _install_stubs(
        monkeypatch,
        clients=[_customer("c1", hours_ago=96)],  # 4 days
        state_by_id={"c1": _state(setup=True)},
    )
    r = activation._first_paid_delivery()
    assert r["status"] == activation._WARN
    assert r["checks"]["zero_generated_after_grace"] == 1
    assert r["checks"]["zero_visible_after_sla"] == 1
    assert r["checks"]["oldest_zero_generated_bucket"] == "3-7d"
    assert "0 generated artifacts" in r["action"]


# --------------------------------------------------------------------------- #
# 4. ≥24h with generated draft but admin-only → WARN on visible SLA
# --------------------------------------------------------------------------- #


def test_4_generated_draft_admin_only_still_warns_on_visible_sla(monkeypatch):
    """Jiya-shape AFTER draft was generated: draft exists in content_queue
    but customer visibility not verified. Probe must still WARN on visible SLA
    because customer >72h old and no approved/scheduled items."""
    _install_stubs(
        monkeypatch,
        clients=[_customer("c1", hours_ago=96)],
        state_by_id={"c1": _state(setup=True, generated=1)},  # draft but no approvals
    )
    r = activation._first_paid_delivery()
    assert r["status"] == activation._WARN
    assert r["checks"]["with_generated_artifacts"] == 1
    assert r["checks"]["zero_generated_after_grace"] == 0
    assert r["checks"]["zero_visible_after_sla"] == 1  # still stale on visibility
    assert "customer-visible" in r["action"]


# --------------------------------------------------------------------------- #
# 5. ≥72h with customer-visible artifact → OK on visible tier
# --------------------------------------------------------------------------- #


def test_5_visible_artifact_satisfies_visible_sla(monkeypatch):
    _install_stubs(
        monkeypatch,
        clients=[_customer("c1", hours_ago=96)],
        state_by_id={"c1": _state(setup=True, generated=1, waiting=1)},
    )
    r = activation._first_paid_delivery()
    assert r["status"] == activation._OK
    assert r["checks"]["with_customer_visible_artifacts"] == 1
    assert r["checks"]["zero_visible_after_sla"] == 0


# --------------------------------------------------------------------------- #
# 6. ≥7d without evidence-backed completed → WARN
# --------------------------------------------------------------------------- #


def test_6_stale_7d_without_evidence_warns(monkeypatch):
    _install_stubs(
        monkeypatch,
        clients=[_customer("c1", hours_ago=24 * 8)],  # 8 days
        state_by_id={"c1": _state(setup=True, generated=1, waiting=1)},
    )
    r = activation._first_paid_delivery()
    assert r["status"] == activation._WARN
    assert r["checks"]["zero_completed_after_sla"] == 1
    assert r["checks"]["oldest_zero_completed_bucket"] == "7d+"
    assert "evidence-backed" in r["action"]


# --------------------------------------------------------------------------- #
# 7. ≥7d with posts_published > 0 → OK
# --------------------------------------------------------------------------- #


def test_7_evidence_backed_satisfies_all_slas(monkeypatch):
    _install_stubs(
        monkeypatch,
        clients=[_customer("c1", hours_ago=24 * 8)],
        state_by_id={"c1": _state(setup=True, generated=5, waiting=1, published=1)},
    )
    r = activation._first_paid_delivery()
    assert r["status"] == activation._OK
    assert r["checks"]["with_evidence_backed_delivery"] == 1


# --------------------------------------------------------------------------- #
# 8. Evidence-backed via evidence_url on a deliverable → OK
# --------------------------------------------------------------------------- #


def test_8_evidence_url_on_non_setup_deliverable_counts_as_completed(monkeypatch):
    """Manual-publish fallback: admin uploads screenshot URL on `proof` or
    `social_posts` deliverable. Must count as evidence-backed completion."""
    _install_stubs(
        monkeypatch,
        clients=[_customer("c1", hours_ago=24 * 10)],
        state_by_id={
            "c1": _state(
                setup=True,
                generated=1,
                waiting=1,
                deliverables=[
                    {
                        "id": "proof",
                        "status": "done",
                        "evidence_url": "https://leadsgenai.in/proof/x.png",
                    },
                ],
            )
        },
    )
    r = activation._first_paid_delivery()
    assert r["status"] == activation._OK
    assert r["checks"]["with_evidence_backed_delivery"] == 1


# --------------------------------------------------------------------------- #
# 9. business_profile + brand_kit alone NEVER count as customer-value
# --------------------------------------------------------------------------- #


def test_9_business_profile_and_brand_kit_alone_do_not_count_as_delivery(monkeypatch):
    """Even if the deliverables list marks business_profile + brand_kit `done`
    with an evidence_url (defensive), they must NEVER satisfy the
    evidence-backed tier. They're onboarding, not marketing delivery."""
    _install_stubs(
        monkeypatch,
        clients=[_customer("c1", hours_ago=24 * 10)],
        state_by_id={
            "c1": _state(
                setup=True,
                deliverables=[
                    {"id": "business_profile", "status": "done", "evidence_url": "https://x/y"},
                    {"id": "brand_kit", "status": "done", "evidence_url": "https://x/z"},
                ],
            )
        },
    )
    r = activation._first_paid_delivery()
    assert r["status"] == activation._WARN
    assert r["checks"]["with_evidence_backed_delivery"] == 0
    assert r["checks"]["zero_completed_after_sla"] == 1


# --------------------------------------------------------------------------- #
# 10. Stage field alone doesn't count
# --------------------------------------------------------------------------- #


def test_10_stage_field_alone_does_not_count_as_delivery(monkeypatch):
    """A customer whose stage moved to 'renewal_ready' but has no generated /
    visible / completed persisted evidence must still WARN — stage labels lie."""
    _install_stubs(
        monkeypatch,
        clients=[_customer("c1", hours_ago=96)],
        state_by_id={
            "c1": {
                "stage": "renewal_ready",  # label present but no evidence
                "deliverable_completion_pct": 60,
                "setup_checks": {"business": True, "brand": True},
                "content_generated": 0,
                "posts_waiting_for_approval": 0,
                "posts_scheduled": 0,
                "posts_published": 0,
                "deliverables": [],
            }
        },
    )
    r = activation._first_paid_delivery()
    assert r["status"] == activation._WARN
    assert r["checks"]["zero_generated_after_grace"] == 1


# --------------------------------------------------------------------------- #
# 11. Percentage alone doesn't count
# --------------------------------------------------------------------------- #


def test_11_deliverable_completion_pct_alone_does_not_grant_ok(monkeypatch):
    """The old probe treated deliverable_completion_pct > 0 as progress. New
    probe ignores the label — only persisted artifacts count."""
    _install_stubs(
        monkeypatch,
        clients=[_customer("c1", hours_ago=96)],
        state_by_id={
            "c1": {
                "deliverable_completion_pct": 99,  # inflated label
                "setup_checks": {"business": True},
                "content_generated": 0,
                "posts_waiting_for_approval": 0,
                "posts_scheduled": 0,
                "posts_published": 0,
                "deliverables": [],
            }
        },
    )
    r = activation._first_paid_delivery()
    assert r["status"] == activation._WARN


# --------------------------------------------------------------------------- #
# 12. Trial customer never counts
# --------------------------------------------------------------------------- #


def test_12_trial_customer_not_counted(monkeypatch):
    _install_stubs(
        monkeypatch,
        clients=[_customer("c1", hours_ago=96, plan="trial")],
        state_by_id={"c1": _state()},
    )
    r = activation._first_paid_delivery()
    assert r["status"] == activation._NEUTRAL
    assert r["checks"]["paid_customers"] == 0


# --------------------------------------------------------------------------- #
# 13. Wholesale eval failure → WARN with sanitized message
# --------------------------------------------------------------------------- #


def test_13_wholesale_eval_failure_returns_warn_with_sanitized_type(monkeypatch):
    import app.marketing.clients_store as real_store

    class _CustomDBError(RuntimeError):
        pass

    def _boom(*a, **kw):
        # sensitive-looking message that MUST NOT reach the response
        raise _CustomDBError(
            "postgres://leadgen:S3cretP@ss@10.0.0.42:5432/leadgen_db offline; "  # pragma: allowlist secret
            "SELECT * FROM clients WHERE email='jiya@example.com'"
        )

    monkeypatch.setattr(real_store, "list_clients", _boom)
    activation._FIRST_PAID_CACHE.clear()
    activation._FIRST_PAID_CACHE.update({"at": 0.0, "result": None})

    r = activation._first_paid_delivery()
    assert r["status"] == activation._WARN
    assert r["checks"]["eval_error"] is True
    assert r["checks"]["eval_error_type"] == "_CustomDBError"


# --------------------------------------------------------------------------- #
# 14. Exception with credentials/SQL/IP/customer_id/email leaks NONE of them
# --------------------------------------------------------------------------- #


def test_14_no_credentials_or_pii_leak_via_exception_path(monkeypatch):
    import app.marketing.clients_store as real_store

    def _boom(*a, **kw):
        raise RuntimeError(
            "postgres://leadgen:P@sw0rd_9!@172.17.0.2:5432/db; "  # nosecret — synthetic
            "SELECT * FROM clients WHERE id='jiya-makeover' AND "
            "email='sumit@leadsgenai.in' AND access_token='sk-live-ABC123DEF'"  # nosecret — synthetic
        )

    monkeypatch.setattr(real_store, "list_clients", _boom)
    activation._FIRST_PAID_CACHE.clear()
    activation._FIRST_PAID_CACHE.update({"at": 0.0, "result": None})
    r = activation._first_paid_delivery()
    blob = str(r)
    for forbidden in (
        "postgres://",
        "P@sw0rd_9!",
        "172.17.0.2",
        "5432",
        "leadgen_db",
        "jiya-makeover",
        "sumit@leadsgenai.in",
        "sk-live-ABC123DEF",
        "SELECT *",
    ):
        assert forbidden not in blob, f"exception-path leak: {forbidden!r} appears in result"


# --------------------------------------------------------------------------- #
# 15. Result exposes only aggregate counts + bucket strings
# --------------------------------------------------------------------------- #


def test_15_result_exposes_only_aggregate_counts_and_bucket_strings(monkeypatch):
    _install_stubs(
        monkeypatch,
        clients=[
            _customer("distinctive-id-9876543210", hours_ago=96),
            _customer("user_two@example.com", hours_ago=48),
        ],
        state_by_id={
            "distinctive-id-9876543210": _state(setup=True),
            "user_two@example.com": _state(),
        },
    )
    r = activation._first_paid_delivery()
    blob = str(r)
    for identifier in (
        "distinctive-id-9876543210",
        "user_two@example.com",
        "@example.com",
    ):
        assert identifier not in blob, f"identifier leak: {identifier!r}"
    # Buckets present, no raw timestamps
    for k in (
        "oldest_zero_generated_bucket",
        "oldest_zero_visible_bucket",
        "oldest_zero_completed_bucket",
    ):
        v = r["checks"].get(k)
        assert v is None or v in ("<24h", "24-48h", "48-72h", "3-7d", "7d+")


# --------------------------------------------------------------------------- #
# 16. Exact timestamps NEVER appear
# --------------------------------------------------------------------------- #


def test_16_no_iso_timestamp_in_result(monkeypatch):
    _install_stubs(
        monkeypatch,
        clients=[_customer("c1", hours_ago=96)],
        state_by_id={"c1": _state()},
    )
    r = activation._first_paid_delivery()
    blob = str(r)
    # No `T` in the middle of a digit-heavy substring, no `Z` suffix, no `+00:00`
    for pat in ("T00:", "T01:", "T02:", "+00:00", "2026-07-", "2025-", ".000000"):
        assert pat not in blob, f"timestamp leak: {pat!r} in result"


# --------------------------------------------------------------------------- #
# 17. Cache does not preserve stale results beyond TTL
# --------------------------------------------------------------------------- #


def test_17_cache_ttl_bounded(monkeypatch):
    """Within TTL: single evaluation. After TTL simulate: fresh evaluation."""
    call_count = {"n": 0}

    import app.marketing.clients_store as real_store
    import app.marketing.product_one_delivery as real_p1

    def _list(status=None, product=None):
        call_count["n"] += 1
        return []

    monkeypatch.setattr(real_store, "list_clients", _list)
    monkeypatch.setattr(real_p1, "_client_plan_paid", lambda c: False)
    monkeypatch.setattr(real_p1, "customer_delivery_status", lambda cid, c=None: {})

    activation._FIRST_PAID_CACHE.clear()
    activation._FIRST_PAID_CACHE.update({"at": 0.0, "result": None})

    activation._first_paid_delivery()
    activation._first_paid_delivery()
    activation._first_paid_delivery()
    assert call_count["n"] == 1  # cached

    # Simulate TTL expiry by resetting `at`
    activation._FIRST_PAID_CACHE["at"] = 0.0
    activation._first_paid_delivery()
    assert call_count["n"] == 2  # re-evaluated


# --------------------------------------------------------------------------- #
# Cross-tenant safety (paranoid guardrail)
# --------------------------------------------------------------------------- #


def test_18_cross_tenant_artifact_never_counted_for_wrong_customer(monkeypatch):
    """customer_delivery_status stub deliberately returns SAME artifacts for
    both customer IDs. Each customer must be scored on its OWN state only —
    stub returns per-id state, so if cross-tenant leak existed both would
    have artifacts. Assert independent scoring."""
    _install_stubs(
        monkeypatch,
        clients=[
            _customer("cust-a", hours_ago=96),
            _customer("cust-b", hours_ago=96),
        ],
        state_by_id={
            "cust-a": _state(setup=True, generated=1, waiting=1, published=1),
            "cust-b": _state(setup=True),  # no artifacts at all
        },
    )
    r = activation._first_paid_delivery()
    # Exactly ONE customer has generated/visible/completed. NOT both.
    assert r["checks"]["with_generated_artifacts"] == 1
    assert r["checks"]["with_customer_visible_artifacts"] == 1
    assert r["checks"]["with_evidence_backed_delivery"] == 1
    # And exactly ONE is stale-on-visible (cust-b).
    assert r["checks"]["zero_visible_after_sla"] == 1
    assert r["status"] == activation._WARN


# --------------------------------------------------------------------------- #
# Wiring guardrails
# --------------------------------------------------------------------------- #


def test_wiring_probe_in_probes_tuple():
    assert activation._first_paid_delivery in activation._PROBES
    assert "first_paid_delivery" in activation._PROBE_BY_KEY
    survival_keys = activation._PHASES[0][2]
    assert "first_paid_delivery" in survival_keys


# --------------------------------------------------------------------------- #
# Plan-level vs item-level accounting distinction (2026-07-11 P0)
# --------------------------------------------------------------------------- #


def test_19_item_level_delivery_does_not_imply_plan_complete(monkeypatch):
    """Jiya-shape: 1 published item + 4/10 deliverables done (40%). ITEM-level
    counter increments; PLAN-level counter does NOT."""
    _install_stubs(
        monkeypatch,
        clients=[_customer("c1", hours_ago=96)],
        state_by_id={
            "c1": _state(
                setup=True,
                generated=1,
                waiting=1,
                published=1,
                deliverable_pct=40,
            )
        },
    )
    r = activation._first_paid_delivery()
    assert r["checks"]["with_evidence_backed_delivery"] == 1  # item-level: ≥1 published
    assert r["checks"]["with_completed_plan"] == 0  # plan-level: NOT complete
    assert r["checks"]["plan_completion_distribution"]["26-50%"] == 1
    assert r["checks"]["plan_completion_distribution"]["100%"] == 0


def test_20_full_plan_completion_counted_separately(monkeypatch):
    """Customer with all 10 deliverables done (100%) increments both counters."""
    _install_stubs(
        monkeypatch,
        clients=[_customer("c1", hours_ago=96)],
        state_by_id={
            "c1": _state(
                setup=True,
                generated=12,
                waiting=0,
                published=12,
                deliverable_pct=100,
            )
        },
    )
    r = activation._first_paid_delivery()
    assert r["checks"]["with_evidence_backed_delivery"] == 1
    assert r["checks"]["with_completed_plan"] == 1
    assert r["checks"]["plan_completion_distribution"]["100%"] == 1


def test_21_plan_distribution_covers_all_paid_customers(monkeypatch):
    """Multiple paid customers land in different buckets — no double-counting,
    sum(distribution) == paid_customers."""
    _install_stubs(
        monkeypatch,
        clients=[
            _customer("c1", hours_ago=96),  # 0%
            _customer("c2", hours_ago=96),  # 40%
            _customer("c3", hours_ago=96),  # 100%
        ],
        state_by_id={
            "c1": _state(deliverable_pct=0),
            "c2": _state(setup=True, generated=1, waiting=1, published=1, deliverable_pct=40),
            "c3": _state(setup=True, generated=12, waiting=0, published=12, deliverable_pct=100),
        },
    )
    r = activation._first_paid_delivery()
    dist = r["checks"]["plan_completion_distribution"]
    assert sum(dist.values()) == r["checks"]["paid_customers"] == 3
    assert dist["0%"] == 1
    assert dist["26-50%"] == 1
    assert dist["100%"] == 1
    assert r["checks"]["with_completed_plan"] == 1  # only c3


def test_22_result_shape_includes_new_plan_accounting_fields():
    """Contract lock: downstream consumers can rely on these keys existing."""
    empty = activation._EMPTY_CHECKS
    for k in (
        "with_evidence_backed_delivery",
        "with_completed_plan",
        "plan_completion_distribution",
    ):
        assert k in empty, f"missing key: {k}"
    dist = empty["plan_completion_distribution"]
    assert set(dist.keys()) == {"0%", "1-25%", "26-50%", "51-75%", "76-99%", "100%"}


def test_23_payment_evidence_accepts_current_or_legacy_invoice_identity(monkeypatch, tmp_path):
    from app.billing import gst_invoice

    store = tmp_path / "invoices.jsonl"
    store.write_text(
        '{"number":"INV/2026-27/0001","client_id":"old-client-id","gateway":"upi"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(gst_invoice, "_STORE", lambda: str(store))

    assert activation._client_has_payment_evidence({"id": "old-client-id"}) is True
    assert (
        activation._client_has_payment_evidence(
            {"id": "current-client-id", "billing_client_ids": ["old-client-id"]}
        )
        is True
    )
    assert activation._client_has_payment_evidence({"id": "plan-only", "plan": "starter"}) is False


def test_24_probe_ignores_active_plan_without_payment_evidence(monkeypatch):
    _install_stubs(
        monkeypatch,
        clients=[_customer("paid", hours_ago=96), _customer("test-only", hours_ago=96)],
        state_by_id={
            "paid": _state(setup=True, generated=1, waiting=1, published=1),
            "test-only": _state(),
        },
    )
    monkeypatch.setattr(
        activation,
        "_client_has_payment_evidence",
        lambda c: c.get("id") == "paid",
    )

    r = activation._first_paid_delivery()
    assert r["checks"]["paid_customers"] == 1
    assert r["checks"]["zero_completed_after_sla"] == 0


def test_wiring_readiness_shape_stable(monkeypatch):
    """All 16 probes must return dicts with the canonical shape when the
    new probe runs alongside them."""
    import app.marketing.clients_store as real_store

    monkeypatch.setattr(real_store, "list_clients", lambda *a, **kw: [])
    activation._FIRST_PAID_CACHE.clear()
    activation._FIRST_PAID_CACHE.update({"at": 0.0, "result": None})

    items = [p() for p in activation._PROBES]
    for it in items:
        assert set(it.keys()) >= {"key", "label", "status", "env_vars", "checks", "action"}
        assert it["status"] in (
            activation._OK,
            activation._WARN,
            activation._NEUTRAL,
            activation._BLOCKER,
        )
