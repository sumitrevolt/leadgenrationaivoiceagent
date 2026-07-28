"""
Tests: referral_kit + evergreen (last 2 free-buildable marketing features).

No network — free_ai.chat is monkeypatched to ("","") so every path exercises
the deterministic TEMPLATE / never-empty fallback. File path resolvers (_REFERRALS_FILE, auto_content._QUEUE_DIR) tmp_path pe redirect
hote hain — real data/ na chhue.
"""

import json
import os

import pytest

from app.marketing import auto_content, evergreen, referral_kit


@pytest.fixture
def no_llm(monkeypatch):
    """free_ai.chat ko hamesha ("","") return karwao — template path force."""

    async def _empty(*args, **kwargs):
        return "", ""

    if evergreen.free_ai is not None:
        monkeypatch.setattr(evergreen.free_ai, "chat", _empty)


# --------------------------------------------------------------------------- #
# 1) referral_kit.make_referral
# --------------------------------------------------------------------------- #


class TestMakeReferral:
    def test_returns_code_message_link_svg(self):
        r = referral_kit.make_referral("Sharma Solar Solutions", reward="15% off")
        # code: initials + 4 alnum, non-empty
        assert r["code"].strip()
        assert r["code"].startswith("SSS")  # 3-word initials
        assert r["reward"] == "15% off"
        # WA message references the code + reward, never empty
        assert r["code"] in r["wa_message"]
        assert "15% off" in r["wa_message"]
        # link is the mini-site ?ref= form with the code
        assert r["link"].startswith("https://leadsgenai.in/b/")
        assert "ref=" + r["code"] in r["link"]
        assert r["slug"] in r["link"]
        # card SVG has the code and is a valid svg element
        assert r["card_svg"].startswith("<svg")
        assert r["card_svg"].rstrip().endswith("</svg>")
        assert r["code"] in r["card_svg"]
        assert "Refer" in r["card_svg"]

    def test_deterministic_code(self):
        a = referral_kit.make_referral("Cafe Mocha")
        b = referral_kit.make_referral("Cafe Mocha")
        assert a["code"] == b["code"]  # same business => same code

    def test_svg_escapes_injection(self):
        # malicious business name must be escaped in the card SVG
        r = referral_kit.make_referral("Evil<script>alert(1)</script>", reward='"x"&y')
        assert "<script>" not in r["card_svg"]
        assert "&lt;script&gt;" in r["card_svg"]
        # escaped reward (quotes/amp) — raw quote/amp pair must not appear unescaped
        assert '"x"&y' not in r["card_svg"]

    def test_never_raises_empty_input(self):
        r = referral_kit.make_referral("", reward="")
        assert r["code"].strip()
        assert r["card_svg"].startswith("<svg")
        assert r["wa_message"].strip()

    def test_brand_color_applied_invalid_ignored(self):
        r = referral_kit.make_referral("Brand Biz", brand_primary="#112233", brand_accent="nothex")
        assert "#112233" in r["card_svg"]  # valid hex applied
        # invalid accent ignored => default accent present, no literal "nothex"
        assert "nothex" not in r["card_svg"]


# --------------------------------------------------------------------------- #
# 2) referral_kit record / stats roundtrip (monkeypatch file const)
# --------------------------------------------------------------------------- #


class TestReferralRecordStats:
    def test_record_and_stats_roundtrip(self, monkeypatch, tmp_path):
        f = os.path.join(str(tmp_path), "referrals.jsonl")
        monkeypatch.setattr(referral_kit, "_REFERRALS_FILE", f)

        # empty store
        assert referral_kit.referral_stats()["total"] == 0

        ok1 = referral_kit.record_referral("ABCD23", "9876543210")
        ok2 = referral_kit.record_referral("abcd23", "9123456780")  # case-normalised same code
        ok3 = referral_kit.record_referral("XYZ99")
        assert ok1["recorded"] and ok2["recorded"] and ok3["recorded"]
        assert os.path.isfile(f)

        stats = referral_kit.referral_stats()
        assert stats["total"] == 3
        assert stats["by_code"]["ABCD23"] == 2  # both normalised to upper
        assert stats["by_code"]["XYZ99"] == 1

        # per-code query
        one = referral_kit.referral_stats("abcd23")
        assert one["code"] == "ABCD23"
        assert one["count"] == 2

        # each line is valid json
        with open(f, encoding="utf-8") as fh:
            lines = [json.loads(x) for x in fh if x.strip()]
        assert len(lines) == 3
        assert all("at" in r and "code" in r for r in lines)

    def test_record_empty_code_noop(self, monkeypatch, tmp_path):
        f = os.path.join(str(tmp_path), "referrals.jsonl")
        monkeypatch.setattr(referral_kit, "_REFERRALS_FILE", f)
        res = referral_kit.record_referral("")
        assert res["recorded"] is False
        assert referral_kit.referral_stats()["total"] == 0


