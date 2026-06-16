"""Activation-readiness probe — encode the wired-but-OFF registry.

The 2026-06-16 billionaire-scale audit named **activation debt** as the #1 hidden
liability: ~25 capabilities sit wired-but-OFF in the repo, waiting on env vars or
credentials. There's no single pane that says "here is what is BLOCKING the first
paid customer right now" — `/api/growth/infra/flags` lists 80 flags, but doesn't
distinguish a launch-blocker (Razorpay live keys, Turnstile arming) from an
opt-in growth lever (`CHANNEL_EXPERIMENTS`).

This module fills exactly that gap. It returns a curated list of activation-
gated items grouped by category, each with `status` (BLOCKER / WARN / OK /
NEUTRAL), the env vars involved, granular check booleans, and a one-line action.
Plus a top-level `ready_for_first_paid_customer` boolean.

Design rules:
- READ-ONLY (admin). Never mutates env. Never makes outbound calls — purely
  shape-checks os.environ. Cheap to call from a dashboard polling loop.
- Format-aware: e.g. Razorpay status is BLOCKER if `RAZORPAY_KEY_ID` is the
  literal placeholder (`rzp_test_you...` from .env.example) OR doesn't start
  with `rzp_live_`. This catches the exact root cause CLAUDE.md proved on
  2026-06-14 (`.env` has placeholder values, not real keys).
- INERT for not-yet-activated items: unset = NEUTRAL (waiting), not BLOCKER.
  Only the things that gate first revenue / customer trust escalate to BLOCKER.

Used by /app/automation Mission Control "Activation" tab (UI hookup separate).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends

from app.api.auth_deps import require_admin

router = APIRouter(prefix="/api/activation", tags=["Infrastructure"])


# --------------------------------------------------------------------------- #
# Status semantics
# --------------------------------------------------------------------------- #
# BLOCKER  — gates revenue or trust; first paid customer cannot transact until OK
# WARN     — strongly recommended but funnel works without it (no error tracking,
#            no analytics, no bot-protection); not revenue-critical
# OK       — armed and looks healthy at the shape-check level
# NEUTRAL  — opt-in capability sitting unset by design (e.g. Cloudflare Tunnel
#            for HA / origin-hide — valuable but not blocker)
_BLOCKER, _WARN, _OK, _NEUTRAL = "BLOCKER", "WARN", "OK", "NEUTRAL"


def _v(key: str) -> str:
    return (os.environ.get(key) or "").strip()


def _set(key: str) -> bool:
    return bool(_v(key))


def _is_placeholder(value: str) -> bool:
    """Detect .env.example-leftover values that look set but aren't real."""
    if not value:
        return False
    lower = value.lower()
    markers = (
        "your-", "your_", "change-me", "change_me", "xxxxxxxx",
        "rzp_test_you", "rzp_live_xxxxx", "placeholder",
    )
    return any(m in lower for m in markers)


# --------------------------------------------------------------------------- #
# Per-item probes
# --------------------------------------------------------------------------- #
def _razorpay() -> dict[str, Any]:
    """Revenue-blocker: live keys + webhook secret."""
    kid, ksec, whs = _v("RAZORPAY_KEY_ID"), _v("RAZORPAY_KEY_SECRET"), _v("RAZORPAY_WEBHOOK_SECRET")
    checks = {
        "key_id_set": bool(kid),
        "key_id_live": kid.startswith("rzp_live_"),
        "key_id_placeholder": _is_placeholder(kid),
        "secret_set": bool(ksec),
        "secret_placeholder": _is_placeholder(ksec),
        "webhook_secret_set": bool(whs),
    }
    blocked = (
        not checks["key_id_set"]
        or not checks["key_id_live"]
        or checks["key_id_placeholder"]
        or not checks["secret_set"]
        or checks["secret_placeholder"]
    )
    return {
        "key": "razorpay",
        "label": "Razorpay live payments",
        "category": "revenue",
        "status": _BLOCKER if blocked else (_OK if checks["webhook_secret_set"] else _WARN),
        "env_vars": ["RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"],
        "checks": checks,
        "action": (
            "Set real rzp_live_* keys in .env + register webhook at "
            "https://leadsgenai.in/api/billing/webhooks/razorpay"
            if blocked
            else "Set RAZORPAY_WEBHOOK_SECRET to harden against forged callbacks"
            if not checks["webhook_secret_set"]
            else ""
        ),
        "doc": "docs/ACTIVATION_RUNBOOK_2026_06_16.md#B4",
    }


