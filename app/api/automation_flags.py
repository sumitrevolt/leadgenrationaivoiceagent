"""Automation flags registry — saare gated automation/env flags ek jagah.

Extracted from app/api/growth.py (2026-06-20 refactor) for data/route separation.
growth.py re-exports AUTOMATION_FLAGS for backward-compat (admin_dashboard.py +
tests import `from app.api.growth import AUTOMATION_FLAGS`).
"""

# Saare gated automation flags ka registry — live env status ek jagah.
AUTOMATION_FLAGS = [
    "OWNER_OS",  # Owner Operating System (/app/owner + /api/admin/owner-os) — always mounted for admin; flag documents surface
    "OWNER_OS_LITMUS",  # ADR-155 HITL litmus on Owner OS plan/execute (deterministic; default ON; set 0 to bypass block)
    "BOSS_DECISION_GOVERNANCE",  # Boss+Second-Brain hash-bound decision approvals (proposed→advice→boss→consume); OFF default; execute fail-closed when unset
    "BOSS_FULL_AUTONOMY",  # Boss full-autonomy loop over BOSS_DECISION_GOVERNANCE (sweep→advice→review→consume); OFF default inert
    "STAFF_BUS_ENABLED",  # 31-STAFF Buzz collaboration bus (envelopes/bridge/canaries); OFF default; never executes protected customer actions
    "OPENCLAW_ENABLED",  # OpenClaw Owner Copilot edge layer (/api/owner-copilot) — OFF default; Owner OS remains sole action authority
    "CONTROL_CENTER",  # enterprise Control Center cockpit (/app/control-center) — nav-surface gate, default OFF
    "ROUTE_HIT_COUNTER",  # per-route hit counter middleware (Redis route_hits:{YYYYMMDD}) for the Control Center "unused API" view — default OFF (middleware not in stack when off)
    "FLOW_RUNNER",  # visual builder -> process-as-code execution (admin, linear+DAG, default OFF)
    "FLOW_AUTO_TRIGGERS",  # Phase 3: cron + event auto-fire for saved flows (needs FLOW_RUNNER too, default OFF)
    "FLOW_RUNNER_CUSTOMER",  # Phase 7: per-client flow builder in customer portal (needs FLOW_RUNNER too, draft-only, default OFF)
    "FEATURE_FLAGS",  # SaaS infra Phase-1: per-tenant runtime feature-flag system master gate (default OFF)
    "APPROVAL_EMAIL_NOTIFY_HARD_OFF",  # emergency precedence over env/runtime approval-reminder gates
    "APPROVAL_EMAIL_NOTIFY",  # pending-approval EMAIL sweep (staff job approval_email_sweep) — OFF default; allowlist fail-closed
    "APPROVAL_EMAIL_CLIENT_ALLOWLIST",  # CSV client_ids allowed for approval emails when env path used
    "WARM_SLA_NUDGE",  # office HQ warm-lead SLA founder nudge (nested under ops) — OFF default
    "WARM_SLA_MIN",  # minutes threshold for warm SLA nudge (value-carrying)
    "TEAM_AUTOMATION",
    "RUN_IN_PROCESS_SCHEDULER",
    "NICHE_ROTATION",
    "AUTO_EMAIL_OUTREACH",
    "JOURNEY_ENGINE",
    "AUTO_QUALIFY_CALLS",
    "REPLY_AGENT",
    "CALL_LOG_DB",  # write structured call_logs row per call -> DB-backed analytics dashboard (default ON)
    "OPS_WATCHDOG",  # Kavya scheduler watchdog (hourly) — NOT Agent Runtime gate
    "OPS_HEALTH_AGENT",  # Kavya Agent Runtime ops_health_check — independent of OPS_WATCHDOG
    "AUTO_ONBOARD",
    "SIGNUP_AUTO_ONBOARD",  # public signup → auto client onboard path (checked in public_site/customer_onboard)
    "SOCIAL_PREFS_HONOR",
    "USE_STRUCTURED_CONTENT",
    "USE_AGENTIC_RAG",
    "USE_RERANKER",
    "USE_CONTEXTUAL_INGEST",
    "USE_CONTEXTUAL_INGEST_LLM",
    "USE_HYBRID_SEARCH",
    "USE_LANGGRAPH_SUPERVISOR",
    "USE_LANGGRAPH_HIGH_STAKES",
    "AGENT_STANDUP",
    "LLM_COUNCIL",  # Karpathy multi-model council (boss unclear → decide); OFF = council-decide endpoints fail soft
    "COUNCIL_TIMEOUT_S",  # council per-call timeout seconds (value-carrying)
    "SALES_ENGINE",
    "CADENCE_ENGINE",
    "DUNNING_ENGINE",
    "RENEWAL_REMINDER_ENABLED",  # independent renewal email; no-ops when DUNNING_ENGINE already sweeps
    "LIFECYCLE_NURTURE",
    "CLIENT_HEALTH_ALERTS",
    "REVENUE_DIGEST",
    "GROWTH_OPTIMIZER",
    "CHANNEL_EXPERIMENTS",
    "CAMPAIGN_OPTIMIZER",  # Kiran: orchestrates optimizer+bandit+feedback every 100 interactions
    "PLATFORM_DIAL_DAILY",  # daily 11:30 IST self-sale AI cold-call batch (Swara; limit=PLATFORM_DIAL_LIMIT, niche=PLATFORM_DIAL_NICHE)
    "PLATFORM_DIAL_LIMIT",  # value-carrying daily dial attempt ceiling (NOT a boolean; default/clamp in platform_dial)
    # --- Controlled voice-calling launch spine (2026-07-17, app/telephony/voice_launch.py) ---
    "VOICE_LAUNCH_CAMPAIGN",  # master gate for controlled cold-call campaign — OFF default (INERT); UPAR of platform_dial 3-layer kill
    "VOICE_LAUNCH_KILL",  # global admin kill switch — 1 = ALL outbound calls ineligible (fail-safe); data/voice_launch_kill.json fallback
    "VOICE_DAILY_CALL_CAP",  # attempts/IST-day ceiling (default 100, hard-clamped ≤100). Every provider-accepted attempt counts
    "VOICE_CALLS_PER_SESSION",  # attempts per launch session (default 30, hard-clamped ≤200) — Redis-backed, reset ONLY via session lifecycle (worker restart NO); 31st attempt blocked before provider
    "VOICE_TEST_DAILY_CAP",  # internal allowlist test-call quota (default 25) — SEPARATE from campaign cap
    "VOICE_CALL_CONCURRENCY",  # simultaneous outbound calls (default 1; launch starts at 1)
    "VOICE_TRAIN_BATCH",  # calls-per-batch before a training pause (default 30 → pause@30/60/90)
    "VOICE_CIRCUIT_FAIL_THRESHOLD",  # consecutive provider failures before circuit breaker trips (default 5)
    "VOICE_RECORDING_REQUIRED",  # 1 = recording MANDATORY; unhealthy recordings dir blocks new dials (fail-closed). Default OFF (graceful)
    "OUTREACH_CAMPAIGN_VARIANTS",  # cold email uses Kiran champion/challenger copy (impression/reply tracked)
    "VOICE_CAMPAIGN_VARIANTS",  # Swara phone/web greeting uses voice_opening champion/challenger
    "PROCESS_ENGINE",  # deterministic process-as-code workflows (complement to PROCESS_AUTOSTART)
    "AUTO_INVOICE",
    "EMAIL_WARMUP",
    "EMAIL_TRACKING",  # cold-email open/click pixels (listmonk parity); OFF = no tracking emitted
    "USAGE_ALERTS",
    "REVIEW_MONITOR",
    "BOOKING_REMINDERS",
    "FORM_BUILDER",  # admin form/survey builder JSONL; OFF default; API 503 when unset
    "PROPOSAL_BUILDER",  # admin proposal/quote drafts JSONL; OFF default; API 503 when unset
    "DELIVERABILITY_MONITOR",
    "AUTOMATION_HEALTH_ALERTS",
    "LLM_COMPARE_ENABLED",  # admin-only blind LLM arena (/api/llm/compare/ui) — Odysseus-inspired A/B for free-tier chain, INERT default
    "MODEL_COOKBOOK_ENABLED",  # admin-only niche→LLM recipe catalog (/api/cookbook/ui) — Odysseus-inspired, INERT default
    "DEEP_RESEARCH_ENABLED",  # admin-only multi-step cited web research (/api/research/deep/ui) — Odysseus-inspired, needs SEARXNG_URL, INERT default
    "DOCS_AI_EDIT_ENABLED",  # admin-only writing editor with AI actions (/api/docs/edit/ui) — Odysseus-inspired, INERT default
    "WHATSAPP_AUTO_SEND",  # §5 MASTER auto-send gate — enforced at the SENDER boundary (app/integrations/whatsapp.py::send_permitted), so EVERY caller is gated by default
    "WHATSAPP_SEND_ALLOWLIST",  # canary recipients for automated WhatsApp. EMPTY = nobody (fail-closed); '*' = explicit graduation to all. Numbers live in .env only
    "WHATSAPP_RECIPIENT_CHECK_FAIL_OPEN",  # 1 = restore pre-2026-07-31 fail-OPEN when the WAHA recipient check itself errors. Default 0 = fail-CLOSED
    "VOICE_CLOSE_WHATSAPP",  # voice-call close-signal auto WhatsApp (needs WHATSAPP_AUTO_SEND too) — default OFF, separate opt-in
    "WHATSAPP_PROVIDER",  # "cloud" (Meta Cloud API, default) | "waha"/"selfhost" (own WAHA stack)
    "WAHA_BASE_URL",  # self-hosted WhatsApp stack URL (set = reachable; sidesteps Meta verification)
    "MISSED_CALL_CALLBACK",
    "SMS_DLT_ENABLED",
    "USE_SILERO_VAD",
    "USE_SMART_TURN",
    "USE_LIGHTRAG",
    "ENABLE_OTEL",
    "ENABLE_LEGACY_BEAT",
    "FESTIVALS_LIVE_HOLIDAYS",
    "VIDEO_AD_CYCLE",  # har 5 din per-client AI video ad -> approval -> social publish (default OFF)
    "VIDEO_AD_INTERVAL_DAYS",  # video_ad_cycle cadence in days (default 5) — set 1 for daily
    "DAILY_VIDEO_ENABLED",  # daily per-client video producer, own beat job, enqueue-only (default OFF)
    "DAILY_VIDEO_CLIENTS",  # comma tenant allowlist; EMPTY = no client (fail-closed), '*' = all eligible
    "DAILY_VIDEO_ENGINE",  # auto|advanced|classic (default auto: advanced when gated+healthy, else classic)
    "DAILY_VIDEO_MAX_PENDING",  # per-client open-review backpressure cap (default 2)
    "DAILY_VIDEO_MAX_PER_RUN",  # per-run enqueue cap (default 10)
    "DAILY_VIDEO_ADVANCED_FAIL_WINDOW",  # consecutive advanced failures before auto-downgrade (default 2)
    "DAILY_VIDEO_ADVANCED_BLOCK_DAYS",  # how long a permanent brief refusal parks a tenant on classic (default 7)
    "DAILY_VIDEO_RECIPE",  # Creative OS recipe for the advanced path (default offer_announcement)
    "VIDEO_PRODUCTION_ENABLED",  # OpenClaw Video Production Cell master (default OFF)
    "VIDEO_DAILY_SCHEDULER_ENABLED",  # daily video planning job (aliases VIDEO_AD_CYCLE when on)
    "VIDEO_CUSTOMER_REVIEW_ENABLED",  # customer dashboard + WA feedback ingest
    "VIDEO_CUSTOMER_REVIEW_CLIENTS",  # comma Stage-3 tenant allowlist; '*' = explicit all
    "VIDEO_WHATSAPP_REVIEW_ENABLED",  # auto WA preview send (ban-safety; default OFF)
    "VIDEO_SOCIAL_PUBLISH_ENABLED",  # approval-gated Postiz publish when production cell ON
    "VIDEO_HARNESS_ENFORCE",  # harness evaluate_action must allow mutating video tools
    "VIDEO_HARNESS_SHADOW_ENABLED",  # Stage 1: observe video harness decisions; no enforcement / side effects
    "VIDEO_OWN_BRAND_ENABLED",  # LeadGen AI own-brand canary lane
    "CREATIVE_OS_ENABLED",  # ADR-143 Creative Automation OS master (default OFF)
    # HyperFrames = the "advanced" animated deliverable. It was MISSING from this
    # registry, so /api/growth/infra/flags reported Creative OS healthy while the
    # only enterprise-grade provider sat unset and every advanced render fell
    # through (hyperframes is in providers.NO_SILENT_FALLBACK — no quiet downgrade).
    "CREATIVE_PROVIDER_HYPERFRAMES_ENABLED",  # HyperFrames render provider (default OFF)
    "CREATIVE_HYPERFRAMES_CANARY_TENANTS",  # comma tenant allowlist; EMPTY = no tenant (fail-closed)
    "CREATIVE_HYPERFRAMES_DEFAULT_TEMPLATE",  # template id (default beauty_luxury_offer_v1)
    "CELERY_VIDEO_QUEUE",  # route video render tasks to the dedicated 'video' queue/worker (default OFF)
    "CELERY_ONBOARD_QUEUE",  # route onboard_client to existing heavy worker (default OFF; no new queue)
    "ONBOARDING_PIPELINE",  # staged onboarding factory (retry/DLQ/backpressure); OFF=legacy auto_onboard still works
    "CREATIVE_PROVIDER_QWEN_IMAGE",  # Qwen-Image adapter (skeleton; default OFF)
    "CREATIVE_PROVIDER_FLUX_SCHNELL",  # FLUX.1-schnell only (skeleton; default OFF; flux.dev rejected)
    "CREATIVE_PROVIDER_WAN22",  # Wan2.2 TI2V GPU worker only (skeleton; default OFF)
    "CREATIVE_PROVIDER_COMFYUI",  # ComfyUI lab adapter (skeleton; default OFF)
    "CREATIVE_GPU_LAB_ENABLED",  # GPU lab preflight gate (default OFF)
    "CREATIVE_COMFYUI_ENABLED",  # isolated ComfyUI lab (default OFF)
    "CREATIVE_LEARNING_ENABLED",  # performance recommendations only — never auto-mutate/spend (OFF)
    "CREATIVE_MAX_REVISIONS",  # revision cap (default 3)
    "CREATIVE_TENANT_DAILY_BUDGET",  # per-tenant generation cap/day (default 20)
    "CREATIVE_WORKER_TIMEOUT_S",  # generation timeout seconds (default 300)
    "CONTENT_TIME_BUDGET_S",  # content mega-job wall-clock budget (default 420; SoftTimeLimit margin)
    "ONBOARD_TIME_BUDGET_S",  # onboard sweep wall-clock budget (default 300)
    "PROSPECT_TIME_BUDGET_S",  # prospect harvest wall-clock budget (default 300)
    "SOCIAL_ENGINE",  # native social-posting engine (own queue+providers; default OFF, video_ad_cycle inline fallback)
    "POSTIZ_PINTEREST_BOARD",  # required for Pinterest in multi-channel Postiz create; unset = skip Pinterest only
    "POSTIZ_PUBLISH_MAX_CHANNELS",  # hard cap per create-post (0=block; unset=uncapped legacy fan-out)
    "ALLOW_TOS_SCRAPE",  # hard-off default — JustDial/IndiaMART/LinkedIn/social auto-scrape refuse (§5)
    "SOCIAL_DRY_RUN",  # ADR-098: drain queue but fabricate post_id=dry-* — NEVER real provider publish. Env wins over data/social_engine.json dry_run. Invisible-until-registered = fake "published" confidence.
    "CLIENT_REPORTS",
    "CUSTOMER_WISHES",
    "RANK_TRACKER",
    "MEMORY_VAULT",
    "LIVE_NOTES",
    "DLQ_AUTO_RETRY",
    "INTEGRATION_ALERTS",
    "INFRA_HANDLER",
    "NPS_ALERTS",
    "INDEXNOW",
    "SALES_TEAM",
    "SELF_IMPROVE_LOOP",
    "LEAD_HARVESTER",
    "PROSPECT_SCORE_V2",  # Prospect Score V2 (lead_scoring_v2) via prospect_lists._scorer_for — OFF default; V1 read path preserved (2026-07-31)
    "EMAIL_ENRICH_SWEEP",  # bounded Celery email-enrichment sweep over data/prospects.jsonl (app.tasks.scraping.email_enrichment_sweep, scraping queue) — INERT default; task no-ops when off
    "HARVEST_INGEST_VALIDATION",  # SERP-junk ingest gate (junk-title regex + websearch contact requirement) — ON default; =0 rollback (backlog 2026-07-05, platform_dial IVR root-enabler fix)
    "GTM_TARGETING",  # systematic City x Niche coverage matrix for the lead-harvester (gtm_targeting.py) — OFF default
    "UDYAM_PIPELINE",  # Udyam-primary acquisition: data.gov.in seed -> Maps+website enrich (udyam_pipeline.py) — OFF default
    "OPENCORPORATES_API_TOKEN",  # company-registry enrich (CIN/status) — inert without token
    "INDIAMART_CRM_KEY",  # IndiaMART official Lead Manager API (seller's own leads) — inert without key
    "CALL_TRANSFER",
    "OUTREACH_AB",
    "OUTREACH_AUDIT_LED",  # cold-email leads with a personalized audit-gap hook (additive, no cap change) — OFF default
    "UPI_AUTO_ACTIVATE",  # self-serve UPI submit auto-activates plan immediately (reconcile later) — OFF default
    "UPI_AUTO_ACTIVATE_CLIENTS",  # comma tenant allowlist required when UPI_AUTO_ACTIVATE=1; empty=fail-closed; '*'=all
    "SERVICE_REMINDERS",
    "LLM_CAPACITY_ALERTS",
    "KB_PREWARM",
    "KB_WEEKLY_REFRESH",
    "MIDDAY_PROSPECT",
    "WEEKLY_MARKETING_PACK",
    "SCHEDULER_HYGIENE",
    "CELERY_TRIM_MIN_DEPTH",
    "SEMANTIC_CACHE",  # semantic LLM response cache (Qdrant+Redis, off-loop) — OFF default, fail-open
    "AGENT_MEMORY",  # cross-session per-lead/client memory (Qdrant+free LLM, off-loop) — OFF default, fail-open
    "WORKFORCE_MEMORY",  # ADR-154: per-STAFF-agent layered memory hub (TencentDB patterns, JSONL+refs) — OFF default, fail-open
    "WORKFORCE_MEMORY_DIR",  # optional override root (default data/workforce_memory) — tests/canary only
    "WORKFORCE_MEMORY_MAX_CHARS_PER",  # recall budget per entry (default 280)
    "WORKFORCE_MEMORY_MAX_TOTAL",  # total brief char budget (default 1200)
    "WORKFORCE_MEMORY_RECALL_TIMEOUT_MS",  # soft recall wall-clock (default 50)
    "WORKFORCE_MEMORY_L0_L1_DAYS",  # L0/L1 retention days; 0=forever (default 90)
    "MEMORY_STACK_ENABLED",  # MASTER gate for the 7-layer agent-memory facade — OFF default; every layer flag is subordinate to it
    "MEMORY_STACK_LAYER_WORKING",  # per-layer override (default ON when master ON)
    "MEMORY_STACK_LAYER_PROSPECTIVE",  # per-layer override; OFF = no durable dispatch
    "MEMORY_STACK_LAYER_EPISODIC",  # per-layer override (needs AGENT_MEMORY to have data)
    "MEMORY_STACK_LAYER_SEMANTIC",  # per-layer override (needs WORKFORCE_MEMORY)
    "MEMORY_STACK_LAYER_PROCEDURAL",  # per-layer override (skill_library)
    "MEMORY_STACK_LAYER_SHARED",  # per-layer override (needs WORKFORCE_MEMORY)
    "MEMORY_STACK_CONTEXT_TOKENS",  # model context window used for budgeting (default 8000)
    "MEMORY_STACK_RESERVE_TOKENS",  # completion/system headroom held back (default 1200)
    "MEMORY_STACK_TOKEN_BUDGET",  # tokens the memory block may occupy (default 600)
    "MEMORY_STACK_DEADLINE_MS",  # wall-clock for the whole assembly; lanes past it are dropped (default 250)
    "MEMORY_STACK_TIERS",  # optional hot,warm,cold subset (default all three)
    "MEMORY_STACK_WORKING_TURNS",  # working-memory FIFO depth per session (default 12)
    "MEMORY_STACK_WORKING_TTL_S",  # working-memory idle TTL before eviction (default 1800)
    "MEMORY_STACK_COORDINATOR_CANARY",  # coordinator.plan() context cutover — OFF default, legacy hint path preserved
    "MEMORY_STACK_COORDINATOR_TOKENS",  # canary token budget for coordinator context (default 300)
    "MEMORY_STACK_PLATFORM_TENANT",  # tenant id used for platform-internal (non-customer) agent runs
    "LLM_BUDGET_GUARD",  # per-scope LLM daily cost/usage cap + kill-switch — OFF default, fail-open
    "LLM_BUDGET_HARD_KILL",  # emergency manual stop: ALL LLM block (fail-closed) — OFF default
    "EXTERNAL_AGENT_ORCHESTRATOR",  # Cursor/Claude mission orchestrator (records only; no shell/deploy/send) — OFF default
    "EXTERNAL_AGENT_RUNNER",  # unattended Cursor/Claude CLI invocation (needs ORCHESTRATOR too); local/Windows canary — OFF default
    "PR_FACTORY_ENABLED",  # ADR-156 PR Factory thin dispatcher (needs ORCHESTRATOR too); local canary — OFF default
    "PR_FACTORY_PILOT_ENABLED",  # ADR-166 bounded PR-orchestration pilot (triple-gate; never merge/deploy) — OFF default
    "COORDINATION_HUB_ENABLED",  # Owner OS thin projection (tools/missions/events/git); NOT second control plane — OFF default
    "COORD_HUB_BUZZ_SECRET",  # Buzz webhook HMAC secret (≥32) — unset = webhook fail-closed
    "COORD_HUB_TOOL_CURSOR_SECRET",  # Cursor tool heartbeat HMAC — unset = fail-closed
    "COORD_HUB_TOOL_CLAUDE_SECRET",  # Claude tool heartbeat HMAC — unset = fail-closed
    "COORD_PLAN_NODE",  # ADR-159 MetaGPT steal-#1: ActionNode-style structured plan fill/review/revise canary for coordinator.plan() — OFF default, legacy _extract_list authoritative
    "COORD_PLAN_NODE_REVIEWS",  # bounded self-correction rounds when the fill fails schema validation (default 1; 0 = no review, straight legacy fallback)
    "HARNESS_SESSION_EVENTS",  # ADR-180 dsh steal-#1: typed SessionEvent + hash-chained jsonl (seq/prev_hash/event_hash); OFF default, historical keys unchanged
    "DSH_RUNTIME_ENABLED",  # hardened source-built DSH authority; OFF = direct executor rollback, owner authorization required
    "DSH_SHADOW_ENABLED",  # proposal-only DSH shadow lane; OFF default
    "DSH_AGENT_ALLOWLIST",  # bounded CSV identities eligible for DSH authority/shadow; empty = none
    "DEV_ORCHESTRATOR",  # Claude-managed engineering task ledger; draft-safe and OFF by default
    "DEV_WORKER_ENABLED",  # arms the draft-only dev-task Celery runner (needs DEV_ORCHESTRATOR too) — OFF default
    "AUTO_APPLY_PATCH",  # dev-control hard gate: patch application is REFUSED regardless; OFF default
    "AUTO_DEPLOY",  # dev-control transparency flag: code NEVER auto-deploys (manual Hostinger runbook); OFF default
    "DEV_DEPLOY_APPROVAL_TOKEN",  # fail-closed human production-approval token for dev-tasks (unset = no approval possible)
    "MAGIC_LINK",  # passwordless customer login (single-use email link) — OFF default
    "IMPERSONATION",  # super-admin "login as customer" support tool (audited) — OFF default
    "PUBLIC_GUARDRAILS",  # PII-redact + prompt-injection block on public chatbot/widget LLM — OFF default, fail-open
    "CONTENT_APPROVAL_AUTO",  # daily auto_content → approval queue AUTO-SUBMIT (not auto-approve) — OFF default
    "OLLAMA_URL",
    "OLLAMA_PRIMARY",  # self-hosted own LLM (GPU/PC) — URL set = active
    "NEWSLETTER_ENGINE",
    "WINBACK_ENGINE",
    "BRAND_PULSE",
    "TEAM_REPORT",
    # Customer Autopilot — per-client hands-free drafts (customer_autopilot.run_all), all DEFAULT-OFF, draft-only
    "EVERGREEN_RECYCLE",  # purane top posts auto-freshen + content-queue re-append
    "NPS_AUTO",  # periodic NPS/CSAT survey WhatsApp drafts (ban-safe, no auto-send)
    "STALE_INQUIRY_NUDGE",  # untouched >24h inquiry -> follow-up nudge DRAFT
    "OWNER_BRIEF_DAILY",  # roz-subah per-client owner-brief auto-prepare (scheduled studio owner-brief)
    "HOT_QUEUE_BRIEF_DAILY",  # 08:15 admin revenue brief; health-gated, read-only, default OFF
    "HQ_AUTO_CHASE",  # unactioned inquiry cards -> automated EMAIL follow-up; WhatsApp stays 1-click human (OFF default)
    "CONTENT_APPROVAL_SWEEP",  # orphaned-pending approval retirement daily sweep (dry_run default; LIVE variant actuates writes)
    "DAILY_OWNER_BRIEF_NTFY",  # daily 08:10 owner brief + ntfy push (P0/P1 exceptions); INERT off default
    "SKILL_PACK",
    "SKILL_PACK_KB_INGEST",  # expensive embedding ingest from trainer; explicit opt-in, OFF default
    "OKF_INGEST_ENABLED",  # ADR-119 Phase-1: knowledge/ → kb_main namespace=okf ingest — OFF default
    "OKF_PUBLIC_BUNDLE",  # public agent-readable /okf/ Markdown surface — default ON (git-curated, no secrets)
    "OKF_BUNDLE_DIR",  # optional override root for tests/canary (default repo knowledge/)
    "OBSIDIAN_SYNC",  # second-brain markdown staging + daily obsidian_push job (audit 2026-07-04: was registry-invisible)
    "COMBO_PRODUCT",  # Product-3 combo public router mount — OFF default (ADR-009 two-product truth; audit 2026-07-04)
    "STUDIO_ENTITLEMENT_GATE",  # customer studio: block expired trials + never-paid signups after 7-day grace — OFF default
    "WHATSAPP_WELCOME",  # send welcome WhatsApp to customer on signup/trial — ON default (consented/transactional; no-op until WA engine armed)
    "POST_CALL_WHATSAPP",  # send WhatsApp trial-link to interested lead after a qualified voice call — ON default (no-op until WA armed)
    "ONBOARD_WIZARD_APPLY",  # business-type wizard auto-setup apply (salon/clinic/restaurant templates) — OFF default
    "POST_CALL_SUMMARY",  # AI post-call WhatsApp summary + action items to qualified leads — OFF default (needs WHATSAPP_AUTO_SEND)
    "VOICE_FOLLOWUP",  # trial day8/9 + interested-not-converted transactional voice callbacks — OFF default
    "CODE_UPGRADER",
    "RECORDING_RETENTION",
    "VOICE_EVAL_AUTO",  # daily voice persona eval suite (qa job) + self-improve voice_eval action — OFF default
    "ML_NIGHTLY_TRAINING",  # nightly ML train (intent classifier + lead scorer + prompt-opt) in trainer job — OFF default
    "SEARXNG_URL",
    "NTFY_URL",
    "NTFY_TOPIC",  # self-hosted tools stack (URL-valued = set hone pe ON)
    "CRM_SYNC",  # qualified lead -> client ka Zoho/HubSpot auto-push
    "CRM_SYNC_PULL",  # pull lead status back from HubSpot/Zoho (bidirectional, OFF default)
    "TELEPHONY_READY_ALERTS",  # Tara readiness score-drop email alert
    "SOCIAL_AUTOPOST",  # Meta Graph real publish (content job)
    "GSC_ENABLED",  # Google Search Console rank/impression daily snapshot (staff-gsc-rank-daily job) — OFF default
    "GSC_SERVICE_ACCOUNT_JSON",  # service-account JSON path for GSC (URL/string-valued = set hona + GSC_ENABLED=1 = ON)
    "GSC_SITE_URL",  # Search Console property (default sc-domain:leadsgenai.in)
    "AUTO_CALLBACK_INQUIRY",  # inquiry submit pe instant AI callback
    "LEAD_NTFY_ALERT",  # naya lead pe platform owner ke phone pe instant ntfy push (email complement, 1-tap WhatsApp) — ON default, no-op until NTFY_URL+NTFY_TOPIC set
    "WHATSAPP_LEAD_FLOW_ID",  # Meta Flow in-chat lead capture (URL-valued = set hone pe ON)
    "REPLY_AUTO_SEND",  # guarded known-prospect email auto-reply; default OFF
    "REPLY_AUTO_SEND_HARD_OFF",  # emergency precedence override; 1 always blocks sends
    "REPLY_AGENT_INTERACTION_LOG",  # auto-reply OUT → interaction_log; default ON (opt-out=0); mirrors ROUTINE_TASK_LEDGER
    "SELF_IMPROVE_APPROVAL",  # LLM-heavy self-improve actions human approve gate
    "AGENT_RUNTIME",  # Agent-OS Phase-B shared runtime master gate — OFF default (pilots kavya/isha/zara only; RED lane hamesha blocked)
    "AGENT_MATURITY_CONTEXT",  # ADR-164: bounded role/agent-KB context; OFF default, profiles remain read-only visible
    "AGENT_RUNTIME_LLM",  # isha pilot draft-brief me free-stack LLM allow (OFF = deterministic template)
    "REQUEST_GUARD",  # per-request timeout + load-shed middleware
    "PLAN_RATE_LIMIT",  # tier-based API rpm limits
    "CIRCUIT_BREAKER",  # external-service breaker (Pollinations etc.) — OFF default, fast-fail on outage
    # Edge protection (Cloudflare) — URL-valued flags become ON when set.
    "CLOUDFLARE_TUNNEL_TOKEN",  # deploy/compose/docker-compose.edge.yml cloudflared — origin-hide + WAF/DDoS
    "TURNSTILE_SITE_KEY",  # public site-key (safe to expose) — widget renders only when set
    "TURNSTILE_SECRET_KEY",  # server secret — present = bot-check armed on /audit /site-audit /demo /inquiry
    # F.3 eval_gate close-the-loop reward signal for self_improve + DeepEval CI
    "EVAL_GATE",  # records baseline + decides; observe-only until HARD set
    "EVAL_GATE_HARD",  # makes reject decisions actually block (after baseline trusted)
    # 2026-06-28 agent/queue governance guards (INERT default — docs/WORKFLOW_IMPROVEMENT_BACKLOG.md)
    "COORDINATOR_LLM_CAP_PER_MIN",  # coordinator LLM rate-cap/min (0=off) — over → call skipped fail-open
    "COORD_KB_SHARE",  # coordinator successful executed runs → Qdrant skills namespace (OFF default)
    "COORD_GUARDRAILS",  # coordinator/_llm() PRE-LLM PII-redact + injection-block + POST-LLM system-leak/unsafe-promise block (OFF default, fail-open)
    "KB_SKILL_LEARN",  # self_improve high-value runs + reflections → Qdrant skills namespace (OFF default)
    "QUEUE_DEPTH_BACKPRESSURE",  # DLQ retry-sweep defers when celery depth > QUEUE_DEPTH_CAP (retry-storm guard)
    "QUEUE_DEPTH_CAP",  # default 800 — celery depth above which backpressure trips
    # F.5 engineer agents (Pranav SRE / Vidya FinOps / Arnav Security)
    "SRE_AGENT",  # Pranav reliability score (hourly :45)
    "FINOPS_AGENT",  # Vidya margin score + LiteLLM-attributed cost-per-tenant
    "SECURITY_AGENT",  # Arnav scheduler daily posture entry — NOT Agent Runtime gate
    "SECURITY_POSTURE_AGENT",  # Arnav Agent Runtime security posture — independent of SECURITY_AGENT
    # Nikhil Revenue Ops — isolated runtime gate (default OFF; never ungated)
    "DELIVERY_ASSURANCE_AGENT",  # Nikhil scan_delivery_assurance only
    # council 2026-06-25 — 3 new engineer agents (genuinely-uncovered loops)
    "DBRE_AGENT",  # Kabir Postgres reliability — slow-queries/indices/connections (daily 10:00)
    "DEPS_AGENT",  # Aryan dependency/supply-chain CVE audit, proposal-only (weekly Sun 04:30)
    "DATA_INTEGRITY_AGENT",  # Diya lead/CRM data integrity, report-only (daily 10:30)
    # G.1 ops_alerts ntfy fan-out (engineer-score / eval-reject / readiness-digest / dead-letter)
    "OPS_ALERTS",  # master gate — needs NTFY_URL+NTFY_TOPIC already set
    "OPS_ALERT_ENGINEER_THRESHOLD",  # default 60 (engineer score below this pages)
    "OPS_ALERT_EVAL_REJECT_BURST",  # default 3 (rejects-per-window before paging)
    "OPS_ALERT_EVAL_REJECT_WINDOW",  # default 86400s (window for burst count)
    "OPS_ALERT_WEBHOOK_DEAD_LETTER_THRESHOLD",  # default 3 (consecutive failures before page)
    "UPI_PENDING_ALERT_HOURS",  # default 6 — stale pending UPI → readiness digest BLOCKER
    # H.1 customer-facing webhooks (Svix-style HMAC-SHA256 fan-out)
    "CUSTOMER_WEBHOOKS",  # master gate for emit()
    "CUSTOMER_WEBHOOK_DENY_PRIVATE",  # default 1; set 0 only for dev SSRF tests
    # H.2 customer-side 2FA — opt-in per customer; TOTP_CHALLENGE_KEY optional
    "TOTP_CHALLENGE_KEY",  # HMAC key for login-challenge token; unset = per-process random
    # H.3 MCP-as-product + A2A Agent Card metered surface
    "MCP_PRODUCT",  # arms /api/mcp-product/v1/* (503 when off)
    # council 2026-06-26: Arya MCP Engineer + /mcp expose gate
    "MCP_ENGINEER",  # hourly health pulse (3-layer surface); off = disabled-result
    "FASTAPI_MCP_TOKEN",  # bearer required by /mcp/* expose (gate the admin tools)
    "MCP_IP_ALLOWLIST",  # CSV of admin IPs allowed at /mcp/* (alternative gate)
    "MCP_KEY_ROTATION_DAYS",  # default 90 — rotation reminder window
    "MCP_QUOTA_PRESSURE_PCT",  # default 80 — quota-warn threshold per key
    "MCP_AUTH_FAIL_ALERT",  # default 20 — 24h auth-failure ntfy trigger
    # H.4 LiteLLM per-tenant cost + warm-DR replica probe
    "LITELLM_COSTS",  # master gate; needs LITELLM_MASTER_KEY + LITELLM_GATEWAY_URL
    "LITELLM_MASTER_KEY",  # bearer for /spend/keys probe
    "LITELLM_GATEWAY_URL",  # e.g. http://litellm:4000 once edge.yml --profile gateway up
    "DR_REPLICA_URL",  # postgres://... Neon/Supabase replica for warm-DR
    "DR_LAG_WARN_S",  # default 60 (replica lag WARN threshold)
    "DR_LAG_FAIL_S",  # default 600 (replica lag FAIL threshold)
    # F.4 agent_memory cross-session lead recall (Qdrant agent_memory collection)
    "MEM0_BACKEND",  # "mem0" to use pip-installed Mem0 SDK; else native (default)
    "AGENT_MEMORY_MIN_SIM",  # default 0.35 (recall similarity cutoff)
    "AGENT_MEMORY_RECALL_LIMIT",  # default 4 (recall row cap)
    "AGENT_MEMORY_MAX_FACTS",  # default 4 (extract-store cap per turn)
    "HERMES_HANDOFF",  # Phase-2 future: code_upgrader -> Hostinger Hermes draft-PR executor.
    # Phase-1 (read-only daily health report) hai HOSTINGER sandbox me, flag-independent.
    # Docs: docs/HOSTINGER_HERMES_SETUP.md
    # Voice DLT unlock ke baad build — spec: voice-consent-confirm skill
    "CONSENT_CONFIRM",  # in-call "press 1 to confirm consent" gate (TRAI DLT required) — OFF until DLT unlock
    # --- Parallel automation batch 2026-06-19 (all default OFF / inert) ---
    "METER_ALERTS",  # SP1: billing meter-failure watcher (reads Redis billing:meter_failures, ntfy)
    "METER_ALERT_GROWTH_THRESHOLD",  # default 5 (new failures per check before paging)
    "METER_ALERT_COOLDOWN_SEC",  # default 21600 (6h alert cooldown)
    "LOOP_SUPERVISOR",  # SP3: call-processor re-spawn watchdog + boot-grace-skip ntfy visibility
    "PROCESS_AUTOSTART",  # D V1.1: process-engine deterministic workflows auto-start (idempotent, 1/tick)
    "AMD_DETECT",  # SP7: answering-machine detection on vobiz stream (saves credits) — OFF default
    # --- Research-improvements batch 2026-06-19 ---
    "USE_TEXT_ENDPOINT",  # text-based semantic end-of-turn (complements audio Smart-Turn) — OFF default
    "USE_LLM_STREAM_TTS",  # LLM token stream → early sentence TTS (vobiz) — OFF default
    "VOICE_TOOLS",  # agentic in-call actions (book/capture/transfer/end via function_calling) on the live
    # voice loop — isolated reply_with_tools path, brain default untouched. OFF default; test on web-call first.
    "BOOKING_NOTIFY",  # on a successful AI booking, best-effort ntfy + email to the business owner — default ON,
    # inert when no NTFY/NOTIFY_EMAIL/client-email target. Durable ledger (data/bookings/) is always written.
    "CALCOM_API_KEY",  # optional Cal.com BYOK (no OAuth) real-calendar booking — set with CALCOM_EVENT_TYPE_ID;
    # unset = internal durable ledger. URL/key-valued = ON.
    "OBJECTION_KB",  # transcript/reply objection extraction → Qdrant objections:{niche} (default ON)
    "INTERACTION_LOG",  # omnichannel interaction timeline DB+jsonl (default ON)
    # --- Readiness + dashboard batch 2026-06-20 (all default OFF / inert) ---
    "REVENUE_TRENDS",  # B1: admin revenue time-series (/revenue-trend + daily snapshot job) — OFF default
    "CLIENT_TIMELINE",  # B2: per-client activity timeline endpoint — OFF default
    "SYS_HEALTH_DETAIL",  # B3: admin system-health drill-down endpoint — OFF default
    # --- More agent passes 2026-06-22 (default OFF / opt-in extra cadence) ---
    "AFTERNOON_CONTENT",  # 2nd daily content-gen pass (Isha, 15:00 IST) — OFF default
    "EVENING_PROSPECT",  # 3rd daily free lead-harvest pass (Rohan, 17:00 IST) — OFF default
    # --- Engineering-agent codebase search (Kilo-Code parity) 2026-06-24 ---
    "CODE_SEARCH",  # semantic code retrieval grounds Vikram proposals + arms admin
    # GET /api/growth/upgrader/code-search agent-use. Index piggybacks daily training
    # job; read-only ChromaDB "code_patterns" (separate from business-KB). OFF default.
    # --- Engineering-agent code diagnostics (OpenCode parity) 2026-06-24 ---
    "CODE_DIAGNOSTICS",  # self-check Vikram proposals (cited-path existence) so admin
    # can trust them. Admin POST /api/growth/upgrader/diagnostics (ast syntax + optional
    # ruff lint + path-existence) is flag-independent. Read-only, never-raise. OFF default.
    # --- Agent-extension batch (Kilo/OpenCode/Ruflo/Hermes) 2026-06-24, /api/agents-ext ---
    "CODE_REVIEWER",  # dedicated code-review agent (perf/security/style/tests) — Kilo
    "AGENT_RECALL",  # agents search their own past runs/decisions — Hermes
    "AGENT_CHECKPOINTS",  # snapshot+rollback for agent data-mutations — Hermes/Kilo
    "TRAJECTORY_LEARN",  # record+replay winning agent traces + training export — Ruflo SONA
    "AGENT_CONSENSUS",  # N-voter quorum decision mode — Ruflo
    "AGENT_PERMISSIONS",  # per-agent tool/side-effect ACL (fail-open; ban-risk fail-safe) — OpenCode
    "AGENT_HOOKS",  # user-definable pre/post/error lifecycle hooks — Hermes/Ruflo
    "CUSTOM_AGENTS",  # data-file-defined custom agent personas (no code deploy) — OpenCode/Kilo
    "BATCH_HARNESS",  # parallel agent-run over many inputs + checkpoint/resume — Ruflo/Hermes
    "CODE_EXEC",  # guarded python tool-script executor — Hermes; SUPER-ADMIN, INERT default
    "BROWSER_TOOLS",  # Playwright headless enrichment — Hermes; SUPER-ADMIN + optional dep, INERT
    "CRED_POOLS",  # multi-key round-robin per provider (free-tier capacity) — Hermes
    "RISK_AUTO_APPROVE",  # risk-scored auto-approve for low-risk self-improve actions — OpenCode
    "RISK_AUTO_APPROVE_MAX_COST",  # ₹ ceiling for auto-approval (default 5)
    # --- Admin DB Explorer (council 2026-06-25, Supabase-Studio alternative) ---
    "ADMIN_DB_EXPLORER",  # super-admin READ-ONLY DB browser + CSV export on OUR Postgres
    # (/api/admin/db/* + /app/admin/db); sensitive cols redacted, no edit. OFF default → 503.
    # --- Page-Agent admin copilot (alibaba/page-agent, 2026-07-03) ---
    "PAGE_AGENT",  # in-page NL GUI copilot on admin pages (automation/admin/growth-tools/
    # marketing/office) — key-safe LLM proxy /api/page-agent/v1 (Mistral→Groq). OFF default → 503.
    # --- Voice STT + LLM flags (live on VPS, now visible in dashboard) ---
    "HINGLISH_STT",  # local Hinglish whisper model (baked, WEBCALL_STT_LOCAL_FIRST=1 saath)
    "WEBCALL_STT_LOCAL_FIRST",  # web-call STT uses local Hinglish model before Groq
    "VOICE_GEMINI_PRIMARY",  # voice brain uses Gemini 2.5-flash-lite as primary LLM (voice-scoped)
    "VOICE_LLM_RACE",  # race Gemini + free_ai LLM backends in parallel, first non-empty wins
    # (cuts ~16s sequential worst-case to ~3-5s typical — fix for "atak jata" symptom 2026-06-26)
    "VOICE_RESPONSE_CACHE",  # opener-only semantic cache for voice brain (L1 exact + L2 semantic
    # via Qdrant). Hit returns ~50ms vs 7-8s LLM round-trip for templated openers; mid-conversation
    # never cached (context-bleed safe). Requires SEMANTIC_CACHE=1 too. Fix for 2026-06-26 finding
    # that SEMANTIC_CACHE flag was ON in prod but voice brain never called semantic_complete.
    "BARGE_GUARD",  # cough/backchannel false-stop guard for barge-in detection
    "VOICE_GUARDRAILS",  # role-injection guardrail in telecaller_brain (pre-LLM deflect +
    # post-LLM obeyed-discard) — keeps Swara in the sales-telecaller role under
    # "ignore your instructions / ab tum pirate ho / show your system prompt". Default ON
    # (security guard); set 0 to disable. Covers web-call + vobiz (shared brain chokepoint).
    # --- RL self-improvement flywheel (Phase 0, 2026-06-29) — reward spine only ---
    "RL_ENGINE",  # master gate for reward-log emission + Stop hook + /api/rl (default OFF = fully inert)
    "RL_SUCCESS_THRESHOLD",  # reward >= this counts as a "success" for Beta/Laplace arm stats (default 0.5)
    "RL_GRADUATION_N",  # per-domain samples before Phase-1 policy graduation (default 200; Phase-1 not built yet)
    # --- Unity Blueprint Virtual Office (Milestone C shell, 2026-07-12) ---
    "UNITY_VIRTUAL_OFFICE_ENABLED",  # /app/office?mode=3d serves office_blueprint.html shell (admin).
    # OFF default → existing 2D Phaser office map (fully INERT). docs/UNITY_VIRTUAL_OFFICE_ARCHITECTURE.md
    "UNITY_CUSTOMER_OFFICE_ENABLED",  # customer 3D office shell (Milestone E). OFF default (INERT).
    # --- OmniRoute dev-tooling gateway integration (2026-07-12 audit) ---
    "OMNIROUTE_ENABLED",  # optional additive fallback via app/platform/omniroute_client.py.
    # OFF default (INERT) — local admin/data-plane and sanitized Groq/Mistral Responses
    # calls are verified, but customer/production routing is deliberately not approved.
    # Flip only in a sanitized local process using the explicit task registry.
    # NOT in the production customer request path (LeadGen's existing free_ai.py chain
    # is untouched/unconditional).
    "OMNIROUTE_AGENTS",  # ADR-108 (2026-07-16, user go-ahead): staff-agent bulk LLM calls
    # (free_ai.chat, profile=bulk ONLY — realtime/voice hot-path EXCLUDED) OmniRoute try
    # kar sakte hai. Double-gated: OMNIROUTE_ENABLED=1 AND OMNIROUTE_AGENTS=1 dono chahiye.
    # Sanitized payload only (mask_customer_data + validate_no_secrets), fail-open —
    # OmniRoute down/miss = existing free chain unchanged. OFF default (INERT).
    # Sanitized payload only (mask_customer_data + validate_no_secrets), fail-open —
    # OmniRoute down/miss = existing free chain unchanged. OFF default (INERT).
    "OMNIROUTE_VOICE",  # Swara live LLM brain via omniroute_voice.py (streaming).
    # Requires OMNIROUTE_ENABLED=1 + OMNIROUTE_API_KEY. Masked customer payload only.
    # OFF default (INERT) — flip after canary on allowlisted call.
    "VOICE_PROCESSING_ACK",  # After ~2s without first audio: short "Ji, ek second." bridge.
    # Cancelled on first audio or barge-in. OFF default (INERT).
    "VOICE_PROCESSING_ACK_DELAY_S",  # Seconds before processing ack (default 2.0).
    # --- Swara enterprise conversation upgrade (2026-07-17) ---
    "VOICE_STICKY_ROUTE",  # pin provider/model at call start (default ON) — no mid-call churn
    "STT_UNDERSTANDING_GATE",  # pre-LLM STT classify + clarify (default ON)
    "VOICE_TRAINING_LOOP",  # 30-call pause → QA proposal (default ON; auto fine-tune NEVER)
    # Social OAuth env-approval (ADR-112): env ON ≠ oauth_ready until authorize URL wired.
    "META_OAUTH_APPROVED",
    "GBP_OAUTH_APPROVED",
    "LINKEDIN_OAUTH_APPROVED",
    "X_OAUTH_APPROVED",
    "GOOGLE_OAUTH_APPROVED",
    # --- Autonomous Sales Engine / Sales Autopilot (2026-07-24, app/platform/sales_autopilot) ---
    # Policy-driven, fail-closed, DRY-RUN default. Separate from WHATSAPP_AUTO_SEND (never the
    # master gate here). Calling stays HARD OFF. All default OFF / INERT.
    "SALES_AUTOPILOT_ENABLED",  # master gate — OFF default → engine fully inert (no work, dry-run)
    "SALES_AUTOPILOT_WHATSAPP_ENABLED",  # arm WA channel live-send (needs dry_run=false too)
    "SALES_AUTOPILOT_EMAIL_ENABLED",  # arm email channel (live email is handoff-stub only)
    "SALES_AUTOPILOT_DRY_RUN",  # force simulation (env can only make it MORE safe)
    "SALES_AUTOPILOT_NEW_OUTREACH_KILL",  # block brand-new first-touch outreach
    "SALES_AUTOPILOT_FOLLOWUP_KILL",  # block follow-ups
    "SALES_AUTOPILOT_AUTOREPLY_KILL",  # block safe auto-replies (escalate to Owner OS only)
    "SALES_AUTOPILOT_PAYMENT_REMINDER_KILL",  # block payment/onboarding nudges
    "SALES_AUTOPILOT_CANARY_BATCH",  # per-tick batch size (default 1)
    "SALES_AUTOPILOT_LLM_TONE",  # OPTIONAL tone-only LLM review (never authoritative)
    "SALES_AUTOPILOT_REFILL",  # prospector → autopilot store upsert (OFF default; tick + admin)
    # --- Agent task-queue lease reclaim (2026-07-31, app/platform/agent_task_queue) ---
    # stale_tasks() only SURFACES stuck work by design ("Paperclip philosophy"), so a worker
    # that dies between claim_next() and complete()/fail() strands its lease forever and the
    # task is never resolved. This arms the TERMINAL close-out: the expired lease is marked
    # failed (never requeued — complete()/fail() ignore checkout_version, so a requeue could
    # double-run side-effecting work). Re-assignment stays a human decision.
    # No sends, no customer mutation, no migration. OFF default → surface-only.
    "AGENT_TASK_LEASE_REAP",
    # Orphan-ledger sweep. DISJOINT from AGENT_TASK_LEASE_REAP above: that one closes
    # EXPIRED LEASES (claimed/running, claimed_at < cutoff); this one closes rows that were
    # never claimable at all (pending + claimed_at IS NULL) — a bookkeeping leak from
    # self-assigned producers that called start() (requires `claimed`) instead of begin().
    # Closed as `cancelled`, NOT `failed`: most of those routines succeeded and their real
    # outcome lives in automation_logs; marking them failed would fabricate an incident
    # history. Bounded batch + JSONL backup before mutation + idempotent + NEVER requeues
    # (these wrap platform_dial/email_outreach — a re-run would place real calls).
    # OFF default.
    "AGENT_TASK_ORPHAN_REAP",
    # Monthly billing-cycle deliverable seed, riding the product_one_health sweep.
    # OFF default. initialize_deliverables_for_client fires ONLY on plan activation
    # (billing/usage.py), so nothing creates the NEXT month's rows: prod held 20 rows,
    # all cycle 2026-07, newest created 2026-07-18, while the paying customer was 30+
    # days into a paid month. Selector is the SUBSCRIPTION (non-terminal) not
    # clients.status, so quarantined fixtures are excluded by construction. Seeds under
    # the BILLING id (FK to clients.id). Idempotent; DB rows only — no content, no sends.
    "DELIVERABLE_CYCLE_SEED",
    # Post-prospect nested harvest (websearch/opendata). Default ON. Set 0 to skip
    # the morning nest and rely on midday/evening_prospect (D2 SoftTimeLimit, 2026-08-07).
    "PROSPECT_INLINE_HARVEST",
    # Wall-clock budget seconds for that nest (default 240, clamp 30..300). Replaces the
    # old hard min(remain, 120) that starved harvest after D1 raised Places fan-out.
    "PROSPECT_POST_HARVEST_BUDGET_S",
    # Scheduler routine-ledger switch. DEFAULT ON — this is the only flag in this
    # block that is not INERT by default, because it preserves existing behaviour.
    # The bridge writes one agent_tasks row per job invocation (~700/day) and nothing
    # in the codebase prunes this table, so even once the rows close correctly the
    # ledger grows ~255k/year. The authoritative job record is automation_logs; this
    # is a duplicate audit trail. Set 0 to stop writing it without touching the jobs.
    "ROUTINE_TASK_LEDGER",
]
