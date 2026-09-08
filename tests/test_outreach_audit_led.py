"""
Tests: audit-led first-touch outreach (OUTREACH_AUDIT_LED, default OFF).
====================================================================

Pure python, NO network / SMTP. Covers:
  - _audit_gap priority logic (website / low-rating / low-reviews / niche / none)
  - flag ON  -> subject + first body line carry an "audit gap" fragment
  - flag OFF -> first-touch email is the existing generic pattern (no gap)
  - additive guarantees: audit link + unsubscribe + footer ALWAYS present

Flag is read at call-time via _audit_led_on() (env OUTREACH_AUDIT_LED or
settings.outreach_audit_led). Tests force it ON/OFF with monkeypatch.setenv.
"""

import pytest

from app.platform import auto_outreach


# --------------------------------------------------------------------------- #
# _audit_gap — priority logic
# --------------------------------------------------------------------------- #
class TestAuditGap:
    def test_no_website_flag_false(self):
        gap = auto_outreach._audit_gap(
            {"business_name": "Sharma Solar", "has_website": False, "rating": 4.8}
        )
        assert "website" in gap.lower()

    def test_no_website_missing_string(self):
        # No has_website flag + empty website string -> website gap.
        gap = auto_outreach._audit_gap({"business_name": "Sharma Solar", "website": ""})
        assert "website" in gap.lower()

    def test_low_rating(self):
        # Has a website, but rating < 4.0 -> rating gap.
        gap = auto_outreach._audit_gap(
            {
                "business_name": "Sharma Solar",
                "website": "https://sharmasolar.in",
                "has_website": True,
                "rating": 3.4,
                "reviews_count": 40,
            }
        )
        assert "3.4" in gap and "rating" in gap.lower()

    def test_low_reviews(self):
        # Good rating + website, but very few reviews -> reviews gap.
        gap = auto_outreach._audit_gap(
            {
                "business_name": "Sharma Solar",
                "website": "https://sharmasolar.in",
                "has_website": True,
                "rating": 4.6,
                "reviews_count": 2,
            }
        )
        assert "review" in gap.lower()

    def test_niche_flavored_generic(self):
        # Website present, good rating, healthy reviews -> niche-flavored gap.
        gap = auto_outreach._audit_gap(
            {
                "business_name": "Sharma Solar",
                "website": "https://sharmasolar.in",
                "has_website": True,
                "rating": 4.7,
                "reviews_count": 120,
                "niche": "solar_residential",
            }
        )
        assert gap  # non-empty
        assert "solar residential" in gap  # underscore -> space, niche-flavored

    def test_complete_prospect_no_niche_returns_empty(self):
        # Everything good and NO niche/category -> no gap.
        gap = auto_outreach._audit_gap(
            {
                "business_name": "Sharma Solar",
                "website": "https://sharmasolar.in",
                "has_website": True,
                "rating": 4.7,
                "reviews_count": 120,
            }
        )
        assert gap == ""

    def test_never_raises_on_garbage(self):
        # Bad types must NOT raise — must return a string (never throw).
        # ({} and the garbage prospect both lack website info, so by priority
        # rule #1 they fall to the website gap — the point is: no exception.)
        assert isinstance(auto_outreach._audit_gap({}), str)
        assert isinstance(
            auto_outreach._audit_gap({"rating": "nonsense", "reviews_count": "x"}), str
        )

    def test_empty_prospect_returns_website_gap(self):
        # Empty/None prospect has no website signal -> website gap (rule #1).
        assert "website" in auto_outreach._audit_gap({}).lower()
        assert "website" in auto_outreach._audit_gap(None).lower()


# --------------------------------------------------------------------------- #
# _email_subject_body — flag ON weaves the gap
# --------------------------------------------------------------------------- #
class TestAuditLedSubjectBody:
    @pytest.fixture
    def gappy(self):
        # Low rating -> deterministic "rating ... gap".
        return {
            "business_name": "Sharma Solar",
            "city": "Pune",
            "website": "https://sharmasolar.in",
            "has_website": True,
            "rating": 3.2,
            "reviews_count": 40,
            "email": "info@sharmasolar.in",
        }

    def test_flag_on_subject_and_body_carry_gap(self, gappy, monkeypatch):
        monkeypatch.setenv("OUTREACH_AUDIT_LED", "1")
        subject, text, html = auto_outreach._email_subject_body(gappy)
        # gap fragment ("3.2" rating) is woven into subject + first body line
        assert "3.2" in subject
        assert "3.2" in text
        assert "3.2" in html
        # additive guarantees: link + unsubscribe + footer still present
        assert auto_outreach._audit_url_tracked() in text  # W1.6 lazy accessor (tracked link)
        assert "REMOVE" in text
        assert "LeadGen AI" in text
        assert "Sharma Solar" in subject

    def test_flag_off_is_generic_no_gap(self, gappy, monkeypatch):
        # Flag explicitly OFF (no env; settings has no such attr -> default False).
        monkeypatch.delenv("OUTREACH_AUDIT_LED", raising=False)
        subject, text, html = auto_outreach._email_subject_body(gappy)
        # existing generic subject pattern
        assert subject == "Sharma Solar — aapka Google profile (free audit)"
        # gap fragment must NOT appear in the subject
        assert "3.2" not in subject
        # mandatory pieces still present (unchanged path)
        assert auto_outreach._audit_url_tracked() in text  # W1.6 lazy accessor (tracked link)
        assert "REMOVE" in text

    def test_flag_on_but_no_gap_is_generic(self, monkeypatch):
        # Flag ON but a "complete" prospect with no derivable gap -> generic.
        monkeypatch.setenv("OUTREACH_AUDIT_LED", "1")
        complete = {
            "business_name": "Sharma Solar",
            "city": "Pune",
            "website": "https://sharmasolar.in",
            "has_website": True,
            "rating": 4.7,
            "reviews_count": 120,
            "email": "info@sharmasolar.in",
        }
        subject, text, html = auto_outreach._email_subject_body(complete)
        # _audit_gap returns "" here -> generic subject, additive branch no-op
        assert subject == "Sharma Solar — aapka Google profile (free audit)"
        assert "REMOVE" in text


# --------------------------------------------------------------------------- #
# Default-OFF behavior is byte-for-byte identical (no env, no settings attr)
# --------------------------------------------------------------------------- #
class TestDefaultOff:
    def test_audit_led_off_by_default(self, monkeypatch):
        monkeypatch.delenv("OUTREACH_AUDIT_LED", raising=False)
        # settings has no outreach_audit_led attr by default -> getattr False.
        assert auto_outreach._audit_led_on() is False

    def test_default_subject_unchanged(self, monkeypatch):
        # With the flag at its default (OFF), the subject equals the
        # pre-existing generic template exactly.
        monkeypatch.delenv("OUTREACH_AUDIT_LED", raising=False)
        prospect = {
            "business_name": "Sharma Solar",
            "city": "Pune",
            "rating": 3.2,  # would be gappy IF the flag were on
            "reviews_count": 1,
            "email": "info@sharmasolar.in",
        }
        subject, text, html = auto_outreach._email_subject_body(prospect)
        assert subject == "Sharma Solar — aapka Google profile (free audit)"
