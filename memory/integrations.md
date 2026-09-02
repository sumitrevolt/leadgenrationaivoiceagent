# Integrations — per external service (NO secret values — env var NAMES only)

Schema per entry: `Service — purpose | auth env var(s) | rate limits | observed failure modes | retry policy`

## LLM / AI providers (chain order in `app/voice_agent/free_ai.py`; all free tier)
- **Mistral** — LLM PRIMARY (`mistral-small-latest`, ~99% ok) | `MISTRAL_API_KEY` | free-tier RPM | occasional 429 | escalating circuit-breaker 60s→2x→30min cap, success resets.
- **Groq** — LLM fallback (`llama-3.1-8b-instant`) + **STT PRIMARY** (`whisper-large-v3`) | `GROQ_API_KEY` | TPD (tokens/day) — content-heavy days pe khatam | Hinglish STT mangling (dominant voice-quality bug → HINGLISH_STT correction layer) | breaker: "per day/TPD/limit reached" = straight 30min cooldown.
- **Cerebras** — free 120B fallback (`gpt-oss-120b`) | `CEREBRAS_API_KEY` | aggressive — **429-PRONE** | frequent quota bounce | breaker as above.
- **Gemini** — VOICE-scoped primary (`gemini-2.5-flash-lite` via `VOICE_GEMINI_PRIMARY=1`) + audio STT fallback; marketing chain me `gemini-2.0-flash-lite` deep | `GEMINI_API_KEY` + runtime 9-key pool `data/voice_gemini_keys.json` (admin "Voice Keys" page, no-restart) | free quota per key | quota exhaust mid-call | pool `advance_key` auto-rotate on 429, graceful fallback to free_ai chain.
- **NVIDIA NIM** — deep-tail LLM (`meta/llama-3.3-70b-instruct`) | `NVIDIA_API_KEY` (`NVIDIA_LLM_MODEL`, `NVIDIA_PRIMARY`) | 40 RPM + **~5k LIFETIME credits** | credit exhaust = soft-paid ceiling | kept deep in chain so credits only burn when all above are down; 402/out-of-credits = 30min breaker.
- **SambaNova / OpenRouter** — additional free fallbacks (OpenRouter deepseek/llama free ×keys) | `SAMBANOVA_API_KEY`, `OPENROUTER_API_KEY` | free-tier | — | breaker chain.
- **Ollama** — optional local floor/head (`OLLAMA_PRIMARY`) | none (local) | hardware-bound | slow on VPS | opt-in only.
- **EdgeTTS** — TTS (free, `hi-IN-SwaraNeural`) | none | none known | **needs `edge-tts>=7.2.0` else 403**; awaits must stay bounded (`_TTS_TIMEOUT_S`) | prosody knobs `PHONE_TTS_RATE`/`PHONE_TTS_PITCH`.
- **Pollinations** — AI image/video gen (`app/marketing/ai_image.py`) | `POLLINATIONS_API_KEY` (legacy `POLLINATIONS_TOKEN`) | free tier; 402 without key | KEY-SAFETY: `pk_` = client-safe URL embed; `sk_` = server-proxy only (`/api/marketing/ai-image-proxy` + disk cache `data/ai_images/`) | SVG posters = fallback.

