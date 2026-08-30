"""Tests for Jio Mobile SIP Trunk scaffold (INERT-default).
No real calls, no provider creds. Just config + readiness + dispatcher.

Plan doc: docs/coordination/JIO_SIP_SETUP_PLAN.md
"""

from __future__ import annotations

import importlib
import os

import pytest

# --- helpers ---


def _reload_modules():
    """Reload trunks + readiness so env changes take effect."""
    import app.telephony.telephony_readiness as readiness
    import app.telephony.trunks as trunks

    importlib.reload(trunks)
    importlib.reload(readiness)
    return trunks, readiness


@pytest.fixture(autouse=True)
def _clean_jio_env(monkeypatch):
    """Strip all JIO_* env before each test."""
    for k in list(os.environ):
        if k.startswith("JIO_"):
            monkeypatch.delenv(k, raising=False)
    yield


# --- dispatcher ---


def test_pick_trunk_returns_none_when_no_creds(monkeypatch):
    monkeypatch.delenv("VOBIZ_AUTH_ID", raising=False)
    monkeypatch.delenv("VOBIZ_AUTH_TOKEN", raising=False)
    trunks, _ = _reload_modules()
    provider, cid = trunks.pick_trunk()
    assert provider == "none"
    assert cid == ""


def test_jio_creds_present_but_disabled_returns_only_vobiz(monkeypatch):
    monkeypatch.setenv("VOBIZ_AUTH_ID", "VA")
    monkeypatch.setenv("VOBIZ_AUTH_TOKEN", "VT")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+919999999999")
    monkeypatch.setenv("JIO_SIP_HOST", "sip.jio.in")
    monkeypatch.setenv("JIO_SIP_USER", "leadgen")
    monkeypatch.setenv("JIO_SIP_PASS", "secret")
    monkeypatch.setenv("JIO_SIP_DID", "+918888888888")
    # JIO_TRUNK_ENABLED NOT set → INERT
    trunks, _ = _reload_modules()
    active = trunks.list_active_trunks()
    names = [t.name for t in active]
    assert "vobiz" in names
    assert "jio_mobile" not in names, "Jio must be INERT when JIO_TRUNK_ENABLED=0"


def test_jio_enabled_no_did_pick_returns_none(monkeypatch):
    """Without DID, list_active_trunks shows it (DID-empty is config error)
    but pick_trunk skips it (caller_id filter) → returns ('none', '')."""
    monkeypatch.setenv("JIO_SIP_HOST", "sip.jio.in")
    monkeypatch.setenv("JIO_SIP_USER", "leadgen")
    monkeypatch.setenv("JIO_SIP_PASS", "secret")
    monkeypatch.setenv("JIO_TRUNK_ENABLED", "1")
    # No JIO_SIP_DID, no Vobiz creds
    trunks, _ = _reload_modules()
    active = trunks.list_active_trunks()
    # jio_mobile is in active list (config is set, just no DID)
    assert any(t.name == "jio_mobile" for t in active)
    # But pick_trunk filters out empty caller_id
    provider, cid = trunks.pick_trunk()
    assert provider == "none"
    assert cid == ""


def test_jio_enabled_with_creds_and_did_appears(monkeypatch):
    monkeypatch.setenv("JIO_SIP_HOST", "sip.jio.in")
    monkeypatch.setenv("JIO_SIP_USER", "leadgen")
    monkeypatch.setenv("JIO_SIP_PASS", "secret")
    monkeypatch.setenv("JIO_SIP_DID", "+918888888888")
    monkeypatch.setenv("JIO_TRUNK_ENABLED", "1")
    trunks, _ = _reload_modules()
    active = trunks.list_active_trunks()
    jio = [t for t in active if t.name == "jio_mobile"]
    assert len(jio) == 1
    t = jio[0]
    assert t.caller_id == "+918888888888"
    assert t.max_concurrent == 10  # default
    assert t.cost_per_min_inr == 0.0  # flat unlimited
    assert t.enabled is True


def test_pick_trunk_vobiz_only(monkeypatch):
    monkeypatch.setenv("VOBIZ_AUTH_ID", "VA")
    monkeypatch.setenv("VOBIZ_AUTH_TOKEN", "VT")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+919999999999")
    trunks, _ = _reload_modules()
    provider, cid = trunks.pick_trunk()
    assert provider == "vobiz"
    assert cid == "+919999999999"


def test_pick_trunk_round_robin_distribution(monkeypatch):
    """1000 picks should distribute roughly per weight."""
    monkeypatch.setenv("VOBIZ_AUTH_ID", "VA")
    monkeypatch.setenv("VOBIZ_AUTH_TOKEN", "VT")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+919999999999")
    monkeypatch.setenv("JIO_SIP_HOST", "sip.jio.in")
    monkeypatch.setenv("JIO_SIP_USER", "leadgen")
    monkeypatch.setenv("JIO_SIP_PASS", "secret")
    monkeypatch.setenv("JIO_SIP_DID", "+918888888888")
    monkeypatch.setenv("JIO_TRUNK_ENABLED", "1")
    # Both default weight=50, expect ~50/50 distribution
    trunks, _ = _reload_modules()
    counts = {"vobiz": 0, "jio_mobile": 0}
    for _ in range(1000):
        provider, _ = trunks.pick_trunk()
        counts[provider] += 1
    # Allow ±10% tolerance
    assert 400 < counts["vobiz"] < 600
    assert 400 < counts["jio_mobile"] < 600


