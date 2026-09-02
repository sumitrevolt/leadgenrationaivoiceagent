"""Un-actionable approvals get retired; live ones get a queue-aware nudge.

Prod evidence 2026-08-09: `content_approval.pending()` held **422** rows.
- 321 belonged to client ids absent from `clients_store` — nobody can ever
  decide them, yet they inflated every backlog number.
- 101 belonged to live clients and were still perfectly completable from the
  authenticated dashboard (which does NOT enforce the 7-day token TTL; only the
  public token link does).
- The single paying customer had received **36** approval mails, all delivered,
  and still had 20 items open — each mail said "you have content awaiting your
  approval" and never "you have 20 waiting, oldest 17 days".

So: retire the orphans (never the live ones, never by approving), and make the
mails that already go out carry the state of the queue.
"""

from __future__ import annotations

import json

import pytest

from app.marketing import content_approval
from app.platform import approval_notifier


@pytest.fixture
def _store(tmp_path, monkeypatch):
    path = tmp_path / "content_approvals.jsonl"
    monkeypatch.setattr(content_approval, "_FILE", lambda: str(path))
    return path


def _write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _row(rid, cid, status="pending", created="2026-07-01T00:00:00"):
    return {"id": rid, "client_id": cid, "status": status, "created_at": created}


# ------------------------------- retirement --------------------------------- #
def test_dry_run_reports_but_writes_nothing(_store):
    _write(_store, [_row("a", "dead-1"), _row("b", "dead-2"), _row("c", "live-1")])
    before = _store.read_text(encoding="utf-8")

    out = content_approval.retire_orphaned_pending(dry_run=True, live_client_ids={"live-1"})

    assert out["ok"] and out["dry_run"] is True
    assert out["retired"] == 2
    assert out["skipped_live"] == 1
    assert _store.read_text(encoding="utf-8") == before, "dry run must not touch the store"
    assert len(content_approval.pending()) == 3


def test_retires_only_orphans_and_never_deletes(_store):
    _write(_store, [_row("a", "dead-1"), _row("c", "live-1")])

    out = content_approval.retire_orphaned_pending(dry_run=False, live_client_ids={"live-1"})
    assert out["retired"] == 1

    still_pending = {r["id"] for r in content_approval.pending()}
    assert still_pending == {"c"}, "the live client's work must survive untouched"

    # Append-only: the original submission line is still readable.
    lines = [json.loads(x) for x in _store.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert sum(1 for x in lines if x["id"] == "a") == 2
    terminal = [x for x in lines if x["id"] == "a"][-1]
    assert terminal["status"] == content_approval.STATUS_EXPIRED
    assert terminal["retired_reason"] == "client_no_longer_exists"


def test_retiring_is_not_approving(_store):
    """A retired row must never read as consent to publish."""
    _write(_store, [_row("a", "dead-1")])
    content_approval.retire_orphaned_pending(dry_run=False, live_client_ids={"live-1"})

    lines = [json.loads(x) for x in _store.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert all(x.get("status") != "approved" for x in lines)
    assert lines[-1]["decided_by"].startswith("system:")


def test_live_client_work_is_never_retired_however_old(_store):
    """Age is not the criterion — a live customer can still complete these from
    the dashboard, so retiring them would delete real work."""
    _write(_store, [_row("old", "live-1", created="2020-01-01T00:00:00")])
    out = content_approval.retire_orphaned_pending(dry_run=False, live_client_ids={"live-1"})
    assert out["retired"] == 0
    assert len(content_approval.pending()) == 1


def test_unresolvable_client_list_refuses_rather_than_retiring_everything(_store, monkeypatch):
    """Fail-closed: an empty client set must not mean 'every client is dead'."""
    _write(_store, [_row("a", "c1"), _row("b", "c2")])
    import app.marketing.clients_store as cs

    monkeypatch.setattr(cs, "list_clients", lambda *a, **k: [])
    out = content_approval.retire_orphaned_pending(dry_run=False)
    assert out["ok"] is False
    assert out["error"] == "no_live_clients_resolved"
    assert len(content_approval.pending()) == 2


def test_retired_rows_leave_the_backlog_counters(_store):
    _write(_store, [_row("a", "dead-1"), _row("b", "dead-1"), _row("c", "live-1")])
    content_approval.retire_orphaned_pending(dry_run=False, live_client_ids={"live-1"})
    assert len(content_approval.pending("dead-1")) == 0
    assert len(content_approval.pending("live-1")) == 1


# --------------------------- queue-aware nudge ------------------------------ #
def test_single_item_keeps_the_original_wording():
    phrase = approval_notifier._backlog_phrase({"count": 1, "oldest_days": 0})
    assert phrase == "You have content awaiting your approval."


def test_backlog_states_the_count_and_age():
    phrase = approval_notifier._backlog_phrase({"count": 20, "oldest_days": 17})
    assert "20 items" in phrase
    assert "17 days" in phrase


def test_fresh_backlog_states_count_without_nagging_about_age():
    phrase = approval_notifier._backlog_phrase({"count": 3, "oldest_days": 0})
    assert "3 items" in phrase
    assert "days" not in phrase


def test_link_survives_in_both_bodies():
    b = {"count": 20, "oldest_days": 17}
    assert "https://x/y" in approval_notifier._backlog_text(b, "https://x/y")
    assert 'href="https://x/y"' in approval_notifier._backlog_html(b, "https://x/y")


def test_unreadable_store_degrades_to_singular_not_a_crash(monkeypatch):
    import app.marketing.content_approval as ca

    def _boom(client_id=""):
        raise RuntimeError("store unreadable")

    monkeypatch.setattr(ca, "pending", _boom)
    backlog = approval_notifier._client_backlog("c1")
    assert backlog == {"count": 0, "oldest_days": 0}
    assert approval_notifier._backlog_phrase(backlog).startswith("You have content")


def test_backlog_is_scoped_to_the_one_client(_store):
    _write(_store, [_row("a", "c1"), _row("b", "c1"), _row("c", "other")])
    assert approval_notifier._client_backlog("c1")["count"] == 2
    assert approval_notifier._client_backlog("other")["count"] == 1
