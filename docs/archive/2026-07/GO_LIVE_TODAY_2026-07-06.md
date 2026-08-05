# Go-Live Runbook — Product-1 delivery + audit fixes (2026-07-06)

> Everything below is **code-complete + verified locally** but **UNCOMMITTED / UNDEPLOYED** (§8).
> This is the exact sequence to make it live for the paying customer (jiya makeover) TODAY.
> Each step is YOUR action — Claude cannot deploy (§8), touch prod `.env` (§5), or scan a WhatsApp QR.

---

## What was shipped this session (all local-verified: tests + prod_check + secrets)

**Product-1 delivery (the "not delivering" fix):**
- **Day-1 seed** — new customer now gets website→KB seed + first content pack + content queue **immediately** on signup/onboard (worker Celery task `onboard_client`), default-ON (`SIGNUP_AUTO_ONBOARD`), idempotent.
- **Hands-free drafts now reach the customer** — `GET /api/customer/autopilot` + a "🤖 Aapki AI team ne ye taiyaar kiya" card in `customer_marketing.html` (browser-verified). Draft-only, 1-click WhatsApp/Copy.

**Enterprise AI audit + security (report: `docs/archive/2026-07/ENTERPRISE_AI_AUDIT_2026-07-06.md`):**
- KB integrity: no silent all-tenant wipe · dedup · delete-before-reseed.
- Voice: 2nd-order prompt-injection sanitize (5 sites).
- Infra: `mem_limit` on 7 observability containers.
- Security sweep: `/api/platform/health` + `/api/v1/status` gated (were anon leaks) · `/api/activation/summary` recon-trim · booking-cancel possession-factor · browser-tools SSRF guard.

---

## STEP 0 — Commit surgically (a parallel session is editing the same tree)

There are **two independent work-streams** uncommitted. Do NOT `git add -A`.

- **This session's files:** `app/voice_agent/knowledge_base.py`, `app/voice_agent/telecaller_brain.py`, `app/marketing/onboarding.py`, `app/api/{public_site,customer_onboard,customer_dashboard,activation,platform,health,booking}.py`, `app/integrations/calendar_booking.py`, `app/agents/browser_tools.py`, `app/platform/customer_autopilot.py`, `app/tasks/staff_jobs.py`, `docker-compose.observability.yml`, `frontend/customer_marketing.html`, `docs/API.md`, `docs/archive/2026-07/ENTERPRISE_AI_AUDIT_2026-07-06.md`, and `tests/test_{kb_point_id,kb_delete_before_reseed,prompt_content_sanitize,booking_cancel_ownership,browser_tools_ssrf,onboard_day1_delivery,customer_autopilot_surface}.py` + `tests/security/test_rbac.py`.
- **Parallel session (W1.x scheduler/outreach — review separately):** `app/platform/team_scheduler.py`, `app/agents/self_improve.py`, `app/platform/auto_outreach.py`, `tests/test_scheduler_*.py`, `tests/test_self_improve_failclosed.py`, `tests/test_outreach_*.py`.
- **Shared:** `progress.md` (both appended — keep both).

`git status` + `git diff <file>` before staging each.

## STEP 1 — Voice gate (mandatory before `telecaller_brain.py` ships)

```
python -m app.voice_agent.eval_suite      # expect ~100% pass
python scripts/agent_tester.py            # no double/empty/repeat regression
```
Regression is unlikely (clean KB content is byte-identical through the new sanitizer) but this is the voice path's bar. If either fails, hold `telecaller_brain.py` out of the deploy.

## STEP 2 — Deploy (leadgen-ops runbook, CLAUDE.md §3)

Windows push → SSH → `cd /opt/leadgen && git pull && docker compose -f docker-compose.vps.yml build app && docker compose -f docker-compose.vps.yml up -d --no-deps app` → verify `/health` = `environment:production` (sleep 16 + 2× check). Recreate `worker`/`scheduler` too so the new `onboard_client` task registers.
Observability caps deploy separately: `docker compose -f docker-compose.observability.yml up -d`.

## STEP 3 — Enable the draft-safe delivery flags (prod `.env`, then recreate app+worker)

```
OWNER_BRIEF_DAILY=1
NPS_AUTO=1
STALE_INQUIRY_NUDGE=1
EVERGREEN_RECYCLE=1
AUTO_DELIVER_VALUE=1      # only meaningful once WhatsApp is armed (Step 4)
```
These are draft-only / ban-safe. Left OFF-by-default in code deliberately (inert-by-default convention; daily-LLM-gen for all clients is your cost/business call). Once ON + a day of generation, the `/api/customer/autopilot` card fills.
(`SIGNUP_AUTO_ONBOARD` is already default-ON — new signups get day-1 seed with no action.)

