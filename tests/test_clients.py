"""
Tests: marketing clients_store + auto_content engine (per-client social media).
================================================================================

No network — post_generator.free_ai.chat monkeypatched to ("","") so every
content piece exercises the TEMPLATE fallback (never-empty guarantee). File
paths are redirected to tmp_path via _CLIENTS_FILE (module-level) and
auto_content._QUEUE_DIR (call-time resolver) so tests never touch the real data/ dir.
"""

import os
from datetime import date

import pytest

from app.marketing import auto_content, clients_store, post_generator


@pytest.fixture
def no_llm(monkeypatch):
    """free_ai.chat ko ("","") force karo — har content piece template path se."""

    async def _empty(*args, **kwargs):
        return "", ""

    if post_generator.free_ai is not None:
        monkeypatch.setattr(post_generator.free_ai, "chat", _empty)


@pytest.fixture
def tmp_store(monkeypatch, tmp_path):
    """clients_store + auto_content ke file paths tmp_path pe redirect."""
    clients_file = os.path.join(str(tmp_path), "marketing_clients.jsonl")
    queue_dir = os.path.join(str(tmp_path), "content_queue")
    brand_dir = os.path.join(str(tmp_path), "brand_kits")
    monkeypatch.setattr(clients_store, "_CLIENTS_FILE", lambda: clients_file)
    monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: queue_dir)
    # brand_kit mirror bhi tmp me rahe (real data dir na chhue)
    try:
        from app.marketing import brand_kit

        monkeypatch.setattr(brand_kit, "_BRAND_DIR", brand_dir)
    except Exception:
        pass
    return tmp_path


# --------------------------------------------------------------------------- #
# clients_store
# --------------------------------------------------------------------------- #


class TestClientsStore:
    def test_add_list_get_roundtrip(self, tmp_store):
        rec = clients_store.add_client(
            "Sharma Solar",
            niche="solar_residential",
            city="Pune",
            phone="+919876543210",
            plan="growth",
            brand={"primary": "#0b5fff", "accent": "#ffce00", "tagline": "Go Solar"},
            socials={"instagram": "sharma_solar"},
        )
        assert rec.get("id")
        assert rec["business_name"] == "Sharma Solar"
        assert rec["status"] == "active"
        assert rec["brand"]["primary"] == "#0b5fff"
        assert rec["socials"]["instagram"] == "sharma_solar"

        listed = clients_store.list_clients()
        assert any(c["id"] == rec["id"] for c in listed)

        got = clients_store.get_client(rec["id"])
        assert got is not None and got["id"] == rec["id"]
        assert clients_store.get_client("nope-missing") is None

    def test_dedupe_by_phone(self, tmp_store):
        a = clients_store.add_client("Biz A", "general", phone="+91 98765 43210")
        b = clients_store.add_client("Biz A Renamed", "general", phone="9876543210")
        # Same last-10 digits => same record, no duplicate
        assert a["id"] == b["id"]
        assert len(clients_store.list_clients()) == 1

    def test_set_status_and_filter(self, tmp_store):
        rec = clients_store.add_client("Paused Co", "general", phone="9000000001")
        assert clients_store.set_status(rec["id"], "paused") is True
        assert clients_store.set_status("missing-id", "paused") is False
        assert clients_store.list_clients("active") == []
        paused = clients_store.list_clients("paused")
        assert len(paused) == 1 and paused[0]["id"] == rec["id"]

    def test_update_client(self, tmp_store):
        rec = clients_store.add_client("Old Name", "general", phone="9000000002")
        upd = clients_store.update_client(rec["id"], city="Mumbai", niche="real_estate")
        assert upd is not None
        assert upd["city"] == "Mumbai"
        assert upd["niche"] == "real_estate"
        assert clients_store.update_client("nope", city="X") is None

    def test_update_client_persists_approval_notification_contact_and_preferences(self, tmp_store):
        rec = clients_store.add_client("Approval Client", "beauty", phone="9000000003")
        upd = clients_store.update_client(
            rec["id"],
            contact_email="owner@example.com",
            email_notifications=True,
            approval_email_opt_out=False,
        )

        assert upd is not None
        assert upd["contact_email"] == "owner@example.com"
        assert upd["email_notifications"] is True
        assert upd["approval_email_opt_out"] is False
        stored = clients_store.get_client(rec["id"])
        assert stored is not None and stored["contact_email"] == "owner@example.com"

    def test_update_client_persists_billing_identity_aliases_as_a_list(self, tmp_store):
        rec = clients_store.add_client("Recreated Customer", "beauty", phone="9000000004")
        upd = clients_store.update_client(
            rec["id"],
            billing_client_ids=[" old-client-id ", "old-client-id", ""],
        )

        assert upd is not None
        assert upd["billing_client_ids"] == ["old-client-id"]
        assert clients_store.get_client(rec["id"])["billing_client_ids"] == ["old-client-id"]


