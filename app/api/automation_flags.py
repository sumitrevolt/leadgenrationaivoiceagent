"""Automation flags registry — saare gated automation/env flags ek jagah.

Extracted from app/api/growth.py (2026-06-20 refactor) for data/route separation.
growth.py re-exports AUTOMATION_FLAGS for backward-compat (admin_dashboard.py +
tests import `from app.api.growth import AUTOMATION_FLAGS`).
"""

# Saare gated automation flags ka registry — live env status ek jagah.
AUTOMATION_FLAGS = [
    "CONTROL_CENTER",  # enterprise Control Center cockpit (/app/control-center) — nav-surface gate, default OFF
    "FLOW_RUNNER",  # visual builder -> process-as-code execution (admin, linear+DAG, default OFF)
    "FLOW_AUTO_TRIGGERS",  # Phase 3: cron + event auto-fire for saved flows (needs FLOW_RUNNER too, default OFF)
    "FLOW_RUNNER_CUSTOMER",  # Phase 7: per-client flow builder in customer portal (needs FLOW_RUNNER too, draft-only, default OFF)
    "FEATURE_FLAGS",  # SaaS infra Phase-1: per-tenant runtime feature-flag system master gate (default OFF)
    "TEAM_AUTOMATION",
    "RUN_IN_PROCESS_SCHEDULER",
    "NICHE_ROTATION",
    "AUTO_EMAIL_OUTREACH",
    "JOURNEY_ENGINE",
    "AUTO_QUALIFY_CALLS",
    "REPLY_AGENT",
    "CALL_LOG_DB",  # write structured call_logs row per call -> DB-backed analytics dashboard (default ON)
    "OPS_WATCHDOG",
    "AUTO_ONBOARD",
    "USE_STRUCTURED_CONTENT",
    "USE_AGENTIC_RAG",
    "USE_RERANKER",
    "USE_CONTEXTUAL_INGEST",
    "USE_CONTEXTUAL_INGEST_LLM",
    "USE_HYBRID_SEARCH",
    "USE_LANGGRAPH_SUPERVISOR",
    "USE_LANGGRAPH_HIGH_STAKES",
    "AGENT_STANDUP",
    "SALES_ENGINE",
    "CADENCE_ENGINE",
    "DUNNING_ENGINE",
    "LIFECYCLE_NURTURE",
    "CLIENT_HEALTH_ALERTS",
    "REVENUE_DIGEST",
    "GROWTH_OPTIMIZER",
    "CHANNEL_EXPERIMENTS",
    "CAMPAIGN_OPTIMIZER",  # Kiran: orchestrates optimizer+bandit+feedback every 100 interactions
    "OUTREACH_CAMPAIGN_VARIANTS",  # cold email uses Kiran champion/challenger copy (impression/reply tracked)
    "VOICE_CAMPAIGN_VARIANTS",  # Swara phone/web greeting uses voice_opening champion/challenger
    "PROCESS_ENGINE",  # deterministic process-as-code workflows (complement to PROCESS_AUTOSTART)
    "AUTO_INVOICE",
    "EMAIL_WARMUP",
    "EMAIL_TRACKING",  # cold-email open/click pixels (listmonk parity); OFF = no tracking emitted
    "USAGE_ALERTS",
    "REVIEW_MONITOR",
    "BOOKING_REMINDERS",
    "DELIVERABILITY_MONITOR",
    "AUTOMATION_HEALTH_ALERTS",
    "WHATSAPP_AUTO_SEND",
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
    "SOCIAL_ENGINE",  # native social-posting engine (own queue+providers; default OFF, video_ad_cycle inline fallback)
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
    "GTM_TARGETING",  # systematic City x Niche coverage matrix for the lead-harvester (gtm_targeting.py) — OFF default
    "UDYAM_PIPELINE",  # Udyam-primary acquisition: data.gov.in seed -> Maps+website enrich (udyam_pipeline.py) — OFF default
    "OPENCORPORATES_API_TOKEN",  # company-registry enrich (CIN/status) — inert without token
    "INDIAMART_CRM_KEY",  # IndiaMART official Lead Manager API (seller's own leads) — inert without key
    "CALL_TRANSFER",
    "OUTREACH_AB",
    "OUTREACH_AUDIT_LED",  # cold-email leads with a personalized audit-gap hook (additive, no cap change) — OFF default
    "UPI_AUTO_ACTIVATE",  # self-serve UPI submit auto-activates plan immediately (reconcile later) — OFF default
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
    "LLM_BUDGET_GUARD",  # per-scope LLM daily cost/usage cap + kill-switch — OFF default, fail-open
    "LLM_BUDGET_HARD_KILL",  # emergency manual stop: ALL LLM block (fail-closed) — OFF default
    "MAGIC_LINK",  # passwordless customer login (single-use email link) — OFF default
    "IMPERSONATION",  # super-admin "login as customer" support tool (audited) — OFF default
    "PUBLIC_GUARDRAILS",  # PII-redact + prompt-injection block on public chatbot/widget LLM — OFF default, fail-open
    "CONTENT_APPROVAL_AUTO",  # daily auto_content → client approval queue auto-submit — OFF default
    "OLLAMA_URL",
    "OLLAMA_PRIMARY",  # self-hosted own LLM (GPU/PC) — URL set = active
    "NEWSLETTER_ENGINE",
    "WINBACK_ENGINE",
    "BRAND_PULSE",
    "TEAM_REPORT",
    "SKILL_PACK",
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
    "AUTO_CALLBACK_INQUIRY",  # inquiry submit pe instant AI callback
    "WHATSAPP_LEAD_FLOW_ID",  # Meta Flow in-chat lead capture (URL-valued = set hone pe ON)
    "REPLY_AUTO_SEND",  # interested reply auto-send (ban-risk — default OFF)
    "SELF_IMPROVE_APPROVAL",  # LLM-heavy self-improve actions human approve gate
    "REQUEST_GUARD",  # per-request timeout + load-shed middleware
    "PLAN_RATE_LIMIT",  # tier-based API rpm limits
    "CIRCUIT_BREAKER",  # external-service breaker (Pollinations etc.) — OFF default, fast-fail on outage
    # Edge protection (Cloudflare) — URL-valued flags become ON when set.
    "CLOUDFLARE_TUNNEL_TOKEN",  # docker-compose.edge.yml cloudflared — origin-hide + WAF/DDoS
    "TURNSTILE_SITE_KEY",  # public site-key (safe to expose) — widget renders only when set
    "TURNSTILE_SECRET_KEY",  # server secret — present = bot-check armed on /audit /site-audit /demo /inquiry
    # F.3 eval_gate close-the-loop reward signal for self_improve + DeepEval CI
    "EVAL_GATE",  # records baseline + decides; observe-only until HARD set
    "EVAL_GATE_HARD",  # makes reject decisions actually block (after baseline trusted)
    # 2026-06-28 agent/queue governance guards (INERT default — docs/WORKFLOW_IMPROVEMENT_BACKLOG.md)
    "COORDINATOR_LLM_CAP_PER_MIN",  # coordinator LLM rate-cap/min (0=off) — over → call skipped fail-open
    "QUEUE_DEPTH_BACKPRESSURE",  # DLQ retry-sweep defers when celery depth > QUEUE_DEPTH_CAP (retry-storm guard)
    "QUEUE_DEPTH_CAP",  # default 800 — celery depth above which backpressure trips
    # F.5 engineer agents (Pranav SRE / Vidya FinOps / Arnav Security)
    "SRE_AGENT",  # Pranav reliability score (hourly :45)
    "FINOPS_AGENT",  # Vidya margin score + LiteLLM-attributed cost-per-tenant
    "SECURITY_AGENT",  # Arnav DPDP/TRAI posture
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
]
