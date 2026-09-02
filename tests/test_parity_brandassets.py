"""Tests — brand assets batch (brand_frames, business_card, magic_resize,
review_to_post, sticker_pack + /api/brand router).

Pure-python: tmp stores (clients_store/brand_kit monkeypatched), free_ai.chat
mocked (no network/DB), PIL local. Sab fns never-raise + never-empty contract.
"""

from __future__ import annotations

import asyncio
import os


async def _fake_chat(system, messages, **kw):
    return ('["Mock caption 1 🙏", "Mock caption 2 ✨", "Mock caption 3 🔥"]', "mock")


async def _broken_chat(system, messages, **kw):
    raise RuntimeError("llm down")


def _setup_client(tmp_path, monkeypatch):
    """Tmp clients_store + brand_kit + ek test client (brand colors ke saath)."""
    from app.marketing import brand_frames, brand_kit, clients_store

    monkeypatch.setattr(clients_store, "_CLIENTS_FILE", lambda: str(tmp_path / "clients.jsonl"))
    monkeypatch.setattr(brand_kit, "_BRAND_DIR", str(tmp_path / "brand_kits"))
    monkeypatch.setattr(brand_frames, "_LOGOS_DIR", str(tmp_path / "logos"))
    rec = clients_store.add_client(
        "Sharma Solar",
        "solar",
        city="Pune",
        phone="9876543210",
        brand={"primary": "#112233", "accent": "#ffcc00", "tagline": "Roshni ka bharosa"},
    )
    assert rec.get("id") and rec.get("slug")
    return rec


# ------------------------------ brand_frames ------------------------------- #
def test_compose_frame_svg_escaped():
    from app.marketing import brand_frames

    brand = {
        "business_name": 'Evil <script>"x"</script>',
        "phone": "9876543210",
        "primary": "#112233",
        "accent": "#ffcc00",
    }
    tpl = '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080"><rect width="1080" height="1080" fill="#fff"/></svg>'
    out = brand_frames.compose_frame(tpl, brand)
    assert out["ok"] is True and out["format"] == "svg"
    assert out["svg"].startswith("<svg") and out["height"] == 1080 + 110
    assert "<script>" not in out["svg"]  # XML-escaped
    assert "&lt;script&gt;" in out["svg"]
    assert "9876543210" in out["svg"] and "#112233" in out["svg"]


def test_compose_frame_never_raises():
    from app.marketing import brand_frames

    assert brand_frames.compose_frame("", {})["ok"] is False
    assert brand_frames.compose_frame("not-a-path.xyz", None)["ok"] is False
    # garbage brand bhi crash nahi karta
    out = brand_frames.compose_frame(
        '<svg width="100" height="100"></svg>', {"primary": "javascript:alert(1)"}
    )
    assert out["ok"] is True and "javascript:" not in out["svg"]  # invalid color = default


def test_compose_frame_raster(tmp_path, monkeypatch):
    from PIL import Image

    from app.marketing import brand_frames

    monkeypatch.setattr(brand_frames, "_FRAMES_DIR", str(tmp_path / "frames"))
    src = tmp_path / "in.png"
    Image.new("RGB", (300, 200), "#abcdef").save(src)
    out = brand_frames.compose_frame(str(src), {"business_name": "Test Biz", "phone": "98765"})
    assert out["ok"] is True and out["format"] == "png"
    assert os.path.isfile(out["png_path"])
    with Image.open(out["png_path"]) as im:
        assert im.width == 300 and im.height > 200  # strip add hua


def test_daily_feed_three_posts(tmp_path, monkeypatch):
    from app.marketing import brand_frames
    from app.voice_agent import free_ai

    rec = _setup_client(tmp_path, monkeypatch)
    monkeypatch.setattr(free_ai, "chat", _fake_chat)
    out = asyncio.run(brand_frames.daily_feed(rec["slug"]))
    assert out["ok"] is True and len(out["posts"]) == 3
    kinds = {p["kind"] for p in out["posts"]}
    assert kinds <= {"festival", "quote", "offer"} and "offer" in kinds
    for p in out["posts"]:
        assert p["caption"].strip()  # never-empty
        assert p["svg"].startswith("<svg")
    assert out["business_name"] == "Sharma Solar"


