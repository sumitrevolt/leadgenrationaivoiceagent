"""
Offline tests for the mini-site BUILDER (config / logo validation / reviews /
render integration). No network, no DB — pure in-process. Each test redirects
the builder's storage paths to a tmp dir via monkeypatch.
"""

from __future__ import annotations

import importlib

import pytest

import app.api.minisite_builder as mb
import app.marketing.mini_site as ms


@pytest.fixture(autouse=True)
def _tmp_store(tmp_path, monkeypatch):
    """Point all builder storage at a fresh tmp dir + reset rate limiter."""
    monkeypatch.setattr(mb, "_DATA_DIR", str(tmp_path), raising=True)
    monkeypatch.setattr(mb, "_CONFIG_FILE", str(tmp_path / "mini_site_config.jsonl"), raising=True)
    monkeypatch.setattr(mb, "_REVIEWS_DIR", str(tmp_path / "reviews"), raising=True)
    monkeypatch.setattr(mb, "_LOGOS_DIR", str(tmp_path / "logos"), raising=True)
    mb._rl_hits.clear()
    yield


# --------------------------------------------------------------------------- #
# A) CONFIG defaults + persist
# --------------------------------------------------------------------------- #
def test_config_defaults_when_unset():
    cfg = mb.get_config("brand-new-slug")
    assert cfg["palette"] == mb.DEFAULT_PALETTE
    assert cfg["layout"] == mb.DEFAULT_LAYOUT
    assert cfg["logo_url"] == ""
    # unset slug => primary/accent EMPTY (client brand colors jeet sakein);
    # concrete hex sirf SAVED config pe resolve hota hai (bug-fix 2026-06-10)
    assert cfg["primary"] == ""
    assert cfg["accent"] == ""


def test_config_persist_and_roundtrip():
    out = mb.set_config("acme-1234", palette="ocean", layout="bold")
    assert out["palette"] == "ocean"
    assert out["layout"] == "bold"
    assert out["primary"] == mb.PALETTES["ocean"]["primary"]
    # re-read = same (latest line wins)
    again = mb.get_config("acme-1234")
    assert again["palette"] == "ocean"
    assert again["layout"] == "bold"


def test_config_rejects_unknown_palette_and_layout():
    out = mb.set_config("acme-9", palette="rainbow-unknown", layout="spaceship")
    assert out["palette"] == mb.DEFAULT_PALETTE  # fell back
    assert out["layout"] == mb.DEFAULT_LAYOUT


def test_config_latest_line_wins():
    mb.set_config("x-slug", palette="ocean")
    mb.set_config("x-slug", palette="forest")
    assert mb.get_config("x-slug")["palette"] == "forest"


def test_get_config_never_raises_on_garbage(monkeypatch):
    # even with a corrupt file, returns defaults
    p = mb._CONFIG_FILE
    import os

    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write("{not json\n}\n\n")
    cfg = mb.get_config("whatever")
    assert cfg["palette"] == mb.DEFAULT_PALETTE


# --------------------------------------------------------------------------- #
# B) LOGO validation
# --------------------------------------------------------------------------- #
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
_WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 16


def test_validate_logo_accepts_png_jpg_webp():
    assert mb.validate_logo("a.png", _PNG)[0] is True
    assert mb.validate_logo("a.jpg", _JPG)[0] is True
    assert mb.validate_logo("a.jpeg", _JPG)[1] == "jpg"  # normalized
    assert mb.validate_logo("a.webp", _WEBP)[0] is True


def test_validate_logo_rejects_bad_type():
    ok, ext, err = mb.validate_logo("evil.svg", b"<svg></svg>")
    assert ok is False
    assert "Unsupported" in err


def test_validate_logo_rejects_oversize():
    big = _PNG[:8] + b"\x00" * (3 * 1024 * 1024)
    ok, _, err = mb.validate_logo("big.png", big)
    assert ok is False
    assert "Too large" in err


def test_validate_logo_rejects_ext_content_mismatch():
    # .png extension but JPEG bytes → magic-byte sniff blocks it
    ok, _, err = mb.validate_logo("spoof.png", _JPG)
    assert ok is False
    assert "does not match" in err


def test_validate_logo_rejects_empty():
    ok, _, err = mb.validate_logo("a.png", b"")
    assert ok is False


def test_save_logo_writes_file_and_returns_served_url():
    ok, url, err = mb.save_logo("my-shop", "logo.png", _PNG)
    assert ok is True
    assert url.startswith("/api/minisite/logo/")
    assert url.endswith(".png")


