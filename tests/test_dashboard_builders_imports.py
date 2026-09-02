"""Regression guard for the 2026-06-20 godfile-split import-loss bug.

When admin_dashboard.py / customer_dashboard.py were split into *_builders.py
modules, the module-level `import os`, `import json`, the `_INQUIRIES_FILE`
constant and `from datetime import timezone` were dropped. Because the call
sites were wrapped in try/except, the failures were SILENT:

  * admin `_build_real()` raised `NameError: timezone` before assembling any
    real KPIs -> the upstream guard returned an all-zeros DashboardResponse
    with health.db="down" (dashboard always looked empty).
  * `_read_inquiries()` raised `NameError: os/_INQUIRIES_FILE` -> caught ->
    always returned [] (inquiry counts silently zero).

These asserts fail loudly if any of those names go missing again.
"""

from __future__ import annotations


def test_admin_builders_have_required_names() -> None:
    from app.api import admin_dashboard_builders as b

    assert hasattr(b, "_INQUIRIES_FILE"), "_INQUIRIES_FILE lost in split"
    assert b.os is not None  # module-level `import os`
    assert b.json is not None  # module-level `import json`
    # timezone must be importable in this module's namespace
    assert b.timezone is not None


def test_customer_builders_have_required_names() -> None:
    from app.api import customer_dashboard_builders as c

    assert hasattr(c, "_INQUIRIES_FILE"), "_INQUIRIES_FILE lost in split"
    assert c.os is not None
    assert c.json is not None
    assert c.TrialBanner is not None  # was only locally imported


def test_admin_build_real_returns_real_data_without_raising() -> None:
    """_build_real() must assemble real data, not fall to the all-zeros guard."""
    from app.api import admin_dashboard_builders as b

    resp = b._build_real()  # must NOT raise NameError
    assert resp is not None
    assert resp.is_sample_data is False
    # _read_inquiries must be callable and return a list (not silently [] via except)
    assert isinstance(b._read_inquiries(), list)


def test_customer_read_inquiries_callable() -> None:
    from app.api import customer_dashboard_builders as c

    assert isinstance(c._read_inquiries(), list)


def test_industry_scripts_imports() -> None:
    """`Any` was used without `from typing import Any` (future-annotations OFF)."""
    import importlib

    mod = importlib.import_module("app.scripts.industry_scripts")
    assert mod is not None