# --------------------------------------------------------------------------- #
# 3) evergreen.recyclable_items
# --------------------------------------------------------------------------- #


class TestRecyclableItems:
    def test_empty_queue_returns_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: str(tmp_path / "queue"))
        assert evergreen.recyclable_items("client-x") == []

    def test_picks_only_old_posted_or_approved(self, monkeypatch, tmp_path):
        qdir = str(tmp_path / "queue")
        monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: qdir)
        os.makedirs(qdir, exist_ok=True)
        cid = "c1"
        from datetime import datetime, timedelta, timezone

        old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        new = datetime.now(timezone.utc).isoformat()
        rows = [
            # old + posted + has caption => eligible
            {
                "id": "a",
                "type": "post",
                "status": "posted",
                "caption": "Old hit",
                "created_at": old,
            },
            # old + approved => eligible
            {
                "id": "b",
                "type": "post",
                "status": "approved",
                "caption": "Liked",
                "created_at": old,
            },
            # old but draft => NOT eligible
            {"id": "c", "type": "post", "status": "draft", "caption": "Draft", "created_at": old},
            # posted but too new => NOT eligible
            {"id": "d", "type": "post", "status": "posted", "caption": "Fresh", "created_at": new},
            # old recycle output => NOT re-recycled
            {"id": "e", "type": "recycle", "status": "posted", "caption": "Re", "created_at": old},
            # old poster (no caption) => NOT eligible
            {"id": "f", "type": "poster", "status": "posted", "svg": "<svg/>", "created_at": old},
        ]
        path = os.path.join(qdir, cid + ".jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

        out = evergreen.recyclable_items(cid, older_than_days=21, limit=10)
        ids = {it["id"] for it in out}
        assert ids == {"a", "b"}


# --------------------------------------------------------------------------- #
# 4) evergreen.recycle_for_client
# --------------------------------------------------------------------------- #


class TestRecycleForClient:
    @pytest.mark.asyncio
    async def test_empty_queue_no_crash_noop(self, monkeypatch, tmp_path, no_llm):
        monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: str(tmp_path / "queue"))
        out = await evergreen.recycle_for_client({"id": "nobody", "business_name": "X"})
        assert out == []

    @pytest.mark.asyncio
    async def test_no_client_id_noop(self, monkeypatch, tmp_path, no_llm):
        monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: str(tmp_path / "queue"))
        assert await evergreen.recycle_for_client({}) == []
        assert await evergreen.recycle_for_client(None) == []

    @pytest.mark.asyncio
    async def test_recycles_old_item_into_new_draft(self, monkeypatch, tmp_path, no_llm):
        qdir = str(tmp_path / "queue")
        monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: qdir)
        os.makedirs(qdir, exist_ok=True)
        cid = "c2"
        from datetime import datetime, timedelta, timezone

        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        seed = {
            "id": "src1",
            "client_id": cid,
            "type": "post",
            "status": "posted",
            "caption": "Diwali pe 20% off! Aaj hi aao.",
            "hashtags": ["#Diwali", "#Offer"],
            "created_at": old,
        }
        path = os.path.join(qdir, cid + ".jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(seed) + "\n")

        out = await evergreen.recycle_for_client(
            {"id": cid, "business_name": "Sweet Shop", "niche": "bakery_sweets"}
        )
        assert len(out) >= 1
        item = out[0]
        assert item["type"] == "recycle"
        assert item["status"] == "draft"
        assert item["caption"].strip()  # never-empty (template tweak via no_llm)
        assert item["recycled_from"] == "src1"
        # appended to queue as a new draft
        drafts = auto_content.list_queue(cid, status="draft")
        assert any(d.get("type") == "recycle" for d in drafts)
