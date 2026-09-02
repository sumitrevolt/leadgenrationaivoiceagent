"""
Plugin Catalog — initial registration of existing LeadGen AI components.

This module bootstraps the plugin registry by registering manifests for
every significant existing component. It is called once at startup
(import-time side effect is DELIBERATE here — the catalog IS the inventory).

Each manifest maps one existing component to the governed plugin contract.
Nothing changes in runtime behaviour — this is an additive observation layer.
"""

from __future__ import annotations

from .plugin_manifest import (
    AuditEventTypes,
    Budget,
    EvidenceStatus,
    HealthProbe,
    MetricsSpec,
    PluginCategory,
    PluginManifest,
    PluginScope,
    PrivacyClass,
    RetryPolicy,
    RiskClass,
    register,
)


def bootstrap_catalog() -> None:
    """Register all known plugins. Idempotent (re-register = update)."""

    # =====================================================================
    # A. MODEL ROUTING PLUGINS
    # =====================================================================

    register(
        PluginManifest(
            plugin_id="free_ai_chain",
            version="1.0.0",
            category=PluginCategory.MODEL_ROUTING,
            owner="SRE",
            business_outcome="Primary free LLM routing (Mistral→Groq→Cerebras→Gemini cascade)",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            feature_flag="",
            budget=Budget(timeout_s=30.0, token_budget=4000, wall_clock_budget_s=45.0),
            retry_policy=RetryPolicy(max_retries=2, backoff_base_s=2.0),
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            health_probe=HealthProbe(endpoint="/health", interval_s=60.0),
            metrics=MetricsSpec(
                counters=["llm_calls_total", "llm_errors_total", "llm_tokens_total"]
            ),
            audit_events=AuditEventTypes(
                on_start="llm.request", on_success="llm.success", on_failure="llm.failure"
            ),
            tags=["free-stack", "core"],
        )
    )

    register(
        PluginManifest(
            plugin_id="omniroute_gateway",
            version="1.0.0",
            category=PluginCategory.MODEL_ROUTING,
            owner="SRE",
            business_outcome="Optional additive LLM routing fallback via self-hosted OmniRoute",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            feature_flag="OMNIROUTE_ENABLED",
            kill_switch="OMNIROUTE_ENABLED=0",
            evidence_status=EvidenceStatus.CODE_PRESENT,
            health_probe=HealthProbe(endpoint="http://127.0.0.1:20128/v1/models", interval_s=120.0),
            tags=["optional", "dev-tooling"],
        )
    )

    register(
        PluginManifest(
            plugin_id="voice_gemini_primary",
            version="1.0.0",
            category=PluginCategory.MODEL_ROUTING,
            owner="VOICE_FROZEN",
            business_outcome="Voice-scoped Gemini 2.5-flash-lite primary LLM (9-key rotation)",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="VOICE_GEMINI_PRIMARY",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["voice-frozen", "free-stack"],
        )
    )

    # =====================================================================
    # B. HARNESS PLUGINS
    # =====================================================================

    register(
        PluginManifest(
            plugin_id="native_harness",
            version="1.0.0",
            category=PluginCategory.HARNESS,
            owner="Boss",
            business_outcome="Native LeadGen harness: planning → turn → tool → audit loop",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            feature_flag="AGENT_HARNESS",
            budget=Budget(
                timeout_s=60.0, token_budget=8000, tool_calls_budget=10, wall_clock_budget_s=120.0
            ),
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["core", "harness"],
        )
    )

    register(
        PluginManifest(
            plugin_id="dsh_runtime",
            version="1.0.0",
            category=PluginCategory.HARNESS,
            owner="Boss",
            business_outcome="DeepSeek Harness governed planning/turn/tool-loop runtime",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            feature_flag="DSH_RUNTIME_ENABLED",
            kill_switch="DSH_RUNTIME_ENABLED=0",
            budget=Budget(
                timeout_s=120.0, token_budget=16000, tool_calls_budget=20, wall_clock_budget_s=300.0
            ),
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["dsh", "governed"],
        )
    )

    register(
        PluginManifest(
            plugin_id="dsh_shadow",
            version="1.0.0",
            category=PluginCategory.HARNESS,
            owner="Boss",
            business_outcome="DSH shadow lane — observe decisions without enforcement",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            feature_flag="DSH_SHADOW_ENABLED",
            kill_switch="DSH_SHADOW_ENABLED=0",
            evidence_status=EvidenceStatus.CODE_PRESENT,
            tags=["dsh", "shadow"],
        )
    )

    register(
        PluginManifest(
            plugin_id="session_events",
            version="1.0.0",
            category=PluginCategory.HARNESS,
            owner="SRE",
            business_outcome="Typed SessionEvent + hash-chained jsonl for audit trail",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            feature_flag="HARNESS_SESSION_EVENTS",
            evidence_status=EvidenceStatus.CODE_PRESENT,
            tags=["dsh", "audit"],
        )
    )

    register(
        PluginManifest(
            plugin_id="boss_decision_governance",
            version="1.0.0",
            category=PluginCategory.HARNESS,
            owner="Owner",
            business_outcome="Boss+Second-Brain hash-bound decision approvals",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            feature_flag="BOSS_DECISION_GOVERNANCE",
            approval_requirement="owner",
            evidence_status=EvidenceStatus.TEST_PROVEN,
            tags=["governance", "boss"],
        )
    )

    # =====================================================================
    # C. WORKER PLUGINS
    # =====================================================================

    register(
        PluginManifest(
            plugin_id="celery_worker",
            version="1.0.0",
            category=PluginCategory.WORKER,
            owner="SRE",
            business_outcome="Main Celery worker (conc=4): scraping, calling, reporting, sync, training",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            queue="celery,calling,scraping,reporting,sync,training",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["core", "worker"],
        )
    )

    register(
        PluginManifest(
            plugin_id="celery_worker_heavy",
            version="1.0.0",
            category=PluginCategory.WORKER,
            owner="SRE",
            business_outcome="Heavy worker (conc=1): ML/LLM isolation — kb-warmup, self-improve",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            queue="heavy",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["worker", "heavy"],
        )
    )

    register(
        PluginManifest(
            plugin_id="celery_worker_video",
            version="1.0.0",
            category=PluginCategory.WORKER,
            owner="SRE",
            business_outcome="Video worker (conc=1): creative video rendering",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            queue="video",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["worker", "video"],
        )
    )

    register(
        PluginManifest(
            plugin_id="dsh_worker",
            version="1.0.0",
            category=PluginCategory.WORKER,
            owner="SRE",
            business_outcome="DSH-dedicated worker (conc=1): separate image, no app skew",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            queue="dsh",
            feature_flag="DSH_RUNTIME_ENABLED",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["worker", "dsh"],
        )
    )

    register(
        PluginManifest(
            plugin_id="external_cursor",
            version="1.0.0",
            category=PluginCategory.WORKER,
            owner="Owner",
            business_outcome="Cursor ACP bounded implementation worker",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="EXTERNAL_AGENT_ORCHESTRATOR",
            approval_requirement="owner",
            evidence_status=EvidenceStatus.TEST_PROVEN,
            tags=["external", "coding"],
        )
    )

    register(
        PluginManifest(
            plugin_id="external_opencode",
            version="1.0.0",
            category=PluginCategory.WORKER,
            owner="Owner",
            business_outcome="OpenCode independent implementation/research lane",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="EXTERNAL_AGENT_ORCHESTRATOR",
            approval_requirement="owner",
            evidence_status=EvidenceStatus.CODE_PRESENT,
            tags=["external", "coding"],
        )
    )

    register(
        PluginManifest(
            plugin_id="external_freebuff",
            version="1.0.0",
            category=PluginCategory.WORKER,
            owner="Owner",
            business_outcome="FreeBuff UI/UX and assigned implementation lane",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            approval_requirement="owner",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["external", "coding"],
        )
    )

    # =====================================================================
    # D. DOMAIN CAPABILITY PLUGINS
    # =====================================================================

    register(
        PluginManifest(
            plugin_id="prospecting",
            version="1.0.0",
            category=PluginCategory.DOMAIN_CAPABILITY,
            owner="Boss",
            business_outcome="Lead prospecting via Google Maps + web enrichment",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            feature_flag="LEAD_HARVESTER",
            budget=Budget(timeout_s=300.0, wall_clock_budget_s=300.0),
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["acquisition", "prospecting"],
        )
    )

    register(
        PluginManifest(
            plugin_id="hot_queue_triage",
            version="1.0.0",
            category=PluginCategory.DOMAIN_CAPABILITY,
            owner="Owner",
            business_outcome="Hot Queue inbox: interested prospects → owner action → close",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="",
            approval_requirement="owner",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["revenue", "hot-queue"],
        )
    )

    register(
        PluginManifest(
            plugin_id="onboarding",
            version="1.0.0",
            category=PluginCategory.DOMAIN_CAPABILITY,
            owner="Boss",
            business_outcome="New client onboarding: scrape → KB seed → first content pack",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.TENANT,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="AUTO_ONBOARD",
            budget=Budget(timeout_s=300.0, wall_clock_budget_s=300.0),
            queue="celery",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["onboarding", "core"],
        )
    )

    register(
        PluginManifest(
            plugin_id="onboarding_factory",
            version="1.0.0",
            category=PluginCategory.DOMAIN_CAPABILITY,
            owner="Boss",
            business_outcome="Staged onboard pipeline with retry/DLQ/backpressure (INERT default)",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.TENANT,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="ONBOARDING_PIPELINE",
            kill_switch="ONBOARDING_PIPELINE=0",
            budget=Budget(timeout_s=300.0, wall_clock_budget_s=300.0),
            queue="celery",
            dlq="dlq:failed_tasks",
            idempotency_key_contract="plugin_id + client_id + stage",
            evidence_status=EvidenceStatus.CODE_PRESENT,
            tags=["onboarding", "factory", "inert-default"],
        )
    )

    register(
        PluginManifest(
            plugin_id="form_builder",
            version="1.0.0",
            category=PluginCategory.DOMAIN_CAPABILITY,
            owner="Boss",
            business_outcome="Tenant-scoped form/survey builder for lead capture (flag default OFF)",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.TENANT,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="FORM_BUILDER",
            kill_switch="FORM_BUILDER=0",
            approval_requirement="boss_recommend",
            evidence_status=EvidenceStatus.CODE_PRESENT,
            tags=["lead-capture", "inert-default"],
        )
    )

    register(
        PluginManifest(
            plugin_id="proposal_builder",
            version="1.0.0",
            category=PluginCategory.DOMAIN_CAPABILITY,
            owner="Boss",
            business_outcome="Manual UPI proposal/quote drafts — never auto-confirms payment",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.TENANT,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="PROPOSAL_BUILDER",
            kill_switch="PROPOSAL_BUILDER=0",
            approval_requirement="owner",
            evidence_status=EvidenceStatus.CODE_PRESENT,
            tags=["sales", "inert-default"],
        )
    )

    register(
        PluginManifest(
            plugin_id="content_generation",
            version="1.0.0",
            category=PluginCategory.DOMAIN_CAPABILITY,
            owner="Boss",
            business_outcome="Daily content generation (social posts, blog, email templates)",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.TENANT,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            budget=Budget(timeout_s=420.0, wall_clock_budget_s=420.0),
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["content", "delivery"],
        )
    )

    register(
        PluginManifest(
            plugin_id="delivery",
            version="1.0.0",
            category=PluginCategory.DOMAIN_CAPABILITY,
            owner="Boss",
            business_outcome="Content delivery to customer channels (social, email, WhatsApp)",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.TENANT,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="SOCIAL_ENGINE",
            approval_requirement="boss_recommend",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["delivery", "customer-facing"],
        )
    )

    register(
        PluginManifest(
            plugin_id="billing_proposal",
            version="1.0.0",
            category=PluginCategory.DOMAIN_CAPABILITY,
            owner="Owner",
            business_outcome="Manual UPI billing: submit → approve → bind → bank confirm → activate",
            risk_class=RiskClass.RED,
            tenant_scope=PluginScope.TENANT,
            privacy_class=PrivacyClass.RESTRICTED,
            approval_requirement="owner",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["billing", "money", "upi"],
        )
    )

    register(
        PluginManifest(
            plugin_id="customer_health",
            version="1.0.0",
            category=PluginCategory.DOMAIN_CAPABILITY,
            owner="Boss",
            business_outcome="Customer health monitoring: delivery assurance, churn risk, NPS",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.TENANT,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="CLIENT_HEALTH_ALERTS",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["health", "monitoring"],
        )
    )

    register(
        PluginManifest(
            plugin_id="reply_agent",
            version="1.0.0",
            category=PluginCategory.DOMAIN_CAPABILITY,
            owner="Boss",
            business_outcome="Auto-reply to known prospects; guarded, fail-closed",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="REPLY_AUTO_SEND",
            kill_switch="REPLY_AUTO_SEND_HARD_OFF=1",
            approval_requirement="boss_recommend",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["outreach", "email"],
        )
    )

    register(
        PluginManifest(
            plugin_id="sales_autopilot",
            version="1.0.0",
            category=PluginCategory.DOMAIN_CAPABILITY,
            owner="Owner",
            business_outcome="Policy-driven sales automation (dry-run default, fail-closed)",
            risk_class=RiskClass.RED,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="SALES_AUTOPILOT_ENABLED",
            kill_switch="SALES_AUTOPILOT_WHATSAPP_ENABLED=0",
            approval_requirement="owner",
            evidence_status=EvidenceStatus.CODE_PRESENT,
            tags=["sales", "autopilot"],
        )
    )

    # =====================================================================
    # E. AUTOMATION PLUGINS
    # =====================================================================

    register(
        PluginManifest(
            plugin_id="staff_scheduler",
            version="1.0.0",
            category=PluginCategory.AUTOMATION,
            owner="SRE",
            business_outcome="Celery beat + team_scheduler: ~40 daily STAFF jobs",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["scheduler", "core"],
        )
    )

    register(
        PluginManifest(
            plugin_id="dlq_recovery",
            version="1.0.0",
            category=PluginCategory.AUTOMATION,
            owner="SRE",
            business_outcome="DLQ retry sweep with backpressure guard",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            feature_flag="DLQ_AUTO_RETRY",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["reliability", "dlq"],
        )
    )

    register(
        PluginManifest(
            plugin_id="dunning_engine",
            version="1.0.0",
            category=PluginCategory.AUTOMATION,
            owner="Boss",
            business_outcome="Payment dunning + renewal reminders",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.TENANT,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="DUNNING_ENGINE",
            approval_requirement="owner",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["billing", "dunning"],
        )
    )

    register(
        PluginManifest(
            plugin_id="email_outreach",
            version="1.0.0",
            category=PluginCategory.AUTOMATION,
            owner="Boss",
            business_outcome="Scheduled cold email outreach (25/day cap, warmup)",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="AUTO_EMAIL_OUTREACH",
            approval_requirement="boss_recommend",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["outreach", "email"],
        )
    )

    register(
        PluginManifest(
            plugin_id="platform_dial",
            version="1.0.0",
            category=PluginCategory.AUTOMATION,
            owner="Owner",
            business_outcome="Daily 11:30 IST self-sale AI cold-call batch (compliance-gated)",
            risk_class=RiskClass.RED,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="PLATFORM_DIAL_DAILY",
            kill_switch="VOICE_LAUNCH_KILL=1",
            approval_requirement="owner",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["calling", "compliance"],
        )
    )

    register(
        PluginManifest(
            plugin_id="daily_video",
            version="1.0.0",
            category=PluginCategory.AUTOMATION,
            owner="Boss",
            business_outcome="Per-client daily video producer (enqueue to video queue)",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.TENANT,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="DAILY_VIDEO_ENABLED",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["video", "content"],
        )
    )

    register(
        PluginManifest(
            plugin_id="self_improve_loop",
            version="1.0.0",
            category=PluginCategory.AUTOMATION,
            owner="SRE",
            business_outcome="Continuous self-improvement loop (LLM eval + prompt optimization)",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            feature_flag="SELF_IMPROVE_LOOP",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["ml", "self-improve"],
        )
    )

    register(
        PluginManifest(
            plugin_id="hot_queue_brief",
            version="1.0.0",
            category=PluginCategory.AUTOMATION,
            owner="Owner",
            business_outcome="08:15 IST admin revenue brief (health-gated, read-only)",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            feature_flag="HOT_QUEUE_BRIEF_DAILY",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["briefing", "admin"],
        )
    )

    # =====================================================================
    # F. COORDINATION PLUGINS
    # =====================================================================

    register(
        PluginManifest(
            plugin_id="staff_bus",
            version="1.0.0",
            category=PluginCategory.COORDINATION,
            owner="Boss",
            business_outcome="31-STAFF Buzz collaboration bus (envelopes/bridge/canaries)",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            feature_flag="STAFF_BUS_ENABLED",
            evidence_status=EvidenceStatus.TEST_PROVEN,
            tags=["coordination", "staff"],
        )
    )

    register(
        PluginManifest(
            plugin_id="buzz_relay",
            version="1.0.0",
            category=PluginCategory.COORDINATION,
            owner="Boss",
            business_outcome="Local Buzz relay (ws://127.0.0.1:3100) for coding tool coordination",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["coordination", "buzz"],
        )
    )

    register(
        PluginManifest(
            plugin_id="boss_coordination",
            version="1.0.0",
            category=PluginCategory.COORDINATION,
            owner="Owner",
            business_outcome="Boss hierarchical coordination: 7 teams → 30 workers",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            approval_requirement="owner",
            evidence_status=EvidenceStatus.TEST_PROVEN,
            tags=["coordination", "boss"],
        )
    )

    register(
        PluginManifest(
            plugin_id="coordination_hub",
            version="1.0.0",
            category=PluginCategory.COORDINATION,
            owner="Owner",
            business_outcome="Owner OS thin projection (tools/missions/events/git) — NOT second control plane",
            risk_class=RiskClass.AMBER,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            feature_flag="COORDINATION_HUB_ENABLED",
            approval_requirement="owner",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["coordination", "hub"],
        )
    )

    # =====================================================================
    # G. UI PROJECTION PLUGINS
    # =====================================================================

    register(
        PluginManifest(
            plugin_id="admin_dashboard",
            version="1.0.0",
            category=PluginCategory.UI_PROJECTION,
            owner="Owner",
            business_outcome="Admin dashboard: Aaj kya karna hai + delivery + revenue",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["ui", "admin"],
        )
    )

    register(
        PluginManifest(
            plugin_id="customer_portal",
            version="1.0.0",
            category=PluginCategory.UI_PROJECTION,
            owner="Boss",
            business_outcome="Customer portal: delivered content, usage, plan, support",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.TENANT,
            privacy_class=PrivacyClass.CONFIDENTIAL,
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["ui", "customer"],
        )
    )

    register(
        PluginManifest(
            plugin_id="explorer_graph",
            version="1.0.0",
            category=PluginCategory.UI_PROJECTION,
            owner="SRE",
            business_outcome="Architecture graph: blueprint + sync + drift detection",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["ui", "explorer"],
        )
    )

    register(
        PluginManifest(
            plugin_id="control_center",
            version="1.0.0",
            category=PluginCategory.UI_PROJECTION,
            owner="SRE",
            business_outcome="Enterprise Control Center cockpit",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            feature_flag="CONTROL_CENTER",
            evidence_status=EvidenceStatus.CODE_PRESENT,
            tags=["ui", "control-center"],
        )
    )

    register(
        PluginManifest(
            plugin_id="automation_mission_control",
            version="1.0.0",
            category=PluginCategory.UI_PROJECTION,
            owner="Owner",
            business_outcome="/app/automation — visual automation builder + status",
            risk_class=RiskClass.GREEN,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.INTERNAL,
            feature_flag="FLOW_RUNNER",
            evidence_status=EvidenceStatus.CODE_PRESENT,
            tags=["ui", "automation"],
        )
    )

    register(
        PluginManifest(
            plugin_id="owner_os",
            version="1.0.0",
            category=PluginCategory.UI_PROJECTION,
            owner="Owner",
            business_outcome="Owner Operating System — sole action authority surface",
            risk_class=RiskClass.RED,
            tenant_scope=PluginScope.PLATFORM,
            privacy_class=PrivacyClass.RESTRICTED,
            feature_flag="OWNER_OS",
            approval_requirement="owner",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            tags=["ui", "owner-os"],
        )
    )
