"""Master Project Blueprint — canonical, versioned architecture graph.

Single source of truth for the ``/app/explorer`` **Master Blueprint** mode,
served read-only by :mod:`app.api.blueprint` (``GET /api/blueprint/graph``).
The legacy hand-curated graph inside ``frontend/explorer.html`` is preserved
untouched; this module is the *additive* canonical contract the mission asked
for so the frontend stops hard-coding its own architecture truth.

Design discipline (Agent Harness Engineering Standard v0.1, 2026-07-22,
``C:\\Users\\Ratanshila\\Downloads\\Agent_Harness_Engineering_Standard.docx`` —
owner-declared authoritative):
  * **Schema-validated contract** — every node/edge/flow has required fields and
    :func:`validate_graph` is the pass/fail gate (the M2 tool-contract analogue).
  * **Evidence artifacts** — every implemented node names real repo files; the
    validator refuses an "implemented" node with no evidence.
  * **Honest status** — unverified runtime is ``UNKNOWN``, never a fabricated
    "healthy"; roadmap items are ``PLANNED``; retired items ``LEGACY`` /
    ``DEPRECATED``. Never invent a node.
  * **Fail-closed safety** — ``platform_dial`` / cold outbound is HARD OFF
    (``disabled=True``) and this module never re-enables it.

No secrets ever live here (env-var *names* only, never values).
"""

from __future__ import annotations

import os
import pathlib
import re
from typing import Any

# Canonical schema version — bump on any breaking node/edge/flow field change.
SCHEMA_VERSION = "2026-07-24-mbp-v2"

_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

# Canonical workforce truth lives in app.platform.team.STAFF (code-defined roster,
# includes the "manager"/Boss persona — NOT a 32nd employee). The graph MUST NOT
# hard-code a drifting number; it derives from the registry at build time.
_CANONICAL_STAFF_FALLBACK = 31  # last-known; used only if the registry import fails


def _workforce() -> dict[str, Any]:
    """Registry-derived workforce metadata (never raises).

    Returns the real ``len(STAFF)`` + per-product split from the canonical
    ``app.platform.team.STAFF`` roster so the blueprint stays in lock-step with
    code. ``source`` is ``registry`` on success, ``fallback`` if the import
    fails (degraded, still honest)."""
    try:
        from app.platform.team import STAFF

        by_product: dict[str, int] = {}
        for v in STAFF.values():
            p = str(v.get("product") or "unknown")
            by_product[p] = by_product.get(p, 0) + 1
        return {
            "count": len(STAFF),
            "by_product": by_product,
            "includes_manager": "manager" in STAFF,
            "source": "registry",
        }
    except Exception:
        return {
            "count": _CANONICAL_STAFF_FALLBACK,
            "by_product": {},
            "includes_manager": True,
            "source": "fallback",
        }


# --- evidence labels (honesty vocabulary) ---------------------------------
EVIDENCE_LABELS = (
    "PRODUCTION-PROVEN",
    "TEST-PROVEN",
    "CODE-PRESENT",
    "LOCAL-ONLY",
    "PLANNED",
    "UNVERIFIED",
    "EXTERNAL-BLOCKED",
    "LEGACY",
    "DEPRECATED",
    "UNKNOWN",
)
# statuses that assert working code → MUST carry file evidence.
_IMPLEMENTED = {"PRODUCTION-PROVEN", "TEST-PROVEN", "CODE-PRESENT"}

NODE_TYPES = (
    "edge",
    "app",
    "engine",
    "agent",
    "provider",
    "store",
    "integration",
    "observability",
    "compliance",
    "frontend",
    "product",
)
EDGE_KINDS = (
    "flow",
    "calls",
    "reads",
    "writes",
    "deploys",
    "guards",
    "observes",
    "routes_to",
    "triggers",
    "depends_on",
)

# Optional node fields (P1 schema expansion). Absent/None/empty = honestly
# UNKNOWN, never fabricated. Required fields are validated in validate_graph.
_REQUIRED_NODE_FIELDS = ("id", "title", "layer", "domain", "type", "status", "files", "desc")
_OPTIONAL_NODE_FIELDS = (
    "flags",
    "disabled",
    "runtime",
    "io",  # {"input": str|None, "output": str|None} | None
    "process",  # short "what it does" step | None
    "triggers",  # list of trigger descriptions
    "feedback_loop",  # str describing any close-the-loop signal | None
    "tech_refs",  # list of legacy technical-graph module/id hints for drill-down
)