def test_daily_feed_llm_down_fallback(tmp_path, monkeypatch):
    from app.marketing import brand_frames
    from app.voice_agent import free_ai

    rec = _setup_client(tmp_path, monkeypatch)
    monkeypatch.setattr(free_ai, "chat", _broken_chat)
    out = asyncio.run(brand_frames.daily_feed(rec["id"]))  # id se bhi chalta
    assert out["ok"] is True and len(out["posts"]) == 3
    for p in out["posts"]:
        assert p["caption"].strip() and "Sharma Solar" in p["caption"]


# ------------------------------ business_card ------------------------------ #
def test_card_data_and_html(tmp_path, monkeypatch):
    from app.marketing import business_card

    rec = _setup_client(tmp_path, monkeypatch)
    d = business_card.card_data(rec["slug"])
    assert d["ok"] is True
    assert d["business_name"] == "Sharma Solar" and d["wa_number"] == "919876543210"
    assert d["minisite_url"].endswith(f"/b/{rec['slug']}")

    res = business_card.render_card_html(rec["slug"])
    assert res["ok"] is True
    html = res["html"]
    assert "tel:9876543210" in html and "wa.me/919876543210" in html
    assert "Sharma Solar" in html and f"/api/brand/card/{rec['slug']}.vcf" in html
    assert "<svg" in html  # QR embedded


def test_card_html_escapes_injection(tmp_path, monkeypatch):
    from app.marketing import business_card, clients_store

    _setup_client(tmp_path, monkeypatch)
    rec = clients_store.add_client("Evil <img src=x onerror=alert(1)>", "gym", phone="9123456780")
    res = business_card.render_card_html(rec["slug"])
    assert res["ok"] is True
    assert "<img src=x" not in res["html"] and "&lt;img" in res["html"]


def test_card_vcf(tmp_path, monkeypatch):
    from app.marketing import business_card

    rec = _setup_client(tmp_path, monkeypatch)
    res = business_card.render_vcf(rec["slug"])
    assert res["ok"] is True
    vcf = res["vcf"]
    assert vcf.startswith("BEGIN:VCARD") and "END:VCARD" in vcf
    assert "FN:Sharma Solar" in vcf and "TEL;TYPE=CELL,VOICE:9876543210" in vcf
    assert res["filename"].endswith(".vcf")


def test_card_missing_client(tmp_path, monkeypatch):
    from app.marketing import business_card

    _setup_client(tmp_path, monkeypatch)
    assert business_card.card_data("no-such-slug-xyz")["ok"] is False
    assert business_card.render_vcf("no-such-slug-xyz")["ok"] is False


# ------------------------------- magic_resize ------------------------------ #
def test_resize_raster_pack(tmp_path, monkeypatch):
    from PIL import Image

    from app.marketing import magic_resize

    monkeypatch.setattr(magic_resize, "_RESIZED_DIR", str(tmp_path / "resized"))
    src = tmp_path / "poster.png"
    Image.new("RGB", (800, 800), "#ff0000").save(src)
    out = magic_resize.resize_pack(image_path=str(src), sizes=["square", "banner"])
    assert out["ok"] is True and set(out["files"]) == {"square", "banner"}
    with Image.open(out["files"]["square"]) as im:
        assert im.size == (1080, 1080)
    with Image.open(out["files"]["banner"]) as im:
        assert im.size == (1200, 628)


