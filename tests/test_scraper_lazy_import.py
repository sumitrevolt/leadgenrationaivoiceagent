"""Lead scraper package should stay lazy at import time."""

from __future__ import annotations

import importlib
import sys


def test_scraper_manager_import_does_not_load_sources(monkeypatch):
    target_modules = (
        "app.lead_scraper.scraper_manager",
        "app.lead_scraper.google_maps",
        "app.lead_scraper.indiamart",
        "app.lead_scraper.justdial",
        "app.lead_scraper.linkedin",
        "app.lead_scraper.social_media",
        "app.lead_scraper.web_search",
    )
    for name in target_modules:
        sys.modules.pop(name, None)

    mod = importlib.import_module("app.lead_scraper.scraper_manager")
    assert hasattr(mod, "LeadScraperManager")

    for name in target_modules[1:]:
        assert name not in sys.modules

    from app.lead_scraper import LeadScraperManager

    mgr = LeadScraperManager()
    assert mgr is not None
    for name in target_modules[1:]:
        assert name not in sys.modules