# --- Layers 1-9 (swimlanes) -----------------------------------------------
LAYERS: list[dict[str, Any]] = [
    {
        "id": 1,
        "key": "edge",
        "title": "Ingress & Edge",
        "desc": "Caddy TLS termination + reverse proxy in front of the app.",
    },
    {
        "id": 2,
        "key": "app",
        "title": "Application",
        "desc": "FastAPI app + ~700 domain routes (server-rendered HTML).",
    },
    {
        "id": 3,
        "key": "automation",
        "title": "Automation & AI Staff",
        "desc": "Celery worker/beat, scheduler, agent runtime, 31 canonical AI staff.",
    },
    {
        "id": 4,
        "key": "ai",
        "title": "AI / LLM Providers",
        "desc": "Free-only LLM/STT/TTS chain with 429 circuit-breaker.",
    },
    {
        "id": 5,
        "key": "voice",
        "title": "Voice & Telephony",
        "desc": "FreeSWITCH + Vobiz SIP + WS voice (FROZEN this wave).",
    },
    {
        "id": 6,
        "key": "data",
        "title": "Data Stores",
        "desc": "Postgres via PgBouncer, Redis, Qdrant RAG.",
    },
    {
        "id": 7,
        "key": "integrations",
        "title": "External Integrations",
        "desc": "WhatsApp, SMTP/IMAP, Maps, Stripe, UPI, Postiz, webhooks.",
    },
    {
        "id": 8,
        "key": "observability",
        "title": "Observability & Ops",
        "desc": "Prometheus/Grafana/Loki/Tempo/Sentry + health aggregators.",
    },
    {
        "id": 9,
        "key": "compliance",
        "title": "Security & Compliance",
        "desc": "DND/DPDP/consent gates, RBAC, tenant isolation, secrets.",
    },
]
_LAYER_IDS = {l["id"] for l in LAYERS}

# --- 18 domain blueprints --------------------------------------------------
DOMAINS: list[dict[str, Any]] = [
    {"id": 1, "key": "public_funnel", "title": "Public Funnel & Landing", "layer": 2},
    {"id": 2, "key": "pricing_packages", "title": "Pricing & Packages", "layer": 2},
    {"id": 3, "key": "signup_onboarding", "title": "Signup & Onboarding", "layer": 2},
    {"id": 4, "key": "billing_payments", "title": "Billing & Payments", "layer": 7},
    {"id": 5, "key": "lead_pipeline", "title": "Lead Pipeline & Prospecting", "layer": 3},
    {"id": 6, "key": "crm_hotqueue", "title": "CRM & Hot Queue", "layer": 3},
    {"id": 7, "key": "email_outreach", "title": "Email Outreach & Deliverability", "layer": 3},
    {"id": 8, "key": "content_gen", "title": "Content Generation", "layer": 3},
    {"id": 9, "key": "social_publish", "title": "Social Publishing", "layer": 7},
    {"id": 10, "key": "voice_telephony", "title": "Voice & Telephony", "layer": 5},
    {"id": 11, "key": "ai_staff_runtime", "title": "AI Staff & Agent Runtime", "layer": 3},
    {
        "id": 12,
        "key": "automation_scheduler",
        "title": "Automation Scheduler & Flow Runner",
        "layer": 3,
    },
    {"id": 13, "key": "owner_os_copilot", "title": "Owner OS & Copilot", "layer": 2},
    {"id": 14, "key": "customer_delivery", "title": "Customer Delivery & Assurance", "layer": 2},
    {"id": 15, "key": "kb_rag", "title": "Knowledge Base & RAG", "layer": 6},
    {"id": 16, "key": "integrations_webhooks", "title": "Integrations & Webhooks", "layer": 7},
    {"id": 17, "key": "observability_ops", "title": "Observability & Ops", "layer": 8},
    {"id": 18, "key": "security_compliance", "title": "Security, Compliance & Tenancy", "layer": 9},
]
_DOMAIN_KEYS = {d["key"] for d in DOMAINS}


def _n(nid, title, layer, domain, ntype, status, files, desc, **extra) -> dict[str, Any]:
    node = {
        "id": nid,
        "title": title,
        "layer": layer,
        "domain": domain,
        "type": ntype,
        "status": status,
        "files": list(files),
        "desc": desc,
        "flags": list(extra.get("flags", [])),
        "disabled": bool(extra.get("disabled", False)),
        "runtime": extra.get("runtime"),  # optional live-status probe key
        # P1 schema expansion — honest defaults (None/empty = UNKNOWN, not faked).
        "io": extra.get("io"),
        "process": extra.get("process"),
        "triggers": list(extra.get("triggers", [])),
        "feedback_loop": extra.get("feedback_loop"),
        # canonical→technical drill-down hints (module basenames the legacy
        # technical graph also carries); defaults to this node's own files.
        "tech_refs": list(extra.get("tech_refs", []) or files),
    }
    return node


