"""Contract: admin + customer office payloads advertise ONE canonical schema
version, from a single source of truth. Additive field — Unity ignores unknowns.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.platform.office_schema import UNITY_OFFICE_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_version_format():
    assert re.fullmatch(r"unity-office/\d+\.\d+", UNITY_OFFICE_SCHEMA_VERSION)


def test_both_payload_builders_stamp_the_shared_constant():
    admin = (ROOT / "app" / "platform" / "office_hq.py").read_text(encoding="utf-8")
    cust = (ROOT / "app" / "api" / "customer_dashboard_builders.py").read_text(encoding="utf-8")
    api = (ROOT / "app" / "api" / "office_hq.py").read_text(encoding="utf-8")
    for src in (admin, cust, api):
        assert "UNITY_OFFICE_SCHEMA_VERSION" in src
        assert '"schema_version"' in src


def test_customer_office_payload_includes_schema_version():
    # _build_office never raises; both success and degraded returns carry the field.
    from app.api.customer_dashboard_builders import _build_office

    payload = _build_office("nonexistent-client-xyz")
    assert payload.get("schema_version") == UNITY_OFFICE_SCHEMA_VERSION
