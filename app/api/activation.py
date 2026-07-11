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
# Payments are no longer a BLOCKER gate; payments_ready reflects a REAL check —
# _payments_ready() -> upi_config.is_armed() (a configured UPI VPA, env UPI_VPA
# fallback) — NOT hard-coded (comment corrected 2026-06-25 audit).


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
    try:
        from app.platform import posthog_config

        key, host = posthog_config.get_api_key(), posthog_config.get_host()
        source = posthog_config.status().get("source") or "none"
    except Exception:
        key, host = _v("POSTHOG_API_KEY"), _v("POSTHOG_HOST")
        source = "env" if key else "none"
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
        "checks": {**checks, "source": source},
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


def _compliance_env() -> dict[str, Any]:
    """TRAI/DPDP compliance-env readiness — an ADVISORY section only.

    Deliberately NOT part of _PROBES: these do NOT feed blockers/warns and MUST
    NOT flip ``ready_for_first_paid_customer`` (existing consumers unchanged).
    Surfaces three signals for the operator:
      (a) recording_retention_armed — RECORDING_RETENTION=1 => the 90-day DPDP
          recording purge actually deletes (not dry-run/observe-only).
      (b) dnd_fail_closed — WARNs loudly when DND_FAIL_OPEN=1 (a TRAI risk: it
          would turn the promotional DND gate fail-OPEN; prod ignores it at
          runtime but it should be unset).
      (c) the effective (post-clamp) promotional calling window (09:00–21:00
          IST ceiling), informationally.
    Never raises."""
    retention_on = _v("RECORDING_RETENTION").lower() in ("1", "true", "yes", "on")
    dnd_fail_open = _v("DND_FAIL_OPEN").lower() in ("1", "true", "yes", "on")
    try:
        from app.telephony.compliance import effective_promo_window

        win_start, win_end = effective_promo_window()
    except Exception:
        win_start, win_end = "09:00", "19:00"

    probes = [
        {
            "key": "recording_retention_armed",
            "label": "Recording retention purge (DPDP 90-day delete)",
            "category": "compliance",
            "status": _OK if retention_on else _WARN,
            "env_vars": ["RECORDING_RETENTION"],
            "checks": {"enabled": retention_on},
            "action": (
                "Set RECORDING_RETENTION=1 so the 90-day DPDP recording purge "
                "deletes (currently dry-run/observe-only)"
                if not retention_on
                else ""
            ),
            "doc": "docs/SWARA_HANDOFF_SOP.md#E",
        },
        {
            "key": "dnd_fail_closed",
            "label": "DND gate fail-CLOSED (TRAI)",
            "category": "compliance",
            "status": _OK if not dnd_fail_open else _WARN,
            "env_vars": ["DND_FAIL_OPEN"],
            "checks": {"dnd_fail_open": dnd_fail_open},
            "action": (
                "TRAI RISK: DND_FAIL_OPEN=1 turns the promotional DND gate "
                "fail-OPEN — unset it. (Production ignores the flag at runtime, "
                "but leave it UNSET so the intent is explicit.)"
                if dnd_fail_open
                else ""
            ),
            "doc": "app/telephony/compliance.py",
        },
    ]
    return {
        "ok": all(p["status"] == _OK for p in probes),
        "warn_count": sum(1 for p in probes if p["status"] == _WARN),
        "probes": probes,
        "promo_calling_window": {"start": win_start, "end": win_end, "tz": "IST"},
    }


# --------------------------------------------------------------------------- #
# Delivery-outcome probe (2026-07-11 loop): closes the "production_ready:true =
# tautology" gap. Before this probe, no probe in _PROBES ever returned _BLOCKER
# — every probe returned _OK/_WARN/_NEUTRAL — so `blockers = [...]` in
# activation_readiness() was structurally guaranteed to be empty, and
# `launch_ready = not blockers` was always True regardless of whether any real
# paid customer had actually received anything. This probe asks the one
# question the shape-check probes cannot: is there a paying customer whose
# `deliverable_completion_pct` is stuck at 0 more than 24h post-payment? If
# yes → _WARN with actionable next step (Admin → Delivery Cockpit → Generate
# Content). Cached 60s to keep the public /api/activation/summary cheap.
# Never raises: clients_store / customer_delivery_status are already defensive;
# any unexpected error → _NEUTRAL (fail-open — never breaks the endpoint).
_FIRST_PAID_TTL_S = 60
_FIRST_PAID_CACHE: dict[str, Any] = {"at": 0.0, "result": None}