# --- NODES (evidence-backed; every implemented node names real repo files) --
NODES: list[dict[str, Any]] = [
    # L1 Edge
    _n(
        "edge_caddy",
        "Caddy (TLS reverse proxy)",
        1,
        "security_compliance",
        "edge",
        "PRODUCTION-PROVEN",
        ["docker-compose.edge.yml", "docker-compose.vps.yml"],
        "Host TLS for leadsgenai.in → app:8080.",
    ),
    # L2 App core
    _n(
        "app_fastapi",
        "FastAPI app (leadgen_app)",
        2,
        "public_funnel",
        "app",
        "PRODUCTION-PROVEN",
        ["app/main.py"],
        "ASGI app, ~700 routes, port 8080 (host 8000).",
    ),
    # Domain 1 — Public funnel
    _n(
        "public_landing",
        "Marketing landing + lead magnets",
        2,
        "public_funnel",
        "frontend",
        "PRODUCTION-PROVEN",
        ["frontend/marketing.html", "app/api/public_site.py"],
        "28-tab marketing site + /audit /site-audit /demo magnets.",
    ),
    _n(
        "activation_summary",
        "Launch/activation summary",
        2,
        "public_funnel",
        "app",
        "PRODUCTION-PROVEN",
        ["app/api/activation.py"],
        "Public readiness snapshot (no secrets).",
        runtime="activation",
    ),
    # Domain 2 — Pricing
    _n(
        "pricing_page",
        "Pricing page",
        2,
        "pricing_packages",
        "frontend",
        "PRODUCTION-PROVEN",
        ["frontend/pricing.html"],
        "Two Marketing plans + Voice bands.",
    ),
    _n(
        "packages_truth",
        "Package/plan truth",
        2,
        "pricing_packages",
        "app",
        "CODE-PRESENT",
        ["app/api/voice_product.py", "app/api/combo_product.py"],
        "Public package contract feeding pricing + billing.",
    ),
    # Domain 3 — Signup/onboarding
    _n(
        "signup_start",
        "Signup / start flow",
        2,
        "signup_onboarding",
        "frontend",
        "PRODUCTION-PROVEN",
        ["frontend/onboard.html", "app/api/customer_onboard.py"],
        "/start → account → plan selection.",
    ),
    _n(
        "customer_auth",
        "Customer auth",
        2,
        "signup_onboarding",
        "app",
        "CODE-PRESENT",
        ["app/api/customer_auth.py", "app/api/customer_totp.py"],
        "Customer login + optional TOTP.",
    ),
    # Domain 4 — Billing/payments
    _n(
        "upi_payments",
        "Manual UPI payments (primary)",
        7,
        "billing_payments",
        "integration",
        "PRODUCTION-PROVEN",
        ["app/api/upi_payments.py", "app/platform/upi_payments.py"],
        "Manual UPI intent → admin approval → activation.",
    ),
    _n(
        "stripe_intl",
        "Stripe (international only)",
        7,
        "billing_payments",
        "integration",
        "CODE-PRESENT",
        ["app/api/billing.py"],
        "Intl-only card path.",
        flags=["STRIPE_ENABLED"],
    ),
    _n(
        "subscription",
        "Subscription + entitlement",
        2,
        "billing_payments",
        "engine",
        "CODE-PRESENT",
        ["app/billing/subscription.py", "app/billing/entitlement_assurance.py"],
        "Plan sync from package truth + entitlement gate.",
    ),
    _n(
        "gst_invoice",
        "GST invoice (Rule-46 sequential)",
        2,
        "billing_payments",
        "engine",
        "CODE-PRESENT",
        ["app/billing/gst_invoice.py"],
        "Sequential INV/FY numbering; GST only when GSTIN set.",
    ),
    # Domain 5 — Lead pipeline
    _n(
        "prospector",
        "Prospecting (Maps/niche)",
        3,
        "lead_pipeline",
        "engine",
        "CODE-PRESENT",
        ["app/platform/prospector.py", "app/platform/niche_prospector.py"],
        "Google Maps Places prospecting, bounded lookups/run.",
    ),
    _n(
        "lead_harvester",
        "Lead harvester / import",
        3,
        "lead_pipeline",
        "engine",
        "CODE-PRESENT",
        ["app/platform/lead_harvester.py"],
        "CSV/import harvest (ToS-safe sources only).",
    ),
    _n(
        "lead_scoring",
        "Lead scoring",
        3,
        "lead_pipeline",
        "engine",
        "CODE-PRESENT",
        ["app/platform/lead_scoring.py"],
        "Score prospects Hot/Warm/Cold.",
    ),
    # Domain 6 — CRM/Hot queue
    _n(
        "crm",
        "Client CRM",
        3,
        "crm_hotqueue",
        "app",
        "CODE-PRESENT",
        ["app/api/clientcrm.py"],
        "Deals/prospects CRM surface.",
    ),
    _n(
        "hot_queue",
        "Hot Queue / inbox",
        2,
        "crm_hotqueue",
        "frontend",
        "PRODUCTION-PROVEN",
        ["frontend/inbox.html", "app/platform/speed_to_lead.py"],
        "Inbound inquiry → human follow-up mid-funnel.",
    ),
    # Domain 7 — Email outreach
    _n(
        "auto_outreach",
        "Auto email outreach",
        3,
        "email_outreach",
        "engine",
        "CODE-PRESENT",
        ["app/platform/auto_outreach.py"],
        "Daily cold email (cap 25/day + warmup).",
        flags=["OUTREACH_ENABLED"],
    ),
    _n(
        "email_warmup",
        "Email warmup + caps",
        3,
        "email_outreach",
        "engine",
        "CODE-PRESENT",
        ["app/platform/email_warmup.py"],
        "Ramp + daily send caps.",
    ),
    _n(
        "deliverability",
        "Deliverability monitor",
        3,
        "email_outreach",
        "engine",
        "CODE-PRESENT",
        ["app/platform/deliverability_monitor.py"],
        "Bounce/spam guard.",
    ),
    _n(
        "reply_agent",
        "Reply triage agent",
        3,
        "email_outreach",
        "agent",
        "CODE-PRESENT",
        ["app/platform/reply_agent.py"],
        "IMAP reply classification → guarded response.",
    ),
    # Domain 8 — Content
    _n(
        "content_auto",
        "Content generation",
        3,
        "content_gen",
        "engine",
        "CODE-PRESENT",
        ["app/api/contentauto.py", "app/api/growth_content.py"],
        "AI content gen → approval → publish.",
    ),
    # Domain 9 — Social
    _n(
        "social_publish",
        "Social publishing (Postiz)",
        7,
        "social_publish",
        "integration",
        "CODE-PRESENT",
        ["app/api/social_oauth.py", "app/platform/brand_pulse.py"],
        "Own-brand social publish via Postiz (4 channels).",
    ),
    # Domain 10 — Voice (FROZEN)
    _n(
        "voice_agent",
        "Voice agent (Swara/Kavya)",
        5,
        "voice_telephony",
        "agent",
        "CODE-PRESENT",
        ["app/voice_agent/agent.py"],
        "FROZEN this wave — visualize only.",
        flags=["AGENT_RUNTIME"],
    ),
    _n(
        "telephony_vobiz",
        "Vobiz telephony (India SIP)",
        5,
        "voice_telephony",
        "integration",
        "CODE-PRESENT",
        ["app/api/telephony_vobiz.py", "app/api/voiceai.py"],
        "Inbound + auto-callback (DLT-gated for cold).",
    ),
    _n(
        "free_ai_chain",
        "Free LLM/STT/TTS chain",
        4,
        "voice_telephony",
        "provider",
        "CODE-PRESENT",
        ["app/voice_agent/free_ai.py"],
        "Mistral→Groq→Cerebras→…; 429 breaker.",
    ),
    # Domain 11 — AI staff runtime
    _n(
        "agent_runtime",
        "Agent runtime (canary)",
        3,
        "ai_staff_runtime",
        "engine",
        "CODE-PRESENT",
        ["app/platform/agent_runtime.py"],
        "AGENT_RUNTIME=1 canary loop.",
        flags=["AGENT_RUNTIME"],
    ),
    _n(
        "team_roster",
        "AI staff roster (canonical registry)",
        3,
        "ai_staff_runtime",
        "engine",
        "PRODUCTION-PROVEN",
        ["app/platform/team.py", "app/api/agents.py"],
        "Canonical AI staff roster (count derived from app.platform.team.STAFF; "
        "includes Boss/manager persona).",
        runtime="team",
        process="Serve per-member live status (working/idle/offline) + today counts.",
        io={"input": "agent_events + STAFF registry", "output": "team_status() rollup"},
        triggers=["/api/agents/run", "scheduler jobs", "dashboard poll"],
        feedback_loop="agent_events feed today-counts back into status rollup.",
    ),
    # Domain 12 — Scheduler / flow runner
    _n(
        "scheduler",
        "Celery beat scheduler",
        3,
        "automation_scheduler",
        "engine",
        "PRODUCTION-PROVEN",
        ["app/platform/team_scheduler.py", "app/platform/scheduler_config.py"],
        "Durable beat (RUN_IN_PROCESS_SCHEDULER=0), boot-grace.",
    ),
    _n(
        "staff_jobs",
        "Staff scheduled jobs",
        3,
        "automation_scheduler",
        "engine",
        "CODE-PRESENT",
        ["app/tasks/staff_jobs.py"],
        "~24 scheduled jobs registry.",
    ),
    _n(
        "flow_runner",
        "Flow runner / process",
        3,
        "automation_scheduler",
        "engine",
        "CODE-PRESENT",
        ["app/api/growth_process.py"],
        "Flow runs, journal, replay.",
    ),
    # Domain 13 — Owner OS
    _n(
        "owner_os",
        "Owner OS (sole authority)",
        2,
        "owner_os_copilot",
        "app",
        "CODE-PRESENT",
        ["app/api/owner_os.py", "frontend/owner_os.html"],
        "Owner control plane.",
    ),
    _n(
        "owner_copilot",
        "OpenClaw Owner Copilot",
        2,
        "owner_os_copilot",
        "app",
        "LOCAL-ONLY",
        ["app/api/owner_copilot.py"],
        "NL copilot edge; OPENCLAW_ENABLED off in prod.",
        flags=["OPENCLAW_ENABLED"],
    ),
    # Domain 14 — Customer delivery
    _n(
        "customer_dashboard",
        "Customer dashboard",
        2,
        "customer_delivery",
        "frontend",
        "PRODUCTION-PROVEN",
        ["app/api/customer_dashboard.py", "frontend/customer_dashboard.html"],
        "Customer portal + delivery view.",
    ),
    _n(
        "delivery_assurance",
        "Delivery assurance",
        2,
        "customer_delivery",
        "engine",
        "CODE-PRESENT",
        ["app/platform/client_health.py", "frontend/delivery_command_center.html"],
        "Per-client delivery health + proof.",
    ),
    # Domain 15 — KB / RAG
    _n(
        "kb_refresh",
        "KB / RAG refresh",
        6,
        "kb_rag",
        "engine",
        "CODE-PRESENT",
        ["app/platform/kb_refresh.py"],
        "Qdrant kb_main namespaces refresh.",
    ),
    _n(
        "skill_library",
        "Skill library",
        6,
        "kb_rag",
        "engine",
        "CODE-PRESENT",
        ["app/platform/skill_library.py"],
        "Auto-learned skills store.",
    ),
    _n(
        "qdrant",
        "Qdrant (RAG vectors)",
        6,
        "kb_rag",
        "store",
        "PRODUCTION-PROVEN",
        ["docker-compose.vps.yml"],
        "127.0.0.1:6333 single kb_main.",
    ),
    # Domain 16 — Integrations / webhooks
    _n(
        "whatsapp",
        "WhatsApp (Meta + WAHA)",
        7,
        "integrations_webhooks",
        "integration",
        "PRODUCTION-PROVEN",
        ["app/integrations/whatsapp.py", "app/api/whatsapp.py"],
        "1-click human send; bulk auto-send OFF (ban-safety).",
        flags=["WHATSAPP_AUTO_SEND"],
    ),
    _n(
        "webhooks",
        "Inbound/outbound webhooks",
        7,
        "integrations_webhooks",
        "integration",
        "CODE-PRESENT",
        ["app/api/webhooks.py", "app/api/customer_webhooks.py"],
        "In-network hooks use app:8080.",
    ),
    # Domain 17 — Observability
    _n(
        "automation_health",
        "Automation health aggregator",
        8,
        "observability_ops",
        "observability",
        "CODE-PRESENT",
        ["app/platform/automation_health.py"],
        "Heartbeats, DLQ/queue depth.",
        runtime="automation_health",
    ),
    _n(
        "infra_handler",
        "Infra snapshot",
        8,
        "observability_ops",
        "observability",
        "CODE-PRESENT",
        ["app/platform/infra_handler.py"],
        "Disk/mem/backup score.",
    ),
    _n(
        "obs_stack",
        "Prometheus/Grafana/Loki/Tempo",
        8,
        "observability_ops",
        "observability",
        "PRODUCTION-PROVEN",
        ["docker-compose.observability.yml"],
        "~13 obs containers + Sentry.",
    ),
    # Domain 18 — Security & compliance
    _n(
        "rbac",
        "RBAC + tenant isolation",
        9,
        "security_compliance",
        "compliance",
        "CODE-PRESENT",
        ["app/platform/rbac.py", "app/platform/tenant_manager.py"],
        "Roles + module grants; fail-open tenant middleware.",
    ),
    _n(
        "dpdp",
        "DPDP consent + retention",
        9,
        "security_compliance",
        "compliance",
        "CODE-PRESENT",
        ["app/platform/dpdp.py", "app/platform/data_privacy.py"],
        "Consent ledger, 90-day recording retention, purge.",
    ),
    _n(
        "platform_dial",
        "platform_dial (cold outbound)",
        9,
        "security_compliance",
        "compliance",
        "DEPRECATED",
        ["app/platform/platform_dial.py"],
        "HARD OFF (user-mandate 2026-07-05). 3-layer kill; never re-enabled.",
        flags=["PLATFORM_DIAL_DAILY"],
        disabled=True,
    ),
    # L6 stores
    _n(
        "postgres",
        "Postgres via PgBouncer",
        6,
        "kb_rag",
        "store",
        "PRODUCTION-PROVEN",
        ["docker-compose.vps.yml", "app/config.py"],
        "leadgen_db via :6432.",
    ),
    _n(
        "redis",
        "Redis (broker + cache)",
        6,
        "kb_rag",
        "store",
        "PRODUCTION-PROVEN",
        ["docker-compose.vps.yml", "app/config.py"],
        "Celery broker + call-state + DLQ.",
    ),
]

