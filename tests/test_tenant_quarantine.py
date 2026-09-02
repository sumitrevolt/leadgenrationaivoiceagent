"""Fixture-tenant quarantine - must never touch a paying customer.

Production 2026-08-06: 10 seeded `@example.com` clients (7 `active`, 3 `paused`)
sit alongside the one real payer. Each fixture carries 12 seeded
`billing_records`, so the choice of quarantine status is not cosmetic - see
`tenant_quarantine`'s module docstring for why `cancelled` is the only value
legal in the Postgres enum AND terminal in `entitlement_assurance`.

These tests pin the refusal rules first, because the failure mode that matters
is cancelling a real customer, not leaving a fixture active.
"""

from __future__ import annotations

from app.platform import tenant_quarantine as tq

# Real production tenant ids, kept verbatim so this fixture set matches the live
# shape these rules were written against. TENANT IDS, not credentials - the same
# values appear in `clients_store`'s docstrings. detect-secrets reads them as hex
# high-entropy strings; allowlisted rather than obscured so the test still
# documents the exact rows it protects.
_PAYING_ID = "d79d690f61b3"  # pragma: allowlist secret
_DISPOSABLE_ID = "041a2fb0ca1e"  # pragma: allowlist secret


# --------------------------------------------------------------------------- #
# status choice - the whole point of the module
# --------------------------------------------------------------------------- #
def test_quarantine_status_is_legal_in_the_postgres_enum():
    from app.models.client import ClientStatus

    assert tq.QUARANTINE_STATUS == ClientStatus.CANCELLED.value


def test_quarantine_status_is_terminal_for_entitlement_assurance():
    """`paused`/`inactive` would raise invoice_without_active_subscription on
    every fixture, since each carries 12 seeded billing_records."""
    from app.billing.entitlement_assurance import _TERMINAL_STATUSES

    assert tq.QUARANTINE_STATUS in _TERMINAL_STATUSES
    assert "paused" not in _TERMINAL_STATUSES
    assert "inactive" not in _TERMINAL_STATUSES


def test_inactive_is_never_used():
    assert tq.QUARANTINE_STATUS != "inactive"


# --------------------------------------------------------------------------- #
# fixture detection
# --------------------------------------------------------------------------- #
def test_real_upi_customer_email_is_not_a_fixture():
    """Real UPI customers get `<client_id>@upi.local` - must never match."""
    assert tq._looks_like_fixture(f"{_PAYING_ID}@upi.local") is False


def test_example_com_is_a_fixture():
    """The seeded shape is `contact{i}@{company}.example.com` - a naive
    `"@example.com" in email` check is False for EVERY one of them, because the
    `@` sits before `perfect`, not before `example.com`. Matching must be on the
    domain suffix. (The same flaw is present in the two existing
    `endswith("@example.com")` blocklists, which therefore do not block these.)"""
    assert tq._looks_like_fixture("contact5@perfect.example.com") is True
    assert tq._looks_like_fixture("CONTACT0@SUNVOLT.EXAMPLE.COM") is True
    assert tq._looks_like_fixture("someone@example.com") is True  # bare domain too


def test_lookalike_domain_is_not_a_fixture():
    """`notexample.com` must not match the `example.com` suffix."""
    assert tq._looks_like_fixture("a@notexample.com") is False
    assert tq._looks_like_fixture("a@example.com.evil.io") is False


def test_blank_email_is_not_a_fixture():
    assert tq._looks_like_fixture("") is False
    assert tq._looks_like_fixture(None) is False  # type: ignore[arg-type]
    assert tq._looks_like_fixture("no-at-sign") is False


# --------------------------------------------------------------------------- #
# fail-CLOSED guards
# --------------------------------------------------------------------------- #
def test_subscription_check_fails_closed_on_error():
    """If we cannot prove a tenant has no live subscription, refuse."""

    class _Boom:
        def query(self, *_a):
            raise RuntimeError("db down")

    assert tq._has_live_subscription(_Boom(), "any") is True


def test_alias_check_fails_closed_on_error(monkeypatch):
    from app.marketing import clients_store

    def _boom(_c):
        raise RuntimeError("jsonl unreadable")

    monkeypatch.setattr(clients_store, "resolve_client", _boom)
    assert tq._has_billing_alias("any") is True


def test_alias_check_true_when_linked(monkeypatch):
    from app.marketing import clients_store

    monkeypatch.setattr(
        clients_store, "resolve_client", lambda _c: {"id": "m", "billing_client_ids": ["b"]}
    )
    assert tq._has_billing_alias("b") is True


def test_alias_check_false_when_unlinked(monkeypatch):
    from app.marketing import clients_store

    monkeypatch.setattr(
        clients_store, "resolve_client", lambda _c: {"id": "m", "billing_client_ids": []}
    )
    assert tq._has_billing_alias("m") is False


# --------------------------------------------------------------------------- #
# classification against a production-shaped fixture set
# --------------------------------------------------------------------------- #
class _Client:
    def __init__(self, cid, name, email, status, amount=0):
        self.id = cid
        self.business_name = name
        self.contact_email = email
        self.status = status
        self.monthly_amount = amount


class _Q:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_a):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class _Sess:
    def __init__(self, rows):
        self.rows = rows
        self.committed = 0

    def query(self, *_a):
        return _Q(self.rows)

    def commit(self):
        self.committed += 1


def _patch(monkeypatch, sess, *, live_subs=(), aliased=()):
    import contextlib

    import app.models.base as mb

    @contextlib.contextmanager
    def _ctx():
        yield sess

    monkeypatch.setattr(mb, "get_db_session", _ctx, raising=False)
    monkeypatch.setattr(tq, "_has_live_subscription", lambda _db, cid: cid in live_subs)
    monkeypatch.setattr(tq, "_has_billing_alias", lambda cid: cid in aliased)


