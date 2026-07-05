# Architecture Decision Records (append-only — NEVER edit past entries; supersede with a new one)

Schema per entry: `[DATE] [ID] Decision | Context | Alternatives rejected | Consequence`

[2026-05-XX] [ADR-000] Free AI stack only — no paid STT/TTS/LLM | User mandate: phone-call paisa khaata hai, margins pehle | Paid Deepgram/ElevenLabs/OpenAI (pyproject me stale pins reh gaye) | Multi-provider free chain in `app/voice_agent/free_ai.py` + circuit breakers; tuning FREE web-call pe, phone = final verify only.

[2026-06-10] [ADR-001] Durable Celery scheduler path on VPS | In-process scheduler web process ko block karta tha; restart pe jobs lost | Keep in-process (rollback fallback rakha `RUN_IN_PROCESS_SCHEDULER=1`) | `leadgen_worker` (conc=4) + `leadgen_scheduler` beat containers (`--profile celery`); web = HTTP-only (`WEB_CONCURRENCY=2`); DLQ → Redis `dlq:failed_tasks`.

[2026-06-11] [ADR-002] Product split: DO alag products (docs/ADR_2026_06_11_Product_Split_Pricing.md = ADR-009 wahan) | "Marketing + voice bundle" USP framing galat thi; user-clarified | Single bundled product | (1) AI Automated Marketing = MAIN (voice sirf Advanced-tier feature); (2) AI Voice Calling Agent = standalone, DLT-gated. `/compare` page dono dikhata.

[2026-06-12] [ADR-003] Voice pricing = FLAT monthly per niche-band (A ₹4,999 / B ₹9,999 / C ₹19,999, annual 10×) | Per-10-qualified-leads model = lead-counting disputes | Old vstarter/vgrowth/vpro per-lead system (REMOVED) | UNLIMITED AI calls per niche; `lead_usage.py` meter = UNLIMITED_QUOTA fail-open; 7 plan ids sync via `subscription._sync_voice_plans`; FREE pilot 7 din/50 calls.

[2026-06-18] [ADR-004] Razorpay REMOVED code-level → manual UPI primary + Stripe international | Razorpay onboarding blocked; koi India online gateway nahi | Waiting on gateway approval | Payments = `UPI_VPA` manual (ARMED 2026-06-20 via `app/platform/upi_config.py`, no-restart admin config); checkout Stripe-only, unconfigured = clean 503; DB `razorpay_*` columns dormant kept.

[2026-06-18] [ADR-005] Telephony provider = Vobiz; Exotel DELETED | Exotel path dead; Vobiz India-native SIP sasta (₹0.45/min) | Twilio India-domestic (ILLEGAL foreign trunk — intl-only fallback rakha) | `vobiz_handler.py` + WS `vobiz_stream.py` L16/16k; `/ws/exotel-voicebot` graceful-close stub.

[2026-06-18] [ADR-006] Cross-path parity RULE: har voice hook dono paths me | AUTO_QUALIFY call_manager me tha par vobiz_stream me nahi — silent gap | Single-path fixes | `scripts/cross_path_audit.py` guard in final_integration_check; lesson repeat 2026-07-03 (close-signals stream me missing) → "har reply() guard reply_stream_sentences() me mirror".

[2026-06-20] [ADR-007] Godfile split: 10 god-files → 22 modules | growth.py/marketing.py unmaintainable; duplicate-route risk | Big-bang rewrite (vobiz_stream deferred — voice-unsafe) | Routes ab `growth_revenue/growth_crm/growth_deliverability/growth_feature_flags` + `marketing_tools/marketing_models` me bhi; duplicate-route grep IN SAB me. Fallout: 37 latent NameErrors (see incidents).

[2026-06-22] [ADR-008] Telegram GLOBAL bot REMOVED | Ban-risk + global broadcast galat pattern | Keep gated | Per-client `social_engine.enqueue_publish()` (Telegram/Postiz/Meta per client) hi legal path; koi global auto-broadcast nahi.

[2026-06-23] [ADR-009] Obsidian Second Brain: agents → markdown staging → HOST-cron git push | Container me git/SSH nahi | In-container push | `data/obsidian_staging/` bind-mount; `scripts/obsidian_host_push.sh` crontab 20:45 UTC; Windows vault auto-pull.

[2026-06-25] [ADR-010] VOICE-scoped Gemini-primary + 9-key rotation pool | Free Mistral chain voice ke liye slow/quota-tight; Gemini 2.5-flash-lite fast | Global Gemini-primary (rejected — marketing/agents wapas Mistral) | `VOICE_GEMINI_PRIMARY=1` (voice only) + `data/voice_gemini_keys.json` runtime pool, 429 pe auto-advance; graceful fallback to free_ai chain.