## Telephony / messaging
- **Vobiz** — ACTIVE telephony provider (India SIP, ~₹0.45/min) | `VOBIZ_AUTH_ID`, `VOBIZ_AUTH_TOKEN`, `VOBIZ_CALLER_ID` | account balance | `get_balance()` API itself errors but `place_call()` works (2026-07-03 confirmed, 4 real calls) | webhooks `/api/webhooks/vobiz/answer|status`; WS stream token-auth.
- **Twilio** — INTERNATIONAL-ONLY fallback (India-domestic = illegal foreign trunk) | `TWILIO_*` | — | dormant-India risk audited | signature-verified webhooks, fail-closed in prod.
- **WhatsApp Meta Cloud** — official API sends | `WHATSAPP_*` creds | template approval required | bulk auto-send = number BAN | auto-send triple-gated (`WHATSAPP_AUTO_SEND=1` + creds + approved template) — OFF; default = 1-click human send.
- **WAHA (self-host)** — own WhatsApp engine on biz number, container `leadgen_waha` :3111 | session via QR scan (**user action pending**) | unofficial = ban-risk aware | routing via `get_whatsapp_sender()` | rollback `PROVIDER=cloud`.
- **Hostinger SMTP/IMAP** — outreach send + reply-triage read (admin@leadsgenai.in, smtp.hostinger.com:465) | `SMTP_*`/IMAP creds | self-capped 25/day + warmup ramp (`EMAIL_WARMUP=1`) | bounces → auto-pause | MX-verify pre-send (`OUTREACH_VERIFY_MX=1`); SPF/DKIM/DMARC all set.
- **ntfy (self-host)** — phone push alerts (https://ntfy.leadsgenai.in) | topic-based | — | — | ops_alerts fan-out with cooldowns.

## Data / prospecting
- **Google Maps Places (New)** — prospector real phones+reviews | `GOOGLE_MAPS_API_KEY` | self-cap `PROSPECT_MAX_LOOKUPS=60`/run (cost gate) | — | OSM Overpass = free fallback.
- **SearXNG (self-host)** — free websearch for lead harvester | none | self-hosted | — | part of `deploy/compose/docker-compose.tools.yml`.
- **data.gov.in** — public business datasets for harvester | API key (pending) | — | — | flag-gated OFF till key.
- **Zoho CRM (India DC) / HubSpot** — native CRM sync (`crm_sync.py`) | per-client or global creds | vendor quotas | — | `CRM_SYNC` flag OFF default.

## Payments / infra
- **UPI (manual)** — PRIMARY payment path | `UPI_VPA` (+ admin `POST /api/admin/upi/configure` no-restart) | n/a | — | `/api/public/pay-info` enabled:true; NOTIFY_EMAIL alerts.
- **Stripe** — international payments only | `STRIPE_*` | — | unconfigured → clean 503 (UPI fallback) | webhook signature verified.
- **Sentry** — error tracking (ARMED in prod) | `SENTRY_DSN` | sample 10% traces | — | FastAPI+Celery+Redis+SQLAlchemy integrations.
- **rclone → Google Drive** — offsite backups (LIVE; restore drill PROVEN 2026-07-02) | `/root/.config/rclone/rclone.conf` (chmod 600) + `RCLONE_REMOTE=gdrive:leadgen-backups` | free Drive space (data tar kept 47M via excludes) | — | host crons 02:30 pg_backup + 02:45 data tar.
- **GHCR** — Docker image registry | none — public package; CI build pushes via ephemeral `GITHUB_TOKEN`, VPS pulls anonymously by exact SHA (`GHCR_PAT` retired 2026-07-21) | — | — | CI build gated `DEPLOY_ENABLED` (unset = gate-only).
- **Qdrant (internal)** — RAG vector store 127.0.0.1:6333, single `kb_main` collection, namespaces | none (localhost) | — | embedder dim auto-detect (fastembed version-proof) | ML-asset rule: baked + off-loop + deadline.

## Wired-but-OFF (need only env keys)
- **PostHog** (`POSTHOG_API_KEY`) · **LiteLLM** (`LITELLM_MASTER_KEY`) · **Cloudflare tunnel** (`CLOUDFLARE_TUNNEL_TOKEN`) · **OTel** (`ENABLE_OTEL=1`) · **RequestGuard** (`REQUEST_GUARD=1`). Checklist: `docs/INFRA_UPGRADE_2026.md` Part 8.

## Collaboration / agent workspace (2026-08-03)
- **Block Buzz** � human+agent collaboration plane (Nostr relay) | Desktop local keys in OS credential store | hosted community `leadsgenai.communities.buzz.xyz` | harness `claude-agent-acp` via `buzz-acp` | Nest `~/.buzz` + repo `docs/integrations/BUZZ_ADMIN_PLANE.md` | NOT a STAFF/runtime plane; secrets never in channels.

## 2026-08-11 Google Search Console (rank tracking, FREE) ? ADR-177
- **Purpose:** Programmatic SEO observability — daily clicks/impressions/position snapshot. INERT default (GSC_ENABLED=0).
- **Creds:** service-account JSON; GSC_SERVICE_ACCOUNT_JSON env → fallback google_sheets_credentials (wahi file reuse, calendar_booking pattern).
- **Setup (pending):** GCP project → enable Search Console API → SA + key → Search Console property sc-domain:leadsgenai.in → DNS TXT verify → SA ko property pe FULL access → set GSC_ENABLED=1 + GSC_SERVICE_ACCOUNT_JSON. Runbook: memory/playbooks.md (add).
- **Code:** app/integrations/gsc.py (run_daily_async, never raises); beat staff-gsc-rank-daily 00:30 IST; admin GET /api/clientops/gsc/overview (latest + 30d trend); files data/gsc_daily.jsonl + data/gsc_state.json.
- **Gotcha:** Google libs (google-api-python-client) missing = graceful no-op, ImportError caught; sync API → asyncio.to_thread.
