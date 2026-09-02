"""Customer Delivery OS — wires the mission's last 3 ledger event types:
post_approved / post_published / post_failed. Three independent call sites:

  1. auto_content.mark_item() — admin's manual Approve/Posted buttons (clients.html)
  2. content_approval._decide() — customer's own portal-based approve (fresh
     queue item via enqueue_approved, doesn't go through mark_item)
  3. social_engine.engine.process_queue() — dormant automated publish path
     (SOCIAL_ENGINE flag, currently gated off in prod); published->post_published,
     retries-exhausted ("dead")->post_failed.

Each site is hermetic (tmp-path file redirection or monkeypatched log_event),
mirrors this project's existing fixture conventions (tests/test_clients.py's
tmp_store, tests/test_social_engine.py's iso)."""

from __future__ import annotations

import asyncio
import os

import pytest

from app.marketing import auto_content, clients_store, content_approval


@pytest.fixture
def tmp_store(monkeypatch, tmp_path):
    """clients_store + auto_content file paths -> tmp_path (mirrors test_clients.py)."""
    clients_file = os.path.join(str(tmp_path), "marketing_clients.jsonl")
    queue_dir = os.path.join(str(tmp_path), "content_queue")
    monkeypatch.setattr(clients_store, "_CLIENTS_FILE", lambda: clients_file)
    monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: queue_dir)
    return tmp_path


@pytest.fixture
def logged_events(monkeypatch):
    """Capture every delivery_ledger.log_event call across all 3 modules
    (each does a local `from app.marketing import delivery_ledger` import, so
    patch the shared source module directly)."""
    calls = []

    def _fake_log_event(client_id, event, **kw):
        calls.append((client_id, event, kw.get("detail", "")))
        return True

    from app.marketing import delivery_ledger

    monkeypatch.setattr(delivery_ledger, "log_event", _fake_log_event)
    return calls


def _make_item(client_id, tmp_store):
    """One real queue item via _append_items (mirrors test_clients.py pattern)."""
    item = {
        "id": "item-1",
        "client_id": client_id,
        "date": "2026-07-07",
        "type": "post",
        "title": "Diwali Offer Post",
        "caption": "Diwali dhamaka offer!",
        "hashtags": ["#diwali"],
        "status": "draft",
        "created_at": "2026-07-07T00:00:00Z",
    }
    auto_content._append_items(client_id, [item])
    return item


class TestMarkItemLedgerWiring:
    def test_mark_approved_logs_post_approved(self, tmp_store, logged_events):
        rec = clients_store.add_client("Mark Approve Biz", "general", phone="9000000031")
        _make_item(rec["id"], tmp_store)

        assert auto_content.mark_item(rec["id"], "item-1", "approved") is True

        assert (rec["id"], "post_approved", "Diwali Offer Post") in logged_events

    def test_mark_posted_logs_post_published(self, tmp_store, logged_events):
        rec = clients_store.add_client("Mark Posted Biz", "general", phone="9000000032")
        _make_item(rec["id"], tmp_store)

        assert auto_content.mark_item(rec["id"], "item-1", "posted") is True

        assert (rec["id"], "post_published", "Diwali Offer Post") in logged_events

    def test_mark_draft_and_skipped_do_not_log(self, tmp_store, logged_events):
        """draft/skipped are intentionally NOT delivery-ledger events — drafts
        already fire post_draft_created elsewhere; skip is a deliberate no-op."""
        rec = clients_store.add_client("Mark Skip Biz", "general", phone="9000000033")
        _make_item(rec["id"], tmp_store)
        logged_events.clear()  # drop add_client's own customer_created log

        auto_content.mark_item(rec["id"], "item-1", "skipped")
        assert logged_events == []

    def test_mark_item_failure_never_raises_even_if_ledger_throws(self, tmp_store, monkeypatch):
        """Ledger log_event raising must not break the real status update."""
        rec = clients_store.add_client("Mark Robust Biz", "general", phone="9000000034")
        _make_item(rec["id"], tmp_store)

        from app.marketing import delivery_ledger

        def _boom(*a, **kw):
            raise RuntimeError("ledger down")

        monkeypatch.setattr(delivery_ledger, "log_event", _boom)

        assert auto_content.mark_item(rec["id"], "item-1", "approved") is True
        approved = auto_content.list_queue(rec["id"], status="approved")
        assert any(it["id"] == "item-1" for it in approved)


