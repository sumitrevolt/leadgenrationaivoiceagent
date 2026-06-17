"""Activation-readiness probe — admin endpoint behavior matrix.

The probe must:
- Distinguish BLOCKER (revenue/trust) from WARN (visibility) from NEUTRAL (opt-in).
- Catch the exact 2026-06-14 root cause: placeholder Razorpay keys that look set.
- Stay shape-check only — never make outbound calls.
- Flip `ready_for_first_paid_customer` to true only when zero BLOCKERs remain.
"""

from __future__ import annotations

import os

import pytest

from app.api import activation as ax


# --------------------------------------------------------------------------- #
# Per-probe logic (no FastAPI — pure functions, deterministic)
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every env var any probe might read so each test starts from zero."""
    for k in (
        "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET",
        "SENTRY_DSN", "ENVIRONMENT", "APP_ENV",
        "POSTHOG_API_KEY", "POSTHOG_HOST",
        "TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY",
        "CLOUDFLARE_TUNNEL_TOKEN",
    ):
        monkeypatch.delenv(k, raising=False)


def test_razorpay_unset_is_deferred_neutral() -> None:
    r = ax._razorpay()
    assert r["status"] == "NEUTRAL"
    assert r["checks"]["deferred"] is True


def test_razorpay_placeholder_keys_are_neutral_not_blocker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Placeholder keys = deferred; marketing launch not blocked."""
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_you-key-here")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "your-razorpay-secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "anything")
    r = ax._razorpay()
    assert r["status"] == "NEUTRAL"
    assert r["checks"]["key_id_placeholder"] is True
    assert r["checks"]["secret_placeholder"] is True


def test_razorpay_test_keys_deferred(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_realLookingKey")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "real-looking-secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "whs")
    r = ax._razorpay()
    assert r["status"] == "NEUTRAL"
    assert r["checks"]["key_id_live"] is False


def test_razorpay_live_keys_without_webhook_is_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Live keys set but webhook unset = degraded but not revenue-blocking."""
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live_realKey")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "real-secret")
    r = ax._razorpay()
    assert r["status"] == "WARN"
    assert "WEBHOOK" in r["action"].upper()


def test_razorpay_fully_armed_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live_realKey")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "real-secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "whs")
    r = ax._razorpay()
    assert r["status"] == "OK"
    assert r["action"] == ""


def test_sentry_unset_is_warn_not_blocker() -> None:
    r = ax._sentry()
    assert r["status"] == "WARN"  # not a blocker — funnel runs without it


def test_sentry_armed_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTRY_DSN", "https://x@o.ingest.sentry.io/1")
    monkeypatch.setenv("ENVIRONMENT", "production")
    r = ax._sentry()
    assert r["status"] == "OK"


def test_sentry_armed_but_dev_env_is_neutral(monkeypatch: pytest.MonkeyPatch) -> None:
    """DSN set but ENVIRONMENT not production -> init code skips. Worth surfacing."""
    monkeypatch.setenv("SENTRY_DSN", "https://x@o.ingest.sentry.io/1")
    r = ax._sentry()
    assert r["status"] == "NEUTRAL"
    assert "production" in r["action"].lower()


def test_posthog_unset_is_warn() -> None:
    r = ax._posthog()
    assert r["status"] == "WARN"


def test_posthog_armed_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_realKey")
    r = ax._posthog()
    assert r["status"] == "OK"


def test_turnstile_unset_is_warn() -> None:
    r = ax._turnstile()
    assert r["status"] == "WARN"


def test_turnstile_partial_arming_is_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Just site-key without secret = widget renders but server can't verify."""
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "pk_abc")
    r = ax._turnstile()
    assert r["status"] == "WARN"


def test_turnstile_armed_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "pk_abc")
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "sk_xyz")
    r = ax._turnstile()
    assert r["status"] == "OK"


def test_cloudflare_tunnel_unset_is_neutral_not_blocker() -> None:
    """Origin-hide is opt-in — absence is neutral, not a blocker."""
    r = ax._cloudflare_tunnel()
    assert r["status"] == "NEUTRAL"


def test_cloudflare_tunnel_armed_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_TUNNEL_TOKEN", "eyJabc")
    r = ax._cloudflare_tunnel()
    assert r["status"] == "OK"


# --------------------------------------------------------------------------- #
# Aggregate readiness — the single number that matters
# --------------------------------------------------------------------------- #
async def test_activation_summary_public() -> None:
    from app.api.activation import activation_summary_public

    out = await activation_summary_public()
    assert out["ready_for_launch"] is True
    assert out["payments_deferred"] is True
    assert "graph_version" in out


async def test_readiness_launch_ready_without_razorpay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default empty env -> no BLOCKERs; marketing launch OK; payments deferred."""
    out = await ax.activation_readiness(_user=None)  # type: ignore[arg-type]
    assert out["ready_for_launch"] is True
    assert out["ready_for_first_paid_customer"] is False
    assert out["payments_deferred"] is True
    assert out["blocker_count"] == 0
    assert "razorpay" not in out["blockers"]
    keys = {it["key"] for it in out["items"]}
    # K.1: expanded from 5 -> 13 probes (Phase 1-5 of activation runbook)
    expected = {
        "razorpay", "sentry", "posthog", "turnstile", "cloudflare_tunnel",
        "agent_memory", "eval_gate",
        "engineer_agents", "ops_alerts",
        "customer_webhooks", "mcp_product",
        "litellm_costs", "warm_dr",
    }
    assert keys == expected


async def test_get_activation_summary_has_probes() -> None:
    from app.api.activation import get_activation_summary

    out = await get_activation_summary()
    assert "probes" in out
    assert isinstance(out["probes"], dict)
    assert "telephony" in out
    assert "ready_for_calling" in out


async def test_readiness_flips_paid_when_razorpay_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live_realKey")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "real-secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "whs")
    out = await ax.activation_readiness(_user=None)  # type: ignore[arg-type]
    assert out["ready_for_launch"] is True
    assert out["ready_for_first_paid_customer"] is True
    assert out["payments_ready"] is True
    assert out["blockers"] == []
    assert "telephony" in out
    assert "ready_for_calling" in out
