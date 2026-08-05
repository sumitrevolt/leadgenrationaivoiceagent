"""Durable prospective store (L6) — claim/lease/idempotency + tenant isolation.

These lock the P0 properties the JSONL first cut could not provide:
  - concurrent claimers produce exactly ONE dispatch per row
  - a handler failure retries and eventually goes dead; it never marks completion
  - an expired lease is recoverable (crashed worker)
  - tenant A can neither read, cancel nor purge tenant B
  - secrets are redacted before anything is persisted

Uses its own file-backed SQLite engine (threads share it) and monkeypatches the
store's `_models()` seam, so it neither depends on nor mutates the app engine.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.prospective_memory import ProspectiveMemory
from app.platform import prospective_store as ps


@pytest.fixture()
def store(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'prospective.db'}", future=True)
    ProspectiveMemory.__table__.create(bind=engine, checkfirst=True)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def _session():
        db = Session()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    monkeypatch.setattr(ps, "_models", lambda: (ProspectiveMemory, _session))
    yield ps
    engine.dispose()


# ------------------------------------------------------------------ producer


def test_enqueue_validates_and_is_idempotent(store):
    assert store.enqueue("", "rohan", "x")["ok"] is False
    assert store.enqueue("tenantA", "", "")["ok"] is False

    first = store.enqueue("tenantA", "rohan", "call back lead", in_minutes=-1)
    again = store.enqueue("tenantA", "rohan", "call back lead", in_minutes=-1)
    assert first["ok"] and first["duplicate"] is False
    assert again["duplicate"] is True and again["row"]["id"] == first["row"]["id"]

    # the idempotency basis includes tenant — same action, different tenant, new row
    other = store.enqueue("tenantB", "rohan", "call back lead", in_minutes=-1)
    assert other["row"]["id"] != first["row"]["id"]


def test_secrets_are_redacted_before_persist(store):
    row = store.enqueue(
        "tenantA", "neha", "use key sk-ABCDEFGHIJKLMNOP1234 now", in_minutes=5
    )  # pragma: allowlist secret
    assert "sk-ABCDEFGHIJKLMNOP1234" not in row["row"]["action"]  # pragma: allowlist secret


# ---------------------------------------------------------------- exactly-once


def test_concurrent_claimers_never_double_dispatch(store):
    n_rows, n_workers = 25, 4
    for i in range(n_rows):
        store.enqueue("tenantA", "rohan", f"followup-{i}", in_minutes=-1)

    claimed: dict[int, list[str]] = {}
    lock = threading.Lock()
    barrier = threading.Barrier(n_workers)

    def claimer(wid: int) -> None:
        barrier.wait()  # maximise overlap
        got = store.claim_batch(f"worker-{wid}", limit=n_rows)
        with lock:
            claimed[wid] = [r["id"] for r in got]

    threads = [threading.Thread(target=claimer, args=(i,)) for i in range(n_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    all_ids = [i for ids in claimed.values() for i in ids]
    assert len(all_ids) == n_rows, "a row was lost"
    assert len(set(all_ids)) == n_rows, "a row was claimed twice"
    assert store.claim_batch("late-worker", limit=50) == []


def test_dispatch_is_terminal_and_not_repeatable(store):
    store.enqueue("tenantA", "rohan", "one", in_minutes=-1)
    row = store.claim_batch("w1", limit=1)[0]
    assert store.mark_dispatched(row["id"], "task-1") is True
    assert store.mark_dispatched(row["id"], "task-2") is False


def test_handler_failure_retries_then_dies(store):
    store.enqueue("tenantA", "rohan", "boom", in_minutes=-1)
    row = store.claim_batch("w1", limit=1)[0]

    assert store.mark_failed(row["id"], "downstream down", max_attempts=3) == store.STATUS_PENDING
    pending = store.list_rows("tenantA", status=store.STATUS_PENDING)
    assert [r["id"] for r in pending] == [row["id"]]
    assert pending[0]["attempt_count"] == 1  # progress is recorded, work is not lost

    for _ in range(3):
        store.claim_batch("w1", limit=5)
        store.mark_failed(row["id"], "still down", max_attempts=3)

    dead = store.list_rows("tenantA", status=store.STATUS_DEAD)
    assert [r["id"] for r in dead] == [row["id"]]


def test_expired_lease_is_recoverable(store):
    store.enqueue("tenantA", "rohan", "lease-test", in_minutes=-1)
    assert len(store.claim_batch("crashy", limit=5, lease_seconds=5)) == 1

    assert store.recover_expired() == 0  # lease still valid
    assert store.recover_expired(now=store._now() + timedelta(seconds=30)) == 1
    assert len(store.list_rows("tenantA", status=store.STATUS_PENDING)) == 1


# ------------------------------------------------------------ tenant isolation


def test_tenant_a_cannot_touch_tenant_b(store):
    store.enqueue("tenantA", "rohan", "secret-A", in_minutes=60)
    b_row = store.enqueue("tenantB", "neha", "secret-B", in_minutes=60)["row"]

    a_rows = store.list_rows("tenantA")
    assert all(r["tenant_id"] == "tenantA" for r in a_rows)
    assert all(r["id"] != b_row["id"] for r in a_rows)

    assert store.cancel("tenantA", b_row["id"])["ok"] is False
    assert store.purge("tenantA")["purged"] == 1
    assert len(store.list_rows("tenantB")) == 1  # survived A's purge


def test_blank_tenant_has_no_global_access(store):
    store.enqueue("tenantA", "rohan", "x", in_minutes=5)
    assert store.list_rows("") == []
    assert store.cancel("", "any-id")["ok"] is False
    assert store.purge("")["ok"] is False


def test_stats_and_retention(store):
    store.enqueue("tenantA", "rohan", "x", in_minutes=-1)
    s = store.stats("tenantA")
    assert s["available"] is True and s["pending"] == 1 and s["due_now"] == 1
    assert store.retention_sweep(days=0) == 0  # 0 = keep forever
