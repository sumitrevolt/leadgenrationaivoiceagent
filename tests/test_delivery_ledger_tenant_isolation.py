"""The ledger filename IS the tenant boundary, so it must be guarded.

`delivery_ledger._ledger_path(cid)` interpolated the client id straight into
`data/delivery_ledger/<cid>.jsonl`. Empirically, `cid="../email_suppression"`
resolved to `data/email_suppression.jsonl` — a real compliance store — and
`cid="x/../../secrets"` climbed out of the data root entirely.

That is two distinct bugs, which is why the guard sits in `_ledger_path` and
not only on the write side:

  * WRITE — a tenant's delivery rows land in another store's file.
  * READ  — one tenant's history request returns another store's contents.
            A cross-tenant read leak, forbidden by CLAUDE.md section 5.

The guard REFUSES (raises) rather than coercing. `auto_content._safe_id`
rewrites offending characters instead; that also stops the escape, but files
the rows under a silently different name. For a paying customer's delivery
history, quiet misplacement is the failure mode we are trying to prevent.
"""

from __future__ import annotations

import os

import pytest

from app.marketing import delivery_ledger
from app.platform import runtime_data as rd

GOOD = "jiya-makeover-isolation-test"

#: Shapes observed to escape before the guard, plus the absolute-path variant.
ESCAPES = [
    "../email_suppression",
    "x/../../secrets",
    "..",
    ".",
    "",
    "a/b",
    "a\\b",
    os.path.join(os.sep, "tmp", "absolute"),
]


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(delivery_ledger, "_LEDGER_DIR", lambda: str(tmp_path / "delivery_ledger"))
    monkeypatch.setattr(
        delivery_ledger, "_CONTENT_QUEUE_DIR", lambda: str(tmp_path / "content_queue")
    )
    yield


# --------------------------------------------------------------- path shaping
@pytest.mark.parametrize("cid", ESCAPES)
def test_ledger_path_refuses_ids_that_leave_the_store(cid):
    with pytest.raises(rd.RuntimeDataError):
        delivery_ledger._ledger_path(cid)


@pytest.mark.parametrize("cid", ESCAPES)
def test_marker_path_refuses_the_same_ids(cid):
    """The backfill marker shares the boundary and was guarded separately."""
    with pytest.raises(rd.RuntimeDataError):
        delivery_ledger._marker_path(cid)


def test_ledger_path_stays_inside_its_own_directory(tmp_path):
    resolved = os.path.realpath(delivery_ledger._ledger_path(GOOD))
    store = os.path.realpath(str(tmp_path / "delivery_ledger"))
    assert os.path.dirname(resolved) == store


# ---------------------------------------------------------------- read leak
def test_read_does_not_return_another_stores_contents(tmp_path):
    """The regression that made this a leak rather than a mishap."""
    victim = tmp_path / "email_suppression.jsonl"
    victim.write_text('{"event":"post_published","phone":"+919000011122"}\n', encoding="utf-8")

    with pytest.raises(rd.RuntimeDataError):
        delivery_ledger._read_events("../email_suppression")

    assert victim.read_text(encoding="utf-8").count("\n") == 1, "victim file must be untouched"


# ---------------------------------------------------------------- write leak
def test_write_refuses_and_creates_nothing_outside_the_store(tmp_path):
    assert delivery_ledger.log_event("../email_suppression", "post_published", detail="x") is False
    assert not (tmp_path / "email_suppression.jsonl").exists()


# --------------------------------------------------------------- anti-vacuity
def test_an_ordinary_client_id_still_reads_and_writes():
    """Without this the guard could simply refuse everything and still pass."""
    assert delivery_ledger.log_event(GOOD, "post_published", detail="hello") is True
    events = delivery_ledger._read_events(GOOD)
    assert [e["event"] for e in events] == ["post_published"]


def test_dots_inside_an_id_are_allowed():
    """`v1.2` is a legal id; the guard must reject traversal, not punctuation."""
    cid = "client.v1.2"
    assert delivery_ledger.log_event(cid, "post_published", detail="ok") is True
    assert len(delivery_ledger._read_events(cid)) == 1
