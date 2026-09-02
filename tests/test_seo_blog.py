"""
Tests: programmatic SEO blog engine (app.marketing.seo_blog).
=============================================================

No network — seo_blog.free_ai.chat ko ("","") monkeypatch karke har article
TEMPLATE fallback se banta hai (never-empty + CTA guarantee). Storage dir
tmp_path pe redirect hota hai (_BLOG_DIR const) — real data/blog kabhi nahi
chhuti. Fast: koi LLM/network call nahi.
"""

import os

import pytest

from app.marketing import seo_blog


@pytest.fixture
def no_llm(monkeypatch):
    """free_ai.chat ko ("","") force karo — har article template path se banega."""

    async def _empty(*args, **kwargs):
        return "", ""

    if seo_blog.free_ai is not None:
        monkeypatch.setattr(seo_blog.free_ai, "chat", _empty)


@pytest.fixture
def tmp_blog(monkeypatch, tmp_path):
    """_BLOG_DIR ko tmp_path pe redirect — real data/blog dir untouched."""
    d = os.path.join(str(tmp_path), "blog")
    monkeypatch.setattr(seo_blog, "_BLOG_DIR", d)
    return d


# --------------------------------------------------------------------------- #
# generate_article — template fallback (never-empty + CTA)
# --------------------------------------------------------------------------- #


class TestGenerateArticle:
    @pytest.mark.asyncio
    async def test_template_fallback_has_slug_title_html_cta(self, no_llm, tmp_blog):
        art = await seo_blog.generate_article("restaurant_cafe", city="Pune")
        # required keys
        for k in ("slug", "title", "meta_description", "html_body", "niche", "city", "created_at"):
            assert k in art, f"missing key {k}"
        assert art["slug"].strip()
        assert art["title"].strip()
        assert art["html_body"].strip()
        # provider = template (LLM mocked empty)
        assert art["provider"] == "template"
        # CTA ALWAYS appended (audit URL + WhatsApp)
        assert "leadsgenai.in/audit" in art["html_body"]
        assert "wa.me/918459012607" in art["html_body"]

    @pytest.mark.asyncio
    async def test_html_is_clean_h2_p_no_markdown(self, no_llm, tmp_blog):
        art = await seo_blog.generate_article("salon_spa", city="Mumbai")
        body = art["html_body"]
        # clean HTML: <h2>/<p> present, no markdown leakage
        assert body.count("<h2>") >= 2
        assert "<p>" in body
        assert "##" not in body
        assert "**" not in body

    @pytest.mark.asyncio
    async def test_meta_description_within_155(self, no_llm, tmp_blog):
        art = await seo_blog.generate_article("real_estate", city="Delhi")
        assert len(art["meta_description"]) <= 155
        assert art["meta_description"].strip()

    @pytest.mark.asyncio
    async def test_slug_kebab_and_reflects_niche_city(self, no_llm, tmp_blog):
        art = await seo_blog.generate_article("salon_spa", city="Nagpur")
        slug = art["slug"]
        # kebab-case: lowercase + hyphens, no spaces/underscores
        assert slug == slug.lower()
        assert " " not in slug and "_" not in slug
        assert "salon-spa" in slug
        assert "nagpur" in slug

    @pytest.mark.asyncio
    async def test_unknown_niche_still_useful(self, no_llm, tmp_blog):
        # custom/unknown niche -> generic-but-useful template, never empty
        art = await seo_blog.generate_article("totally_unknown_niche", city="Pune")
        assert art["html_body"].count("<h2>") >= 2
        assert "leadsgenai.in/audit" in art["html_body"]


# --------------------------------------------------------------------------- #
# save -> get -> list roundtrip + slug uniqueness
# --------------------------------------------------------------------------- #


class TestStorageRoundtrip:
    @pytest.mark.asyncio
    async def test_save_get_list_roundtrip(self, no_llm, tmp_blog):
        art = await seo_blog.generate_article("restaurant_cafe", city="Pune")
        slug = seo_blog.save_article(art)
        assert slug

        # get_article returns the saved record
        got = seo_blog.get_article(slug)
        assert got is not None
        assert got["slug"] == slug
        assert got["html_body"] == art["html_body"]

        # list_articles -> lightweight row present
        rows = seo_blog.list_articles()
        assert any(r["slug"] == slug for r in rows)
        row = next(r for r in rows if r["slug"] == slug)
        for k in ("slug", "title", "meta_description", "niche", "city", "created_at"):
            assert k in row
        # lightweight: no html_body in list rows
        assert "html_body" not in row

        # all_slugs reflects it
        assert slug in seo_blog.all_slugs()

    def test_get_unknown_slug_returns_none(self, tmp_blog):
        assert seo_blog.get_article("does-not-exist") is None
        assert seo_blog.get_article("") is None

    @pytest.mark.asyncio
    async def test_slug_uniqueness_on_duplicate(self, no_llm, tmp_blog):
        art = await seo_blog.generate_article("restaurant_cafe", city="Pune")
        s1 = seo_blog.save_article(art)
        # saving an identical-slug article again must NOT overwrite — unique slug
        art2 = await seo_blog.generate_article("restaurant_cafe", city="Pune")
        s2 = seo_blog.save_article(art2)
        assert s1 != s2
        # both retrievable
        assert seo_blog.get_article(s1) is not None
        assert seo_blog.get_article(s2) is not None
        assert len(seo_blog.all_slugs()) == 2


# --------------------------------------------------------------------------- #
# run_daily_blog — publishes n, never raises, unique slugs
# --------------------------------------------------------------------------- #


class TestRunDailyBlog:
    @pytest.mark.asyncio
    async def test_publishes_n_articles(self, no_llm, tmp_blog):
        result = await seo_blog.run_daily_blog(3)
        assert result["published"] == 3
        assert len(result["slugs"]) == 3
        # all unique + all retrievable
        assert len(set(result["slugs"])) == 3
        for s in result["slugs"]:
            assert seo_blog.get_article(s) is not None
        # list reflects them
        assert len(seo_blog.list_articles()) == 3

    @pytest.mark.asyncio
    async def test_does_not_recover_already_covered(self, no_llm, tmp_blog):
        first = await seo_blog.run_daily_blog(3)
        second = await seo_blog.run_daily_blog(3)
        # second run picks DIFFERENT combos (no slug overlap with first)
        assert not (set(first["slugs"]) & set(second["slugs"]))
        # total grew
        assert len(seo_blog.all_slugs()) == len(first["slugs"]) + len(second["slugs"])

    @pytest.mark.asyncio
    async def test_never_raises_and_returns_dict(self, no_llm, tmp_blog):
        result = await seo_blog.run_daily_blog(1)
        assert isinstance(result, dict)
        assert "published" in result and "slugs" in result
        assert result["published"] >= 1