# --- FreeSWITCH gateway XML ---


def test_gateway_xml_ip_auth(monkeypatch):
    monkeypatch.setenv("JIO_SIP_HOST", "sip.jio.in")
    monkeypatch.setenv("JIO_SIP_REALM", "jio.in")
    monkeypatch.setenv("JIO_SIP_AUTH_MODE", "ip")
    monkeypatch.setenv("JIO_SIP_TRANSPORT", "udp")
    monkeypatch.setenv("JIO_SIP_FROM_DOMAIN", "leadsgenai.in")
    monkeypatch.setenv("JIO_SIP_USER", "leadgen")
    monkeypatch.setenv("JIO_SIP_PASS", "secret")
    monkeypatch.setenv("JIO_SIP_DID", "+918888888888")
    monkeypatch.setenv("JIO_TRUNK_ENABLED", "1")
    trunks, _ = _reload_modules()
    active = [t for t in trunks.list_active_trunks() if t.name == "jio_mobile"]
    assert len(active) == 1
    xml = trunks.freeswitch_gateway_xml(active[0])
    assert 'name="jio_mobile"' in xml
    assert 'proxy" value="sip.jio.in"' in xml
    assert 'register" value="false"' in xml  # IP-auth
    assert "username" not in xml  # NO creds in IP-auth mode
    assert "codec-prefs" in xml


def test_gateway_xml_registration_mode(monkeypatch):
    monkeypatch.setenv("JIO_SIP_HOST", "sip.jio.in")
    monkeypatch.setenv("JIO_SIP_REALM", "jio.in")
    monkeypatch.setenv("JIO_SIP_AUTH_MODE", "registration")
    monkeypatch.setenv("JIO_SIP_TRANSPORT", "udp")
    monkeypatch.setenv("JIO_SIP_FROM_DOMAIN", "leadsgenai.in")
    monkeypatch.setenv("JIO_SIP_USER", "leadgen")
    monkeypatch.setenv("JIO_SIP_PASS", "secret")
    monkeypatch.setenv("JIO_SIP_DID", "+918888888888")
    monkeypatch.setenv("JIO_TRUNK_ENABLED", "1")
    trunks, _ = _reload_modules()
    active = [t for t in trunks.list_active_trunks() if t.name == "jio_mobile"]
    xml = trunks.freeswitch_gateway_xml(active[0])
    assert 'register" value="true"' in xml
    assert 'username" value="leadgen"' in xml
    assert 'password" value="secret"' in xml


# --- readiness gate ---


def test_readiness_includes_jio_checks(monkeypatch):
    _, readiness = _reload_modules()
    # Default: no JIO_* env, so checks should report missing
    r = readiness.run_checks()
    assert "jio_sip_creds" in r["checks"]
    assert "jio_sip_did" in r["checks"]
    assert "jio_sip_enabled" in r["checks"]
    assert r["checks"]["jio_sip_creds"]["ok"] is False
    assert r["checks"]["jio_sip_did"]["ok"] is False
    assert r["checks"]["jio_sip_enabled"]["ok"] is False


def test_readiness_jio_creds_pass_when_set(monkeypatch):
    monkeypatch.setenv("JIO_SIP_HOST", "sip.jio.in")
    monkeypatch.setenv("JIO_SIP_USER", "leadgen")
    monkeypatch.setenv("JIO_SIP_PASS", "secret")
    monkeypatch.setenv("JIO_SIP_DID", "+918888888888")
    _, readiness = _reload_modules()
    r = readiness.run_checks()
    assert r["checks"]["jio_sip_creds"]["ok"] is True
    assert r["checks"]["jio_sip_did"]["ok"] is True
    # Enabled flag still OFF (intentional)
    assert r["checks"]["jio_sip_enabled"]["ok"] is False


def test_readiness_jio_enabled_after_live_test(monkeypatch):
    """JIO_TRUNK_ENABLED=1 → readiness flag goes green."""
    monkeypatch.setenv("JIO_SIP_HOST", "sip.jio.in")
    monkeypatch.setenv("JIO_SIP_USER", "leadgen")
    monkeypatch.setenv("JIO_SIP_PASS", "secret")
    monkeypatch.setenv("JIO_SIP_DID", "+918888888888")
    monkeypatch.setenv("JIO_TRUNK_ENABLED", "1")
    _, readiness = _reload_modules()
    r = readiness.run_checks()
    assert r["checks"]["jio_sip_creds"]["ok"] is True
    assert r["checks"]["jio_sip_did"]["ok"] is True
    assert r["checks"]["jio_sip_enabled"]["ok"] is True
