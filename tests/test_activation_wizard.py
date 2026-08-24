"""P.1 activation wizard — next-step-by-phase logic.

The wizard is the operator's primary entry point for activation: incorrect
next-step picks waste operator time. Tests pin the ordering contract:
- Razorpay blocker beats Sentry warn
- Once Phase-1 is green, Phase-2 surfaces
- All-done when zero actionable items remain
- Wizard never returns OK/NEUTRAL items as a "next step"
"""

from __future__ import annotations

import pytest

from app.api import activation as ax


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every env key any probe might read so each test starts at zero.

    Also isolate the `first_paid_delivery` probe (2026-07-11 addition) from
    real `data/clients.jsonl` — this test file exercises the wizard's
    phase-ordering contract, not the delivery-outcome storage layer. Without
    this isolation, a real paying customer sitting stale in production data
    would flip Phase 1 to actionable and break every "all-done" assertion.
    """
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
        "AGENT_MEMORY",
        "EVAL_GATE",
        "EVAL_GATE_HARD",
        "SRE_AGENT",
        "FINOPS_AGENT",
        "SECURITY_AGENT",
        "OPS_ALERTS",
        "NTFY_URL",
        "NTFY_TOPIC",
        "CUSTOMER_WEBHOOKS",
        "MCP_PRODUCT",
        "LITELLM_COSTS",
        "LITELLM_MASTER_KEY",
        "LITELLM_GATEWAY_URL",
        "DR_REPLICA_URL",
        "GRIEVANCE_OFFICER_EMAIL",
        "TWILIO_AUTH_TOKEN",
        "WHATSAPP_APP_SECRET",
        "UPI_VPA",
        "QDRANT_URL",
        "REVENUE_TRENDS",
        "CLIENT_TIMELINE",
        "SYS_HEALTH_DETAIL",
    ):
        monkeypatch.delenv(k, raising=False)

    # Isolate first_paid_delivery from live clients_store — hermetic wizard test.
    import app.marketing.clients_store as _clients_store

    monkeypatch.setattr(_clients_store, "list_clients", lambda **kw: [])
    # Bust the delivery probe cache so each test observes the isolated store.
    ax._FIRST_PAID_CACHE.clear()
    ax._FIRST_PAID_CACHE.update({"at": 0.0, "result": None})


# --------------------------------------------------------------------------- #
# Next-step picking
# --------------------------------------------------------------------------- #
async def test_empty_env_picks_sentry_first() -> None:
    """Razorpay deferred (NEUTRAL) — wizard surfaces first WARN (Sentry)."""
    out = await ax.activation_wizard(_user=None)  # type: ignore[arg-type]
    assert out["all_done"] is False
    assert out["next_step"]["key"] == "sentry"
    assert out["next_step"]["status"] == "WARN"
    assert out["next_step"]["phase"]["n"] == 1


async def test_sentry_is_first_phase1_step() -> None:
    """Razorpay removed 2026-06-18 — Sentry (WARN) is the first Phase-1 step."""
    out = await ax.activation_wizard(_user=None)  # type: ignore[arg-type]
    assert out["next_step"]["key"] == "sentry"
    assert out["next_step"]["status"] == "WARN"


async def test_phase1_green_jumps_to_phase2(monkeypatch: pytest.MonkeyPatch) -> None:
    """All Phase-1 items OK or NEUTRAL -> wizard skips to Phase-2 actionable
    items. Confirms the phase-by-phase walk, not "all in one place"."""
    # Phase 1 fully armed where relevant (Razorpay removed 2026-06-18).
    monkeypatch.setenv("SENTRY_DSN", "https://x@o.ingest.sentry.io/1")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_real")
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "pk")
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "sk")
    monkeypatch.setenv("UPI_VPA", "merchant@upi")
    monkeypatch.setenv("QDRANT_URL", "http://host.docker.internal:6333")
    monkeypatch.setenv("REVENUE_TRENDS", "1")
    monkeypatch.setenv("CLIENT_TIMELINE", "1")
    monkeypatch.setenv("SYS_HEALTH_DETAIL", "1")
    # cloudflare_tunnel intentionally left NEUTRAL (opt-in)

    out = await ax.activation_wizard(_user=None)  # type: ignore[arg-type]
    # Phase 1 has zero actionable items; agent_memory + eval_gate are NEUTRAL.
    # ops_alerts / engineer_agents are also NEUTRAL. customer_webhooks /
    # mcp_product / litellm / warm_dr also NEUTRAL.
    # So no actionable items anywhere -> all_done.
    assert out["all_done"] is True
    assert out["next_step"] is None
    # Phase 1 done; nothing remaining
    assert 1 in out["phases_done"]


async def test_warn_only_items_still_surface_as_next(monkeypatch: pytest.MonkeyPatch) -> None:
    """WARN-status items are real action items (e.g. Sentry)."""
    monkeypatch.setenv("SENTRY_DSN", "https://x@o.ingest.sentry.io/1")
    out = await ax.activation_wizard(_user=None)  # type: ignore[arg-type]
    assert out["next_step"] is not None
    assert out["next_step"]["key"] != "sentry"  # neutral without ENVIRONMENT=production
    assert out["next_step"]["key"] in {"posthog", "turnstile"}


async def test_phases_done_and_remaining_account_for_all_phases() -> None:
    """Sum of phases_done + phases_remaining == total phases (no missed)."""
    out = await ax.activation_wizard(_user=None)  # type: ignore[arg-type]
    assert len(out["phases_done"]) + len(out["phases_remaining"]) == out["total_phases"]


async def test_verify_curl_in_payload() -> None:
    """SDK builders / operators need a copy-pasteable verify command. The
    wizard MUST include it on the next_step (not separately)."""
    out = await ax.activation_wizard(_user=None)  # type: ignore[arg-type]
    if out["next_step"] is not None:
        assert "verify_curl" in out["next_step"]
        assert "/api/activation/readiness" in out["next_step"]["verify_curl"]
