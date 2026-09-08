"""Ingest-gate contract tests (backlog 2026-07-05: SERP-junk in ready pool).

`ingest_reject_reason` pure function hai (no env/IO) — junk SERP titles reject,
real business names accept. Flag helper HARVEST_INGEST_VALIDATION default-ON.
"""

from app.platform.lead_harvester import ingest_reject_reason, ingest_validation_enabled

P = "9822012345"  # valid-looking 10-digit mobile
E = "owner@business.in"


class TestJunkTitles:
    def test_top_n_listicle_rejected(self):
        assert ingest_reject_reason("Top 10 Home Loan Providers in Pune", P, "", "websearch")

    def test_n_best_listicle_rejected(self):
        assert ingest_reject_reason("10 Best Interior Designers", P, "", "websearch")

    def test_year_listicle_rejected(self):
        assert ingest_reject_reason("Best Coaching Institutes in Nagpur 2026", P, "", "websearch")

    def test_pipe_title_rejected(self):
        assert ingest_reject_reason("Sharma Interiors | Justdial", P, "", "websearch")

    def test_domain_in_name_rejected(self):
        assert ingest_reject_reason("HomeLoans.in - Apply Online", P, "", "websearch")

    def test_helpline_phrase_rejected(self):
        assert ingest_reject_reason("HDFC Bank Customer Care Helpline", P, "", "websearch")

    def test_official_railway_entity_rejected(self):
        assert ingest_reject_reason("IRCTC Customer Care", P, "", "google_maps")
        assert ingest_reject_reason("Indian Railways Reservation Office", P, "", "osm")

    def test_interest_rate_page_rejected(self):
        assert ingest_reject_reason("Home Loan Interest Rates Comparison", P, "", "websearch")

    def test_overlong_page_title_rejected(self):
        assert ingest_reject_reason("A" * 91, P, "", "websearch") == "name_too_long"


class TestRealNamesAccepted:
    def test_plain_business_name_ok(self):
        assert ingest_reject_reason("Sharma Interiors", P, "", "websearch") == ""

    def test_hinglish_name_ok(self):
        assert ingest_reject_reason("Jiya Makeover Studio", P, "", "osm") == ""

    def test_single_dash_name_ok(self):
        assert ingest_reject_reason("Sai Solar - Pune", P, "", "osm") == ""

    def test_airport_word_alone_is_not_junk(self):
        assert ingest_reject_reason("Hotel Airport Centre Point", P, "", "osm") == ""

    def test_opendata_seed_no_contact_ok(self):
        # Udyam seeds phone-less hote hain — structured source, allow (needs_enrich path)
        assert ingest_reject_reason("SHREE GANESH FABRICATORS", "", "", "opendata") == ""

    def test_empty_name_passthrough(self):
        # empty-name handling existing persist logic ka kaam hai, gate ka nahi
        assert ingest_reject_reason("", "", "", "websearch") == ""


class TestWebsearchContactRequirement:
    def test_websearch_no_contact_rejected(self):
        assert (
            ingest_reject_reason("Sharma Interiors", "", "", "websearch") == "websearch_no_contact"
        )

    def test_websearch_email_only_ok(self):
        assert ingest_reject_reason("Sharma Interiors", "", E, "websearch") == ""


class TestFlagDefault:
    def test_default_on(self, monkeypatch):
        monkeypatch.delenv("HARVEST_INGEST_VALIDATION", raising=False)
        assert ingest_validation_enabled() is True

    def test_kill_switch(self, monkeypatch):
        monkeypatch.setenv("HARVEST_INGEST_VALIDATION", "0")
        assert ingest_validation_enabled() is False

    def test_registered_in_automation_flags(self):
        from app.api.automation_flags import AUTOMATION_FLAGS

        assert "HARVEST_INGEST_VALIDATION" in AUTOMATION_FLAGS
