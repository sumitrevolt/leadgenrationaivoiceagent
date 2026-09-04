"""Tests for the WhatsApp pending-drafts inbox (the human-send queue).

Why this exists: `_record_block` counted every gate-denied send but threw the
would-send away. 1829 real customer intents produced a counter and nothing clickable
— no queue, and the count was lost on restart. `auto_send_blocked` now persists the
draft; these tests pin that contract.

The most important property here is #6: persistence sits on a hot outbound path, so a
storage failure must leave `auto_send_blocked`'s return value byte-for-byte identical.
An operator with auto-send off must never see a different payload because a disk write
failed.

Also pinned: the caller contract. `auto_send_blocked` carries an `error` key ON PURPOSE
— every caller detects success with `bool(res) and not res.get("error")`, so persisting
must not disturb that shape.

No network, no provider. The store path is redirected to tmp so `data/` is never
touched.
"""

import itertools

import pytest
from fastapi.testclient import TestClient

from app.integrations import whatsapp as wa

TO = "9000000000"  # 10 digits -> normalised to 919000000000


@pytest.fixture(autouse=True)
def draft_store(monkeypatch, tmp_path):
    """Redirect the draft store so the real data/ is never written."""
    p = tmp_path / "wa_drafts.jsonl"
    monkeypatch.setattr(wa, "_drafts_path", lambda: str(p))
    return p


@pytest.fixture
def clock(monkeypatch):
    """Deterministic, monotonic timestamps so 'newest' is unambiguous."""
    ticks = itertools.count()

    def _install():
        monkeypatch.setattr(wa, "_now_iso", lambda: f"2026-09-04T00:00:{next(ticks):06d}+00:00")

    return _install


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def _block(i: int = 0, msg: str | None = None, reason: str = "auto_send_disabled"):
    return wa.auto_send_blocked(f"90000000{i:02d}", msg if msg is not None else f"hello {i}", reason)


# --------------------------------------------------------------------------- #
# 1. A blocked send persists a draft and keeps the caller contract
# --------------------------------------------------------------------------- #
def test_blocked_send_persists_a_draft_and_keeps_the_caller_contract(draft_store):
    res = wa.auto_send_blocked(TO, "Hello Jiya")

    # The caller contract is untouched — callers branch on `not res.get("error")`.
    assert res["error"] == "auto_send_disabled"
    assert res["status"] == "blocked"
    assert res["mode"] == "link"
    assert res["would_send"] is True
    assert res["link"] == "https://wa.me/919000000000?text=Hello%20Jiya"
    assert set(res) == {"error", "status", "mode", "would_send", "link"}

    rows = wa.list_pending_drafts(50)
    assert len(rows) == 1
    row = rows[0]
    assert row["to"] == "919000000000"
    assert row["message"] == "Hello Jiya"
    assert row["link"] == res["link"]
    assert row["reason"] == "auto_send_disabled"
    assert row["sent"] is False
    assert row["sent_ts"] is None
    assert len(row["id"]) == 12
    assert wa.pending_drafts_count() == 1


def test_long_message_is_truncated_to_2000(draft_store):
    wa.auto_send_blocked(TO, "x" * 5000)

    row = wa.list_pending_drafts(50)[0]
    assert len(row["message"]) == 2000, "an unbounded message body must not reach the store"


# --------------------------------------------------------------------------- #
# 2. Dedupe — repeats must not bury the operator
# --------------------------------------------------------------------------- #
def test_duplicate_number_and_message_does_not_create_a_second_pending_row(draft_store):
    _block(0, "same message")
    _block(0, "same message")
    _block(0, "same message")

    rows = wa.list_pending_drafts(50)
    assert len(rows) == 1, "the hourly job repeats the same message and must not pile up"
    assert wa.pending_drafts_count() == 1


def test_different_message_to_the_same_number_is_a_separate_draft(draft_store):
    _block(0, "first")
    _block(0, "second")

    assert len(wa.list_pending_drafts(50)) == 2


def test_same_message_to_a_different_number_is_a_separate_draft(draft_store):
    _block(0, "same")
    _block(1, "same")

    assert len(wa.list_pending_drafts(50)) == 2


