"""Monthly billing-cycle deliverable seed.

Production 2026-08-07: `customer_deliverables` held 20 rows, ALL
`billing_cycle_month = '2026-07'`, newest created 2026-07-18, and no scheduler
job referenced deliverables at all. `initialize_deliverables_for_client` is
called from exactly one place — `app/billing/usage.py` on plan activation — so
nothing creates the next month's rows.

Consequence: the one paying customer was 30+ days into a paid month with no
current-cycle ledger, and `sync_customer_deliverable_status` (update-only by
contract) had nothing to attach to no matter how much content was generated.
PR #269's alias expansion was necessary but not sufficient.

The selector is deliberately the SUBSCRIPTION, not `clients.status`: a
non-terminal subscription is the only honest definition of "still paying", and
it excludes quarantined fixture tenants by construction since they have no
subscription rows.
"""

from __future__ import annotations

from app.marketing import product_one_delivery as pod

_PAYING_ID = "d79d690f61b3"  # pragma: allowlist secret


# --------------------------------------------------------------------------- #
# flag + cycle key
# --------------------------------------------------------------------------- #
def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("DELIVERABLE_CYCLE_SEED", raising=False)
    assert pod.cycle_seed_enabled() is False


def test_flag_on_tokens(monkeypatch):
    for tok in ("1", "true", "yes", "on", "ON"):
        monkeypatch.setenv("DELIVERABLE_CYCLE_SEED", tok)
        assert pod.cycle_seed_enabled() is True, tok


def test_cycle_month_is_ist_not_utc():
    """Indian billing cycles — a UTC boundary would roll the month 5h30m early
    for the customer."""
    from datetime import datetime, timedelta

    expected = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%Y-%m")
    assert pod.current_cycle_month() == expected
    assert len(pod.current_cycle_month()) == 7


def test_dead_subscription_states_cover_both_spellings():
    assert "cancelled" in pod._DEAD_SUBSCRIPTION_STATES
    assert "canceled" in pod._DEAD_SUBSCRIPTION_STATES
    assert "expired" in pod._DEAD_SUBSCRIPTION_STATES
    # a live one must NOT be treated as dead
    assert "active" not in pod._DEAD_SUBSCRIPTION_STATES


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class _Sub:
    def __init__(self, client_id, status="active", plan_name="starter"):
        self.client_id = client_id
        self.status = status
        self.plan_name = plan_name


class _Client:
    def __init__(self, cid, plan="starter"):
        self.id = cid
        self.plan = plan


class _Query:
    def __init__(self, sess, rows, counting=False):
        self.sess = sess
        self.rows = rows
        self.counting = counting

    def limit(self, _n):
        return self

    def filter(self, *_a):
        return self

    def all(self):
        return self.rows

    def count(self):
        return self.sess.existing_count


class _Sess:
    def __init__(self, subs, clients, existing_count=0):
        self.subs = subs
        self.clients = clients
        self.existing_count = existing_count
        self.committed = 0
        self.init_calls = []

    def query(self, model):
        name = getattr(model, "__name__", str(model))
        if "Subscription" in name:
            return _Query(self, self.subs)
        return _Query(self, [], counting=True)

    def get(self, _model, pk):
        return self.clients.get(pk)

    def commit(self):
        self.committed += 1


def _patch(monkeypatch, sess, init_spy=None):
    import contextlib

    import app.models.base as mb

    @contextlib.contextmanager
    def _ctx():
        yield sess

    monkeypatch.setattr(mb, "get_db_session", _ctx, raising=False)
    if init_spy is not None:
        monkeypatch.setattr(pod, "initialize_deliverables_for_client", init_spy)


# --------------------------------------------------------------------------- #
# behaviour
# --------------------------------------------------------------------------- #
def test_dry_run_creates_nothing(monkeypatch):
    sess = _Sess([_Sub(_PAYING_ID)], {_PAYING_ID: _Client(_PAYING_ID)})
    calls = []
    _patch(monkeypatch, sess, lambda *a, **k: calls.append(a))

    out = pod.seed_current_cycle_deliverables(dry_run=True)
    assert out["dry_run"] is True
    assert out["clients_scanned"] == 1
    assert out["rows_created"] == 0
    assert calls == [], "dry-run must not seed"
    assert sess.committed == 0


