---
name: automation-flags
description: The gated env-flag catalog for LeadGen AI automation engines — what each flag does, ban/cost risk, and the safe enable→verify procedure. Use when the user says "flag on/off karo", "enable automation", mentions JOURNEY_ENGINE / CADENCE_ENGINE / SALES_ENGINE / NICHE_ROTATION / AUTO_ONBOARD, "kaunsa flag safe hai", or before flipping any automation switch.
---

# Automation Flags (additive · safe-to-flip)

Har engine ek env-flag pe gated. Set in `.env` (VPS `/opt/leadgen/.env`, gitignored) → **container recreate** (`docker compose -f docker-compose.vps.yml up -d --no-deps app`, NOT sirf `restart` — env_file reload ke liye recreate chahiye) → verify.

**Live registry = `GET /api/growth/infra/flags`** (single source of truth, on/off/unset dikhata). Master list = `AUTOMATION_FLAGS` in `app/api/growth.py` — ab **~100+ flags** (engines + new F–M capabilities + URL-valued integrations). Naya flag wahaan add karo warna flags-endpoint pe nahi dikhega.

⚠️ Default OFF nahi hai sab — **kayi engines ON-by-default** (env unset = ON ya code-default ON): `LEAD_HARVESTER`, `REPLY_AGENT`, `CADENCE_ENGINE`, `SALES_ENGINE`, `SALES_TEAM`, `SELF_IMPROVE_LOOP`, `GROWTH_OPTIMIZER`, `CHANNEL_EXPERIMENTS`, `AUTO_ONBOARD`, `NICHE_ROTATION`, `SKILL_PACK`, `CODE_UPGRADER`, `AUTO_EMAIL_OUTREACH`, `USE_AGENTIC_RAG`, `USE_STRUCTURED_CONTENT`. Har engine ka exact default code me check karo, assume mat karo.

## Safe to enable (free, ban-safe)
| Flag | Engine | Notes |
|---|---|---|
| `NICHE_ROTATION=1` | all-39-builtin-niche scrape rotation | warna 4-niche |
| `AUTO_EMAIL_OUTREACH=true` | Rohan daily cold-email | cap 25/day, MX-verified, SPF/DKIM/DMARC set |
| `REPLY_AGENT=1` | inbox reply triage (draft-only) | IMAP creds reuse SMTP |
| `JOURNEY_ENGINE=1` | event→rule→action drafts | inquiry/signup triggers |
| `AUTO_QUALIFY_CALLS=1` | post-call AI qualifier | latency-safe (post-call) |
| `CADENCE_ENGINE=1` | omnichannel cadence advance | drafts; channel-gate pe hi send |
| `SALES_ENGINE=1` | deal pipeline next-actions | drafts/links |
| `OPS_WATCHDOG=1` | hourly health + email-alert | needs `NOTIFY_EMAIL` |
| `AUTO_ONBOARD=1` | paid-client done-for-you setup | website→KB + content pack |

## RISKY — bina readiness flip MAT karo
| Flag | Risk |
|---|---|
| `WHATSAPP_AUTO_SEND=1` | number BAN — sirf official Cloud API + approved template + opt-in |
| `MISSED_CALL_CALLBACK=1` | Vobiz DID + inbound webhook chahiye |
| `SMS_DLT_ENABLED=1` | DLT templates + BSP creds (MSG91/AiSensy/Fast2SMS) |
| cold-calling | DLT (₹10L TRAI penalty) — Udyam pending |