def test_resize_svg_pack():
    from app.marketing import magic_resize

    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080"><circle cx="540" cy="540" r="100"/></svg>'
    out = magic_resize.resize_pack(svg=svg, sizes="story,square")
    assert out["ok"] is True and set(out["svgs"]) == {"story", "square"}
    assert out["svgs"]["story"].startswith("<svg") and 'height="1920"' in out["svgs"]["story"]


def test_resize_never_raises():
    from app.marketing import magic_resize

    assert magic_resize.resize_pack()["ok"] is False
    assert magic_resize.resize_pack(image_path="missing.png")["ok"] is False
    # unknown sizes => default full pack names (validated)
    svg = '<svg width="10" height="10"></svg>'
    out = magic_resize.resize_pack(svg=svg, sizes=["bogus"])
    assert out["ok"] is True and set(out["svgs"]) == set(magic_resize.SIZES)


# ------------------------------ review_to_post ----------------------------- #
def test_review_post_rejects_low_rating():
    from app.marketing import review_to_post

    out = asyncio.run(review_to_post.from_review("thik thaak tha", "Ravi", 2, ""))
    assert out["ok"] is False and "star" in out["error"].lower()


def test_review_post_ok_and_escaped(tmp_path, monkeypatch):
    from app.marketing import review_to_post
    from app.voice_agent import free_ai

    rec = _setup_client(tmp_path, monkeypatch)
    monkeypatch.setattr(free_ai, "chat", _broken_chat)  # fallback caption path
    out = asyncio.run(
        review_to_post.from_review(
            "Zabardast kaam <script>alert(1)</script>", "Priya", 5, rec["slug"]
        )
    )
    assert out["ok"] is True and out["svg"].startswith("<svg")
    assert "<script>" not in out["svg"] and "&lt;script&gt;" in out["svg"]
    assert "★★★★★" in out["svg"] and "Sharma Solar" in out["svg"]
    assert out["caption"].strip() and "Khush" in out["caption"]


# ------------------------------- sticker_pack ------------------------------ #
def test_sticker_pack_six_pngs(tmp_path, monkeypatch):
    from PIL import Image

    from app.marketing import sticker_pack

    monkeypatch.setattr(sticker_pack, "_STICKERS_DIR", str(tmp_path / "stickers"))
    out = sticker_pack.generate_stickers(business_name="Sharma Solar", niche="solar")
    assert out["ok"] is True and out["count"] == 6 and len(out["files"]) == 6
    for p in out["files"]:
        with Image.open(p) as im:
            assert im.size == (512, 512) and im.mode == "RGBA"


def test_sticker_safe_path_locked(tmp_path, monkeypatch):
    from app.marketing import sticker_pack

    monkeypatch.setattr(sticker_pack, "_STICKERS_DIR", str(tmp_path / "stickers"))
    out = sticker_pack.generate_stickers(slug="test-pack")
    assert out["ok"] is True
    name = os.path.basename(out["files"][0])
    assert sticker_pack.safe_sticker_path("test-pack", name)  # valid
    assert sticker_pack.safe_sticker_path("../evil", name) is None
    assert sticker_pack.safe_sticker_path("test-pack", "../../etc/passwd") is None
    assert sticker_pack.safe_sticker_path("test-pack", "sticker_1.png.exe") is None


# --------------------------------- router ---------------------------------- #
def test_router_paths():
    from app.api.brandassets import router

    paths = {r.path for r in router.routes}
    expected = {
        "/brand/frames/daily",
        "/brand/frames/compose",
        "/brand/card/{slug}.vcf",
        "/brand/card/{slug}",
        "/brand/resize",
        "/brand/resize-file/{name}",
        "/brand/review-post",
        "/brand/stickers",
        "/brand/sticker-file/{slug}/{name}",
    }
    assert expected <= paths
    # .vcf route /card/{slug} se PEHLE (greedy-match shadow guard)
    ordered = [r.path for r in router.routes]
    assert ordered.index("/brand/card/{slug}.vcf") < ordered.index("/brand/card/{slug}")
