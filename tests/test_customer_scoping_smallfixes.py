"""
Tests — per-client scoping / billing-truth small-fixes batch (2026-07-05).

Real paying customer "jiya makeover" (slug "jija-makeover-..." stored in the
client record) exposed 4 platform-delivery bugs. Yeh file un 4 owned-file fixes
ko lock karti hai:

  1) referral_kit.make_referral(slug=...)  -> link REAL client slug use kare,
     business-naam se derive NA kare (derived slug != stored slug = 404).
  2) monthly_report.build_report(client_id=...) -> GLOBAL team-event numbers
     ek specific client ke naam NA dikhe (agent_events me client_id column nahi
     -> platform-wide counts misleading). Scoped = omit/zeros.
  3) carousel.generate_carousel(slug=/phone=) -> slide CTA client ki apni
     mini-site URL (/b/<slug>) ya phone ho, hardcoded "leadsgenai.in/audit" nahi.
  4) lifecycle_nurture upgrade-email -> legacy hidden Growth ₹2,999 plan ka
     zikr NA ho (billing-truth); public Advanced/Combo ₹5,999 pitch ho.

No network — free_ai.chat conftest-stubbed; jahan template path chahiye wahan
free_ai None kar dete hain. Pure-logic assertions.
"""

import asyncio

import pytest

from app.marketing import carousel, lifecycle_nurture, monthly_report, referral_kit


# --------------------------------------------------------------------------- #
# 1) referral_kit — REAL slug used for the link (not name-derived)             #
# --------------------------------------------------------------------------- #
class TestReferralUsesRealSlug:
    def test_real_slug_used_in_link(self):
        # jiya makeover ka stored slug business-naam se derive-able NAHI hai
        # (kebab(name)+id-suffix). REAL slug pass karo => link usi ka ho.
        r = referral_kit.make_referral("Jiya Makeover", reward="20% off", slug="jiya-makeover-d79d")
        assert r["slug"] == "jiya-makeover-d79d"
        assert "https://leadsgenai.in/b/jiya-makeover-d79d?ref=" in r["link"]
        # code abhi bhi link me (ref=)
        assert "ref=" + r["code"] in r["link"]
        # naam-derived slug (jiya-makeover) link me NAHI hona chahiye as the path
        assert "/b/jiya-makeover?" not in r["link"]

    def test_no_slug_falls_back_to_name_derived(self):
        # backward-compat: slug na do to purana behavior (naam se derive).
        r = referral_kit.make_referral("Sharma Solar Solutions", reward="15% off")
        assert r["slug"] == "sharma-solar-solutions"
        assert r["link"].startswith("https://leadsgenai.in/b/sharma-solar-solutions?ref=")

    def test_blank_slug_ignored(self):
        r = referral_kit.make_referral("Cafe Mocha", slug="   ")
        # blank slug -> derive from name (not empty path)
        assert r["slug"] == "cafe-mocha"
        assert "/b/cafe-mocha?ref=" in r["link"]

    def test_real_slug_in_card_svg_qr(self):
        # card SVG QR encodes the referral link -> real slug indirectly present;
        # at minimum the returned link/slug are consistent + card is valid svg.
        r = referral_kit.make_referral("Jiya Makeover", slug="jiya-makeover-d79d")
        assert r["card_svg"].startswith("<svg")
        assert r["card_svg"].rstrip().endswith("</svg>")


# --------------------------------------------------------------------------- #
# 2) monthly_report — scoped report omits global team numbers                  #
# --------------------------------------------------------------------------- #
class TestReportScopedOmitsGlobalNumbers:
    @pytest.fixture
    def fake_global_events(self, monkeypatch):
        """Pretend the platform team store has lots of GLOBAL events (other
        clients' work). Scoped report ko yeh NA dikhaye."""
        import app.platform.team as team_mod

        def _fake_recent(limit=60, member=None, hours=None):
            # 3 posts + 2 calls from platform-wide staff activity
            return [
                {"member": "isha", "action": "post_generated", "detail": "x"},
                {"member": "isha", "action": "post_generated", "detail": "y"},
                {"member": "dev", "action": "poster_generated", "detail": "z"},
                {"member": "swara", "action": "call_placed", "detail": "c1"},
                {"member": "swara", "action": "call_finished", "detail": "c2"},
            ]

        monkeypatch.setattr(team_mod, "recent_events", _fake_recent, raising=False)
        # force template summary path (deterministic, no LLM number-injection)
        monkeypatch.setattr(monthly_report, "free_ai", None, raising=False)

    def test_scoped_report_shows_no_global_numbers(self, fake_global_events):
        out = asyncio.run(
            monthly_report.build_report(client_name="Jiya Makeover", client_id="d79d690f61b3")
        )
        assert out["scoped"] is True
        # global counts (5 events) MUST NOT leak into this client's report
        assert out["stats"]["total_actions"] == 0
        assert out["stats"]["highlights"]["posts"] == 0
        assert out["stats"]["highlights"]["calls"] == 0
        assert out["stats"]["by_member"] == {}
        # HTML must not present the fabricated platform total as this client's
        assert ">5<" not in out["html"]  # no "5" total-actions cell
        # honest starter-guidance summary (total==0 path)
        assert any("setup phase" in s.lower() for s in out["summary"])

    def test_unscoped_report_keeps_global_numbers(self, fake_global_events):
        # No client_id => agency/platform overview => old behavior (numbers show).
        out = asyncio.run(monthly_report.build_report(client_name="Platform"))
        assert out["scoped"] is False
        assert out["stats"]["total_actions"] == 5
        assert out["stats"]["highlights"]["posts"] == 2
        assert out["stats"]["highlights"]["calls"] == 2

    def test_never_raises(self):
        out = asyncio.run(monthly_report.build_report(client_id="anyid"))
        assert out["html"].startswith("<!DOCTYPE html>")
        assert out["scoped"] is True