## New F–M capabilities (2026-06-16, all OFF default = INERT, fail-safe)
| Flag | What it arms |
|---|---|
| `EVAL_GATE` / `EVAL_GATE_HARD` | eval_gate reward signal: records per-action baseline + regression decision (observe-only until HARD set; wired into self_improve loop + DeepEval CI) |
| `AGENT_MEMORY` | cross-session per-lead/client recall (Qdrant `agent_memory` ns + free LLM, off-loop) + DPDP purge. Tune: `AGENT_MEMORY_MIN_SIM`/`_RECALL_LIMIT`/`_MAX_FACTS` |
| `SRE_AGENT` / `FINOPS_AGENT` / `SECURITY_AGENT` | engineer agents Pranav (SRE, hourly :45) / Vidya (FinOps, 9am) / Arnav (Security DPDP/TRAI, 9:30) |
| `OPS_ALERTS` | ntfy fan-out (engineer-score / eval-reject-burst / dead-letter / readiness-digest). Needs `NTFY_URL`+`NTFY_TOPIC`. Thresholds: `OPS_ALERT_*` |
| `CUSTOMER_WEBHOOKS` | customer-facing Svix-style HMAC-SHA256 webhook fan-out + UI in /app/customer |
| `MCP_PRODUCT` | arms `/api/mcp-product/v1/*` metered surface (503 when off) + A2A Agent Card `/.well-known/agent.json` |
| `FEATURE_FLAGS` | master gate for per-tenant runtime feature-flag system (Redis-backed) |
| `LITELLM_COSTS` | per-tenant LLM spend attribution + warm-DR replica probe (needs `LITELLM_MASTER_KEY`+`LITELLM_GATEWAY_URL`) |
| `REQUEST_GUARD` / `PLAN_RATE_LIMIT` | per-request timeout + load-shed · tier-based API rpm caps |
| `TURNSTILE_SITE_KEY`/`_SECRET_KEY` | Cloudflare Turnstile bot-check on /audit /site-audit /demo /inquiry |

## Procedure
1. **Backup**: `cp .env .env.bak_$(date +%s)`.
2. `.env` me flag add (base64-over-ssh se — secret kabhi plain argv pe nahi).
3. `docker compose -f docker-compose.vps.yml up -d --no-deps app` (recreate = env reload). Worker/scheduler ko flag chahiye to unhe bhi recreate.
4. `docker exec leadgen_app printenv <FLAG>` → confirm value.
5. Smoke: manual API trigger ya next scheduled run → `data/*.jsonl` output.
6. Rollback: `.env.bak_*` restore + recreate.

## Verify
`GET /api/growth/infra/flags` (live on/off/unset) ya `python scripts/setup_status.py` (flags + readiness). USER-PENDING env (Claude fabricate nahi kar sakta): `UPI_VPA` (manual UPI payments), `POLLINATIONS_API_KEY`, Vobiz DID/recharge + DLT, R2/B2 offsite creds.

## Enterprise gate

- **Operating loop**: Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). Discover = flag ka **exact code-default** padho (upar warning: kayi ON-by-default), assume mat karo; live state `GET /api/growth/infra/flags`.
- **Risk-tier varies by flag** — flip se pehle classify:
  - **Standard** (free + draft-only / ban-safe): `NICHE_ROTATION`, `REPLY_AGENT`, `JOURNEY_ENGINE`, `CADENCE_ENGINE`, `SALES_ENGINE`, `EVAL_GATE`, `AGENT_MEMORY` — Procedure (upar) + smoke = enough.
  - **High-risk** (outbound spend / ban / compliance): `AUTO_EMAIL_OUTREACH` (deliverability), `WHATSAPP_AUTO_SEND` / `SMS_DLT_ENABLED` / `MISSED_CALL_CALLBACK` / cold-calling (BAN / DLT ₹10L). Pehle readiness probe (`scripts/setup_status.py` / `/api/activation/readiness`) + compliance pre-reqs (DLT templates · opt-in · DND scrub · 9am–7pm) **fail-CLOSED** — bina ready KABHI flip nahi.
- **Secrets**: URL/key-valued flags (`NTFY_URL`, `LITELLM_*`, `TURNSTILE_*_SECRET_KEY`) sirf `.env` (gitignored) + base64-over-ssh — plain argv / committed file / CLAUDE.md me KABHI nahi (`scripts/check_secrets.py`).
- **Rollback (NAMED)** — already in Procedure step 6: `.env.bak_*` restore + `docker compose -f docker-compose.vps.yml up -d --no-deps app` (worker/scheduler bhi agar unko flag chahiye). Worst case `TEAM_AUTOMATION=0` = scheduler stop.
- **Evidence (flip done)**: `docker exec leadgen_app printenv <FLAG>` (value confirm) + `GET /api/growth/infra/flags` desired state + real `data/*.jsonl` output ya engine-event post-trigger.