def test_valid_logo_url():
    assert mb._valid_logo_url("https://x.com/a.png") is True
    assert mb._valid_logo_url("https://x.com/a.webp?v=2") is True
    assert mb._valid_logo_url("/api/minisite/logo/abc.png") is True
    assert mb._valid_logo_url("https://x.com/a.gif") is False
    assert mb._valid_logo_url("ftp://x.com/a.png") is False


# --------------------------------------------------------------------------- #
# C) REVIEWS add / list / moderate
# --------------------------------------------------------------------------- #
def test_review_add_pending_not_in_public_until_approved():
    rec = mb.add_review("shop-1", "Rahul", 5, "Great service")
    assert rec["approved"] is False
    # public = approved only → empty
    assert mb.list_reviews("shop-1", approved_only=True) == []
    # admin = all → 1
    assert len(mb.list_reviews("shop-1", approved_only=False)) == 1


def test_review_moderate_approve_then_public():
    rec = mb.add_review("shop-2", "Sita", 4, "Nice")
    assert mb.moderate_review("shop-2", rec["id"], True) is True
    pub = mb.list_reviews("shop-2", approved_only=True)
    assert len(pub) == 1
    assert pub[0]["rating"] == 4


def test_review_rating_clamped():
    rec = mb.add_review("shop-3", "X", 99, "ok")
    assert rec["rating"] == 5
    rec2 = mb.add_review("shop-3", "Y", -2, "ok")
    assert rec2["rating"] == 1


def test_review_per_slug_isolation():
    mb.add_review("shop-a", "A", 5, "")
    mb.add_review("shop-b", "B", 5, "")
    assert len(mb.list_reviews("shop-a", approved_only=False)) == 1
    assert len(mb.list_reviews("shop-b", approved_only=False)) == 1


def test_rate_limiter():
    key = "rev:1.2.3.4"
    allowed = sum(1 for _ in range(10) if mb._rate_ok(key))
    assert allowed == mb._RL_MAX  # capped


# --------------------------------------------------------------------------- #
# C2) Pre-existing reviews via custom store path (no-store fallback path)
# --------------------------------------------------------------------------- #
def test_list_reviews_empty_for_unknown_slug():
    assert mb.list_reviews("no-such-slug") == []


# --------------------------------------------------------------------------- #
# D) RENDER applies palette + layout + logo
# --------------------------------------------------------------------------- #
def test_render_applies_palette_colors():
    mb.set_config("render-shop", palette="forest")
    html = ms.render_site({"business_name": "Green Co", "slug": "render-shop"})
    # forest primary hex should be in the CSS :root
    assert mb.PALETTES["forest"]["primary"] in html
    assert "Green Co" in html


def test_render_applies_layout_css():
    mb.set_config("bold-shop", layout="bold")
    html = ms.render_site({"business_name": "Bold Co", "slug": "bold-shop"})
    # 'bold' layout override sets uppercase section headings
    assert "text-transform:uppercase" in html


def test_render_minimal_layout():
    mb.set_config("min-shop", layout="minimal")
    html = ms.render_site({"business_name": "Min Co", "slug": "min-shop"})
    # minimal hero uses a white background override
    assert ".hero{background:#fff" in html


def test_render_shows_logo_image_when_set():
    ok, url, _ = mb.save_logo("logo-shop", "l.png", _PNG)
    mb.set_config("logo-shop", logo_url=url)
    html = ms.render_site({"business_name": "Logo Co", "slug": "logo-shop"})
    assert 'class="logoimg"' in html
    assert url in html


def test_render_includes_calendar_and_reviews_sections():
    html = ms.render_site({"business_name": "Cal Co", "slug": "cal-shop"})
    assert 'id="calendar"' in html
    assert "/api/booking/slots" in html
    assert "/api/booking/book" in html
    assert 'id="reviews"' in html
    assert "/api/minisite/reviews/public" in html


def test_render_never_raises_on_none():
    html = ms.render_site(None)
    assert "<!DOCTYPE html>" in html


def test_render_default_logo_text_fallback_when_no_logo():
    html = ms.render_site({"business_name": "Zeta", "slug": "zeta-shop"})
    # no logo_url configured → text-initial badge, not an <img>
    assert 'class="logo"' in html


# --------------------------------------------------------------------------- #
# E) module import surface
# --------------------------------------------------------------------------- #
def test_router_and_exports_present():
    importlib.reload(mb)  # ensure clean import
    assert hasattr(mb, "router")
    for fn in ("get_config", "set_config", "add_review", "list_reviews", "validate_logo"):
        assert callable(getattr(mb, fn))
