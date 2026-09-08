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
        "RAZORPAY_KEY_ID",
        "RAZORPAY_KEY_SECRET",
        "RAZORPAY_WEBHOOK_SECRET",
        "SENTRY_DSN",
        "ENVIRONMENT",
        "APP_ENV",
        "POSTHOG_API_KEY",
        "POSTHOG_HOST",
        "TURNSTILE_SITE_KEY",
        "TURNSTILE_SECRET_KEY",
        "CLOUDFLARE_TUNNEL_TOKEN",
    ):
        monkeypatch.delenv(k, raising=False)


# Razorpay activation probe removed 2026-06-18 — gateway gone (manual UPI only).
# payments_ready is hard-coded True now; the razorpay probe tests were deleted.


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
async def test_activation_summary_public(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.activation import activation_summary_public
    from app.platform import upi_config as uc

    # Hermetic: payments-state UPI-arming se derive hota — developer/CI env pe
    # depend nahi karna (CI me UPI_VPA unset → payments_deferred True ho jata tha).
    monkeypatch.setattr(uc, "is_armed", lambda: True)
    out = await activation_summary_public()
    assert out["ready_for_launch"] is True
    assert (
        out["payments_deferred"] is False
    )  # Razorpay removed 2026-06-18 - manual UPI always available
    assert "graph_version" in out


async def test_readiness_launch_ready_default_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default empty env -> no BLOCKERs; marketing launch OK. Razorpay removed
    2026-06-18 — payments via manual UPI, so payments_ready is always True."""
    from app.platform import upi_config as uc

    # Hermetic (CI me UPI unarmed → payments_ready False ho jata tha; unarmed-case
    # ka apna dedicated test niche hai).
    monkeypatch.setattr(uc, "is_armed", lambda: True)
    out = await ax.activation_readiness(_user=None)  # type: ignore[arg-type]
    assert out["ready_for_launch"] is True
    assert out["payments_ready"] is True
    assert out["blocker_count"] == 0
    assert "razorpay" not in out["blockers"]
    keys = {it["key"] for it in out["items"]}
    # Launch-critical probes that MUST be present. Asserted as a SUBSET (not exact
    # match) so adding new probes over time (e.g. qdrant_rag, track_b_admin) does
    # not break this guard — the point is "no blockers + core probes present".
    # Razorpay removed 2026-06-18; UPI revenue probe added.
    required = {
        "sentry",
        "posthog",
        "turnstile",
        "cloudflare_tunnel",
        "upi",
        "agent_memory",
        "eval_gate",
        "engineer_agents",
        "ops_alerts",
        "customer_webhooks",
        "mcp_product",
        "litellm_costs",
        "warm_dr",
    }
    assert required <= keys, f"missing launch-critical probes: {required - keys}"


async def test_get_activation_summary_has_probes() -> None:
    from app.api.activation import get_activation_summary

    out = await get_activation_summary()
    assert "probes" in out
    assert isinstance(out["probes"], dict)
    assert "telephony" in out
    assert "ready_for_calling" in out


async def test_readiness_paid_ready_requires_upi(monkeypatch: pytest.MonkeyPatch) -> None:
    """First paid customer needs armed UPI VPA (env or admin data file)."""
    from app.platform import upi_config as uc

    monkeypatch.setattr(uc, "is_armed", lambda: False)
    out = await ax.activation_readiness(_user=None)  # type: ignore[arg-type]
    assert out["ready_for_launch"] is True
    assert out["ready_for_first_paid_customer"] is False
    assert out["payments_ready"] is False
    assert out["blockers"] == []


async def test_readiness_paid_ready_when_upi_armed(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.platform import upi_config as uc

    monkeypatch.setattr(uc, "is_armed", lambda: True)
    out = await ax.activation_readiness(_user=None)  # type: ignore[arg-type]
    assert out["ready_for_first_paid_customer"] is True
    assert out["payments_ready"] is True
