"""
Tests: per-client MINI WEBSITE (mini_site.render_site) + clients_store slugs.
================================================================================

Fast, no network. clients_store file paths tmp_path pe redirect hote hain
(_CLIENTS_FILE + brand_kit._BRAND_DIR) — real data/ dir kabhi nahi chhute.
render_site pure-sync hai (koi LLM/await nahi) — seedha call.
"""

import os

import pytest

from app.marketing import clients_store, mini_site


@pytest.fixture
def tmp_store(monkeypatch, tmp_path):
    """clients_store + brand_kit ke file paths tmp_path pe redirect."""
    monkeypatch.setattr(
        clients_store,
        "_CLIENTS_FILE",
        lambda: os.path.join(str(tmp_path), "marketing_clients.jsonl"),
    )
    try:
        from app.marketing import brand_kit

        monkeypatch.setattr(brand_kit, "_BRAND_DIR", os.path.join(str(tmp_path), "brand_kits"))
    except Exception:
        pass
    return tmp_path


# --------------------------------------------------------------------------- #
# clients_store slug behaviour
# --------------------------------------------------------------------------- #
class TestSlug:
    def test_add_client_gets_slug(self, tmp_store):
        rec = clients_store.add_client(
            "Sharma Solar Solutions", "solar_residential", phone="9000000001"
        )
        assert rec.get("slug")
        # kebab base + id suffix
        assert rec["slug"].startswith("sharma-solar-solutions-")

    def test_get_by_slug_roundtrip(self, tmp_store):
        rec = clients_store.add_client("Cafe Mocha", "restaurant_cafe", phone="9000000002")
        got = clients_store.get_by_slug(rec["slug"])
        assert got is not None and got["id"] == rec["id"]
        # case-insensitive
        assert clients_store.get_by_slug(rec["slug"].upper())["id"] == rec["id"]
        # missing slug => None
        assert clients_store.get_by_slug("nope-missing-xyz") is None
        assert clients_store.get_by_slug("") is None

    def test_slug_uniqueness_same_name(self, tmp_store):
        # Same business name, different phone => distinct records + distinct slugs.
        a = clients_store.add_client("Glow Salon", "salon_spa", phone="9000000010")
        b = clients_store.add_client("Glow Salon", "salon_spa", phone="9000000011")
        assert a["id"] != b["id"]
        assert a["slug"] != b["slug"]  # id-suffix keeps them unique
        assert clients_store.get_by_slug(a["slug"])["id"] == a["id"]
        assert clients_store.get_by_slug(b["slug"])["id"] == b["id"]

    def test_legacy_record_backfills_slug(self, tmp_store):
        # Simulate an OLD record written without a slug, then ensure it backfills.
        import json

        path = clients_store._CLIENTS_FILE()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                json.dumps({"id": "legacy123abc", "business_name": "Old Biz", "status": "active"})
                + "\n"
            )
        listed = clients_store.list_clients()
        assert len(listed) == 1
        assert listed[0].get("slug")  # backfilled on read
        # and fetchable by that backfilled slug
        assert clients_store.get_by_slug(listed[0]["slug"])["id"] == "legacy123abc"


# --------------------------------------------------------------------------- #
# mini_site.render_site
# --------------------------------------------------------------------------- #
class TestRenderSite:
    def test_contains_core_elements(self, tmp_store):
        rec = clients_store.add_client(
            "Sharma Solar",
            "solar_residential",
            city="Pune",
            phone="9876543210",
            brand={"primary": "#0b5fff", "accent": "#ffce00", "tagline": "Roshni bhi, bachat bhi"},
            socials={"instagram": "sharma_solar", "gbp": "https://maps.google.com/?q=sharma"},
        )
        html = mini_site.render_site(rec)
        assert isinstance(html, str) and html.startswith("<!DOCTYPE html>")
        # business name present
        assert "Sharma Solar" in html
        # tagline present
        assert "Roshni bhi, bachat bhi" in html
        # WhatsApp link (10-digit -> 91 prefixed)
        assert "wa.me/919876543210" in html
        # tel: call link
        assert "tel:9876543210" in html
        # booking form posts to the public inquiry endpoint
        assert "/api/public/inquiry" in html
        # hidden source_slug wired (slug appears in the booking JS)
        assert rec["slug"] in html
        # brand color applied (validated hex)
        assert "#0b5fff" in html
        # footer attribution
        assert "leadsgenai.in" in html

    def test_form_has_required_fields(self, tmp_store):
        rec = clients_store.add_client("Form Biz", "general", phone="9000000020")
        html = mini_site.render_site(rec)
        for field in ('name="name"', 'name="phone"', 'name="message"', 'name="preferred_time"'):
            assert field in html
        # honeypot present (bot-trap)
        assert 'name="website"' in html

    def test_never_raises_on_garbage(self):
        # None, empty, and weird types must all yield a string (never raise).
        for bad in (None, {}, {"business_name": "<script>x</script>", "brand": "notadict"}):
            out = mini_site.render_site(bad)
            assert isinstance(out, str) and "<html" in out.lower()
        # XSS-y name is HTML-escaped (no raw <script> tag emitted)
        out = mini_site.render_site({"business_name": "<script>alert(1)</script>", "slug": "x-1"})
        assert "<script>alert(1)</script>" not in out
        assert "&lt;script&gt;" in out

    def test_invalid_brand_color_falls_back(self, tmp_store):
        rec = clients_store.add_client(
            "Color Biz", "general", phone="9000000021", brand={"primary": "javascript:evil"}
        )
        html = mini_site.render_site(rec)
        # invalid color rejected -> default violet used, evil string not injected
        assert "javascript:evil" not in html
        assert "#6d28d9" in html