# --- EDGES (source→target within the canonical node set) ------------------
EDGES: list[dict[str, Any]] = [
    {"source": "edge_caddy", "target": "app_fastapi", "kind": "flow", "label": "TLS proxy"},
    {"source": "app_fastapi", "target": "public_landing", "kind": "calls"},
    {"source": "app_fastapi", "target": "activation_summary", "kind": "calls"},
    {"source": "public_landing", "target": "pricing_page", "kind": "flow"},
    {"source": "pricing_page", "target": "packages_truth", "kind": "reads"},
    {"source": "pricing_page", "target": "signup_start", "kind": "flow"},
    {"source": "signup_start", "target": "customer_auth", "kind": "calls"},
    {"source": "signup_start", "target": "upi_payments", "kind": "flow"},
    {"source": "upi_payments", "target": "subscription", "kind": "flow"},
    {"source": "stripe_intl", "target": "subscription", "kind": "flow"},
    {"source": "subscription", "target": "gst_invoice", "kind": "flow"},
    {"source": "subscription", "target": "customer_dashboard", "kind": "flow"},
    {"source": "prospector", "target": "lead_scoring", "kind": "flow"},
    {"source": "lead_harvester", "target": "lead_scoring", "kind": "flow"},
    {"source": "lead_scoring", "target": "crm", "kind": "writes"},
    {"source": "lead_scoring", "target": "auto_outreach", "kind": "flow"},
    {"source": "auto_outreach", "target": "email_warmup", "kind": "guards"},
    {"source": "auto_outreach", "target": "deliverability", "kind": "guards"},
    {"source": "auto_outreach", "target": "reply_agent", "kind": "flow"},
    {"source": "reply_agent", "target": "hot_queue", "kind": "flow"},
    {"source": "crm", "target": "hot_queue", "kind": "flow"},
    {"source": "content_auto", "target": "social_publish", "kind": "flow"},
    {"source": "voice_agent", "target": "free_ai_chain", "kind": "calls"},
    {"source": "telephony_vobiz", "target": "voice_agent", "kind": "flow"},
    {"source": "voice_agent", "target": "dpdp", "kind": "guards"},
    {"source": "agent_runtime", "target": "team_roster", "kind": "calls"},
    {"source": "scheduler", "target": "staff_jobs", "kind": "calls"},
    {"source": "staff_jobs", "target": "flow_runner", "kind": "flow"},
    {"source": "staff_jobs", "target": "auto_outreach", "kind": "calls"},
    {"source": "staff_jobs", "target": "content_auto", "kind": "calls"},
    {"source": "staff_jobs", "target": "prospector", "kind": "calls"},
    {"source": "agent_runtime", "target": "free_ai_chain", "kind": "calls"},
    {"source": "owner_os", "target": "owner_copilot", "kind": "calls"},
    {"source": "owner_copilot", "target": "team_roster", "kind": "reads"},
    {"source": "customer_dashboard", "target": "delivery_assurance", "kind": "reads"},
    {"source": "kb_refresh", "target": "qdrant", "kind": "writes"},
    {"source": "skill_library", "target": "qdrant", "kind": "reads"},
    {"source": "free_ai_chain", "target": "qdrant", "kind": "reads"},
    {"source": "whatsapp", "target": "webhooks", "kind": "flow"},
    {"source": "webhooks", "target": "hot_queue", "kind": "flow"},
    {"source": "automation_health", "target": "obs_stack", "kind": "observes"},
    {"source": "infra_handler", "target": "obs_stack", "kind": "observes"},
    {"source": "scheduler", "target": "automation_health", "kind": "observes"},
    {"source": "rbac", "target": "app_fastapi", "kind": "guards"},
    {"source": "dpdp", "target": "telephony_vobiz", "kind": "guards"},
    {"source": "platform_dial", "target": "telephony_vobiz", "kind": "guards"},
    {"source": "app_fastapi", "target": "postgres", "kind": "reads"},
    {"source": "app_fastapi", "target": "redis", "kind": "reads"},
    {"source": "scheduler", "target": "redis", "kind": "reads"},
    {"source": "crm", "target": "postgres", "kind": "writes"},
    {"source": "subscription", "target": "postgres", "kind": "writes"},
    {"source": "team_roster", "target": "redis", "kind": "reads"},
]