def test_live_run_seeds_the_paying_customer(monkeypatch):
    sess = _Sess([_Sub(_PAYING_ID)], {_PAYING_ID: _Client(_PAYING_ID)})
    calls = []

    def _spy(db, cid, plan, cycle):
        calls.append((cid, plan, cycle))
        sess.existing_count = 10  # simulate the rows appearing

    _patch(monkeypatch, sess, _spy)
    out = pod.seed_current_cycle_deliverables(month="2026-08", dry_run=False)

    assert calls and calls[0][0] == _PAYING_ID
    assert calls[0][2] == "2026-08"
    assert out["rows_created"] == 10
    assert sess.committed >= 1


def test_cancelled_subscription_is_skipped(monkeypatch):
    sess = _Sess([_Sub("dead-tenant", status="cancelled")], {"dead-tenant": _Client("dead-tenant")})
    calls = []
    _patch(monkeypatch, sess, lambda *a, **k: calls.append(a))

    out = pod.seed_current_cycle_deliverables(dry_run=False)
    assert out["skipped_dead_subscription"] == 1
    assert calls == []


def test_missing_db_client_is_skipped_not_raised(monkeypatch):
    """FK guard — seeding against a missing clients row would raise."""
    sess = _Sess([_Sub("ghost")], {})
    calls = []
    _patch(monkeypatch, sess, lambda *a, **k: calls.append(a))

    out = pod.seed_current_cycle_deliverables(dry_run=False)
    assert out["skipped_no_db_client"] == 1
    assert calls == []
    assert "error" not in out


def test_second_run_creates_no_duplicates(monkeypatch):
    """Idempotency: rows already present for this client+cycle -> nothing new."""
    sess = _Sess([_Sub(_PAYING_ID)], {_PAYING_ID: _Client(_PAYING_ID)}, existing_count=10)
    _patch(monkeypatch, sess, lambda *a, **k: None)  # seeder is a no-op when rows exist

    out = pod.seed_current_cycle_deliverables(month="2026-08", dry_run=False)
    assert out["rows_created"] == 0
    assert out["skipped_existing"] == 1


def test_unknown_subscription_status_fails_safe(monkeypatch):
    """An unrecognised status must SEED (fail safe) rather than silently withhold
    a paying customer's deliverables."""
    sess = _Sess([_Sub(_PAYING_ID, status="past_due")], {_PAYING_ID: _Client(_PAYING_ID)})
    calls = []

    def _spy(db, cid, plan, cycle):
        calls.append(cid)
        sess.existing_count = 10

    _patch(monkeypatch, sess, _spy)
    out = pod.seed_current_cycle_deliverables(dry_run=False)
    assert calls == [_PAYING_ID]
    assert out["skipped_dead_subscription"] == 0


def test_never_raises_on_db_error(monkeypatch):
    import app.models.base as mb

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(mb, "get_db_session", _boom, raising=False)
    out = pod.seed_current_cycle_deliverables(dry_run=False)
    assert out["errors"] >= 1
    assert out["rows_created"] == 0


def test_per_client_failure_does_not_abort_the_sweep(monkeypatch):
    sess = _Sess(
        [_Sub("bad"), _Sub(_PAYING_ID)],
        {"bad": _Client("bad"), _PAYING_ID: _Client(_PAYING_ID)},
    )
    seen = []

    def _spy(db, cid, plan, cycle):
        if cid == "bad":
            raise RuntimeError("boom")
        seen.append(cid)
        sess.existing_count = 10

    _patch(monkeypatch, sess, _spy)
    out = pod.seed_current_cycle_deliverables(dry_run=False)
    assert out["errors"] == 1
    assert seen == [_PAYING_ID], "the good tenant must still be seeded"