## STEP 4 — Arm ONE transactional WhatsApp channel

Scan the WAHA QR (own stack) OR complete Meta Cloud approval. This one chokepoint silently no-ops value-delivery + welcome + hot-lead owner alerts. **Bulk auto-send stays OFF** (ban-safety) — this is only for consented/transactional sends to your own customer.

## STEP 5 — One-time prod data ops

- **KB purge/reseed** (so the KB dedup/delete-before-reseed benefit lands on existing points, which carry old random ids): re-run onboarding/website-reseed for existing clients, or purge+reseed jiya's `client:<id>` namespace.
- **`METRICS_TOKEN`** (closes the `/metrics` + `/health/deep` business-count leak): set it in `.env` AND add the same value as `bearer_token` in `monitoring/prometheus.yml`'s `leadgen_app` scrape job.

## STEP 6 — Verify delivery (smoke)

- Sign up a throwaway business at `/start` → within a few min its dashboard `/creatives` shows seeded content (day-1 seed working).
- Log in as jiya → home dashboard → the "🤖 Aapki AI team ne ye taiyaar kiya" card appears once drafts exist.
- `curl /api/customer/autopilot` with jiya's JWT → returns her drafts (401 anon = gated ✓).

---

## Product-2 (Voice) — also shipped this session

- **Transcripts + AI summary + per-call qualification now reach the paying voice customer** (`CallRow` + `_build_from_db` + a "📝 AI report" expander in `customer_voice.html`). This was a **direct false claim** before ("sab call transcripts + AI summary aapke dashboard me" reached no customer surface — data was CallLog-only / admin-only). Deploys with the app; visible once real `CallLog` rows exist for the client.
- **Autopilot "AI team ne ye taiyaar kiya" card is now on all 3 dashboard forks** (marketing/voice/combo).

## Vobiz-WS cost-burn — fix shipped, GATED OFF (enable after a live test)

The HMAC token gate is in (`app/telephony/stream_token.py` + `telephony_vobiz.py`), **inert by default**. To arm (sequenced — do NOT flip both at once):
1. `VOBIZ_STREAM_SECRET=<random>` in prod `.env` + recreate app → confirm a fresh outbound `stream_token` carries a `.exp.sig` suffix.
2. Run a live **outbound** test call AND a live **inbound** test call (low-traffic; jiya is live). The inbound test is the real gate — it proves no inbound DID path reaches the WS with a token we never minted.
3. Only then `VOBIZ_STREAM_REQUIRE_TOKEN=1`. Rollback = unset either flag.

## Product-2 self-serve calling — SHIPPED, gated OFF (enable after a live test)

The customer can now **see** their calling status (read-only `GET /api/customer/voice/queue-status`) and **trigger** it (`POST /api/customer/voice/call-queue`) via the "📞 AI se apne leads ko call karwao" card. Every call routes through `queue_call` (DND fail-closed / 9am-7pm / DLT / minutes / quota) — bypasses nothing, forces `client_id` from JWT (IDOR-safe), never re-dials a called lead. Gated **`CUSTOMER_VOICE_SELFSERVE`** (default OFF). Arm with `CUSTOMER_VOICE_SELFSERVE=1` **only after a live outbound test call**. Rollback = unset the flag.

## Still needs a dedicated pass (NOT blocking go-live)

- **Product-2 recording AUDIO stream** to the customer (text transcript/summary is shipped; the WAV is DPDP-sensitive and `recording_url` is a *provider URL* → serving = SSRF-proxy, and the local-WAV `CallLog`↔`stream_sid` mapping is unverified. Deferred deliberately — needs a client-scoped route with a verified mapping).

## The honest promise to put on the marketing page

Not "everything automated, you do nothing." The true, deliverable promise is:
**"Done-for-you day-1 setup + 86 on-demand AI marketing tools + daily content drafts + your AI team's hands-free drafts in the portal — 1-click to send."**

---

## PRODUCTION-READY SESSION UPDATE (2026-07-06 continuation)

### Changes shipped this session (all UNCOMMITTED — commit + deploy as per §8):

