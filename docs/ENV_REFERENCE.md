# Environment Variable Reference

> **AUTO-GENERATED** — edit via `scripts/env_reference_sync.py` (`--check` = CI drift gate). Table between the AUTO markers is overwritten; prose above/below is preserved.
>
> Full annotated template with guidance + defaults: [`.env.example`](../.env.example). Gap tracked as **R-10** in `docs/GAP_REGISTER_2026_07_05.md`.
>
> **VALUES kabhi is file me nahi aate — sirf key NAMES.** Secrets sirf `.env` (gitignored) me rehte hain; yeh reference sirf batata hai *kaun si* keys code padhta hai aur `.env.example` me documented hain ya nahi.

---

<!-- AUTO-ENV:START -->

## Env Key Index — auto-generated (584 keys)

> Regenerate: `python scripts/env_reference_sync.py` · Drift-check: `--check`. Edits between the AUTO markers are overwritten. **NAMES only — koi value yahan nahi.**

- **Total keys:** 584
- **Undocumented in `.env.example`** (code me read, example me nahi): 350
- **Example-only** (`.env.example` me hai, code me kahin read nahi — possibly dead): 25

| KEY | read-via | in .env.example? | in flags registry? | source files |
| --- | --- | --- | --- | --- |
| `ACCOUNT_LOCKOUT_MINUTES` | settings | yes | no | app/config.py |
| `ADMIN_API_KEY` | getenv | yes | no | app/middleware/__init__.py |
| `ADMIN_DB_EXPLORER` | getenv | no | yes | app/api/admin_db_explorer.py |
| `ADMIN_OFFICE` | getenv | no | yes | app/api/admin_ops.py |
| `ADMIN_TOTP_SECRET` | getenv | yes | no | app/api/admin.py |
| `AFTERNOON_CONTENT` | getenv | no | yes | app/platform/team_scheduler.py |
| `AGENTIC_RAG_MIN_SCORE` | getenv | no | no | app/agents/agentic_rag.py |
| `AGENT_CHECKPOINTS` | getenv | no | yes | app/agents/agent_checkpoints.py |
| `AGENT_CONSENSUS` | getenv | no | yes | app/agents/agent_consensus.py |
| `AGENT_HOOKS` | getenv | no | yes | app/agents/lifecycle_hooks.py |
| `AGENT_MEMORY` | getenv | yes | yes | app/voice_agent/agent_memory.py |
| `AGENT_MEMORY_COLLECTION` | getenv | no | no | app/voice_agent/agent_memory.py |
| `AGENT_MEMORY_EMBED_TIMEOUT_S` | getenv | no | no | app/voice_agent/agent_memory.py |
| `AGENT_MEMORY_MAX_FACTS` | getenv | yes | yes | app/voice_agent/agent_memory.py |
| `AGENT_MEMORY_MIN_SIM` | getenv | yes | yes | app/voice_agent/agent_memory.py |
| `AGENT_MEMORY_OP_TIMEOUT_S` | getenv | no | no | app/voice_agent/agent_memory.py |
| `AGENT_MEMORY_RECALL_LIMIT` | getenv | yes | yes | app/voice_agent/agent_memory.py |
| `AGENT_PERMISSIONS` | getenv | no | yes | app/agents/agent_permissions.py |
| `AGENT_RECALL` | getenv | no | yes | app/agents/agent_recall.py |
| `AGENT_STANDUP` | getenv | yes | yes | app/platform/team_scheduler.py |
| `AI4BHARAT_ENDPOINT` | getenv | no | no | app/api/web_call.py, app/voice_agent/indic_providers.py |
| `AI4BHARAT_STT_URL` | - | yes | no | - |
| `AI4BHARAT_TTS_URL` | - | yes | no | - |
| `ALLOW_MOCK_STT` | getenv | no | no | app/voice_agent/free_stt.py |
| `AMD_DETECT` | getenv | no | yes | app/telephony/vobiz_stream.py |
| `AMD_LEAVE_VOICEMAIL` | getenv | no | no | app/telephony/webhooks.py |
| `ANTHROPIC_API_KEY` | settings | yes | no | app/config.py |
| `ANTI_LOOP` | getenv | no | no | app/voice_agent/telecaller_brain.py |
| `APP_ENV` | both | yes | no | app/config.py, app/config_production.py |
| `APP_NAME` | settings | yes | no | app/config.py |
| `APP_VERSION` | getenv | no | no | app/api/health.py, app/main.py |
| `AUTOMATION_HEALTH_ALERTS` | getenv | no | yes | app/platform/automation_health.py |
| `AUTO_CALLBACK_INQUIRY` | getenv | no | yes | app/platform/inquiry_hooks.py |
| `AUTO_DETECT_PAYMENT_GATEWAY` | settings | yes | no | app/config.py |
| `AUTO_EMAIL_OUTREACH` | both | yes | yes | app/api/admin_ops.py, app/config.py |
| `AUTO_INVOICE` | getenv | yes | yes | app/billing/gst_invoice.py |
| `AUTO_ONBOARD` | - | yes | yes | - |
| `AUTO_QUALIFY_CALLS` | getenv | no | yes | app/telephony/call_manager.py, app/telephony/post_call_hooks.py, app/telephony/vobiz_stream.py |
| `AUTO_START_PLATFORM` | settings | yes | no | app/config.py |
| `AZURE_SPEECH_KEY` | settings | no | no | app/config.py |
| `AZURE_SPEECH_REGION` | settings | no | no | app/config.py |
| `BARGE_GUARD` | - | no | yes | - |
| `BARGE_IN_ENABLED` | getenv | no | no | app/telephony/vobiz_stream.py |
| `BATCH_HARNESS` | getenv | no | yes | app/agents/batch_harness.py |
| `BOOKING_NOTIFY` | getenv | no | yes | app/integrations/calendar_booking.py |
| `BOOKING_REMINDERS` | getenv | yes | yes | app/platform/booking_reminders.py |
| `BRAND_PULSE` | getenv | no | yes | app/platform/brand_pulse.py |
| `BRAVE_API_KEY` | getenv | no | no | app/platform/lead_harvester.py |
| `BREVO_API_KEY` | settings | no | no | app/config.py |
| `BROWSER_TOOLS` | getenv | no | yes | app/agents/browser_tools.py |
| `CACHE_REDIS_URL` | getenv | yes | no | app/cache/__init__.py |
| `CADENCE_ENGINE` | getenv | yes | yes | app/marketing/cadence.py, app/platform/lead_harvester.py, app/platform/niche_prospector.py |
| `CALCOM_API_KEY` | - | no | yes | - |
| `CALENDARIFIC_API_KEY` | getenv | no | no | app/marketing/festivals.py |
| `CALL_LOG_DB` | getenv | no | yes | app/telephony/post_call_hooks.py |
| `CALL_MIN_SCORE` | getenv | no | no | app/telephony/call_manager.py |
| `CALL_PROCESSOR` | getenv | no | no | app/main.py |
| `CALL_RETRY_ATTEMPTS` | settings | yes | no | app/config.py |
| `CALL_RETRY_DELAY_MINUTES` | settings | yes | no | app/config.py |
| `CALL_TRANSFER` | getenv | no | yes | app/telephony/call_transfer.py |
| `CAMPAIGN_OPTIMIZER` | getenv | no | yes | app/agents/campaign_optimizer.py, app/platform/team.py |
| `CELERY_HEAVY_QUEUE` | getenv | yes | no | app/worker.py |
| `CELERY_TRIM_MIN_DEPTH` | getenv | no | yes | app/platform/scheduled_ops.py |
| `CEREBRAS_API_KEY` | both | yes | no | app/agents/staff_supervisor.py, app/config.py, app/llm/structured.py |
| `CHANNEL_EXPERIMENTS` | getenv | yes | yes | app/marketing/channel_experiments.py |
| `CIRCUIT_BREAKER` | getenv | no | yes | app/infrastructure/circuit_breaker.py |
| `CLIENT_HEALTH_ALERTS` | getenv | yes | yes | app/platform/client_health.py |
| `CLIENT_HOT_LEAD_ALERT` | getenv | no | no | app/platform/lead_alerts.py |
| `CLIENT_NOTIFY_DEFAULT` | - | yes | no | - |
| `CLIENT_REPORTS` | getenv | no | yes | app/marketing/client_report.py |
| `CLIENT_TIMELINE` | getenv | no | yes | app/api/admin_dashboard.py |
| `CLOSE_DETECT` | getenv | no | no | app/voice_agent/telecaller_brain.py |
| `CLOUDFLARE_TUNNEL_TOKEN` | - | yes | yes | - |
| `CODE_DIAGNOSTICS` | getenv | no | yes | app/agents/code_diagnostics.py |
| `CODE_EXEC` | getenv | no | yes | app/agents/code_exec.py |
| `CODE_REVIEWER` | getenv | no | yes | app/agents/code_reviewer.py |
| `CODE_SEARCH` | getenv | no | yes | app/agents/code_search.py |
| `CODE_UPGRADER` | getenv | yes | yes | app/agents/code_upgrader.py |
| `COMBO_PRODUCT` | getenv | no | yes | app/main.py |
| `COMPLIANCE_PROMO_END` | getenv | no | no | app/api/admin_ops.py, app/telephony/campaign_compliance.py |
| `COMPLIANCE_PROMO_START` | getenv | no | no | app/api/admin_ops.py, app/telephony/campaign_compliance.py |
| `COMPLIANCE_TXN_END` | getenv | no | no | app/telephony/campaign_compliance.py |
| `COMPLIANCE_TXN_START` | getenv | no | no | app/telephony/campaign_compliance.py |
| `CONSENT_CONFIRM` | - | no | yes | - |
| `CONSENT_DB` | getenv | no | no | app/telephony/consent_ledger.py |
| `CONTENT_APPROVAL_AUTO` | getenv | no | yes | app/marketing/auto_content.py |
| `CONTROL_CENTER` | getenv | no | yes | app/api/control_center.py |
| `CONVO_DISCIPLINE` | getenv | no | no | app/voice_agent/telecaller_brain.py |
| `COORDINATOR_LLM_CAP_PER_MIN` | getenv | yes | yes | app/agents/coordinator.py |
| `COORD_KB_SHARE` | getenv | yes | no | app/agents/coordinator.py |
| `CORS_ORIGINS` | settings | yes | no | app/config.py |
| `COUNCIL_TIMEOUT_S` | getenv | no | no | app/agents/llm_council.py |
| `CRED_POOLS` | getenv | no | yes | app/agents/cred_pool.py |
| `CRM_SYNC` | getenv | yes | yes | app/agents/process_library.py, app/platform/crm_sync.py |
| `CRM_SYNC_PULL` | getenv | no | yes | app/platform/crm_sync.py |
| `CUSTOMER_OFFICE` | getenv | no | yes | app/api/customer_dashboard.py |
| `CUSTOMER_WEBHOOKS` | - | yes | yes | - |
| `CUSTOMER_WEBHOOK_DENY_PRIVATE` | - | yes | yes | - |
| `CUSTOMER_WISHES` | getenv | yes | yes | app/marketing/customer_crm.py |
| `CUSTOM_AGENTS` | getenv | no | yes | app/agents/custom_agents.py |
| `DATABASE_URL` | both | yes | no | app/api/admin_ops.py, app/config.py, app/models/migrations.py |
| `DATA_DIR` | getenv | no | no | app/agents/eval_gate.py, app/api/ml_training.py, app/billing/lead_usage.py |
| `DATA_GOV_IN_API_KEY` | getenv | no | no | app/platform/lead_harvester.py |
| `DATA_GOV_RESOURCE_ID` | getenv | no | no | app/platform/lead_harvester.py |
| `DATA_INTEGRITY_AGENT` | getenv | no | yes | app/platform/team.py |
| `DBRE_AGENT` | getenv | no | yes | app/platform/team.py |
| `DB_CREATE_ALL` | getenv | yes | no | app/models/base.py |
| `DEBUG` | settings | yes | no | app/config.py |
| `DEEPGRAM_API_KEY` | settings | no | no | app/config.py |
| `DEFAULT_CURRENCY` | settings | yes | no | app/config.py |
| `DEFAULT_LANGUAGE` | getenv | yes | no | app/api/web_call.py, app/voice_agent/indic_providers.py |
| `DEFAULT_LLM` | both | yes | no | app/agents/staff_supervisor.py, app/config.py, app/llm/structured.py |
| `DEFAULT_SPREADSHEET_ID` | settings | yes | no | app/config.py |
| `DEFAULT_STT` | settings | no | no | app/config.py |
| `DEFAULT_TELEPHONY` | settings | yes | no | app/config.py |
| `DEFAULT_TTS` | settings | no | no | app/config.py |
| `DELIVERABILITY_MONITOR` | getenv | no | yes | app/platform/deliverability_monitor.py |
| `DELIVERY_EMAIL_ENABLED` | - | yes | no | - |
| `DELIVERY_HUBSPOT_ENABLED` | - | yes | no | - |
| `DELIVERY_SHEETS_ENABLED` | - | yes | no | - |
| `DELIVERY_WHATSAPP_ENABLED` | - | yes | no | - |
| `DEPS_AGENT` | getenv | no | yes | app/platform/team.py |
| `DIAL_TEST_ALLOWLIST` | getenv | no | no | app/telephony/dial_gate.py |
| `DIAL_TEST_MODE` | getenv | no | no | app/telephony/dial_gate.py |
| `DIAL_TEST_MODE_CONFIG` | getenv | no | no | app/telephony/dial_gate.py |
| `DISCLOSURE_LOCK` | getenv | no | no | app/telephony/vobiz_stream.py |
| `DKIM_SELECTOR` | getenv | no | no | app/platform/deliverability_monitor.py |
| `DLQ_AUTO_RETRY` | getenv | no | yes | app/platform/dlq_retry.py |
| `DLT_APPROVED` | getenv | no | yes | app/platform/setup_status.py |
| `DND_API_KEY` | both | yes | no | app/config.py, app/utils/dnd_checker.py |
| `DND_API_URL` | both | yes | no | app/config.py, app/utils/dnd_checker.py |
| `DND_CARRIER_SCRUB` | getenv | no | no | app/utils/dnd_checker.py |
| `DR_LAG_FAIL_S` | getenv | yes | yes | app/platform/dr_health.py |
| `DR_LAG_WARN_S` | getenv | yes | yes | app/platform/dr_health.py |
| `DR_REPLICA_URL` | - | yes | yes | - |
| `DUNNING_ENGINE` | getenv | yes | yes | app/billing/dunning.py |
| `ELEVENLABS_API_KEY` | settings | no | no | app/config.py |
| `ELEVENLABS_VOICE_ID` | settings | no | no | app/config.py |
| `EMAIL_FROM` | settings | yes | no | app/config.py |
| `EMAIL_TRACKING` | getenv | no | yes | app/marketing/email_tracking.py |
| `EMAIL_UNSUB_SECRET` | getenv | no | no | app/marketing/email_tracking.py, app/platform/email_unsub.py |
| `EMAIL_WARMUP` | getenv | yes | yes | app/platform/email_warmup.py |
| `ENABLE_DND_CHECK` | settings | yes | no | app/config.py |
| `ENABLE_LEGACY_BEAT` | getenv | yes | yes | app/worker.py |
| `ENABLE_OTEL` | getenv | yes | yes | app/observability_otel.py |
| `ENTERPRISE_MONTHLY_PRICE` | settings | no | no | app/config.py |
| `ENV` | getenv | no | no | app/main.py |
| `ENVIRONMENT` | getenv | yes | no | app/observability_llm.py |
| `EVAL_GATE` | - | yes | yes | - |
| `EVAL_GATE_HARD` | - | yes | yes | - |
| `EVAL_KB_BOOST` | getenv | yes | no | app/platform/eval_hub.py |
| `EVENING_PROSPECT` | getenv | no | yes | app/platform/team_scheduler.py |
| `EVERGREEN_RECYCLE` | - | yes | yes | - |
| `FASTAPI_MCP_TOKEN` | getenv | yes | yes | app/main.py, app/platform/mcp_engineer.py |
| `FASTEMBED_CACHE_PATH` | getenv | no | no | app/platform/infra_handler.py |
| `FEATURE_FLAGS` | getenv | yes | yes | app/api/growth_feature_flags.py, app/infrastructure/feature_flags.py |
| `FESTIVALS_LIVE_HOLIDAYS` | getenv | no | yes | app/marketing/festivals.py |
| `FINOPS_AGENT` | getenv | yes | yes | app/platform/team.py |
| `FLOWER_PASSWORD` | - | yes | no | - |
| `FLOWER_USER` | - | yes | no | - |
| `FLOW_AUTO_TRIGGERS` | - | yes | yes | - |
| `FLOW_RUNNER` | getenv | yes | yes | app/agents/flow_dispatch.py, app/agents/process_library.py, app/api/admin_ops.py |
| `FLOW_RUNNER_CUSTOMER` | getenv | no | yes | app/api/customer_flows.py |
| `FUNCTION_NAME` | getenv | no | no | app/config_production.py |
| `FWHISPER_LANG` | getenv | no | no | app/api/web_call.py, app/telephony/vobiz_stream.py |
| `FWHISPER_MODEL` | getenv | no | no | app/telephony/vobiz_stream.py |
| `FWHISPER_PROMPT` | getenv | no | no | app/api/web_call.py, app/telephony/vobiz_stream.py |
| `GAE_APPLICATION` | getenv | no | no | app/config_production.py |
| `GCS_BUCKET_NAME` | settings | yes | no | app/config.py |
| `GCS_PROFILE_PICTURES_BUCKET` | settings | yes | no | app/config.py |
| `GEMINI_API_KEY` | both | yes | no | app/config.py, app/telephony/vobiz_stream.py, app/voice_agent/gemini_keys.py |
| `GEMINI_API_KEYS` | both | yes | no | app/config.py, app/telephony/vobiz_stream.py, app/voice_agent/gemini_keys.py |
| `GEMINI_LLM_MODEL` | getenv | no | no | app/voice_agent/free_ai.py |
| `GEMINI_PRIMARY` | getenv | no | no | app/voice_agent/free_ai.py |
| `GEMINI_TTS` | getenv | no | no | app/voice_agent/gemini_tts.py |
| `GEMINI_TTS_MODEL` | getenv | no | no | app/voice_agent/gemini_tts.py |
| `GEMINI_TTS_VOICE` | getenv | no | no | app/voice_agent/gemini_tts.py |
| `GOOGLE_APPLICATION_CREDENTIALS` | getenv | no | no | app/utils/logger.py |
| `GOOGLE_CLOUD_LOCATION` | both | yes | no | app/config.py, app/voice_agent/free_ai.py |
| `GOOGLE_CLOUD_PROJECT` | getenv | no | no | app/config_production.py, app/voice_agent/free_ai.py |
| `GOOGLE_CLOUD_PROJECT_ID` | both | yes | no | app/config.py, app/voice_agent/free_ai.py |
| `GOOGLE_MAPS_API_KEY` | both | yes | no | app/config.py, app/marketing/review_monitor.py, app/platform/grid_rank.py |
| `GOOGLE_SHEETS_CREDENTIALS` | settings | yes | no | app/config.py |
| `GOOGLE_SPEECH_CREDENTIALS` | settings | no | no | app/config.py |
| `GRAFANA_PASSWORD` | - | yes | no | - |
| `GRIEVANCE_OFFICER_EMAIL` | getenv | no | no | app/platform/engineer_agents.py |
| `GROQ_API_KEY` | both | yes | no | app/agents/staff_supervisor.py, app/api/admin_ops.py, app/config.py |
| `GROQ_STT_LANG` | getenv | no | no | app/telephony/vobiz_stream.py |
| `GROQ_STT_MODEL` | getenv | no | no | app/voice_agent/free_ai.py |
| `GROWTH_MONTHLY_PRICE` | settings | no | no | app/config.py |
| `GROWTH_OPTIMIZER` | getenv | yes | yes | app/agents/growth_optimizer.py |
| `GST_GSTIN` | getenv | yes | no | app/billing/gst_invoice.py, app/billing/subscription.py |
| `GST_SUPPLIER_ADDRESS` | getenv | no | no | app/billing/gst_invoice.py |
| `GST_SUPPLIER_NAME` | getenv | no | no | app/billing/gst_invoice.py |
| `GST_SUPPLIER_STATE_CODE` | getenv | no | no | app/billing/gst_invoice.py |
| `GTM_PAIRS_PER_RUN` | getenv | no | no | app/platform/lead_harvester.py |
| `GTM_TARGETING` | getenv | no | yes | app/platform/gtm_targeting.py |
| `HARVEST_INGEST_VALIDATION` | getenv | no | yes | app/platform/lead_harvester.py |
| `HEALTH_DISK_PATH` | getenv | no | no | app/api/system_health.py |
| `HERMES_HANDOFF` | - | no | yes | - |
| `HINGLISH_STT` | getenv | yes | yes | app/api/web_call.py, app/telephony/vobiz_stream.py |
| `HINGLISH_WHISPER_DIR` | getenv | yes | no | app/telephony/vobiz_stream.py |
| `HQ_ACTION_SECRET` | getenv | no | no | app/platform/reply_agent.py |
| `HUBSPOT_API_KEY` | settings | yes | no | app/config.py |
| `IDEMPOTENCY_TTL_S` | getenv | no | no | app/billing/idempotency.py |
| `IMAP_HOST` | getenv | no | no | app/platform/reply_agent.py |
| `IMPERSONATION` | getenv | no | yes | app/api/impersonation.py |
| `IMPERSONATION_TTL_MIN` | getenv | no | no | app/api/impersonation.py |
| `INDEXNOW` | getenv | no | yes | app/marketing/indexnow.py |
| `INDEXNOW_KEY` | getenv | no | no | app/marketing/indexnow.py |
| `INDIAMART_CRM_KEY` | getenv | no | yes | app/integrations/indiamart_leads.py |
| `INFRA_HANDLER` | getenv | no | yes | app/platform/infra_handler.py |
| `INTEGRATION_ALERTS` | getenv | no | yes | app/platform/integration_health.py |
| `INTEGRATION_FAIL_ALERT_N` | getenv | no | no | app/platform/integration_health.py |
| `INTERACTION_LOG` | getenv | no | yes | app/platform/interaction_log.py |
| `JOURNEY_ENGINE` | getenv | yes | yes | app/marketing/journeys.py, app/platform/pipeline_ops.py |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | settings | yes | no | app/config.py |
| `JWT_ALGORITHM` | settings | yes | no | app/config.py |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | settings | yes | no | app/config.py |
| `JWT_SECRET_KEY` | settings | yes | no | app/config.py |
| `KB_EMBED_LOAD_TIMEOUT_S` | getenv | no | no | app/voice_agent/knowledge_base.py |
| `KB_MIN_SCORE` | getenv | no | no | app/voice_agent/telecaller_brain.py |
| `KB_PREWARM` | getenv | no | yes | app/main.py |
| `KB_REFRESH_SEC` | getenv | no | no | app/voice_agent/telecaller_brain.py |
| `KB_SKILL_LEARN` | getenv | yes | no | app/agents/self_improve.py |
| `KB_WEEKLY_REFRESH` | getenv | no | yes | app/platform/kb_refresh.py |
| `KOKORO_LANG` | getenv | no | no | app/voice_agent/kokoro_tts.py |
| `KOKORO_VOICE` | getenv | no | no | app/voice_agent/kokoro_tts.py |
| `K_SERVICE` | getenv | no | no | app/config_production.py, app/utils/logger.py |
| `LEADGEN_API_URL` | getenv | no | no | app/cli.py |
| `LEADGEN_SCHEDULER_SECRET` | getenv | yes | no | app/api/team.py |
| `LEAD_HARVESTER` | getenv | yes | yes | app/platform/lead_harvester.py |
| `LEAD_HOT_THRESHOLD` | getenv | no | no | app/platform/lead_scoring.py |
| `LIFECYCLE_NURTURE` | getenv | yes | yes | app/marketing/lifecycle_nurture.py |
| `LIGHTRAG_DIR` | getenv | no | no | app/voice_agent/graph_rag.py |
| `LIGHTRAG_EMBED_DIM` | getenv | no | no | app/voice_agent/graph_rag.py |
| `LITELLM_COSTS` | - | yes | yes | - |
| `LITELLM_GATEWAY_URL` | - | yes | yes | - |
| `LITELLM_MASTER_KEY` | getenv | yes | yes | app/platform/engineer_agents.py |
| `LIVE_NOTES` | getenv | no | yes | app/platform/live_notes.py |
| `LLM_BUDGET_GUARD` | getenv | yes | yes | app/llm/budget_guard.py |
| `LLM_BUDGET_HARD_KILL` | getenv | yes | yes | app/llm/budget_guard.py |
| `LLM_BULK_TOKEN_THRESHOLD` | getenv | no | no | app/voice_agent/free_ai.py |
| `LLM_CACHE` | getenv | no | no | app/voice_agent/free_ai.py |
| `LLM_CACHE_TTL_S` | getenv | no | no | app/voice_agent/free_ai.py |
| `LLM_CAPACITY_ALERTS` | getenv | no | yes | app/platform/llm_metrics.py |
| `LLM_COUNCIL` | getenv | no | yes | app/agents/llm_council.py |
| `LLM_GUARD` | getenv | no | no | app/platform/llm_guard.py |
| `LLM_JUDGE` | getenv | no | no | app/agents/live_eval.py |
| `LLM_PROVIDER` | - | yes | no | - |
| `LOCAL_LLM_PATH` | settings | no | no | app/config.py |
| `LOG_LEVEL` | settings | no | no | app/config.py |
| `LOOP_SUPERVISOR` | - | no | yes | - |
| `MAGIC_LINK` | getenv | no | yes | app/api/customer_auth.py, app/api/customer_onboard.py |
| `MAGIC_LINK_TTL_S` | getenv | no | no | app/api/customer_auth.py |
| `MAX_CALL_DURATION_SECONDS` | settings | yes | no | app/config.py |
| `MAX_CONCURRENT_CALLS` | settings | yes | no | app/config.py |
| `MAX_FAILED_LOGIN_ATTEMPTS` | settings | yes | no | app/config.py |
| `MCP_AUTH_FAIL_ALERT` | getenv | yes | yes | app/platform/mcp_engineer.py |
| `MCP_ENGINEER` | getenv | yes | yes | app/platform/team.py |
| `MCP_IP_ALLOWLIST` | getenv | yes | yes | app/main.py, app/platform/mcp_engineer.py |
| `MCP_KEY_ROTATION_DAYS` | getenv | yes | yes | app/platform/mcp_engineer.py |
| `MCP_PRODUCT` | - | yes | yes | - |
| `MCP_QUOTA_PRESSURE_PCT` | getenv | yes | yes | app/platform/mcp_engineer.py |
| `MEM0_BACKEND` | getenv | yes | yes | app/voice_agent/agent_memory.py |
| `MEMORY_VAULT` | getenv | no | yes | app/platform/memory_vault.py |
| `META_FACEBOOK_PAGE_ID` | settings | no | no | app/config.py |
| `META_GRAPH_VERSION` | settings | no | no | app/config.py |
| `META_INSTAGRAM_ACCOUNT_ID` | settings | no | no | app/config.py |
| `META_PAGE_ACCESS_TOKEN` | settings | no | no | app/config.py |
| `METER_ALERTS` | - | no | yes | - |
| `METER_ALERT_COOLDOWN_SEC` | getenv | no | yes | app/billing/meter_watch.py |
| `METER_ALERT_GROWTH_THRESHOLD` | getenv | no | yes | app/billing/meter_watch.py |
| `METRICS_TOKEN` | getenv | yes | no | app/api/health.py |
| `MIDDAY_PROSPECT` | getenv | no | yes | app/platform/team_scheduler.py |
| `MINIO_ACCESS_KEY` | - | yes | no | - |
| `MINIO_BUCKET` | - | yes | no | - |
| `MINIO_ENDPOINT` | - | yes | no | - |
| `MINIO_SECRET_KEY` | - | yes | no | - |
| `MIN_QUALIFY_USER_TURNS` | getenv | no | no | app/voice_agent/call_qualifier.py |
| `MISSED_CALL_CALLBACK` | getenv | yes | yes | app/telephony/missed_call.py |
| `MISTRAL_API_KEY` | settings | no | no | app/config.py |
| `ML_NIGHTLY_TRAINING` | getenv | no | yes | app/platform/team_scheduler.py |
| `NEWSLETTER_ENGINE` | - | no | yes | - |
| `NICHE_ROTATION` | getenv | yes | yes | app/platform/team_scheduler.py |
| `NOINPUT_POLICY` | getenv | no | no | app/telephony/vobiz_stream.py |
| `NOTIFY_EMAIL` | both | yes | no | app/agents/code_upgrader.py, app/billing/usage_alerts.py, app/config.py |
| `NPS_ALERTS` | getenv | no | yes | app/platform/nps.py |
| `NPS_AUTO` | - | yes | yes | - |
| `NTFY_TOKEN` | getenv | no | no | app/integrations/ntfy.py |
| `NTFY_TOPIC` | getenv | yes | yes | app/integrations/ntfy.py |
| `NTFY_URL` | getenv | yes | yes | app/integrations/ntfy.py |
| `NVIDIA_API_KEY` | settings | yes | no | app/config.py |
| `NVIDIA_LLM_MODEL` | getenv | no | no | app/voice_agent/free_ai.py |
| `NVIDIA_PRIMARY` | getenv | no | no | app/voice_agent/free_ai.py |
| `OBJECTION_KB` | getenv | no | yes | app/platform/objection_extractor.py |
| `OBSIDIAN_GIT_REMOTE` | getenv | no | no | app/api/brain.py, app/platform/obsidian_sync.py |
| `OBSIDIAN_SYNC` | getenv | no | yes | app/platform/automation_health.py, app/platform/obsidian_sync.py |
| `OLLAMA_MODEL` | getenv | no | no | app/voice_agent/free_ai.py |
| `OLLAMA_PRIMARY` | getenv | no | yes | app/voice_agent/free_ai.py |
| `OLLAMA_TIMEOUT_S` | getenv | no | no | app/voice_agent/free_ai.py |
| `OLLAMA_URL` | getenv | no | yes | app/voice_agent/free_ai.py |
| `OPENAI_API_KEY` | settings | yes | no | app/config.py |
| `OPENCORPORATES_API_TOKEN` | getenv | no | yes | app/integrations/opencorporates.py |
| `OPENROUTER_API_KEY` | settings | yes | no | app/config.py |
| `OPENROUTER_API_KEY_2` | settings | no | no | app/config.py |
| `OPENROUTER_API_KEY_3` | settings | no | no | app/config.py |
| `OPENROUTER_API_KEY_4` | settings | no | no | app/config.py |
| `OPS_ALERTS` | - | yes | yes | - |
| `OPS_ALERT_ENGINEER_THRESHOLD` | getenv | yes | yes | app/platform/ops_alerts.py |
| `OPS_ALERT_EVAL_REJECT_BURST` | getenv | yes | yes | app/platform/ops_alerts.py |
| `OPS_ALERT_EVAL_REJECT_WINDOW` | getenv | yes | yes | app/platform/ops_alerts.py |
| `OPS_ALERT_WEBHOOK_DEAD_LETTER_THRESHOLD` | getenv | yes | yes | app/platform/ops_alerts.py |
| `OPS_WATCHDOG` | - | no | yes | - |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | getenv | yes | no | app/observability_otel.py |
| `OUTREACH_AB` | getenv | yes | yes | app/platform/auto_outreach.py |
| `OUTREACH_AB_PCT` | getenv | no | no | app/marketing/outreach_variants.py |
| `OUTREACH_AUDIT_LED` | getenv | no | yes | app/platform/auto_outreach.py |
| `OUTREACH_CAMPAIGN_VARIANTS` | getenv | no | yes | app/platform/auto_outreach.py |
| `OUTREACH_DAILY_CAP` | settings | no | no | app/config.py |
| `OUTREACH_DOMAIN` | getenv | no | no | app/platform/deliverability_monitor.py |
| `OUTREACH_FROM_NAME` | settings | no | no | app/config.py |
| `OUTREACH_MAILBOXES` | getenv | no | no | app/marketing/outreach_variants.py |
| `OUTREACH_UNSUB_MAILTO` | getenv | no | no | app/platform/email_unsub.py |
| `OUTREACH_VERIFY_MX` | getenv | no | no | app/platform/auto_outreach.py |
| `OWNER_BRIEF_DAILY` | - | yes | yes | - |
| `PAGE_AGENT` | getenv | no | yes | app/api/page_agent.py |
| `PAGE_AGENT_MODEL` | getenv | no | no | app/api/page_agent.py |
| `PAGE_AGENT_SCRIPT_URL` | getenv | no | no | app/api/page_agent.py |
| `PERMISSION_OPENER` | getenv | no | no | app/voice_agent/niche_scripts.py |
| `PHONE_CELEBRATION` | getenv | no | no | app/telephony/vobiz_stream.py |
| `PHONE_TTS_PITCH` | getenv | yes | no | app/telephony/vobiz_stream.py |
| `PHONE_TTS_RATE` | getenv | yes | no | app/telephony/vobiz_stream.py |
| `PLAN_RATE_LIMIT` | getenv | yes | yes | app/middleware/__init__.py |
| `PLATFORM_COMPANY_NAME` | settings | yes | no | app/config.py |
| `PLATFORM_DIAL_CONFIG` | getenv | no | no | app/platform/platform_dial.py |
| `PLATFORM_DIAL_DAILY` | getenv | no | yes | app/platform/platform_dial.py |
| `PLATFORM_DIAL_LIMIT` | getenv | no | no | app/platform/platform_dial.py |
| `PLATFORM_DIAL_NICHE` | getenv | no | no | app/platform/platform_dial.py |
| `PLATFORM_TARGET_CITIES` | settings | no | no | app/config.py |
| `PLATFORM_TARGET_INDUSTRIES` | settings | no | no | app/config.py |
| `PLATFORM_WEBSITE_URL` | settings | yes | no | app/config.py |
| `POLLINATIONS_API_KEY` | getenv | no | no | app/marketing/ai_image.py |
| `POLLINATIONS_TOKEN` | getenv | no | no | app/marketing/ai_image.py |
| `POSTHOG_API_KEY` | getenv | yes | no | app/platform/posthog_config.py |
| `POSTHOG_HOST` | getenv | yes | no | app/platform/posthog_config.py |
| `POSTIZ_API_KEY` | getenv | no | no | app/marketing/postiz_publish.py |
| `POSTIZ_API_URL` | getenv | no | no | app/marketing/postiz_publish.py |
| `POSTIZ_INTEGRATIONS` | getenv | no | no | app/marketing/postiz_publish.py |
| `POST_CALL_WHATSAPP` | getenv | no | yes | app/telephony/post_call_hooks.py |
| `PROCESS_AUTOSTART` | getenv | no | yes | app/platform/process_autostart.py |
| `PROCESS_ENGINE` | getenv | no | yes | app/agents/process_engine.py |
| `PROMETHEUS_HTTP_METRICS` | getenv | no | yes | app/middleware/http_metrics.py |
| `PROSPECT_CITIES` | getenv | no | no | app/marketing/channel_experiments.py, app/platform/niche_prospector.py |
| `PROSPECT_MAX_EMAIL_FETCH` | getenv | no | no | app/platform/prospector.py |
| `PROSPECT_MAX_LOOKUPS` | getenv | no | no | app/platform/prospector.py |
| `PROSPECT_TARGETS` | getenv | no | no | app/platform/niche_prospector.py, app/platform/prospector.py |
| `PROXY_URL` | settings | yes | no | app/config.py |
| `PUBLIC_BASE_URL` | both | no | no | app/api/customer_auth.py, app/config.py, app/marketing/email_tracking.py |
| `PUBLIC_GUARDRAILS` | getenv | no | yes | app/marketing/chatbot.py |
| `PUBLIC_IP` | getenv | no | no | app/platform/deliverability_monitor.py |
| `QDRANT_HOST` | getenv | no | no | app/voice_agent/agent_memory.py |
| `QDRANT_PORT` | getenv | no | no | app/voice_agent/agent_memory.py |
| `QDRANT_URL` | settings | no | no | app/config.py |
| `QUALIFY_BOT_GATE` | getenv | no | no | app/voice_agent/call_qualifier.py |
| `QUEUE_DEPTH_BACKPRESSURE` | getenv | yes | yes | app/platform/dlq_retry.py |
| `QUEUE_DEPTH_CAP` | getenv | yes | yes | app/platform/dlq_retry.py |
| `RANK_MAX_LOOKUPS` | getenv | no | no | app/platform/rank_tracker.py |
| `RANK_TRACKER` | - | no | yes | - |
| `RATE_LIMIT_PER_MINUTE` | settings | yes | no | app/config.py |
| `RCLONE_REMOTE` | - | yes | no | - |
| `RECONSENT_COOLOFF_DAYS` | getenv | no | no | app/telephony/consent_ledger.py |
| `RECORDING_RETENTION` | getenv | no | yes | app/telephony/consent_ledger.py |
| `RECORDING_RETENTION_DAYS` | getenv | no | no | app/telephony/consent_ledger.py |
| `REDIS_URL` | both | yes | no | app/api/admin_ops.py, app/api/system_health.py, app/billing/lead_usage.py |
| `REPLY_AGENT` | getenv | yes | yes | app/api/admin_ops.py |
| `REPLY_AUTO_SEND` | getenv | no | yes | app/platform/reply_agent.py |
| `REQUEST_GUARD` | getenv | yes | yes | app/middleware/__init__.py |
| `REQUEST_GUARD_SKIP` | getenv | no | no | app/middleware/__init__.py |
| `REQUEST_MAX_INFLIGHT` | getenv | yes | no | app/middleware/__init__.py |
| `REQUEST_TIMEOUT_S` | getenv | yes | no | app/middleware/__init__.py |
| `RERANKER_BACKEND` | getenv | no | no | app/ml/reranker.py |
| `RERANKER_MODEL` | getenv | no | no | app/ml/reranker.py |
| `RERANK_POOL_SIZE` | getenv | no | no | app/voice_agent/knowledge_base.py |
| `RERANK_VECTOR_WEIGHT` | getenv | no | no | app/ml/reranker.py |
| `RESEND_API_KEY` | settings | no | no | app/config.py |
| `RETENTION_DAYS` | getenv | no | no | app/platform/data_privacy.py |
| `REVENUE_DIGEST` | getenv | yes | yes | app/platform/revenue_digest.py |
| `REVENUE_TRENDS` | getenv | no | yes | app/api/admin_dashboard.py, app/platform/team_scheduler.py |
| `REVIEW_MONITOR` | getenv | yes | yes | app/marketing/review_monitor.py |
| `RISK_AUTO_APPROVE` | getenv | no | yes | app/agents/risk_approve.py |
| `RISK_AUTO_APPROVE_MAX_COST` | getenv | no | yes | app/agents/risk_approve.py |
| `RL_ENGINE` | getenv | yes | yes | app/agents/rl/reward.py |
| `RL_GRADUATION_N` | getenv | yes | yes | app/agents/rl/reward.py |
| `RL_SUCCESS_THRESHOLD` | getenv | yes | yes | app/agents/rl/reward.py |
| `ROUTE_HIT_COUNTER` | getenv | no | yes | app/api/control_center.py, app/middleware/__init__.py |
| `RUN_IN_PROCESS_SCHEDULER` | getenv | yes | yes | app/main.py, app/platform/dlq_retry.py, app/platform/team_scheduler.py |
| `SALES_ENGINE` | getenv | yes | yes | app/marketing/sales_pipeline.py |
| `SALES_TEAM` | getenv | yes | yes | app/agents/sales_team.py, app/api/growth.py |
| `SAMBANOVA_API_KEY` | settings | no | no | app/config.py |
| `SARVAM_API_KEY` | getenv | yes | no | app/api/web_call.py, app/voice_agent/indic_providers.py |
| `SCHEDULER_HYGIENE` | getenv | no | yes | app/platform/scheduled_ops.py |
| `SEARXNG_URL` | getenv | no | yes | app/integrations/searxng.py, app/platform/lead_harvester.py |
| `SECRET` | getenv | no | no | app/social_engine/vault.py |
| `SECRET_KEY` | both | yes | no | app/config.py, app/marketing/email_tracking.py, app/platform/email_unsub.py |
| `SECURITY_AGENT` | getenv | yes | yes | app/platform/team.py |
| `SELFIMPROVE_COST_CAP` | getenv | no | no | app/agents/self_improve.py |
| `SELF_HEALTH_URL` | getenv | no | no | app/platform/infra_handler.py |
| `SELF_IMPROVE_APPROVAL` | getenv | no | yes | app/agents/self_improve.py |
| `SELF_IMPROVE_GAP_S` | getenv | no | no | app/agents/self_improve.py |
| `SELF_IMPROVE_LOOP` | getenv | yes | yes | app/agents/growth_optimizer.py, app/agents/self_improve.py |
| `SELF_IMPROVE_MAX_PER_DAY` | getenv | no | no | app/agents/self_improve.py |
| `SEMANTIC_CACHE` | getenv | yes | yes | app/cache/semantic_cache.py |
| `SEMANTIC_CACHE_COLLECTION` | getenv | no | no | app/cache/semantic_cache.py |
| `SEMANTIC_CACHE_EMBED_TIMEOUT_S` | getenv | no | no | app/cache/semantic_cache.py |
| `SEMANTIC_CACHE_MIN_SIM` | getenv | no | no | app/cache/semantic_cache.py |
| `SEMANTIC_CACHE_STORE_TIMEOUT_S` | getenv | no | no | app/cache/semantic_cache.py |
| `SEMANTIC_CACHE_TTL_S` | getenv | no | no | app/cache/semantic_cache.py |
| `SENTRY_DSN` | both | yes | no | app/config.py, app/platform/trust_config.py |
| `SERVICE_REMINDERS` | - | yes | yes | - |
| `SESSION_MEMORY` | getenv | yes | yes | app/voice_agent/agent_memory.py |
| `SESSION_MEMORY_TTL` | getenv | yes | no | app/voice_agent/agent_memory.py |
| `SILERO_VAD_THRESHOLD` | getenv | no | no | app/voice_agent/turn_detector.py |
| `SIP_DID` | - | yes | no | - |
| `SIP_HOST` | - | yes | no | - |
| `SIP_PASSWORD` | - | yes | no | - |
| `SIP_PROVIDER` | - | yes | no | - |
| `SIP_USERNAME` | - | yes | no | - |
| `SITE_BASE` | getenv | no | no | app/telephony/call_manager.py, app/telephony/call_transfer.py, app/telephony/telephony_service.py |
| `SKILL_PACK` | getenv | yes | yes | app/platform/skill_pack.py |
| `SMART_TURN_MODEL_PATH` | getenv | no | no | app/voice_agent/turn_detector.py |
| `SMS_API_KEY` | getenv | no | no | app/integrations/sms_dlt.py |
| `SMS_DLT_ENABLED` | getenv | no | yes | app/integrations/sms_dlt.py |
| `SMS_DLT_TEMPLATE_ID` | getenv | no | no | app/integrations/sms_dlt.py |
| `SMS_PROVIDER_URL` | getenv | no | no | app/integrations/sms_dlt.py |
| `SMS_SENDER_ID` | getenv | no | no | app/integrations/sms_dlt.py |
| `SMTP_HOST` | settings | yes | no | app/config.py |
| `SMTP_PASSWORD` | both | yes | no | app/config.py, app/platform/reply_agent.py |
| `SMTP_PORT` | settings | yes | no | app/config.py |
| `SMTP_USER` | both | yes | no | app/config.py, app/platform/reply_agent.py |
| `SOCIAL_AUTOPOST` | settings | no | yes | app/config.py |
| `SOCIAL_ENGINE` | getenv | no | yes | app/marketing/auto_content.py, app/social_engine/engine.py |
| `SOCIAL_ENGINE_CONFIG` | getenv | no | no | app/api/growth_automation.py, app/social_engine/engine.py |
| `SOCIAL_TOKEN_KEY` | getenv | no | no | app/social_engine/vault.py |
| `SOFTNO_DEESCALATE` | getenv | no | no | app/voice_agent/intent_softno.py |
| `SOPS_AGE_KEY_FILE` | getenv | no | no | app/utils/secrets.py |
| `SOPS_CONFIG_FILE` | getenv | no | no | app/utils/secrets.py |
| `SOPS_ENC_FILE` | getenv | no | no | app/utils/secrets.py |
| `SRE_AGENT` | getenv | yes | yes | app/platform/team.py |
| `STALE_INQUIRY_NUDGE` | - | yes | yes | - |
| `STARTER_MONTHLY_PRICE` | settings | no | no | app/config.py |
| `STREAM_TTS_CLAUSE_MIN` | getenv | no | no | app/voice_agent/llm_stream_tts.py |
| `STRIPE_PUBLISHABLE_KEY` | settings | yes | no | app/config.py |
| `STRIPE_SECRET_KEY` | settings | yes | no | app/config.py |
| `STRIPE_WEBHOOK_SECRET` | settings | yes | no | app/config.py |
| `STRUCTURED_STRICT_MODEL` | getenv | no | no | app/llm/structured.py |
| `STT_BIAS` | getenv | no | no | app/voice_agent/niche_scripts.py |
| `STT_CORRECT` | getenv | no | no | app/voice_agent/hinglish_stt_fix.py |
| `STT_GEMINI_MODEL` | getenv | no | no | app/telephony/vobiz_stream.py |
| `STT_PROVIDER` | getenv | yes | no | app/api/web_call.py |
| `STUDIO_ENTITLEMENT_GATE` | getenv | no | yes | app/api/customer_marketing_studio.py |
| `SUPPORT_EMAIL` | settings | yes | no | app/config.py |
| `SUPPORT_PHONE_NUMBER` | settings | yes | no | app/config.py |
| `SUPPORT_WHATSAPP_NUMBER` | settings | yes | no | app/config.py |
| `SYS_HEALTH_DETAIL` | getenv | no | yes | app/api/system_health.py |
| `TEAM_AUTOMATION` | getenv | yes | yes | app/platform/team_scheduler.py |
| `TEAM_REPORT` | getenv | no | yes | app/platform/team_report.py |
| `TELEGRAM_BOT_TOKEN` | getenv | no | no | app/marketing/video_ad_cycle.py, app/social_engine/providers.py |
| `TELEPHONY_PROVIDER` | getenv | yes | no | app/api/admin_ops.py, app/main.py, app/utils/dnd_checker.py |
| `TELEPHONY_READY_ALERTS` | getenv | no | yes | app/telephony/telephony_readiness.py |
| `TIMEZONE` | settings | yes | no | app/config.py |
| `TOTP_CHALLENGE_KEY` | getenv | yes | yes | app/platform/customer_totp.py |
| `TRAINER_FEEDBACK` | getenv | no | no | app/voice_agent/telecaller_brain.py |
| `TRAJECTORY_LEARN` | getenv | no | yes | app/agents/trajectory.py |
| `TRIAL_CALLS_LIMIT` | settings | yes | no | app/config.py |
| `TRIAL_DURATION_DAYS` | settings | yes | no | app/config.py |
| `TTS_PROVIDER` | getenv | yes | no | app/api/web_call.py |
| `TURNSTILE_SECRET_KEY` | getenv | yes | yes | app/platform/engineer_agents.py, app/platform/trust_config.py, app/security/turnstile.py |
| `TURNSTILE_SITE_KEY` | getenv | yes | yes | app/platform/trust_config.py, app/security/turnstile.py |
| `TURNSTILE_STRICT_MISSING` | getenv | no | no | app/security/turnstile.py |
| `TURN_METRICS` | getenv | no | no | app/voice_agent/turn_metrics.py |
| `TURN_SILENCE_MS` | getenv | no | no | app/telephony/telephony_readiness.py |
| `TWILIO_ACCOUNT_SID` | settings | yes | no | app/config.py |
| `TWILIO_AUTH_TOKEN` | both | yes | no | app/api/webhooks.py, app/config.py, app/platform/engineer_agents.py |
| `TWILIO_PHONE_NUMBER` | settings | yes | no | app/config.py |
| `TWILIO_WEBHOOK_URL` | settings | yes | no | app/config.py |
| `UDYAM_PIPELINE` | getenv | no | yes | app/platform/udyam_pipeline.py |
| `UPI_AUTO_ACTIVATE` | getenv | no | yes | app/platform/upi_payments.py |
| `UPI_VERIFY_WA` | getenv | no | no | app/api/admin_ops.py, app/api/public_site.py, app/platform/upi_config.py |
| `UPI_VPA` | both | yes | no | app/api/admin_ops.py, app/config.py, app/platform/reply_agent.py |
| `USAGE_ALERTS` | getenv | yes | yes | app/billing/usage_alerts.py |
| `USE_AGENTIC_RAG` | getenv | yes | yes | app/marketing/chatbot.py, app/voice_agent/telecaller_brain.py |
| `USE_CONTEXTUAL_INGEST` | getenv | no | yes | app/platform/kb_refresh.py |
| `USE_CONTEXTUAL_INGEST_LLM` | - | no | yes | - |
| `USE_HYBRID_SEARCH` | - | no | yes | - |
| `USE_KOKORO_TTS` | getenv | no | no | app/voice_agent/kokoro_tts.py |
| `USE_LANGGRAPH_HIGH_STAKES` | - | no | yes | - |
| `USE_LANGGRAPH_SUPERVISOR` | - | no | yes | - |
| `USE_LIGHTRAG` | - | yes | yes | - |
| `USE_LLM_STREAM_TTS` | getenv | no | yes | app/voice_agent/llm_stream_tts.py |
| `USE_PROXY` | settings | yes | no | app/config.py |
| `USE_RERANKER` | - | no | yes | - |
| `USE_SILERO_VAD` | - | yes | yes | - |
| `USE_SMART_TURN` | - | yes | yes | - |
| `USE_SOPS` | getenv | no | no | app/utils/secrets.py |
| `USE_STRUCTURED_CONTENT` | getenv | yes | yes | app/marketing/post_generator.py |
| `USE_TEXT_ENDPOINT` | - | no | yes | - |
| `USE_THINKING_FILLER` | getenv | no | no | app/telephony/vobiz_stream.py |
| `VAPID_CLAIM_EMAIL` | getenv | no | no | app/platform/webpush.py |
| `VAPID_PRIVATE_KEY` | getenv | no | no | app/platform/webpush.py |
| `VAPID_PUBLIC_KEY` | getenv | no | no | app/platform/webpush.py |
| `VIDEO_AD_CYCLE` | getenv | no | yes | app/marketing/video_ad_cycle.py |
| `VIDEO_AD_INTERVAL_DAYS` | getenv | no | no | app/marketing/video_ad_cycle.py |
| `VIDEO_AD_MAX_PER_RUN` | getenv | no | no | app/marketing/video_ad_cycle.py |
| `VIDEO_AD_MAX_REVISIONS` | getenv | no | no | app/marketing/video_ad_cycle.py |
| `VOBIZ_AUDIO_TRACK` | getenv | no | no | app/telephony/vobiz_handler.py |
| `VOBIZ_AUTH_ID` | both | yes | no | app/api/admin_ops.py, app/config.py, app/utils/dnd_checker.py |
| `VOBIZ_AUTH_TOKEN` | both | yes | no | app/api/admin_ops.py, app/config.py, app/utils/dnd_checker.py |
| `VOBIZ_CALLER_ID` | both | yes | no | app/api/admin_ops.py, app/config.py, app/telephony/webhooks.py |
| `VOBIZ_CALL_RECORD` | getenv | no | no | app/api/admin_ops.py, app/telephony/vobiz_stream.py |
| `VOBIZ_COST_PAISE_PER_MIN` | getenv | no | no | app/telephony/post_call_hooks.py |
| `VOBIZ_SIP_PASS` | settings | no | no | app/config.py |
| `VOBIZ_SIP_REALM` | settings | no | no | app/config.py |
| `VOBIZ_SIP_USER` | settings | no | no | app/config.py |
| `VOBIZ_STT` | getenv | no | no | app/telephony/vobiz_stream.py |
| `VOBIZ_STT_WARMUP` | getenv | no | no | app/telephony/vobiz_stream.py |
| `VOBIZ_TRUNK_DOMAIN` | settings | yes | no | app/config.py |
| `VOBIZ_TRUNK_ID` | settings | yes | no | app/config.py |
| `VOBIZ_TTS_PITCH` | getenv | no | no | app/telephony/vobiz_stream.py |
| `VOBIZ_TTS_RATE` | getenv | no | no | app/telephony/vobiz_stream.py |
| `VOBIZ_TTS_VOLUME` | getenv | no | no | app/telephony/vobiz_stream.py |
| `VOICEMAIL_CLIENT_NAME` | getenv | no | no | app/telephony/webhooks.py |
| `VOICE_CAMPAIGN_VARIANTS` | getenv | no | yes | app/platform/voice_opening_variants.py |
| `VOICE_CLOSE_WHATSAPP` | getenv | no | yes | app/voice_agent/telecaller_brain.py |
| `VOICE_EVAL_AUTO` | getenv | no | yes | app/agents/self_improve.py, app/platform/team_scheduler.py |
| `VOICE_GEMINI_PRIMARY` | getenv | yes | yes | app/api/admin_ops.py, app/voice_agent/telecaller_brain.py |
| `VOICE_GUARDRAILS` | getenv | no | yes | app/voice_agent/telecaller_brain.py |
| `VOICE_LEARNED_INJECT` | getenv | no | no | app/voice_agent/voice_learned.py |
| `VOICE_LLM_MODEL` | getenv | no | no | app/voice_agent/telecaller_brain.py |
| `VOICE_LLM_RACE` | getenv | no | yes | app/voice_agent/telecaller_brain.py |
| `VOICE_RESPONSE_CACHE` | getenv | no | yes | app/voice_agent/telecaller_brain.py |
| `VOICE_SELFIMPROVE_EVERY` | getenv | no | no | app/telephony/vobiz_stream.py |
| `VOICE_SELF_IMPROVE` | getenv | no | no | app/voice_agent/voice_self_improve.py |
| `VOICE_TOOLS` | getenv | no | yes | app/voice_agent/voice_tools.py |
| `VOSK_MODEL_PATH` | getenv | no | no | app/telephony/vobiz_stream.py, app/voice_agent/free_stt.py |
| `WAHA_API_KEY` | both | yes | no | app/config.py, app/integrations/whatsapp_selfhost.py |
| `WAHA_BASE_URL` | both | yes | yes | app/config.py, app/integrations/whatsapp_selfhost.py |
| `WAHA_SESSION` | both | yes | no | app/config.py, app/integrations/whatsapp_selfhost.py |
| `WAHA_WEBHOOK_TOKEN` | both | yes | no | app/config.py, app/integrations/whatsapp_selfhost.py |
| `WARMUP_START_DATE` | getenv | no | no | app/platform/email_warmup.py |
| `WEBCALL_INLINE_SIGNUP` | getenv | no | no | app/api/web_call.py |
| `WEBCALL_LLM_WARMUP` | getenv | no | no | app/api/web_call.py |
| `WEBCALL_LOCAL_STT_TIMEOUT_S` | getenv | no | no | app/api/web_call.py |
| `WEBCALL_MAX_MSGS` | getenv | no | no | app/api/web_call.py |
| `WEBCALL_STT_LOCAL_FIRST` | getenv | no | yes | app/api/web_call.py |
| `WEBHOOK_MAX_RETRIES` | - | yes | no | - |
| `WEBHOOK_SECRET` | - | yes | no | - |
| `WEBHOOK_TIMEOUT_SECONDS` | - | yes | no | - |
| `WEBHOOK_URLS` | - | yes | no | - |
| `WEB_CALL_EDGE_TTS` | getenv | no | no | app/api/web_call.py |
| `WEB_TTS_RATE` | getenv | no | no | app/api/web_call.py |
| `WEEKLY_MARKETING_PACK` | getenv | no | yes | app/platform/scheduled_ops.py |
| `WHATSAPP_APP_SECRET` | both | no | no | app/config.py, app/integrations/whatsapp.py, app/platform/engineer_agents.py |
| `WHATSAPP_AUTO_SEND` | getenv | yes | yes | app/marketing/review_engine.py, app/marketing/whatsapp_campaign.py, app/telephony/telephony_readiness.py |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | settings | yes | no | app/config.py |
| `WHATSAPP_BUSINESS_NUMBER` | both | yes | no | app/config.py, app/integrations/whatsapp_selfhost.py |
| `WHATSAPP_BUSINESS_TOKEN` | settings | yes | no | app/config.py |
| `WHATSAPP_DAILY_CAP` | getenv | no | no | app/marketing/whatsapp_campaign.py |
| `WHATSAPP_ENFORCE_BUSINESS_NUMBER` | getenv | no | no | app/integrations/whatsapp_selfhost.py |
| `WHATSAPP_GRAPH_VERSION` | getenv | no | no | app/integrations/whatsapp.py |
| `WHATSAPP_LEAD_FLOW_ID` | getenv | no | yes | app/marketing/whatsapp_flows.py |
| `WHATSAPP_PHONE_NUMBER_ID` | settings | yes | no | app/config.py |
| `WHATSAPP_PROVIDER` | both | yes | yes | app/config.py, app/integrations/whatsapp_selfhost.py |
| `WHATSAPP_SEND_DELAY_S` | getenv | no | no | app/marketing/whatsapp_campaign.py |
| `WHATSAPP_VERIFY_TOKEN` | both | no | no | app/api/webhooks.py, app/api/whatsapp.py, app/config.py |
| `WHATSAPP_WELCOME` | getenv | no | yes | app/api/public_site.py |
| `WINBACK_ENGINE` | - | no | yes | - |
| `WORKING_HOURS_END` | settings | yes | no | app/config.py |
| `WORKING_HOURS_START` | settings | yes | no | app/config.py |
| `XAI_API_KEY` | settings | no | no | app/config.py |
| `ZOHO_CLIENT_ID` | settings | yes | no | app/config.py |
| `ZOHO_CLIENT_SECRET` | settings | yes | no | app/config.py |
| `ZOHO_DC` | getenv | yes | no | app/integrations/zoho_crm.py |
| `ZOHO_REFRESH_TOKEN` | settings | yes | no | app/config.py |

<!-- AUTO-ENV:END -->
