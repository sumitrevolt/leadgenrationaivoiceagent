"""W1.6 — audit/site tracked URLs are computed lazily (not at module import).

Bug: `_AUDIT_URL_TRACKED = _track_url(_AUDIT_URL)` (+ the site one) ran at MODULE
IMPORT time, firing a live is.gd/tracked-link network call just to import
`auto_outreach` (slow / hang-prone import; runs in prod_check too).

Fix: a lazy, memoized accessor computes the tracked URL on first use and caches it.
This test proves the accessor is lazy + cached (one `_track_url` call across many uses).
The "not at import" half is guaranteed structurally — the module no longer holds a
top-level `= _track_url(...)` assignment (grep-verified in the loop).
"""

from __future__ import annotations

import app.platform.auto_outreach as ao


def test_audit_tracked_url_is_lazy_and_cached(monkeypatch):
    calls = {"n": 0}

    def _spy(url, campaign="cold_email"):
        calls["n"] += 1
        return f"{url}#tracked"

    monkeypatch.setattr(ao, "_track_url", _spy)
    monkeypatch.setattr(ao, "_AUDIT_TRACKED_CACHE", None)

    first = ao._audit_url_tracked()
    second = ao._audit_url_tracked()

    assert first.endswith("#tracked")
    assert first == second
    assert calls["n"] == 1, "tracked URL must be computed once (lazy + cached), not per use"


def test_site_tracked_url_is_lazy_and_cached(monkeypatch):
    calls = {"n": 0}

    def _spy(url, campaign="cold_email"):
        calls["n"] += 1
        return f"{url}#site"

    monkeypatch.setattr(ao, "_track_url", _spy)
    monkeypatch.setattr(ao, "_SITE_TRACKED_CACHE", None)

    assert ao._site_url_tracked().endswith("#site")
    ao._site_url_tracked()
    assert calls["n"] == 1
