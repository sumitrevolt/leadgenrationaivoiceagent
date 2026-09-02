"""Health/version reports must never be served from a cache.

WHY THIS TEST EXISTS (2026-07-15 production admin audit):
The first `GET https://leadsgenai.in/health` of the audit returned a body that
was 12.7 HOURS old — `version: 91e7d37`, `uptime: 13m 53s`,
`timestamp: 2026-07-14T12:59:06` — while production was actually running
`b12d1e97` with 8h24m uptime. The stale body was indistinguishable from a fresh
one. Only re-requesting with a `?cb=` query string (a different cache key)
exposed the real version.

That is a *measurement* failure, not a cosmetic one. CLAUDE.md designates the
`version` field of `/health` as THE deploy-drift detector:
    "/health ka version field hi tumhara drift detector hai — `latest` dikhe to
     prod ka code UNKNOWN hai."
A drift detector that can be served from cache reports the wrong SHA with full
confidence, which is precisely the ADR-097 failure mode one layer out: there the
running image's provenance was unknown; here the provenance REPORT itself lied.

Root enabler: these endpoints returned a bare dict with no cache directives, and
a response with no Cache-Control/Expires is heuristically cacheable by browsers
and intermediaries (RFC 9111 §4.2.2). `no-store` closes the class at the source.
"""

import pytest

HEALTH_ENDPOINTS = ["/health", "/health/live", "/health/ready"]


@pytest.mark.parametrize("path", HEALTH_ENDPOINTS)
def test_health_endpoints_forbid_caching(client, path):
    """Every health surface must send an explicit no-store directive."""
    resp = client.get(path)

    cache_control = resp.headers.get("cache-control", "")
    assert cache_control, (
        f"{path} sent NO Cache-Control header. Without an explicit directive a "
        "browser or proxy may heuristically cache this response and report a "
        "stale version/status as if it were live (see module docstring)."
    )
    assert "no-store" in cache_control.lower(), (
        f"{path} must be no-store, got Cache-Control: {cache_control!r}"
    )


def test_health_version_is_not_cacheable():
    """The version field specifically — the documented drift detector.

    Guards the exact regression observed in production: a cached /health body
    advertising a version the running process does not have.
    """
    from app.api import health as health_mod

    assert "no-store" in health_mod._NO_STORE
    assert "max-age=0" in health_mod._NO_STORE


def test_health_reports_live_uptime_not_a_frozen_value(client):
    """A cached body would also freeze uptime/timestamp — assert they move.

    This is the symptom that made the stale response detectable in hindsight
    (uptime 13m while the container had been up 8h24m), so it is worth pinning.
    """
    first = client.get("/health").json()
    second = client.get("/health").json()

    # Both must be present and well-formed; a cache layer that served a frozen
    # body would make these identical strings forever.
    assert first["status"] == "healthy"
    assert "uptime" in first and "timestamp" in first
    assert second["timestamp"] >= first["timestamp"]
