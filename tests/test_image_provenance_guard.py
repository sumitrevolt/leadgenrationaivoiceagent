"""ADR-097 — the production image must carry commit provenance, LOUDLY.

WHY this test exists (2026-07-14): `docker-compose.vps.yml` tags
`${APP_VERSION:-latest}`. A deploy that forgot APP_VERSION silently left prod on
an UNVERSIONED `:latest` image, so /health reported version "latest" and nobody
could tell what code was running. Production then sat on STALE code while fixes
were merged to main and never shipped:

  - `/api/voice/niches` (paid Voice Agent revenue route) returned 500 for SIX
    DAYS (~872 Sentry events across PYTHON-G/H/M/R) although the fix was in main,
  - ~277 `app.middleware._record` event-loop errors,
  - qdrant `fastembed model not ready within 90s` (fail_rate 1.0),

and ALL of them went to zero the moment the image was rebuilt with a real SHA.
Silent drift is the most expensive failure mode in this repo — hence fail-LOUD.

Offline/pure — no app startup, no network.
"""

from __future__ import annotations

from app.main import is_unversioned_production_image as unversioned


def test_compose_default_latest_is_flagged_in_production():
    # `${APP_VERSION:-latest}` — the exact value that caused the 6-day outage.
    assert unversioned("latest", "production") is True
    assert unversioned("LATEST", "production") is True  # case-insensitive


def test_unset_or_placeholder_versions_are_flagged_in_production():
    for bad in ("", "   ", None, "dev", "1.0.0"):
        assert unversioned(bad, "production") is True, bad


def test_real_git_sha_is_accepted():
    for good in ("91e7d37", "1feed53", "a8340a4d4556e42c85c0eb7cdd6aa9ea9705d27a"):
        assert unversioned(good, "production") is False, good


def test_non_production_is_never_flagged():
    """Dev/staging legitimately run unversioned images — never page for those."""
    for env in ("development", "staging", "test", "", None):
        assert unversioned("latest", env) is False, env


def test_env_and_version_are_whitespace_and_case_tolerant():
    assert unversioned(" latest ", " Production ") is True
    assert unversioned(" 1feed53 ", "PRODUCTION") is False