def test_a_repeat_refreshes_the_latest_gate_reason(draft_store):
    """Safety property, not bookkeeping: if a number later blocks as `opted_out`,
    the row must not keep advertising the older `auto_send_disabled` reason — a
    human reading the queue would otherwise message someone who opted out."""
    _block(0, "ping", reason="auto_send_disabled")
    _block(0, "ping", reason="opted_out")

    rows = wa.list_pending_drafts(50)
    assert len(rows) == 1
    assert rows[0]["reason"] == "opted_out"


# --------------------------------------------------------------------------- #
# 3. Cap
# --------------------------------------------------------------------------- #
def test_cap_keeps_only_the_newest_pending_rows(draft_store, clock, monkeypatch):
    monkeypatch.setenv("WHATSAPP_DRAFT_CAP", "3")
    clock()

    for i in range(5):
        _block(i)

    rows = wa.list_pending_drafts(50)
    assert len(rows) == 3, "oldest beyond the cap are dropped"
    assert [r["to"] for r in rows] == [
        "919000000004",
        "919000000003",
        "919000000002",
    ], "newest first, oldest two dropped"


def test_cap_defaults_to_500_when_unset_or_garbage(draft_store, monkeypatch):
    for value, expected in (("", 500), ("not-a-number", 500), ("0", 1), ("-5", 1), ("99999", 5000)):
        monkeypatch.setenv("WHATSAPP_DRAFT_CAP", value)
        assert wa.draft_cap() == expected, f"WHATSAPP_DRAFT_CAP={value!r}"


# --------------------------------------------------------------------------- #
# 4. Mark sent — idempotent, leaves the pending list
# --------------------------------------------------------------------------- #
def test_mark_sent_is_idempotent_and_the_draft_leaves_pending(draft_store):
    _block(0, "ping")
    did = wa.list_pending_drafts(50)[0]["id"]

    first = wa.mark_draft_sent(did)
    assert first["sent"] is True
    assert first["already"] is False
    assert wa.list_pending_drafts(50) == [], "a sent draft is no longer in the queue"
    assert wa.pending_drafts_count() == 0

    second = wa.mark_draft_sent(did)
    assert second["sent"] is True
    assert second["already"] is True, "re-marking must be a no-op, not an error"
    assert wa.pending_drafts_count() == 0


def test_mark_sent_on_an_unknown_id_returns_none(draft_store):
    assert wa.mark_draft_sent("does-not-exist") is None
    assert wa.mark_draft_sent("") is None


# --------------------------------------------------------------------------- #
# 5. Dismiss
# --------------------------------------------------------------------------- #
def test_dismiss_removes_it_from_pending(draft_store):
    _block(0, "ping")
    did = wa.list_pending_drafts(50)[0]["id"]

    assert wa.dismiss_draft(did) is True
    assert wa.list_pending_drafts(50) == []
    assert wa.pending_drafts_count() == 0
    assert wa.dismiss_draft(did) is False, "gone -> the route answers 404"


def test_dismiss_leaves_other_drafts_alone(draft_store):
    _block(0, "keep me")
    _block(1, "drop me")
    rows = wa.list_pending_drafts(50)
    victim = next(r["id"] for r in rows if r["message"] == "drop me")

    assert wa.dismiss_draft(victim) is True
    assert [r["message"] for r in wa.list_pending_drafts(50)] == ["keep me"]


