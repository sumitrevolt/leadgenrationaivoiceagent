"""Own-brand auto-approve canary — flag-gated, tenant-isolated, bounded.

VIDEO_OWN_BRAND_AUTO_APPROVE default OFF. When ON, only own-brand allowlist
tenants (leadgenai-self / leadgen-ai) get auto-approved through the canonical
approve_version path with a SYSTEM principal. Customers are never touched.
"""

from __future__ import annotations

import os

from app.marketing.video_production import flags as vflags
from app.marketing.video_production.allowlist import is_own_brand_client_id
from app.marketing.video_production.approval_principal import (
    ApprovalPrincipal,
    PrincipalType,
    from_system_automation,
)


def _clear_flag():
    os.environ.pop("VIDEO_OWN_BRAND_AUTO_APPROVE", None)
    os.environ.pop("VIDEO_OWN_BRAND_AUTO_APPROVE_LIMIT", None)


def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("VIDEO_OWN_BRAND_AUTO_APPROVE", raising=False)
    assert vflags.own_brand_auto_approve_enabled() is False
    assert vflags.own_brand_auto_approve_limit() == 2


def test_flag_on(monkeypatch):
    monkeypatch.setenv("VIDEO_OWN_BRAND_AUTO_APPROVE", "1")
    assert vflags.own_brand_auto_approve_enabled() is True


def test_limit_bounded(monkeypatch):
    monkeypatch.setenv("VIDEO_OWN_BRAND_AUTO_APPROVE_LIMIT", "3")
    assert vflags.own_brand_auto_approve_limit() == 3
    monkeypatch.setenv("VIDEO_OWN_BRAND_AUTO_APPROVE_LIMIT", "0")  # clamp to >=1
    assert vflags.own_brand_auto_approve_limit() == 1
    monkeypatch.setenv("VIDEO_OWN_BRAND_AUTO_APPROVE_LIMIT", "bogus")
    assert vflags.own_brand_auto_approve_limit() == 2


def test_own_brand_allowlist():
    assert is_own_brand_client_id("leadgenai-self") is True
    assert is_own_brand_client_id("leadgen-ai") is True
    assert is_own_brand_client_id("leadgen-ai".upper()) is True  # case-insensitive
    assert is_own_brand_client_id("some-customer") is False
    assert is_own_brand_client_id("") is False


def test_system_principal_is_typed():
    p = from_system_automation("leadgenai-self")
    assert isinstance(p, ApprovalPrincipal)
    assert p.principal_type == PrincipalType.SYSTEM_AUTOMATION
    assert p.subject_id == "system:own_brand_canary"
    assert p.tenant_id == "leadgenai-self"
    assert p.can_approve is True


def test_system_principal_refuses_empty_tenant():
    import pytest

    from app.marketing.video_production.approval_principal import PrincipalRefused

    with pytest.raises(PrincipalRefused):
        from_system_automation("")


def test_auto_approve_noop_when_flag_off(monkeypatch):
    monkeypatch.delenv("VIDEO_OWN_BRAND_AUTO_APPROVE", raising=False)
    from app.marketing.video_production import cell

    out = cell.auto_approve_own_brand_pending()
    assert out.get("ran") is False
    assert "off" in str(out.get("reason") or "")


def test_auto_approve_skips_customer_when_flag_on(monkeypatch):
    """Tenant isolation: a customer's pending video is never auto-approved."""
    import app.marketing.video_ad_cycle as vac
    from app.marketing.video_production import cell

    monkeypatch.setenv("VIDEO_OWN_BRAND_AUTO_APPROVE", "1")
    # Patch list_all to return one OWN-brand pending + one CUSTOMER pending.
    monkeypatch.setattr(
        vac,
        "list_all",
        lambda _limit=200: [
            {"id": "own1", "client_id": "leadgenai-self", "status": "pending", "revision": 0},
            {"id": "cust1", "client_id": "customer-x", "status": "pending", "revision": 0},
        ],
    )
    calls = []

    def _fake_approve(video_ad_id, expected_revision=None, principal=None, expected_sha256=""):
        calls.append(video_ad_id)
        return {"ok": True}

    monkeypatch.setattr(cell, "approve_version", _fake_approve)
    out = cell.auto_approve_own_brand_pending(limit=5)
    assert out.get("ran") is True
    # Only the own-brand row was approved; the customer row was skipped.
    assert calls == ["own1"]