# --- FLOWS 9.1-9.11 (end-to-end, ordered node ids) ------------------------
FLOWS: list[dict[str, Any]] = [
    {
        "id": "9.1",
        "title": "Lead discovery → scoring → outreach",
        "steps": ["prospector", "lead_scoring", "crm", "auto_outreach"],
    },
    {
        "id": "9.2",
        "title": "Inquiry → Hot Queue → human follow-up",
        "steps": ["public_landing", "webhooks", "hot_queue"],
    },
    {
        "id": "9.3",
        "title": "Content generation → approval → social publish",
        "steps": ["content_auto", "social_publish"],
    },
    {
        "id": "9.4",
        "title": "Reply agent → classification → guarded response",
        "steps": ["auto_outreach", "reply_agent", "hot_queue"],
    },
    {
        "id": "9.5",
        "title": "Customer signup → onboarding → delivery assurance",
        "steps": ["signup_start", "customer_auth", "customer_dashboard", "delivery_assurance"],
    },
    {
        "id": "9.6",
        "title": "UPI/payment → subscription → invoice",
        "steps": ["pricing_page", "upi_payments", "subscription", "gst_invoice"],
    },
    {
        "id": "9.7",
        "title": "AI staff → scheduler → execution → audit",
        "steps": ["scheduler", "staff_jobs", "agent_runtime", "team_roster"],
    },
    {
        "id": "9.8",
        "title": "Self-improve / flow runner → evaluation → requeue",
        "steps": ["staff_jobs", "flow_runner", "skill_library"],
    },
    {
        "id": "9.9",
        "title": "Runtime health → alert → recovery/DLQ",
        "steps": ["scheduler", "automation_health", "obs_stack"],
    },
    {
        "id": "9.10",
        "title": "Inbound/callback → consent gate → voice (DLT-gated)",
        "steps": ["telephony_vobiz", "dpdp", "voice_agent"],
    },
    {
        "id": "9.11",
        "title": "KB/RAG refresh → vector store → LLM retrieval",
        "steps": ["kb_refresh", "qdrant", "free_ai_chain"],
    },
]


