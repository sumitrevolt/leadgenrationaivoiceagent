"""
/for/{slug} programmatic SEO landing page — contract tests.

Covers a real bug found by an SEO audit: the canonical tag was built from the
raw (non-lowercased) slug and was a relative path, so mixed-case URL variants
(e.g. /for/Dental-in-Mumbai) each self-canonicalized instead of consolidating
onto one indexable URL, and the JSON-LD url could double-concatenate the
domain if canonical were ever made absolute without updating both call sites.
"""

from fastapi.testclient import TestClient


def test_canonical_is_absolute_and_lowercase_normalized():
    from app.main import app

    with TestClient(app) as c:
        r = c.get("/for/Dental-in-Mumbai")
        assert r.status_code == 200
        html = r.text
        assert 'href="https://leadsgenai.in/for/dental-in-mumbai"' in html
        # Guard against the domain being concatenated twice onto an
        # already-absolute canonical (the exact bug this test was added for).
        assert "leadsgenai.inhttps://" not in html
        assert html.count("leadsgenai.in/for/dental-in-mumbai") == 2  # canonical + JSON-LD


def test_json_ld_url_matches_canonical_exactly():
    from app.main import app

    with TestClient(app) as c:
        r = c.get("/for/restaurant-in-delhi")
        assert r.status_code == 200
        html = r.text
        assert '"url":"https://leadsgenai.in/for/restaurant-in-delhi"' in html


def test_invalid_slug_returns_404_not_500():
    from app.main import app

    with TestClient(app) as c:
        r = c.get("/for/" + ("a" * 200))
        assert r.status_code == 404
        r2 = c.get("/for/<script>alert(1)</script>")
        assert r2.status_code == 404
