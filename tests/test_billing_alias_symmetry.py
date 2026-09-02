"""Regression: billing id resolution must be symmetric (ADR-095 / ADR-106).

Root cause of the 2026-07-24 production UAT finding (F-1): the only paying
customer (Jiya Makeover Studio) has her active Subscription + paid Invoice owned
by a legacy billing id, while her portal session carries the canonical marketing
slug ``jiya-makeover``. Because the canonical marketing record's
``billing_client_ids`` was never linked to that alias,
``_billing_client_ids('jiya-makeover')`` returned only ``['jiya-makeover']`` — so
``GET /api/billing/subscription`` 404'd and her portal rendered "NO PLAN /
Free / Trial" for a paying customer (and even invited her to pay again).

The live fix is a data reconcile (``clients_store.link_billing_alias`` so the
canonical record carries the alias). These tests lock the *contract* that
``_billing_client_ids`` expands a canonical id to the full billing family and
that both directions resolve to the same set, so the resolution helper can never
silently regress and re-orphan a paying customer's plan.
"""

from app.api.billing import _billing_client_ids

# Legacy billing id (ADR-095 family) — a plain client identifier, not a credential.
_ALIAS = "d79d690f61b3"  # pragma: allowlist secret
_CANON = "jiya-makeover"


def _linked_record():
    return {"id": _CANON, "billing_client_ids": [_ALIAS]}


def test_canonical_slug_includes_linked_billing_alias(monkeypatch):
    import app.marketing.clients_store as cs

    monkeypatch.setattr(cs, "resolve_client", lambda cid: _linked_record())
    fam = set(_billing_client_ids(_CANON))
    assert _CANON in fam
    assert _ALIAS in fam, (
        "canonical slug must resolve the linked billing alias — otherwise a "
        "paying customer's subscription/invoice (owned by the alias) is invisible"
    )


def test_alias_and_canonical_resolve_same_family(monkeypatch):
    import app.marketing.clients_store as cs

    def _resolve(cid):
        # resolve_client covers BOTH directions once the alias is linked
        if cid in (_CANON, _ALIAS):
            return _linked_record()
        return None

    monkeypatch.setattr(cs, "resolve_client", _resolve)
    assert set(_billing_client_ids(_CANON)) == set(_billing_client_ids(_ALIAS))


def test_missing_record_falls_back_to_raw_id(monkeypatch):
    import app.marketing.clients_store as cs

    monkeypatch.setattr(cs, "resolve_client", lambda cid: None)
    # never raises, never returns empty — always at least the raw id
    assert _billing_client_ids("unknown-client") == ["unknown-client"]


def test_resolution_never_raises_on_bad_store(monkeypatch):
    import app.marketing.clients_store as cs

    def _boom(cid):
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(cs, "resolve_client", _boom)
    # helper is documented "never raises" — must degrade to the raw id
    assert _billing_client_ids(_CANON) == [_CANON]
