"""Orphan agent_tasks ledger — the pending rows the lease reaper cannot see.

Production 2026-08-06: 12,631 rows `status='pending'`, `claimed_at IS NULL`,
`completed_at IS NULL`, goal `"Scheduled routine: <job>"`, growing ~700/day
since 2026-07-19. Against 48 `done` and 7 `failed`.

Cause: self-assigned producers (`team_scheduler` routine bridge,
`office_hq` admin dispatch) call `assign()` -> `start()`. `start()` requires
`claimed`, a state those rows never enter because nothing calls `claim_next()`
for a job-name pseudo-agent. So `start()` no-op'd, and the later `complete()`
(which matches `claimed|running`) no-op'd too — both discard `{"ok": False}`.
Only `fail()` accepts `pending`, which is exactly why FAILING routines closed
and SUCCEEDING ones leaked.

`reap_stale_leases()` cannot help: its predicate is
`status IN ('claimed','running') AND claimed_at < cutoff` — disjoint on BOTH
clauses (and `NULL < cutoff` is NULL in SQL, not TRUE).

These tests pin the fix from both ends: `begin()` stops new orphans, and
`reap_orphan_routines()` closes the historical ones safely.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from app.platform import agent_task_queue as atq


# --------------------------------------------------------------------------- #
# begin() — the source fix
# --------------------------------------------------------------------------- #
def test_begin_transitions_pending_to_running(monkeypatch):
    seen: dict[str, str] = {}

    async def _fake_update(task_id, from_status, to_status):
        seen.update(task_id=task_id, frm=from_status, to=to_status)
        return {"ok": True}

    monkeypatch.setattr(atq, "_update_status", _fake_update)
    res = asyncio.run(atq.begin("t-1"))
    assert res["ok"] is True
    assert seen["frm"] == "pending", "begin must accept a never-claimed row"
    assert seen["to"] == "running"


def test_start_still_requires_claimed(monkeypatch):
    """begin() must not weaken start(); the queue hand-off contract stands."""
    seen: dict[str, str] = {}

    async def _fake_update(task_id, from_status, to_status):
        seen.update(frm=from_status, to=to_status)
        return {"ok": True}

    monkeypatch.setattr(atq, "_update_status", _fake_update)
    asyncio.run(atq.start("t-2"))
    assert seen["frm"] == "claimed"


# --------------------------------------------------------------------------- #
# flag gating — the two reapers must be independently armable
# --------------------------------------------------------------------------- #
def test_orphan_reap_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("AGENT_TASK_ORPHAN_REAP", raising=False)
    assert atq.orphan_reap_enabled() is False


def test_orphan_reap_flag_is_independent_of_lease_reap(monkeypatch):
    """Arming lease reap must NOT arm the orphan sweep — different risk."""
    monkeypatch.setenv("AGENT_TASK_LEASE_REAP", "1")
    monkeypatch.delenv("AGENT_TASK_ORPHAN_REAP", raising=False)
    assert atq.lease_reap_enabled() is True
    assert atq.orphan_reap_enabled() is False

    monkeypatch.setenv("AGENT_TASK_ORPHAN_REAP", "1")
    monkeypatch.delenv("AGENT_TASK_LEASE_REAP", raising=False)
    assert atq.orphan_reap_enabled() is True
    assert atq.lease_reap_enabled() is False


# --------------------------------------------------------------------------- #
# routine ledger switch — growth control. begin() stops the LEAK; this stops the
# GROWTH. ~700 rows/day with no prune anywhere = ~255k/year even once correct.
# --------------------------------------------------------------------------- #
def test_routine_ledger_defaults_on(monkeypatch):
    """Turning an existing audit trail off must be an owner decision, never a
    side effect of deploying a bug fix."""
    monkeypatch.delenv("ROUTINE_TASK_LEDGER", raising=False)
    assert atq.routine_ledger_enabled() is True


def test_routine_ledger_can_be_disabled(monkeypatch):
    for off in ("0", "false", "no", "off", "OFF"):
        monkeypatch.setenv("ROUTINE_TASK_LEDGER", off)
        assert atq.routine_ledger_enabled() is False, off


def test_routine_ledger_explicit_on(monkeypatch):
    monkeypatch.setenv("ROUTINE_TASK_LEDGER", "1")
    assert atq.routine_ledger_enabled() is True


# --------------------------------------------------------------------------- #
# reap_orphan_routines — classifier + dry-run + bounded close
# --------------------------------------------------------------------------- #
class _Row:
    def __init__(self, rid, agent_id, goal, status="pending", claimed_at=None, age_h=48):
        self.id = rid
        self.agent_id = agent_id
        self.goal = goal
        self.status = status
        self.claimed_at = claimed_at
        self.completed_at = None
        self.created_at = datetime.utcnow() - timedelta(hours=age_h)
        self.delegated_by = "scheduler"
        self.checkout_version = 0


class _Query:
    def __init__(self, session, rows):
        self.session = session
        self.rows = rows
        self._limit = None

    def filter(self, *_a, **_k):
        return self

    def order_by(self, *_a, **_k):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def all(self):
        return self.rows[: self._limit] if self._limit else self.rows

    def update(self, values, **_k):
        self.session.updates.append(values)
        return 1


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.updates: list[dict] = []
        self.committed = 0

    def query(self, *_a, **_k):
        return _Query(self, self.rows)

    def commit(self):
        self.committed += 1


def _patch_db(monkeypatch, session):
    import contextlib

    import app.models.base as mb

    @contextlib.contextmanager
    def _ctx():
        yield session

    monkeypatch.setattr(mb, "get_db_session", _ctx, raising=False)


def test_dry_run_mutates_nothing(monkeypatch):
    rows = [_Row(f"t{i}", "flow_cron", "Scheduled routine: flow_cron") for i in range(3)]
    sess = _Session(rows)
    _patch_db(monkeypatch, sess)

    out = asyncio.run(atq.reap_orphan_routines(dry_run=True))
    assert out["dry_run"] is True
    assert out["scanned"] == 3
    assert out["cancelled"] == 3, "dry-run reports what it WOULD close"
    assert sess.updates == [], "dry-run must not write"
    assert sess.committed == 0
    assert out["backup"] == "", "no backup file for a dry run"
    assert len(out.get("sample", [])) <= 5


def _patch_backup(monkeypatch, tmp_path):
    """Redirect the REAL writer's store resolution into tmp — keeps the actual
    open()/write path under test instead of stubbing it out."""
    from app.platform import runtime_data_authority as auth

    monkeypatch.setattr(
        auth, "resolve_store_path", lambda **_k: tmp_path / "job_runs.jsonl", raising=False
    )
    return tmp_path


def test_live_run_closes_as_cancelled_not_failed(monkeypatch, tmp_path):
    """`failed` would fabricate an incident history — these routines mostly
    SUCCEEDED; only the ledger row was abandoned."""
    rows = [_Row("t1", "growth", "Scheduled routine: growth")]
    sess = _Session(rows)
    _patch_db(monkeypatch, sess)
    _patch_backup(monkeypatch, tmp_path)

    out = asyncio.run(atq.reap_orphan_routines(dry_run=False))
    assert out["cancelled"] == 1
    assert len(sess.updates) == 1
    assert sess.updates[0]["status"] == "cancelled"
    assert sess.updates[0]["status"] != "failed"
    assert sess.updates[0]["completed_at"] is not None
    assert "orphaned_ledger_row" in sess.updates[0]["result_summary"]


def test_live_run_backs_up_before_mutating(monkeypatch, tmp_path):
    rows = [
        _Row("t1", "ops", "Scheduled routine: ops"),
        _Row("t2", "ops", "Scheduled routine: ops"),
    ]
    sess = _Session(rows)
    _patch_db(monkeypatch, sess)
    _patch_backup(monkeypatch, tmp_path)

    out = asyncio.run(atq.reap_orphan_routines(dry_run=False))
    from pathlib import Path

    bk = Path(out["backup"])
    assert bk.exists(), "the real writer must have created the file"
    assert bk.parent == tmp_path, "backup must land beside the resolved store, not in data/"
    assert len(bk.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_backup_failure_aborts_without_mutating(monkeypatch):
    """A terminal close is not reversible from the row once status is
    overwritten, so losing the backup must stop the sweep, not proceed."""
    rows = [_Row("t1", "ops", "Scheduled routine: ops")]
    sess = _Session(rows)
    _patch_db(monkeypatch, sess)

    def _boom(_rows):
        raise OSError("disk full")

    monkeypatch.setattr(atq, "_write_orphan_backup", _boom)

    out = asyncio.run(atq.reap_orphan_routines(dry_run=False))
    assert "backup_failed" in str(out.get("error", ""))
    assert out["cancelled"] == 0
    assert sess.updates == [], "must not close rows it could not back up"


def test_limit_bounds_the_batch(monkeypatch):
    rows = [_Row(f"t{i}", "flow_cron", "Scheduled routine: flow_cron") for i in range(50)]
    sess = _Session(rows)
    _patch_db(monkeypatch, sess)

    out = asyncio.run(atq.reap_orphan_routines(limit=10, dry_run=True))
    assert out["scanned"] == 10, "batch must respect limit — no unbounded sweep"


def test_empty_scan_is_a_clean_noop(monkeypatch):
    sess = _Session([])
    _patch_db(monkeypatch, sess)
    out = asyncio.run(atq.reap_orphan_routines(dry_run=False))
    assert out["scanned"] == 0 and out["cancelled"] == 0
    assert sess.updates == []


def test_never_raises_on_db_error(monkeypatch):
    import app.models.base as mb

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(mb, "get_db_session", _boom, raising=False)
    out = asyncio.run(atq.reap_orphan_routines(dry_run=False))
    assert "error" in out
    assert out["cancelled"] == 0


def test_reaper_never_requeues(monkeypatch, tmp_path):
    """These rows wrap platform_dial / email_outreach. Re-running one to
    'resolve' it would place real calls or send real email."""
    rows = [_Row("t1", "platform_dial", "Scheduled routine: platform_dial")]
    sess = _Session(rows)
    _patch_db(monkeypatch, sess)
    _patch_backup(monkeypatch, tmp_path)

    asyncio.run(atq.reap_orphan_routines(dry_run=False))
    for upd in sess.updates:
        assert upd["status"] != "pending", "must never return a row to the queue"
        assert "claimed_at" not in upd, "must never re-open a lease"


# --------------------------------------------------------------------------- #
# snapshot tolerates the new terminal status
# --------------------------------------------------------------------------- #
def test_queue_snapshot_seeds_cancelled(monkeypatch):
    class _SnapQuery:
        def group_by(self, *_a):
            return self

        def all(self):
            return [("growth", "cancelled", 5), ("growth", "pending", 1)]

    class _SnapSession:
        def query(self, *_a, **_k):
            return _SnapQuery()

    _patch_db(monkeypatch, _SnapSession())
    snap = asyncio.run(atq.agent_queue_snapshot())
    assert snap["growth"]["cancelled"] == 5
    assert snap["growth"]["pending"] == 1
    assert snap["growth"]["done"] == 0