def _prod_shaped_rows():
    return [
        _Client(
            "b66670eb", "Perfect Smile Studio", "contact5@perfect.example.com", "active", 3500000
        ),
        _Client("91ffadf7", "SunVolt Solar", "contact0@sunvolt.example.com", "paused", 1500000),
        _Client("platform", "LeadGen AI (self)", "platform@leadsgenai.in", "active"),
        _Client(_PAYING_ID, "jiya makeover", f"{_PAYING_ID}@upi.local", "active", 1500000),
        _Client(
            _DISPOSABLE_ID, "LAUNCH E2E Disposable", f"{_DISPOSABLE_ID}@upi.local", "cancelled"
        ),
    ]


def test_paying_customer_is_refused(monkeypatch):
    """The failure that actually matters."""
    _patch(monkeypatch, _Sess(_prod_shaped_rows()), live_subs={_PAYING_ID})
    res = tq.find_fixture_tenants()
    ids = [c["id"] for c in res["candidates"]]
    assert _PAYING_ID not in ids
    refusal = [r for r in res["refused"] if r["id"] == _PAYING_ID][0]
    assert refusal["reason"] == "not_a_fixture_email"


def test_platform_self_tenant_is_refused(monkeypatch):
    _patch(monkeypatch, _Sess(_prod_shaped_rows()))
    res = tq.find_fixture_tenants()
    assert "platform" not in [c["id"] for c in res["candidates"]]
    assert [r for r in res["refused"] if r["id"] == "platform"][0]["reason"] == "protected_id"


def test_fixtures_are_selected_regardless_of_active_or_paused(monkeypatch):
    """The 3 already-`paused` fixtures still need flipping - `paused` is NOT
    terminal, so they currently raise an entitlement finding too."""
    _patch(monkeypatch, _Sess(_prod_shaped_rows()))
    ids = [c["id"] for c in tq.find_fixture_tenants()["candidates"]]
    assert "b66670eb" in ids  # active
    assert "91ffadf7" in ids  # paused


def test_already_cancelled_is_skipped(monkeypatch):
    rows = [_Client("x1", "Old Fixture", "a@b.example.com", "cancelled")]
    _patch(monkeypatch, _Sess(rows))
    res = tq.find_fixture_tenants()
    assert res["candidates"] == []
    assert res["refused"][0]["reason"] == "already_quarantined"


def test_fixture_with_live_subscription_is_refused(monkeypatch):
    """Belt and braces: even a fixture email is spared if money is attached."""
    rows = [_Client("x2", "Fixture w/ sub", "a@b.example.com", "active")]
    _patch(monkeypatch, _Sess(rows), live_subs={"x2"})
    res = tq.find_fixture_tenants()
    assert res["candidates"] == []
    assert res["refused"][0]["reason"] == "has_live_subscription"


def test_fixture_with_billing_alias_is_refused(monkeypatch):
    rows = [_Client("x3", "Fixture w/ alias", "a@b.example.com", "active")]
    _patch(monkeypatch, _Sess(rows), aliased={"x3"})
    res = tq.find_fixture_tenants()
    assert res["candidates"] == []
    assert res["refused"][0]["reason"] == "has_billing_alias"


# --------------------------------------------------------------------------- #
# mutation safety
# --------------------------------------------------------------------------- #
def test_dry_run_mutates_nothing(monkeypatch):
    sess = _Sess(_prod_shaped_rows())
    _patch(monkeypatch, sess)
    out = tq.quarantine_fixture_tenants(dry_run=True)
    assert out["dry_run"] is True
    assert out["selected"] >= 2
    assert out["pg_updated"] == 0
    assert sess.committed == 0
    assert out["backup"] == ""
    assert "would_quarantine" in out


def test_backup_failure_aborts_without_mutating(monkeypatch):
    monkeypatch.setenv("TENANT_QUARANTINE", "1")
    sess = _Sess(_prod_shaped_rows())
    _patch(monkeypatch, sess)

    def _boom(_rows):
        raise OSError("disk full")

    monkeypatch.setattr(tq, "_write_backup", _boom)
    out = tq.quarantine_fixture_tenants(dry_run=False)
    assert "backup_failed" in str(out.get("error", ""))
    assert out["pg_updated"] == 0
    assert sess.committed == 0


def test_mutate_refused_when_flag_off(monkeypatch):
    monkeypatch.delenv("TENANT_QUARANTINE", raising=False)
    sess = _Sess(_prod_shaped_rows())
    _patch(monkeypatch, sess)
    out = tq.quarantine_fixture_tenants(dry_run=False)
    assert out["error"] == "TENANT_QUARANTINE_off"
    assert out["flag_enabled"] is False
    assert out["pg_updated"] == 0
    assert sess.committed == 0
    assert "would_quarantine" in out


def test_limit_bounds_the_batch(monkeypatch):
    _patch(monkeypatch, _Sess(_prod_shaped_rows()))
    out = tq.quarantine_fixture_tenants(limit=1, dry_run=True)
    assert out["selected"] == 1


def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("TENANT_QUARANTINE", raising=False)
    assert tq.quarantine_enabled() is False
    monkeypatch.setenv("TENANT_QUARANTINE", "1")
    assert tq.quarantine_enabled() is True


def test_never_raises_on_db_error(monkeypatch):
    import app.models.base as mb

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(mb, "get_db_session", _boom, raising=False)
    res = tq.find_fixture_tenants()
    assert res["candidates"] == []
    assert "error" in res