def build_graph(*, check_files: bool = False) -> dict[str, Any]:
    """Return the FULL canonical graph payload (ADMIN-only — carries repo file
    paths, flags, runtime keys, tech_refs). ``check_files`` adds a per-node
    ``file_ok`` marker for the drift HUD; off by default (hot path)."""
    wf = _workforce()
    nodes = [dict(x) for x in NODES]
    for n in nodes:
        if n["id"] == "team_roster":
            n["workforce"] = wf  # registry-derived; never a hard-coded drift number
        if check_files:
            n["file_ok"] = all((_ROOT / f).exists() for f in n["files"])
    return {
        "schema_version": SCHEMA_VERSION,
        "visibility": "admin",
        "layers": LAYERS,
        "domains": DOMAINS,
        "evidence_labels": list(EVIDENCE_LABELS),
        "node_types": list(NODE_TYPES),
        "edge_kinds": list(EDGE_KINDS),
        "edge_types": list(EDGE_KINDS),  # alias for the schema-contract naming
        "node_fields": {
            "required": list(_REQUIRED_NODE_FIELDS),
            "optional": list(_OPTIONAL_NODE_FIELDS),
        },
        "workforce": wf,
        "nodes": nodes,
        "edges": EDGES,
        "flows": FLOWS,
        "counts": {
            "nodes": len(NODES),
            "edges": len(EDGES),
            "layers": len(LAYERS),
            "domains": len(DOMAINS),
            "flows": len(FLOWS),
            "workforce": wf["count"],
        },
    }


