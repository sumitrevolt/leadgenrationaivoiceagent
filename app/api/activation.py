"""Activation-readiness probe — encode the wired-but-OFF registry.

The 2026-06-16 billionaire-scale audit named **activation debt** as the #1 hidden
liability: ~25 capabilities sit wired-but-OFF in the repo, waiting on env vars or
credentials. There's no single pane that says "here is what is BLOCKING the first
paid customer right now" — `/api/growth/infra/flags` lists 80 flags, but doesn't
distinguish a launch-blocker (Turnstile arming) from an opt-in growth lever (`CHANNEL_EXPERIMENTS`).

This module fills exactly that gap. It returns a curated list of activation-
gated items grouped by category, each with `status` (BLOCKER / WARN / OK /
NEUTRAL), the env vars involved, granular check booleans, and a one-line action.
Plus a top-level `ready_for_first_paid_customer` boolean.

Design rules:
- READ-ONLY (admin). Never mutates env. Never makes outbound calls — purely
  shape-checks os.environ. Cheap to call from a dashboard polling loop.
- Format-aware shape checks. Razorpay is **deferred by default** (NEUTRAL) —
  paid checkout baad me; marketing launch is not blocked on missing keys.
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
        "your-",
        "your_",
        "change-me",
        "change_me",
        "xxxxxxxx",
        "rzp_test_you",
        "rzp_live_xxxxx",
        "placeholder",
    )
    return any(m in lower for m in markers)


# --------------------------------------------------------------------------- #
# Per-item probes
# --------------------------------------------------------------------------- #
# _razorpay() probe removed 2026-06-18 — Razorpay gateway gone (manual UPI only).
# Payments are no longer an activation gate; payments_ready is hard-coded True
# (UPI is always available) so the activation summary still builds.


def _sentry() -> dict[str, Any]:
    """Visibility: error tracking. Funnel survives without it (WARN, not BLOCKER)."""
    dsn = _v("SENTRY_DSN")
    try:
        from app.platform import trust_config

        if not dsn:
            dsn = trust_config.get_sentry_dsn()
    except Exception:
        pass
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
        "status": (
            _OK if armed and checks["env_is_production"] else (_WARN if not armed else _NEUTRAL)
        ),
        "env_vars": ["SENTRY_DSN", "ENVIRONMENT"],
        "checks": checks,
        "action": (
            "Set SENTRY_DSN in .env (sentry.io project DSN)"
            if not armed
            else (
                "Sentry init is gated on ENVIRONMENT=production — set it on prod box"
                if not checks["env_is_production"]
                else ""
            )
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
    try:
        from app.platform import trust_config

        if not sk:
            sk = trust_config.get_turnstile_site_key()
        if not ssk:
            ssk = trust_config.get_turnstile_secret()
    except Exception:
        pass
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


def _agent_memory() -> dict[str, Any]:
    """Voice agent cross-session lead recall (F.4)."""
    on = _set("AGENT_MEMORY")
    return {
        "key": "agent_memory",
        "label": "Voice agent cross-session memory (F.4)",
        "category": "ai",
        "status": _OK if on else _NEUTRAL,
        "env_vars": ["AGENT_MEMORY"],
        "checks": {"enabled": on},
        "action": "Set AGENT_MEMORY=1 for cross-session lead recall (Qdrant)" if not on else "",
        "doc": "docs/SESSION_ACTIVATION_RUNBOOK_2026_06_16.md#23",
    }


def _eval_gate() -> dict[str, Any]:
    """DeepEval close-the-loop reward signal (F.3)."""
    on = _set("EVAL_GATE")
    hard = _set("EVAL_GATE_HARD")
    return {
        "key": "eval_gate",
        "label": "Eval-gate self_improve reward signal (F.3)",
        "category": "ai",
        "status": _OK if on else _NEUTRAL,
        "env_vars": ["EVAL_GATE", "EVAL_GATE_HARD"],
        "checks": {"recording": on, "hard_blocking": hard},
        "action": (
            "Set EVAL_GATE=1 to start recording (observe-only); after baseline trusted, EVAL_GATE_HARD=1 to block regressions"
            if not on
            else "Once 20+ samples per metric, flip EVAL_GATE_HARD=1 to enforce" if not hard else ""
        ),
        "doc": "docs/SESSION_ACTIVATION_RUNBOOK_2026_06_16.md#24",
    }


def _engineer_agents() -> dict[str, Any]:
    """3 engineer agents (F.5) — Pranav SRE, Vidya FinOps, Arnav Security."""
    sre = _set("SRE_AGENT")
    fin = _set("FINOPS_AGENT")
    sec = _set("SECURITY_AGENT")
    on_count = sum([sre, fin, sec])
    status = _OK if on_count == 3 else (_WARN if on_count else _NEUTRAL)
    missing = []
    if not sre:
        missing.append("SRE_AGENT")
    if not fin:
        missing.append("FINOPS_AGENT")
    if not sec:
        missing.append("SECURITY_AGENT")
    return {
        "key": "engineer_agents",
        "label": "Engineer agents Pranav/Vidya/Arnav (F.5)",
        "category": "ai",
        "status": status,
        "env_vars": ["SRE_AGENT", "FINOPS_AGENT", "SECURITY_AGENT"],
        "checks": {"sre": sre, "finops": fin, "security": sec, "on_count": on_count},
        "action": (
            f"Set {', '.join(missing)}=1 to wake the remaining engineer agent(s)" if missing else ""
        ),
        "doc": "docs/SESSION_ACTIVATION_RUNBOOK_2026_06_16.md#31",
    }


def _ops_alerts() -> dict[str, Any]:
    """ntfy fan-out for engineer-score / eval-reject / readiness digest (G.1)."""
    on = _set("OPS_ALERTS")
    ntfy_url = _set("NTFY_URL")
    ntfy_topic = _set("NTFY_TOPIC")
    fully_armed = on and ntfy_url and ntfy_topic
    status = _OK if fully_armed else (_WARN if on else _NEUTRAL)
    return {
        "key": "ops_alerts",
        "label": "ops_alerts ntfy fan-out (G.1)",
        "category": "visibility",
        "status": status,
        "env_vars": ["OPS_ALERTS", "NTFY_URL", "NTFY_TOPIC"],
        "checks": {"master": on, "ntfy_url_set": ntfy_url, "ntfy_topic_set": ntfy_topic},
        "action": (
            "Set OPS_ALERTS=1 + NTFY_URL + NTFY_TOPIC to wake low-score / regression alerts"
            if not fully_armed and not on
            else (
                "OPS_ALERTS on but NTFY_URL/NTFY_TOPIC missing — pushes will no-op"
                if on and not fully_armed
                else ""
            )
        ),
        "doc": "docs/SESSION_ACTIVATION_RUNBOOK_2026_06_16.md#32",
    }


def _customer_webhooks() -> dict[str, Any]:
    """Customer-facing webhooks (H.1 + J.1 UI)."""
    on = _set("CUSTOMER_WEBHOOKS")
    return {
        "key": "customer_webhooks",
        "label": "Customer-facing webhooks (H.1)",
        "category": "revenue",
        "status": _OK if on else _NEUTRAL,
        "env_vars": ["CUSTOMER_WEBHOOKS"],
        "checks": {"enabled": on},
        "action": "Set CUSTOMER_WEBHOOKS=1 to arm event fan-out to customer URLs" if not on else "",
        "doc": "docs/SESSION_ACTIVATION_RUNBOOK_2026_06_16.md#41",
    }


def _mcp_product() -> dict[str, Any]:
    """MCP-as-product metered surface (H.3)."""
    on = _set("MCP_PRODUCT")
    return {
        "key": "mcp_product",
        "label": "MCP-as-product programmatic surface (H.3)",
        "category": "revenue",
        "status": _OK if on else _NEUTRAL,
        "env_vars": ["MCP_PRODUCT"],
        "checks": {"enabled": on},
        "action": (
            "Set MCP_PRODUCT=1 + issue keys via /app/dashboards to enable revenue surface"
            if not on
            else ""
        ),
        "doc": "docs/SESSION_ACTIVATION_RUNBOOK_2026_06_16.md#43",
    }


def _litellm_costs() -> dict[str, Any]:
    """LiteLLM per-tenant cost rollup (H.4 + I.1)."""
    on = _set("LITELLM_COSTS")
    master = _set("LITELLM_MASTER_KEY")
    gateway = _set("LITELLM_GATEWAY_URL")
    fully_armed = on and master and gateway
    status = _OK if fully_armed else (_WARN if on else _NEUTRAL)
    return {
        "key": "litellm_costs",
        "label": "LiteLLM per-tenant cost (H.4)",
        "category": "margin",
        "status": status,
        "env_vars": ["LITELLM_COSTS", "LITELLM_MASTER_KEY", "LITELLM_GATEWAY_URL"],
        "checks": {"flag": on, "master_key": master, "gateway_url": gateway},
        "action": (
            "Set LITELLM_COSTS=1 + LITELLM_MASTER_KEY + LITELLM_GATEWAY_URL (after docker compose -f docker-compose.edge.yml --profile gateway up)"
            if not fully_armed and not on
            else (
                "LITELLM_COSTS on but MASTER_KEY or GATEWAY_URL missing — Vidya will report unavailable"
                if on and not fully_armed
                else ""
            )
        ),
        "doc": "docs/SESSION_ACTIVATION_RUNBOOK_2026_06_16.md#51",
    }


def _warm_dr() -> dict[str, Any]:
    """Warm-DR replica (H.4)."""
    on = _set("DR_REPLICA_URL")
    return {
        "key": "warm_dr",
        "label": "Warm-DR replica (H.4)",
        "category": "edge",
        "status": _OK if on else _NEUTRAL,
        "env_vars": ["DR_REPLICA_URL"],
        "checks": {"configured": on},
        "action": (
            "Set DR_REPLICA_URL to a Neon/Supabase replica for warm-DR (SPOF mitigation)"
            if not on
            else ""
        ),
        "doc": "docs/SESSION_ACTIVATION_RUNBOOK_2026_06_16.md#52",
    }


def _qdrant_url() -> str:
    u = _v("QDRANT_URL")
    if u:
        return u
    try:
        from app.config import settings

        return (getattr(settings, "qdrant_url", "") or "").strip()
    except Exception:
        return ""


def _qdrant_rag() -> dict[str, Any]:
    """Semantic RAG backend — shape-only check (no outbound HTTP on hot path)."""
    url = _qdrant_url()
    trap = bool(url and ("127.0.0.1" in url or "localhost" in url))
    checks = {"url_set": bool(url), "docker_localhost_trap": trap}
    if not checks["url_set"]:
        status, action = (
            _WARN,
            "Set QDRANT_URL in .env — bina iske KB keyword fallback pe chalega (weaker chat/voice grounding)",
        )
    elif trap:
        status, action = (
            _WARN,
            "QDRANT_URL=127.0.0.1 container ke andar unreachable — Docker VPS pe "
            "http://host.docker.internal:6333 use karo (docker-compose.vps.yml wired)",
        )
    else:
        status, action = _OK, ""
    return {
        "key": "qdrant_rag",
        "label": "Qdrant vector RAG (semantic KB)",
        "category": "ai",
        "status": status,
        "env_vars": ["QDRANT_URL"],
        "checks": checks,
        "action": action,
        "doc": "docs/RAG_KnowledgeGraph_Agentic.md",
    }


def _track_b_admin() -> dict[str, Any]:
    """Track B admin UX flags — WARN on production when still OFF."""
    flags = ("REVENUE_TRENDS", "CLIENT_TIMELINE", "SYS_HEALTH_DETAIL")
    checks = {f.lower(): _set(f) for f in flags}
    on_count = sum(1 for v in checks.values() if v)
    env = (_v("ENVIRONMENT") or _v("APP_ENV")).lower()
    if env != "production":
        return {
            "key": "track_b_admin",
            "label": "Admin readiness panels (Track B)",
            "category": "visibility",
            "status": _NEUTRAL,
            "env_vars": list(flags),
            "checks": {**checks, "on_count": on_count},
            "action": "",
            "doc": "docs/superpowers/specs/2026-06-20-readiness-infra-improvement-design.md",
        }
    status = _OK if on_count == 3 else _WARN
    missing = [f for f in flags if not _set(f)]
    return {
        "key": "track_b_admin",
        "label": "Admin readiness panels (Track B)",
        "category": "visibility",
        "status": status,
        "env_vars": list(flags),
        "checks": {**checks, "on_count": on_count},
        "action": (
            f"VPS pe run: python3 scripts/vps_enable_readiness_flags.py (missing: {', '.join(missing)})"
            if missing
            else ""
        ),
        "doc": "docs/superpowers/specs/2026-06-20-readiness-infra-improvement-design.md",
    }


def _payments_ready() -> bool:
    """First paid customer needs a collectable UPI VPA (env or admin data file)."""
    try:
        from app.platform import upi_config

        return upi_config.is_armed()
    except Exception:
        vpa = _v("UPI_VPA")
        return bool(vpa and "@" in vpa)


def _upi() -> dict[str, Any]:
    """Revenue: manual UPI is the primary India payment path (Razorpay removed
    2026-06-18). No VPA = operator cannot collect the first payment."""
    try:
        from app.platform import upi_config

        info = upi_config.info()
        vpa = info.get("vpa") or ""
        src = info.get("source") or "none"
        armed = bool(info.get("enabled"))
    except Exception:
        vpa = _v("UPI_VPA")
        src = "env" if vpa else "none"
        armed = bool(vpa and "@" in vpa)
    checks = {
        "vpa_set": bool(vpa),
        "vpa_format_ok": ("@" in vpa) if vpa else False,
        "source": src,
    }
    return {
        "key": "upi",
        "label": "Manual UPI payments (UPI_VPA)",
        "category": "revenue",
        "status": _OK if armed else _WARN,
        "env_vars": ["UPI_VPA"],
        "checks": checks,
        "action": (
            "Admin dashboard → God Mode → UPI section me VPA save karo, "
            "ya .env me UPI_VPA=<yourvpa>@bank set karo (pricing modal + pay-info)"
            if not armed
            else ""
        ),
        "doc": "docs/ACTIVATION_RUNBOOK_2026_06_16.md#payments",
    }


_PROBES = (
    # Phase 1: Survival (visibility + trust + edge) + first-revenue UPI. Razorpay removed 2026-06-18.
    _sentry,
    _posthog,
    _turnstile,
    _cloudflare_tunnel,
    _upi,
    _qdrant_rag,
    # Phase 2: AI safety + memory + admin UX
    _track_b_admin,
    _agent_memory,
    _eval_gate,
    # Phase 3: AI staff + alerting
    _engineer_agents,
    _ops_alerts,
    # Phase 4: Sellable capabilities
    _customer_webhooks,
    _mcp_product,
    # Phase 5: Margin + survival
    _litellm_costs,
    _warm_dr,
)


# --------------------------------------------------------------------------- #
# Route
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Wizard — pick the single highest-leverage NEXT step from current state.
# --------------------------------------------------------------------------- #
# Operator was getting a 13-item readiness checklist with no ordering hint.
# The runbook (`docs/SESSION_ACTIVATION_RUNBOOK_2026_06_16.md`) groups items by
# phase; this endpoint encodes the same dependency order so the operator
# always sees ONE concrete next step instead of a wall of items.
#
# Phase order matches the runbook:
#   1 Survival  — sentry, posthog, turnstile, cloudflare_tunnel, upi, qdrant_rag
#   2 Visibility — agent_memory, eval_gate
#   3 AI staff   — engineer_agents, ops_alerts
#   4 Sellable   — customer_webhooks, mcp_product
#   5 Margin     — litellm_costs, warm_dr
_PHASES: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (1, "Survival", ("sentry", "posthog", "turnstile", "cloudflare_tunnel", "upi", "qdrant_rag")),
    (2, "Visibility", ("track_b_admin", "agent_memory", "eval_gate")),
    (3, "AI staff", ("engineer_agents", "ops_alerts")),
    (4, "Sellable", ("customer_webhooks", "mcp_product")),
    (5, "Margin", ("litellm_costs", "warm_dr")),
)

# Lookup the probe function by key so we can call it independently of the
# read-only readiness endpoint (which always probes everything).
_PROBE_BY_KEY = {
    "sentry": _sentry,
    "posthog": _posthog,
    "turnstile": _turnstile,
    "cloudflare_tunnel": _cloudflare_tunnel,
    "upi": _upi,
    "qdrant_rag": _qdrant_rag,
    "track_b_admin": _track_b_admin,
    "agent_memory": _agent_memory,
    "eval_gate": _eval_gate,
    "engineer_agents": _engineer_agents,
    "ops_alerts": _ops_alerts,
    "customer_webhooks": _customer_webhooks,
    "mcp_product": _mcp_product,
    "litellm_costs": _litellm_costs,
    "warm_dr": _warm_dr,
}


def _item_is_actionable(probe_result: dict[str, Any]) -> bool:
    """An item is the next-step candidate iff its status is BLOCKER or WARN —
    NEUTRAL (opt-in unset) and OK both mean 'no action needed right now'."""
    return probe_result.get("status") in {_BLOCKER, _WARN}


@router.get("/wizard")
async def activation_wizard(_user=Depends(require_admin)) -> dict[str, Any]:
    """Return the single highest-priority next step.

    Walks the phase order (Survival → Visibility → AI staff → Sellable →
    Margin) and returns the FIRST probe with status BLOCKER or WARN —
    plus the exact env keys and a verify-curl the operator can copy-paste.

    Output shape:
      {
        "all_done": bool,                # True iff every phase is green
        "current_phase": {"n": int, "name": str},
        "next_step": {
            "key": "sentry",
            "label": "Sentry error tracking",
            "category": "observability",
            "status": "BLOCKER",
            "env_vars": ["SENTRY_DSN"],
            "action": "Set SENTRY_DSN from sentry.io project settings",
            "doc": "docs/SESSION_ACTIVATION_RUNBOOK_2026_06_16.md#sentry",
            "verify_curl": "curl -s http://127.0.0.1:8000/api/activation/readiness | ...",
        },
        "phases_done": [1, 2, ...],      # phases with zero actionable items
        "phases_remaining": [...],       # phases still containing actionable items
      }
    """
    phases_done: list[int] = []
    phases_remaining: list[int] = []
    next_step: dict[str, Any] | None = None
    current_phase: dict[str, Any] | None = None

    for phase_n, phase_name, keys in _PHASES:
        phase_has_action = False
        for key in keys:
            probe = _PROBE_BY_KEY.get(key)
            if probe is None:
                continue
            result = probe()
            if not _item_is_actionable(result):
                continue
            phase_has_action = True
            if next_step is None:
                # First actionable item across all phases — this is THE step.
                next_step = {
                    **result,
                    "phase": {"n": phase_n, "name": phase_name},
                    "verify_curl": (
                        "curl -s http://127.0.0.1:8000/api/activation/readiness "
                        "-H 'Authorization: Bearer $TOKEN' | python3 -m json.tool"
                    ),
                }
                current_phase = {"n": phase_n, "name": phase_name}
        if phase_has_action:
            phases_remaining.append(phase_n)
        else:
            phases_done.append(phase_n)

    return {
        "all_done": next_step is None,
        "current_phase": current_phase,
        "next_step": next_step,
        "phases_done": phases_done,
        "phases_remaining": phases_remaining,
        "total_phases": len(_PHASES),
    }


@router.get("/summary")
async def activation_summary_public() -> dict[str, Any]:
    """Public launch snapshot for explorer + status widgets (no secrets, no auth)."""
    items = [p() for p in _PROBES]
    blockers = [it["key"] for it in items if it["status"] == _BLOCKER]
    warns = [it["key"] for it in items if it["status"] == _WARN]
    payments_ready = _payments_ready()
    launch_ready = not blockers
    return {
        "ready_for_launch": launch_ready,
        "production_ready": launch_ready,
        "ready_for_first_paid_customer": launch_ready and payments_ready,
        "payments_ready": payments_ready,
        "payments_deferred": not payments_ready,
        "blocker_count": len(blockers),
        "warn_count": len(warns),
        "blockers": blockers,
        "warns": warns,
        "graph_version": "2026-06-17-v3",
    }


@router.get("/readiness")
async def activation_readiness(_user=Depends(require_admin)) -> dict[str, Any]:
    """Activation-debt snapshot for /app/automation Mission Control.

    Returns per-item status + the one number the operator actually needs:
    `ready_for_first_paid_customer` (true only when zero BLOCKERs remain).
    """
    items = [p() for p in _PROBES]
    blockers = [it["key"] for it in items if it["status"] == _BLOCKER]
    warns = [it["key"] for it in items if it["status"] == _WARN]
    payments_ready = _payments_ready()
    launch_ready = not blockers

    telephony: dict[str, Any] = {}
    try:
        from app.telephony.telephony_readiness import run_checks

        telephony = run_checks()
    except Exception as exc:
        telephony = {"score": 0, "error": str(exc)[:120]}

    return {
        "ready_for_launch": launch_ready,
        "production_ready": launch_ready,
        "ready_for_first_paid_customer": launch_ready and payments_ready,
        "payments_ready": payments_ready,
        "payments_deferred": not payments_ready,
        "blocker_count": len(blockers),
        "warn_count": len(warns),
        "blockers": blockers,
        "warns": warns,
        "items": items,
        "telephony": telephony,
        "ready_for_calling": int(telephony.get("score") or 0) >= 70,
        "calling_optional": True,
    }


async def get_activation_summary() -> dict[str, Any]:
    """Compact readiness snapshot for God Mode (/api/admin/system/summary).

    Returns boolean ``probes`` map (True = OK) plus telephony score for calling
    launch checks. Never raises.
    """
    items = [p() for p in _PROBES]
    blockers = [it for it in items if it["status"] == _BLOCKER]
    warns = [it for it in items if it["status"] == _WARN]
    payments_ready = _payments_ready()
    launch_ready = not blockers
    probes = {it["key"]: it["status"] != _BLOCKER for it in items}

    telephony: dict[str, Any] = {}
    try:
        from app.telephony.telephony_readiness import run_checks

        telephony = run_checks()
    except Exception as exc:
        telephony = {"score": 0, "error": str(exc)[:120]}

    return {
        "ready_for_launch": launch_ready,
        "production_ready": launch_ready,
        "ready_for_first_paid_customer": launch_ready and payments_ready,
        "payments_ready": payments_ready,
        "payments_deferred": not payments_ready,
        "blocker_count": len(blockers),
        "warn_count": len(warns),
        "blockers": [b["key"] for b in blockers],
        "warns": [w["key"] for w in warns],
        "probes": probes,
        "items": items,
        "telephony": telephony,
        "ready_for_calling": int(telephony.get("score") or 0) >= 70,
        "calling_optional": True,
    }


__all__ = ["router", "get_activation_summary"]