class TestContentApprovalLedgerWiring:
    def test_customer_portal_approve_logs_post_approved(self, tmp_path, monkeypatch, logged_events):
        monkeypatch.setattr(
            content_approval,
            "_FILE",
            lambda: os.path.join(str(tmp_path), "content_approvals.jsonl"),
        )
        # enqueue_approved touches the real client queue file too — redirect it.
        monkeypatch.setattr(
            auto_content, "_QUEUE_DIR", lambda: os.path.join(str(tmp_path), "content_queue")
        )

        sub = content_approval.submit(
            "c-portal-1", {"title": "Holi Special", "caption": "Holi hai!"}
        )
        assert sub["ok"] is True
        token = sub["approval"]["token"]

        result = content_approval.approve(token)

        assert result["ok"] is True
        assert ("c-portal-1", "post_approved", "Holi Special") in logged_events

    def test_customer_portal_reject_does_not_log_post_approved(
        self, tmp_path, monkeypatch, logged_events
    ):
        monkeypatch.setattr(
            content_approval,
            "_FILE",
            lambda: os.path.join(str(tmp_path), "content_approvals.jsonl"),
        )
        monkeypatch.setattr(
            auto_content, "_QUEUE_DIR", lambda: os.path.join(str(tmp_path), "content_queue")
        )

        sub = content_approval.submit("c-portal-2", {"title": "Rejected Post"})
        token = sub["approval"]["token"]

        content_approval.reject(token, note="not this one")

        assert logged_events == []

    def test_double_decide_is_idempotent_and_does_not_double_log(
        self, tmp_path, monkeypatch, logged_events
    ):
        monkeypatch.setattr(
            content_approval,
            "_FILE",
            lambda: os.path.join(str(tmp_path), "content_approvals.jsonl"),
        )
        monkeypatch.setattr(
            auto_content, "_QUEUE_DIR", lambda: os.path.join(str(tmp_path), "content_queue")
        )

        sub = content_approval.submit("c-portal-3", {"title": "Once Only"})
        token = sub["approval"]["token"]

        content_approval.approve(token)
        content_approval.approve(token)  # already decided -> short-circuits

        assert len([c for c in logged_events if c[1] == "post_approved"]) == 1


class TestSocialEngineLedgerWiring:
    """Dormant path (SOCIAL_ENGINE flag) — mirrors tests/test_social_engine.py's
    `iso` fixture so this stays consistent with the established test style there."""

    @pytest.fixture
    def iso(self, monkeypatch, tmp_path):
        from app.social_engine import engine, store, vault
        from app.social_engine.base import PublishResult, SocialProvider

        class _Fake(SocialProvider):
            name = "fake"

            def configured(self, account=None):
                return True

            async def publish(self, req, account):
                return PublishResult(ok=True, platform="fake", post_id="P-1")

        class _AlwaysFail(SocialProvider):
            name = "failer"

            def configured(self, account=None):
                return True

            async def publish(self, req, account):
                return PublishResult(ok=False, platform="failer", error="rate_limited")

        monkeypatch.setattr(store, "_PATH", str(tmp_path / "jobs.jsonl"))
        monkeypatch.setattr(vault, "_PATH", str(tmp_path / "tokens.jsonl"))
        monkeypatch.setattr(store, "_mirror", lambda job: None)
        monkeypatch.setattr(store, "max_attempts", lambda: 1)  # first failure -> dead immediately
        monkeypatch.setattr(engine, "_REGISTRY", {"fake": _Fake(), "failer": _AlwaysFail()})
        monkeypatch.setenv("SOCIAL_ENGINE", "1")
        monkeypatch.delenv("SOCIAL_TOKEN_KEY", raising=False)
        return engine

    def test_published_job_logs_post_published(self, iso, logged_events):
        iso.enqueue_publish("c-social-1", caption="hi", platforms=["fake"])
        out = asyncio.run(iso.process_queue())

        assert out["published"] == 1
        assert ("c-social-1", "post_published", "hi") in logged_events

    def test_dead_job_logs_post_failed(self, iso, logged_events):
        iso.enqueue_publish("c-social-2", caption="hi", platforms=["failer"])
        out = asyncio.run(iso.process_queue())

        assert out["dead"] == 1
        matches = [c for c in logged_events if c[0] == "c-social-2" and c[1] == "post_failed"]
        assert len(matches) == 1
        assert "rate_limited" in matches[0][2]

    def test_inert_provider_skip_does_not_log(self, iso, logged_events):
        """Provider-not-configured is a system/config gap, not a per-post
        failure — deliberately not logged as post_failed (scope discipline)."""
        from app.social_engine import engine

        class _Inert:
            name = "inert"

            def configured(self, account=None):
                return False

            async def publish(self, req, account):
                from app.social_engine.base import PublishResult

                return PublishResult(ok=False, platform="inert", error="__inert__")

        engine._REGISTRY["inert"] = _Inert()
        iso.enqueue_publish("c-social-3", caption="hi", platforms=["inert"])
        out = asyncio.run(iso.process_queue())

        assert out["skipped"] == 1
        assert not [event for event in logged_events if event[1] == "post_failed"]