# --- coarse public state (no operational-weakness leakage) -----------------
_PUBLIC_STATE = {
    "PRODUCTION-PROVEN": "live",
    "TEST-PROVEN": "live",
    "CODE-PRESENT": "building",
    "LOCAL-ONLY": "building",
    "EXTERNAL-BLOCKED": "building",
    "PLANNED": "planned",
    "UNVERIFIED": "planned",
    "UNKNOWN": "planned",
    "LEGACY": "off",
    "DEPRECATED": "off",
}


def build_public_graph() -> dict[str, Any]:
    """SANITIZED public contract (no auth). Business-safe labels + high-level
    connections ONLY. Never exposes: repo paths, internal modules, feature-flag
    inventory, runtime probe keys, security-control implementation detail,
    granular evidence labels, or operational-weakness hints. Descriptions are
    dropped entirely (they can carry infra detail like ports/hosts)."""
    wf = _workforce()
    nodes = [
        {
            "id": n["id"],
            "title": n["title"],
            "layer": n["layer"],
            "domain": n["domain"],
            "state": "off" if n["disabled"] else _PUBLIC_STATE.get(n["status"], "planned"),
            # disabled is a compliance-positive fact (feature is OFF), not sensitive
            "disabled": bool(n["disabled"]),
        }
        for n in NODES
    ]
    edges = [{"source": e["source"], "target": e["target"]} for e in EDGES]
    return {
        "schema_version": SCHEMA_VERSION,
        "visibility": "public",
        "layers": [{"id": l["id"], "title": l["title"]} for l in LAYERS],
        "domains": [
            {"id": d["id"], "key": d["key"], "title": d["title"], "layer": d["layer"]}
            for d in DOMAINS
        ],
        "nodes": nodes,
        "edges": edges,
        "flows": [{"id": f["id"], "title": f["title"], "steps": f["steps"]} for f in FLOWS],
        "workforce": {"count": wf["count"]},  # count is a marketing-safe number
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "layers": len(LAYERS),
            "domains": len(DOMAINS),
            "flows": len(FLOWS),
        },
    }