def _first_paid_delivery() -> dict[str, Any]:
    """Delivery-outcome probe: WARN when paid customers exist but no
    deliverables have shipped 24h+ after activation.

    PII discipline (2026-07-11 hardening):
      - `checks` and `action` NEVER contain client_id, business name, phone,
        email, or any other identifier — the /summary + /readiness endpoints
        surface this probe's dict verbatim, and even the admin readiness
        endpoint keeps PII-out for defense-in-depth (log-forwarding, screenshots
        during screenshares, third-party log processors).
      - Instead of naming a stale customer, we expose only aggregate counts and
        an `oldest_pending_hours` bucket ("24-48h" / "48-72h" / "72h+"), so the
        admin knows severity without knowing identity.
      - On evaluation failure we return WARN (NOT NEUTRAL) with a generic
        sanitized reason — a silent NEUTRAL would let a broken store hide the
        exact "audit passed but not delivering" red flag this probe exists to
        catch. The raw exception message is NEVER surfaced (would leak DB
        connect strings / internal IPs / stack fragments); only the exception
        type name (e.g. "OperationalError") goes into a bounded diagnostic.
    """
    import time
    from datetime import datetime, timedelta, timezone

    now = time.time()
    cached = _FIRST_PAID_CACHE.get("result")
    if cached is not None and now - float(_FIRST_PAID_CACHE.get("at") or 0.0) < _FIRST_PAID_TTL_S:
        return cached

    checks = {
        "paid_customers": 0,
        "with_progress": 0,
        "with_zero_deliverables_24h_plus": 0,
        "oldest_pending_hours": None,  # None | "24-48h" | "48-72h" | "72h+"
    }
    oldest_stale_hours: float = 0.0
    try:
        from app.marketing import clients_store, product_one_delivery

        clients = clients_store.list_clients(status="active") or []
        for c in clients:
            try:
                if not product_one_delivery._client_plan_paid(c):
                    continue
                checks["paid_customers"] += 1
                cid = str(c.get("id") or "")
                state = product_one_delivery.customer_delivery_status(cid, c) or {}
                pct = int(state.get("deliverable_completion_pct") or 0)
                if pct > 0:
                    checks["with_progress"] += 1
                    continue
                raw = str(c.get("created_at") or "")
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
                    if age_hours > 24:
                        checks["with_zero_deliverables_24h_plus"] += 1
                        if age_hours > oldest_stale_hours:
                            oldest_stale_hours = age_hours
                except Exception:
                    # can't parse activation timestamp — do NOT count as stale
                    # (would false-alarm on any client with malformed created_at)
                    pass
            except Exception:
                # per-customer eval failure must not abort the whole probe.
                # A single bad row does NOT flip the overall signal to WARN —
                # the WARN is reserved for stale-paid or wholesale eval failure.
                continue
    except Exception as exc:
        # Wholesale eval failure: store unavailable, or heavy import failure.
        # WARN (not NEUTRAL) is intentional — a silent NEUTRAL would let a
        # broken store hide the exact signal the probe exists to surface.
        # Sanitize: expose only exception TYPE (`OperationalError`,
        # `ConnectionRefusedError`, ...) — never the message (may contain host
        # IP, DB path, or SQL fragment).
        result = {
            "key": "first_paid_delivery",
            "label": "First paid customer delivery signal",
            "category": "revenue",
            "status": _WARN,
            "env_vars": [],
            "checks": {
                "paid_customers": 0,
                "with_progress": 0,
                "with_zero_deliverables_24h_plus": 0,
                "oldest_pending_hours": None,
                "eval_error": True,
                "eval_error_type": type(exc).__name__[:60],
            },
            "action": (
                "Delivery evidence could not be evaluated (clients_store / "
                "product_one_delivery raised). Admin → /app/admin → Delivery "
                "Cockpit — verify store connectivity + retry."
            ),
            "doc": "app/marketing/product_one_delivery.py",
        }
        _FIRST_PAID_CACHE.update({"at": now, "result": result})
        return result

    # Bucketize oldest stale age (aggregate, no per-customer timestamp exposed)
    if oldest_stale_hours >= 72:
        checks["oldest_pending_hours"] = "72h+"
    elif oldest_stale_hours >= 48:
        checks["oldest_pending_hours"] = "48-72h"
    elif oldest_stale_hours >= 24:
        checks["oldest_pending_hours"] = "24-48h"

    if checks["paid_customers"] == 0:
        status_val = _NEUTRAL
        action = ""
    elif checks["with_zero_deliverables_24h_plus"] > 0:
        status_val = _WARN
        bucket = checks["oldest_pending_hours"] or "24h+"
        action = (
            f"{checks['with_zero_deliverables_24h_plus']} paid customer(s) have "
            f"0/10 deliverables (oldest {bucket} post-activation). "
            "Admin → /app/admin → Delivery Cockpit → Generate Content / Manual Proof. "
            "This is the 'audit passed but not delivering' signal — fix now."
        )
    else:
        status_val = _OK
        action = ""

    result = {
        "key": "first_paid_delivery",
        "label": "First paid customer delivery signal",
        "category": "revenue",
        "status": status_val,
        "env_vars": [],
        "checks": checks,
        "action": action,
        "doc": "app/marketing/product_one_delivery.py",
    }
    _FIRST_PAID_CACHE.update({"at": now, "result": result})
    return result


_PROBES = (
    # Phase 1: Survival (visibility + trust + edge) + first-revenue UPI. Razorpay removed 2026-06-18.
    _sentry,
    _posthog,
    _turnstile,
    _cloudflare_tunnel,
    _upi,
    _first_paid_delivery,
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
    # `first_paid_delivery` sits in Survival: no point chasing Visibility/Sellable
    # levers if the very first paid customer's deliverables never shipped.
    (1, "Survival", ("sentry", "posthog", "turnstile", "cloudflare_tunnel", "upi", "first_paid_delivery", "qdrant_rag")),
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
    "first_paid_delivery": _first_paid_delivery,
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
    """Public launch snapshot for explorer + status widgets (no secrets, no auth).

    Counts + booleans ONLY. The NAMED `blockers`/`warns` (which specific controls
    are unarmed, e.g. turnstile/sentry) are ADMIN-only via `/readiness` — exposing
    them publicly hands an attacker a recon list of weak defenses (2026-07-06 sec
    sweep). Frontend consumers guard with `|| []` so count-only degrades cleanly."""
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

    # Advisory compliance section (TRAI/DPDP). Separate from `items`/blockers so
    # it never flips ready_for_first_paid_customer for existing consumers.
    try:
        compliance = _compliance_env()
    except Exception as exc:  # pragma: no cover - defensive
        compliance = {"ok": False, "error": str(exc)[:120]}

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
        "compliance": compliance,
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
