"""test_post_generator_parsing.py — daily-content parser bug regression suite.

Real paying-customer incident: broken drafts shipped —
  * caption literally "CAP" (truncated fragment passed the empty-only guard),
  * caption me literal "**HASHTAGS:** ..." markdown leak (bold marker ne
    CAPTION lookahead ko fail kara diya -> poora hashtag-block caption me),
  * broken 2-char hashtag "#H" (truncated tag).

Yeh suite un teeno ko pin karta hai + max_tokens bump verify karta hai.
Sab offline (koi live free_ai call nahi) — chat monkeypatched ya template path.
"""

from __future__ import annotations

import inspect

import pytest

from app.marketing import post_generator


# --- realistic LLM outputs (free models markdown decoration daal dete hain) --- #

MARKDOWN_BOLD_FIXTURE = (
    "**CAPTION:** ✨ Jiya Makeover me aapka swagat hai!\n"
    "💄 Bridal se party glam tak — sab ek jagah.\n"
    "**HASHTAGS:** #JiyaMakeover #BridalMakeup #NagpurMakeup #MakeupArtist "
    "#BeautyStudio #GlamLook #H\n"
    "**IMAGE:** Bride ke before/after split ka bright close-up shot"
)

PLAIN_MARKER_FIXTURE = (
    "CAPTION: 🌟 Trending Tattoos me aapka design, hamari suiyaan!\n"
    "HASHTAGS: #TrendingTattoos #TattooStudio #InkLife\n"
    "IMAGE: Fresh tattoo close-up with studio logo overlay"
)


# ============================================================================ #
# (a) markdown-bold markers — no leak into caption
# ============================================================================ #


def test_markdown_bold_markers_parsed_clean():
    caption, hashtags, image_idea = post_generator._parse_llm_post(MARKDOWN_BOLD_FIXTURE)

    # Caption me hashtag-block bilkul leak nahi hona chahiye (yeh tha real bug).
    assert "HASHTAGS" not in caption.upper()
    assert "#JiyaMakeover" not in caption
    assert "IMAGE" not in caption.upper()
    # Leading/trailing markdown decoration bhi strip ho.
    assert not caption.startswith("*")
    assert not caption.endswith("*")
    assert "Jiya Makeover" in caption

    # Hashtags asli block se parse hue.
    assert "#JiyaMakeover" in hashtags
    assert "#BridalMakeup" in hashtags

    # Image idea saaf (bina ** decoration).
    assert image_idea
    assert not image_idea.startswith("*")
    assert "before/after" in image_idea


def test_plain_markers_still_work():
    """Regression guard — decoration-less output (aam case) pehle jaisa parse ho."""
    caption, hashtags, image_idea = post_generator._parse_llm_post(PLAIN_MARKER_FIXTURE)
    assert "Trending Tattoos" in caption
    assert "HASHTAGS" not in caption.upper()
    assert "#TrendingTattoos" in hashtags
    assert "#TattooStudio" in hashtags
    assert "logo overlay" in image_idea


# ============================================================================ #
# (c) hashtag min-length — truncated "#H" dropped, real tags kept
# ============================================================================ #


def test_short_hashtag_dropped_from_parse():
    _caption, hashtags, _img = post_generator._parse_llm_post(MARKDOWN_BOLD_FIXTURE)
    assert "#H" not in hashtags  # 2-char truncated tag never survives
    assert all(len(t) >= 3 for t in hashtags)


def test_hashtags_for_min_length_floor():
    tags = post_generator._hashtags_for("general", seed_tags=["#H", "#JEE", "#a"])
    assert "#H" not in tags  # len 2 -> dropped
    assert "#a" not in tags  # len 2 -> dropped
    assert "#JEE" in tags  # len 4 -> kept
    assert all(len(t) >= 3 for t in tags)


def test_tag_regex_rejects_two_char_tag():
    import re

    found = re.findall(post_generator._TAG_RE, "#H #JEE #ab #x")
    assert "#H" not in found
    assert "#x" not in found
    assert "#JEE" in found
    assert "#ab" in found  # exactly 2 chars after '#' = total 3 = kept


# ============================================================================ #
# (b) short-caption fallback — "CAP" fragment falls back to template
# ============================================================================ #


def _requires_free_ai() -> None:
    if post_generator.free_ai is None:
        pytest.skip("free_ai import-unavailable in this env")


@pytest.mark.asyncio
async def test_truncated_caption_falls_back_to_template(monkeypatch):
    _requires_free_ai()

    async def _fake_chat(*_a, **_k):
        return "CAPTION: CAP", "groq"

    monkeypatch.setattr(post_generator.free_ai, "chat", _fake_chat)

    r = await post_generator.generate_post("Jiya Makeover", niche="beauty")
    # Truncated "CAP" (<20 chars) reject -> deterministic template.
    assert r["provider"] == "template"
    assert len(r["caption"].strip()) >= 20
    assert "Jiya Makeover" in r["post_text"]
    assert "CAP" != r["caption"].strip()


@pytest.mark.asyncio
async def test_full_markdown_response_produces_clean_post(monkeypatch):
    _requires_free_ai()

    async def _fake_chat(*_a, **_k):
        return MARKDOWN_BOLD_FIXTURE, "groq"

    monkeypatch.setattr(post_generator.free_ai, "chat", _fake_chat)

    r = await post_generator.generate_post("Jiya Makeover", niche="beauty")
    # LLM path chala (template nahi).
    assert r["provider"] != "template"
    # Caption saaf — koi markdown/marker leak nahi.
    assert "HASHTAGS" not in r["caption"].upper()
    assert "**" not in r["caption"]
    assert len(r["caption"].strip()) >= 20
    # post_text me short/broken tag nahi.
    assert "#H " not in (r["post_text"] + " ")
    assert all(len(t) >= 3 for t in r["hashtags"])
    assert len(r["hashtags"]) >= 8  # niche/general se top-up


# ============================================================================ #
# (d) max_tokens bump 350 -> 500 on the free_ai.chat call
# ============================================================================ #


@pytest.mark.asyncio
async def test_generate_post_uses_higher_max_tokens(monkeypatch):
    _requires_free_ai()
    captured: dict = {}

    async def _spy_chat(system, messages, **kwargs):
        captured.update(kwargs)
        return MARKDOWN_BOLD_FIXTURE, "groq"

    monkeypatch.setattr(post_generator.free_ai, "chat", _spy_chat)
    await post_generator.generate_post("Jiya Makeover", niche="beauty")
    assert captured.get("max_tokens") == 500


def test_source_bumped_max_tokens_literal():
    """Belt-and-suspenders: source me 500 hard-set hai (spy env-dependent na ho)."""
    src = inspect.getsource(post_generator.generate_post)
    assert "max_tokens=500" in src
    assert "max_tokens=350" not in src