**1. Gemini SDK migration (telecaller_brain.py)**
- Migrated from deprecated `google.generativeai` → new `google.genai` SDK (matching `llm_brain.py` pattern).
- `GenerativeModel.generate_content_async()` → `client.aio.models.generate_content()` with `GenerateContentConfig`.
- Key rotation: fresh `Client(api_key=key)` per retry attempt (new SDK pattern).
- FutureWarning eliminated. `google.generativeai` no longer imported at module level.
- Tests: `test_call_learning_2026_07_06.py` 34 + `test_prompt_content_sanitize.py` 6 = 40 green.

**2. `.env.example` production flags added**
- New voice quality flags: `IVR_HANGUP`, `NOINPUT_POLICY`, `ACK_TRIAL_CLOSE`, `PHONE_TYPE_GATE`, `CALL_FEEDBACK_LOOP`, `VOBIZ_STREAM_SECRET`, `VOBIZ_STREAM_REQUIRE_TOKEN`.
- New observability flags: `PROMETHEUS_JOB_METRICS`, `DIGEST_NTFY`, `DIGEST_LLM`, `WARM_SLA_NUDGE`, `QA_REAL_TRANSCRIPTS`.
- New delivery flags: `SIGNUP_AUTO_ONBOARD`, `CUSTOMER_VOICE_SELFSERVE`, `AUTO_DELIVER_VALUE`.
- `test_env_example_free_stack.py` still passes.

### STEP 7 — Caddy: block `/metrics` + `/health/deep` from external access

These endpoints currently return **200 to anonymous external requests** (business counts, Celery/Redis/LLM stats leak). Two paths to fix:

**Path A — METRICS_TOKEN (recommended, no Caddy change):**
```bash
# 1. Add to /opt/leadgen/.env:
METRICS_TOKEN=<generate: python -c "import secrets; print(secrets.token_urlsafe(32))">

# 2. Add bearer_token_file support to monitoring/prometheus.yml (or use Path B
#    so Prometheus scrapes internally without auth — simpler):
#    If METRICS_TOKEN is set, Prometheus internal scrape will start 401-ing.
#    Fix: set bearer_token_file in prometheus.yml pointing to a secrets file,
#    OR keep Prometheus scraping via internal Docker network + Caddy blocks external.

# 3. Recreate app container:
docker compose -f docker-compose.vps.yml up -d --no-deps app
```

**Path B — Caddy reverse-proxy block (external only, internal Prometheus unaffected):**
```bash
# SSH to VPS, then:
cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak-$(date +%Y%m%d_%H%M%S)

# Add these respond blocks INSIDE the leadsgenai.in site block, BEFORE the reverse_proxy:
# respond /metrics 403
# respond /health/deep 403

# Then validate + reload:
caddy validate --config /etc/caddy/Caddyfile && caddy reload --config /etc/caddy/Caddyfile

# Verify:
curl -s -o /dev/null -w "%{http_code}" https://leadsgenai.in/metrics     # expect 403
curl -s -o /dev/null -w "%{http_code}" https://leadsgenai.in/health/deep # expect 403
# Internal Prometheus scrape (container-to-container, bypasses Caddy) = unaffected.
```

### STEP 8 — Prod .env flags to set NOW (all new, safe defaults already in code)

```bash
# Voice quality (arm immediately — these are already default-ON in code, confirm in .env):
NOINPUT_POLICY=1           # 0-turn dead-air → reprompt → graceful close
IVR_HANGUP=1               # IVR/voicemail strike → hangup (saves Vobiz paisa)
PHONE_TYPE_GATE=1          # fixed-line/IVR/toll-free dial = BLOCK
CALL_FEEDBACK_LOOP=1       # IVR call → auto-blocklist learning

# Observability (founder visibility — low risk):
PROMETHEUS_JOB_METRICS=1   # /metrics: per-job success/fail/duration (Grafana)
DIGEST_NTFY=1              # daily digest → phone ntfy push
OPS_ALERTS=1               # staff-job crash → phone ntfy alert (NTFY_URL needed)

# Delivery (arm after WhatsApp armed):
# AUTO_DELIVER_VALUE=1     # hands-free draft → WhatsApp send (AFTER WAHA QR)
```

### STEP 9 — VPS one-time data ops (after deploy)

```bash
# SSH into app container:
docker exec -it leadgen_app bash

# 1. Backfill phone types on existing prospects (ADR-027):
python scripts/backfill_phone_type.py --apply

# 2. Purge junk prospects from home_loans niche (ADR-022):
python scripts/purge_junk_prospects.py --niche home_loans --apply

# 3. Verify counts:
python -c "from app.platform.prospector import _count_by_status; print(_count_by_status())"
```