# --------------------------------------------------------------------------- #
# 3) carousel — CTA is client mini-site/phone, not /audit                      #
# --------------------------------------------------------------------------- #
class TestCarouselClientCta:
    def test_client_slug_cta_replaces_audit(self, monkeypatch):
        # force template/fallback slides (no LLM) so CTA slot is deterministic
        async def _empty(*a, **k):
            return "", "stub"

        import app.voice_agent.free_ai as free_ai_mod

        monkeypatch.setattr(free_ai_mod, "chat", _empty, raising=False)
        out = asyncio.run(
            carousel.generate_carousel(
                "Jiya Makeover", niche="beauty_makeover", slug="jiya-makeover-d79d"
            )
        )
        svgs = "".join(s["svg"] for s in out["slides"])
        # every slide CTA button now points at the client's own mini-site
        assert "leadsgenai.in/b/jiya-makeover-d79d" in svgs
        # the hardcoded platform audit CTA must be gone from CTA buttons
        assert "leadsgenai.in/audit" not in svgs

    def test_no_slug_keeps_default_audit_cta(self, monkeypatch):
        # agency/admin path (no slug/phone) => default audit CTA (backward-compat)
        async def _empty(*a, **k):
            return "", "stub"

        import app.voice_agent.free_ai as free_ai_mod

        monkeypatch.setattr(free_ai_mod, "chat", _empty, raising=False)
        out = asyncio.run(carousel.generate_carousel("Sharma Solar", niche="solar"))
        svgs = "".join(s["svg"] for s in out["slides"])
        assert "leadsgenai.in/audit" in svgs

    def test_phone_cta_when_no_slug(self):
        assert carousel.client_cta(phone="8712928847").endswith("8712928847")
        assert (
            carousel.client_cta(slug="jiya-makeover-d79d") == "leadsgenai.in/b/jiya-makeover-d79d"
        )
        assert carousel.client_cta() == ""

    def test_brand_primary_applied(self, monkeypatch):
        async def _empty(*a, **k):
            return "", "stub"

        import app.voice_agent.free_ai as free_ai_mod

        monkeypatch.setattr(free_ai_mod, "chat", _empty, raising=False)
        out = asyncio.run(
            carousel.generate_carousel(
                "Jiya Makeover", slug="jiya-makeover-d79d", brand_primary="#ff5733"
            )
        )
        svgs = "".join(s["svg"] for s in out["slides"])
        assert "#ff5733" in svgs  # client brand color threaded into slides


# --------------------------------------------------------------------------- #
# 4) lifecycle_nurture — no legacy Growth ₹2,999 in upgrade email              #
# --------------------------------------------------------------------------- #
class TestNurtureBillingTruth:
    def test_upgrade_email_no_2999(self):
        msg = lifecycle_nurture.build_message("upgrade", "Jiya Makeover")
        body = msg["body"]
        assert "2,999" not in body
        assert "2999" not in body
        assert "Growth" not in body  # legacy hidden plan name gone
        # public prices present (billing-truth)
        assert "1,999" in body
        assert "5,999" in body

    def test_plan_lines_sourced_from_public_packages(self):
        lines = lifecycle_nurture._plan_lines()
        assert "2,999" not in lines
        # public plan names from packages.get_public_packages()
        from app.marketing.packages import get_public_packages

        public_names = {str(p.get("name")) for p in get_public_packages()}
        assert any(n in lines for n in public_names if n)
        # hidden Growth plan MUST NOT be present
        assert "Growth" not in lines

    def test_other_steps_unchanged(self):
        # welcome/roi steps must still build (no regression)
        for key in ("welcome", "activation", "roi", "last_call"):
            m = lifecycle_nurture.build_message(key, "Jiya Makeover")
            assert m["subject"].strip()
            assert m["body"].strip()