# --- multi-hop traversal (cycle-safe, deterministic) -----------------------
def _adjacency() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Precomputed adjacency: (downstream, upstream), each sorted for
    deterministic output."""
    down: dict[str, list[str]] = {n["id"]: [] for n in NODES}
    up: dict[str, list[str]] = {n["id"]: [] for n in NODES}
    for e in EDGES:
        s, t = e["source"], e["target"]
        if s in down and t in up:
            down[s].append(t)
            up[t].append(s)
    for d in (down, up):
        for k in d:
            d[k] = sorted(set(d[k]))
    return down, up


def traverse(start: str, direction: str = "down", depth: int = 3) -> list[str]:
    """BFS from ``start`` up to ``depth`` hops. ``direction`` = down|up|both.
    Cycle-safe (visited set), deterministic (sorted per level), excludes start."""
    down, up = _adjacency()
    if start not in down:
        return []
    depth = max(0, min(int(depth or 0), 12))
    maps = {"down": [down], "up": [up], "both": [down, up]}.get(direction, [down])
    visited = {start}
    frontier = [start]
    order: list[str] = []
    for _ in range(depth):
        nxt: list[str] = []
        for node in frontier:
            for m in maps:
                for nb in m.get(node, []):
                    if nb not in visited:
                        visited.add(nb)
                        nxt.append(nb)
        for nb in sorted(set(nxt)):
            if nb not in order:
                order.append(nb)
        frontier = sorted(set(nxt))
        if not frontier:
            break
    return order


def shortest_path(src: str, tgt: str) -> list[str]:
    """Directed (downstream) shortest path src→tgt (BFS). [] if none / unknown
    node. Same src==tgt → [src]. Deterministic (sorted neighbour expansion)."""
    down, _ = _adjacency()
    if src not in down or tgt not in down:
        return []
    if src == tgt:
        return [src]
    prev: dict[str, str] = {}
    visited = {src}
    frontier = [src]
    while frontier:
        nxt: list[str] = []
        for node in frontier:
            for nb in down.get(node, []):
                if nb not in visited:
                    visited.add(nb)
                    prev[nb] = node
                    if nb == tgt:
                        path = [tgt]
                        while path[-1] != src:
                            path.append(prev[path[-1]])
                        return list(reversed(path))
                    nxt.append(nb)
        frontier = sorted(set(nxt))
    return []


def impact(start: str, depth: int = 3) -> list[str]:
    """Downstream blast-radius from ``start`` (what breaks if this changes)."""
    return traverse(start, "down", depth)


_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9]{16,}|AIza[0-9A-Za-z\-_]{20,}|xox[baprs]-[0-9A-Za-z\-]{10,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)


def validate_graph(*, strict_files: bool = True) -> dict[str, Any]:
    """Pass/fail integrity gate (harness-standard evidence artifact).

    Errors (block go): duplicate ids · dangling edge endpoints · orphan nodes ·
    implemented-without-evidence · bad layer/domain/type/status · flow step not a
    node · platform_dial not disabled · secret-shaped literal · (strict) file ref
    that does not resolve on disk.
    """
    errors: list[str] = []
    warnings: list[str] = []
    ids = [n["id"] for n in NODES]
    idset = set(ids)

    # duplicate node ids
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            errors.append(f"duplicate node id: {i}")
        seen.add(i)

    # per-node field validation
    for n in NODES:
        for req in _REQUIRED_NODE_FIELDS:
            if req not in n:
                errors.append(f"{n['id']}: missing required field {req}")
        if n["layer"] not in _LAYER_IDS:
            errors.append(f"{n['id']}: bad layer {n['layer']}")
        if n["domain"] not in _DOMAIN_KEYS:
            errors.append(f"{n['id']}: unknown domain {n['domain']}")
        if n["type"] not in NODE_TYPES:
            errors.append(f"{n['id']}: bad type {n['type']}")
        if n["status"] not in EVIDENCE_LABELS:
            errors.append(f"{n['id']}: bad status {n['status']}")
        if n["status"] in _IMPLEMENTED and not n["files"]:
            errors.append(f"{n['id']}: implemented ({n['status']}) but no file evidence")
        # optional-field type discipline (present-but-wrong-type = drift)
        if not isinstance(n.get("triggers", []), list):
            errors.append(f"{n['id']}: triggers must be a list")
        if not isinstance(n.get("tech_refs", []), list):
            errors.append(f"{n['id']}: tech_refs must be a list")
        if n.get("io") is not None and not isinstance(n["io"], dict):
            errors.append(f"{n['id']}: io must be dict|None")
        if strict_files:
            for f in n["files"]:
                if not (_ROOT / f).exists():
                    errors.append(f"{n['id']}: file ref not on disk: {f}")
        if _SECRET_RE.search(n.get("desc", "") + " ".join(n["files"])):
            errors.append(f"{n['id']}: secret-shaped literal in node")
        # workforce-truth guard — the stale "18 AI staff" number must never return
        if "18 AI staff" in (n.get("desc", "") + " " + n.get("title", "")):
            errors.append(f"{n['id']}: stale '18 AI staff' workforce number")

    # edges resolve + degree
    deg = {i: 0 for i in idset}
    for e in EDGES:
        s, t = e.get("source"), e.get("target")
        if s not in idset or t not in idset:
            errors.append(f"dangling edge: {s} -> {t}")
        else:
            deg[s] += 1
            deg[t] += 1
        if e.get("kind") not in EDGE_KINDS:
            errors.append(f"edge {s}->{t}: bad kind {e.get('kind')}")
    orphans = sorted(i for i, d in deg.items() if d == 0)
    for o in orphans:
        errors.append(f"orphan node (0 edges): {o}")

    # flows
    flow_ids = [f["id"] for f in FLOWS]
    if len(set(flow_ids)) != len(flow_ids):
        errors.append("duplicate flow id")
    for f in FLOWS:
        for step in f["steps"]:
            if step not in idset:
                errors.append(f"flow {f['id']}: step not a node: {step}")

    # safety invariant — cold outbound stays HARD OFF
    pd = next((n for n in NODES if n["id"] == "platform_dial"), None)
    if not pd or not pd.get("disabled"):
        errors.append("platform_dial must be disabled=True (HARD OFF invariant)")

    # workforce-truth guard on layer descriptions too
    for l in LAYERS:
        if "18 AI staff" in l.get("desc", ""):
            errors.append(f"layer {l['id']}: stale '18 AI staff' workforce number")

    # coverage warnings (non-blocking)
    covered_layers = {n["layer"] for n in NODES}
    for l in _LAYER_IDS:
        if l not in covered_layers:
            warnings.append(f"layer {l} has no node")
    covered_domains = {n["domain"] for n in NODES}
    for d in _DOMAIN_KEYS:
        if d not in covered_domains:
            warnings.append(f"domain {d} has no node")

    return {
        "ok": not errors,
        "schema_version": SCHEMA_VERSION,
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "nodes": len(NODES),
            "edges": len(EDGES),
            "flows": len(FLOWS),
            "orphans": len(orphans),
            "workforce": _workforce()["count"],
        },
    }


if __name__ == "__main__":
    import json

    print(json.dumps(validate_graph(strict_files=True), indent=2))