[2026-06-26] [ADR-011] MCP surface gated 3-layer | `/mcp` prod me open tha | Open expose | (1) `/mcp` REFUSED without `FASTAPI_MCP_TOKEN`/`MCP_IP_ALLOWLIST` (2) `/api/mcp-product/v1/*` metered B2B (3) Arya MCP-engineer hourly health/rotation.

[2026-06-27] [ADR-012] Enterprise Claude method for every task | Ad-hoc edits se cross-path gaps aate the | Freeform | Loop = Discover → Contract → Execute → Self-review → Evidence; automation change me flag+idempotency+retry/DLQ+metrics+rollback+runbook+security+quota gate mandatory.

[2026-06-28] [ADR-013] Supabase as admin backend REJECTED (council) | Data already own Postgres; ek aur SaaS dependency | Supabase adoption | Read-only Admin DB Explorer on own Postgres (`ADMIN_DB_EXPLORER`, `/app/admin/db`).

[2026-06-29] [ADR-014] Voice self-host STT/TTS stack = Indic (IndicConformer + IndicWhisper + IndicF5/EdgeTTS + Silero) | Hinglish STT = dominant quality bug; fine-tune wrong first lever (data thin) | NVIDIA Parakeet/NeMo-Canary (NO Hindi) | Plan `docs/VOICE_SELFHOST_FINETUNE_PIPELINE.md`; ramp gated on call volume + DLT.

[2026-06-29] [ADR-015] RL flywheel Phase-0 = logging-only reward spine | Cold-start me bandit/OPE premature | Enabling half-baked engine | `RL_ENGINE` flag OFF; rewards → `rl_rewards.jsonl`; Thompson/contextual/OPE DEFERRED behind graduation gate.

[2026-07-02] [ADR-016] Offsite backup = rclone → Google Drive, host crons | VPS-only backups = single point of loss | Paid S3 (MinIO local hai par offsite nahi) | `RCLONE_REMOTE=gdrive:leadgen-backups`; DB dump 5.5M + data tar 47M (excludes ollama/u2net/backups); restore drill PROVEN 2026-07-02.

[2026-07-03] [ADR-017] Scheduler admin: per-job runtime ON/PAUSE + run-now, no-restart | Job control ke liye redeploy karna padta tha | Env-flag-only control | `data/scheduler_overrides.json` FAIL-OPEN; gate = `team_scheduler._run_job` choke-point (in-process + Celery dono); recovery endpoint Bearer `LEADGEN_SCHEDULER_SECRET` (unset = 503 fail-closed, abhi dormant).

[2026-07-03] [ADR-018] USE_SILERO_VAD=0 on VPS (phone path) | Silero 64ms rolling-window real speech ko silence bol raha tha — HAR call deaf | Fixing window-size live pe (deferred) | RMS-only VAD correct kaam karta; re-enable SIRF window-size fix + test ke baad.

[2026-07-05] [ADR-019] platform_dial (Swara self-sale cold-call batch) = HARD OFF, USER-MANDATE | Real Vobiz paisa burn; recordings me agent IVR/bots ko "interested" mark kar raha tha (7 unverified leads) | Ramp to 200/day (CANCELLED) | 3-layer kill: `.env PLATFORM_DIAL_DAILY=0` + `data/platform_dial.json enabled:false` + scheduler override paused. Re-enable needs: user go-ahead + test-allowlist (company numbers) + bot/IVR detection (min user-turns gate).

[2026-07-05] [ADR-020] CLAUDE.md → enterprise 9-section format + two-tier memory/ knowledge base | Flat working-memory dump onboarding ke liye opaque; token discipline vs completeness tension | Wholesale replace (facts kho jaate) | 9 sections + `## Current State` (≤40 lines) in CLAUDE.md; deep detail backfilled into memory/ (this system); AGENTS.md stays byte-copy.

[2026-07-05] [ADR-021] Customer-webhook event names = contract-pinned append-only registry | Stripe path `subscription.created/updated` emit karta tha jo `SUPPORTED_EVENTS` me the hi nahi — `fire_emit()` silently drop; UPI `payment.received` hamesha `amount_inr:None` (eklauta live revenue path) | Emit-side rename-only fix bina pin ke (agla galat naam phir chupchaap girta) | `subscription.updated` registry APPEND; checkout→`subscription.activated`, deleted→`subscription.cancelled`, portal-cancel ab emit karta; UPI real amount via `usage.plan_charge_inr()` (yearly=10×); AST contract-pin test har literal emit-name registry se lock. Saath shipped: ML pickle HMAC signing `app/ml/model_signing.py` (`MODEL_SIGNING_KEY`; mismatch=fail-CLOSED, absent=fail-OPEN — ADR-002 TODO closed); telephony qualify downstream dono paths shared `apply_qualified_downstream` (drift-guard test, POST_CALL_WHATSAPP kill-switch); `campaign_variant_id` end-to-end deal-stamp; conftest loop-repair fixture (asyncio.run file-order flake).