def _sentry() -> dict[str, Any]:
    """Visibility: error tracking. Funnel survives without it (WARN, not BLOCKER)."""
    dsn = _v("SENTRY_DSN")
    env = _v("ENVIRONMENT") or _v("APP_ENV")
    checks = {
        "dsn_set": bool(dsn),
        "dsn_placeholder": _is_placeholder(dsn),
        "env_is_production": env.lower() == "production",
    }
    armed = checks["dsn_set"] and not checks["dsn_placeholder"]
    return {
        "key": "sentry",
        "label": "Sentry error tracking",
        "category": "visibility",
        "status": _OK if armed and checks["env_is_production"] else (_WARN if not armed else _NEUTRAL),
        "env_vars": ["SENTRY_DSN", "ENVIRONMENT"],
        "checks": checks,
        "action": (
            "Set SENTRY_DSN in .env (sentry.io project DSN)"
            if not armed
            else "Sentry init is gated on ENVIRONMENT=production — set it on prod box"
            if not checks["env_is_production"]
            else ""
        ),
        "doc": "docs/ACTIVATION_RUNBOOK_2026_06_16.md#B2",
    }


def _posthog() -> dict[str, Any]:
    """Visibility: product analytics. Funnel works without it (WARN)."""
    key, host = _v("POSTHOG_API_KEY"), _v("POSTHOG_HOST")
    checks = {
        "api_key_set": bool(key),
        "api_key_placeholder": _is_placeholder(key),
        "host_set": bool(host),
    }
    armed = checks["api_key_set"] and not checks["api_key_placeholder"]
    return {
        "key": "posthog",
        "label": "PostHog product analytics",
        "category": "visibility",
        "status": _OK if armed else _WARN,
        "env_vars": ["POSTHOG_API_KEY", "POSTHOG_HOST"],
        "checks": checks,
        "action": (
            "Set POSTHOG_API_KEY in .env (PostHog Cloud free tier — never self-host)"
            if not armed
            else ""
        ),
        "doc": "docs/ACTIVATION_RUNBOOK_2026_06_16.md#B3",
    }


def _turnstile() -> dict[str, Any]:
    """Trust: bot-protection on lead-magnets. WARN until armed."""
    sk, ssk = _v("TURNSTILE_SITE_KEY"), _v("TURNSTILE_SECRET_KEY")
    checks = {
        "site_key_set": bool(sk),
        "secret_set": bool(ssk),
    }
    armed = checks["site_key_set"] and checks["secret_set"]
    return {
        "key": "turnstile",
        "label": "Cloudflare Turnstile bot-protection (F.1)",
        "category": "trust",
        "status": _OK if armed else _WARN,
        "env_vars": ["TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY"],
        "checks": checks,
        "action": (
            "Cloudflare dashboard -> Turnstile -> create widget -> set both keys in .env"
            if not armed
            else ""
        ),
        "doc": "docs/ACTIVATION_RUNBOOK_2026_06_16.md#B1",
    }


def _cloudflare_tunnel() -> dict[str, Any]:
    """Edge: origin-hide + WAF/DDoS. NEUTRAL (highly recommended but not blocker)."""
    tok = _v("CLOUDFLARE_TUNNEL_TOKEN")
    checks = {"token_set": bool(tok)}
    return {
        "key": "cloudflare_tunnel",
        "label": "Cloudflare Tunnel + WAF (edge protection)",
        "category": "edge",
        "status": _OK if checks["token_set"] else _NEUTRAL,
        "env_vars": ["CLOUDFLARE_TUNNEL_TOKEN"],
        "checks": checks,
        "action": (
            "Zero-Trust -> Tunnels -> create -> token in .env -> "
            "`docker compose -f docker-compose.edge.yml --profile edge up -d`"
            if not checks["token_set"]
            else ""
        ),
        "doc": "docs/ACTIVATION_RUNBOOK_2026_06_16.md#B1",
    }


_PROBES = (_razorpay, _sentry, _posthog, _turnstile, _cloudflare_tunnel)


# --------------------------------------------------------------------------- #
# Route
# --------------------------------------------------------------------------- #
@router.get("/readiness")
async def activation_readiness(_user=Depends(require_admin)) -> dict[str, Any]:
    """Activation-debt snapshot for /app/automation Mission Control.

    Returns per-item status + the one number the operator actually needs:
    `ready_for_first_paid_customer` (true only when zero BLOCKERs remain).
    """
    items = [p() for p in _PROBES]
    blockers = [it["key"] for it in items if it["status"] == _BLOCKER]
    warns = [it["key"] for it in items if it["status"] == _WARN]
    return {
        "ready_for_first_paid_customer": not blockers,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warn_count": len(warns),
        "warns": warns,
        "items": items,
    }


__all__ = ["router"]