# --------------------------------------------------------------------------- #
# 6. THE IMPORTANT ONE — storage failure must not break the send path
# --------------------------------------------------------------------------- #
def test_storage_failure_does_not_break_auto_send_blocked(draft_store, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(wa, "_persist_pending_draft", boom)

    res = wa.auto_send_blocked(TO, "Hello Jiya")

    assert res == {
        "error": "auto_send_disabled",
        "status": "blocked",
        "mode": "link",
        "would_send": True,
        "link": "https://wa.me/919000000000?text=Hello%20Jiya",
    }, "a failed write must leave the send-path payload byte-for-byte identical"


def test_low_level_write_failure_is_swallowed_by_the_persister(draft_store, monkeypatch):
    def boom(*_a, **_k):
        raise OSError("read-only filesystem")

    monkeypatch.setattr(wa, "_write_drafts_locked", boom)

    assert wa._persist_pending_draft(
        {"id": "a" * 12, "ts": wa._now_iso(), "to": TO, "message": "m", "link": "l",
         "reason": "r", "sent": False, "sent_ts": None}
    ) is False

    res = wa.auto_send_blocked(TO, "Hello Jiya")
    assert res["error"] == "auto_send_disabled"
    assert res["link"].startswith("https://wa.me/")


def test_a_corrupt_store_reads_as_drafts_not_as_a_crash(draft_store):
    draft_store.write_text("not json\n{}\n", encoding="utf-8")

    assert wa.list_pending_drafts(50) == []
    assert wa.pending_drafts_count() == 0
    assert wa.auto_send_blocked(TO, "hi")["error"] == "auto_send_disabled"


# --------------------------------------------------------------------------- #
# 7. Auth
# --------------------------------------------------------------------------- #
def test_drafts_requires_an_admin_jwt(client):
    """conftest installs global require_admin and get_current_user overrides for every test,
    so both overrides have to be removed for this to exercise real unauthenticated requests."""
    from app.api.auth_deps import get_current_user, require_admin
    from app.main import app

    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(get_current_user, None)

    r = client.get("/api/wa/drafts")
    assert r.status_code in (401, 403), r.text


def test_mark_sent_requires_an_admin_jwt(client, draft_store):
    from app.api.auth_deps import get_current_user, require_admin
    from app.main import app

    _block(0, "ping")
    did = wa.list_pending_drafts(50)[0]["id"]
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(get_current_user, None)

    r = client.post(f"/api/wa/drafts/{did}/sent")
    assert r.status_code in (401, 403), r.text


# --------------------------------------------------------------------------- #
# 8. Route surface
# --------------------------------------------------------------------------- #
def test_status_includes_pending_drafts(client, draft_store):
    _block(0, "one")
    _block(1, "two")

    r = client.get("/api/wa/status")
    assert r.status_code == 200
    assert r.json()["pending_drafts"] == 2, "backlog size must be visible at a glance"


def test_drafts_route_lists_pending_newest_first(client, draft_store, clock):
    clock()
    _block(0, "first")
    _block(1, "second")

    r = client.get("/api/wa/drafts")
    assert r.status_code == 200
    body = r.json()
    assert [d["message"] for d in body["drafts"]] == ["second", "first"]
    assert body["total_pending"] == 2
    assert body["cap"] == 500
    assert body["limit"] == 50


def test_drafts_limit_is_clamped(client, draft_store, clock):
    clock()
    for i in range(5):
        _block(i)

    assert len(client.get("/api/wa/drafts?limit=2").json()["drafts"]) == 2
    assert len(client.get("/api/wa/drafts?limit=0").json()["drafts"]) == 1, "0 clamps up to 1"
    assert len(client.get("/api/wa/drafts?limit=9999").json()["drafts"]) == 5, "capped at count"
    assert client.get("/api/wa/drafts?limit=9999").json()["limit"] == 500


def test_mark_sent_route_is_idempotent_and_404s_on_unknown_id(client, draft_store):
    _block(0, "ping")
    did = wa.list_pending_drafts(50)[0]["id"]

    first = client.post(f"/api/wa/drafts/{did}/sent")
    assert first.status_code == 200
    assert first.json() == {"ok": True, "id": did, "sent": True, "already": False}

    again = client.post(f"/api/wa/drafts/{did}/sent")
    assert again.status_code == 200, "idempotent — the operator may double-click"
    assert again.json()["already"] is True

    assert client.post("/api/wa/drafts/nope/sent").status_code == 404


def test_dismiss_route_removes_and_404s_afterwards(client, draft_store):
    _block(0, "ping")
    did = wa.list_pending_drafts(50)[0]["id"]

    assert client.post(f"/api/wa/drafts/{did}/dismiss").status_code == 200
    assert client.get("/api/wa/drafts").json()["total_pending"] == 0
    assert client.post(f"/api/wa/drafts/{did}/dismiss").status_code == 404