# --------------------------------------------------------------------------- #
# auto_content.generate_for_client
# --------------------------------------------------------------------------- #


class TestGenerateForClient:
    @pytest.mark.asyncio
    async def test_returns_items_with_required_keys(self, no_llm, tmp_store):
        client = clients_store.add_client(
            "Test Biz",
            "solar_residential",
            phone="9000000010",
            brand={"primary": "#0b5fff"},
        )
        items = await auto_content.generate_for_client(client)
        assert isinstance(items, list) and len(items) >= 1
        for it in items:
            assert it["id"]
            assert it["client_id"] == client["id"]
            assert it["date"]  # YYYY-MM-DD
            assert it["type"] in ("post", "poster", "reel", "festival")
            assert it["status"] == "draft"
            assert it["created_at"]
            if it["type"] in ("poster", "festival") and "svg" in it:
                # poster items have svg (may be empty if posters missing, but key present)
                assert isinstance(it["svg"], str)
            else:
                assert it["caption"].strip()

    @pytest.mark.asyncio
    async def test_poster_day_and_festival_bonus(self, no_llm, tmp_store, monkeypatch):
        # Force Wednesday (poster day) + a festival exactly 1 day away.
        monkeypatch.setattr(
            auto_content.festivals,
            "upcoming",
            lambda days=2: [
                {
                    "date": "2026-06-11",  # within 2 days of day=2026-06-10
                    "name": "Diwali",
                    "type": "hindu",
                    "marketing_angle": "x",
                    "days_away": 1,
                }
            ],
        )
        client = clients_store.add_client("Fest Biz", "general", phone="9000000011")
        items = await auto_content.generate_for_client(client, day=date(2026, 6, 10))  # Wed
        types = [it["type"] for it in items]
        assert "poster" in types  # Wednesday main item
        assert "festival" in types  # festival bonus (post + poster both 'festival'/'poster')
        # festival greeting post present
        assert any(it["type"] == "festival" for it in items)


# --------------------------------------------------------------------------- #
# auto_content.run_daily_content + mark_item
# --------------------------------------------------------------------------- #


class TestRunDailyContent:
    @pytest.mark.asyncio
    async def test_run_daily_content_generates_items(self, no_llm, tmp_store):
        clients_store.add_client("Active Biz", "real_estate", phone="9000000020")
        result = await auto_content.run_daily_content()
        assert result["clients"] >= 1
        assert result["items"] > 0

    @pytest.mark.asyncio
    async def test_run_daily_content_dedupes_same_day(self, no_llm, tmp_store, monkeypatch):
        monkeypatch.setattr(auto_content, "AUTO_SEED_SELF", False, raising=False)
        rec = clients_store.add_client("Dedup Biz", "general", phone="9000000021")
        first = await auto_content.run_daily_content()
        assert first["items"] > 0
        # Same-day re-run => 0 new items (date+type dedupe)
        second = await auto_content.run_daily_content()
        assert second["items"] == 0
        # Queue still holds the original items
        queue = auto_content.list_queue(rec["id"])
        assert len(queue) == first["items"]

    @pytest.mark.asyncio
    async def test_run_daily_content_no_clients(self, no_llm, tmp_store, monkeypatch):
        # self-brand auto-seed off => pure empty-loop behaviour
        monkeypatch.setattr(auto_content, "AUTO_SEED_SELF", False, raising=False)
        result = await auto_content.run_daily_content()
        assert result == {"clients": 0, "items": 0}

    @pytest.mark.asyncio
    async def test_mark_item_status_change(self, no_llm, tmp_store):
        rec = clients_store.add_client("Mark Biz", "general", phone="9000000022")
        items = await auto_content.generate_for_client(rec)
        auto_content._append_items(rec["id"], items)
        target = items[0]["id"]

        assert auto_content.mark_item(rec["id"], target, "approved") is True
        approved = auto_content.list_queue(rec["id"], status="approved")
        assert any(it["id"] == target for it in approved)

        assert auto_content.mark_item(rec["id"], target, "posted") is True
        # invalid status / missing item => False
        assert auto_content.mark_item(rec["id"], target, "bogus") is False
        assert auto_content.mark_item(rec["id"], "missing-item", "posted") is False
