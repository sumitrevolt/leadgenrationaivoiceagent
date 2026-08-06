# Activation Runbook — 2026-06-16
**Scope:** Turn on (a) the capabilities coded this session, and (b) the ₹0 credential quick-wins from the infra audit. Every item is flag/credential-gated and **OFF by default** — nothing changes until you act here.

> **Golden rules (your stack):** edit `/opt/leadgen/.env` on the VPS, then recreate only the app container. Validate on staging (`deploy/compose/docker-compose.staging.yml`) first for anything touching deps. Roll back = unset the env var + recreate.

**SSH:** `C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204`

**App recreate recipe (used below as `↻APP`):**
```bash
cd /opt/leadgen
docker compose -f docker-compose.vps.yml build app && \
docker compose -f docker-compose.vps.yml up -d --no-deps app
sleep 16 && curl -fsS http://127.0.0.1:8000/health | head
```
For pure `.env` flag flips (no code/dep change) you can skip `build` and just `up -d --no-deps app`.

---

## PART A — Capabilities coded this session

### A1. Semantic cache (code already in repo — only flag) · ₹0 · risk: low
The Qdrant→Redis cache **and** its Prometheus metrics already exist (`app/cache/semantic_cache.py`, `/metrics`). Just enable.
```
SEMANTIC_CACHE=1
# optional tuning:
SEMANTIC_CACHE_MIN_SIM=0.97
SEMANTIC_CACHE_TTL_S=21600
```
**Verify:** `curl -s http://127.0.0.1:8000/metrics | grep leadgen_semcache` → after some traffic, `leadgen_semcache_hit_rate` > 0.
**ROI:** rate-limit (Groq/Cerebras TPD) avoidance + latency on repeated prompts. **Rollback:** unset `SEMANTIC_CACHE`.

### A2. LLM tracing (NEW — dual sink) · ₹0 · risk: low–medium
`app/observability_llm.py` now feeds **two independent sinks**. Pick either or both.

**Path 1 — Langfuse Cloud (zero-risk, recommended first).** REST-based, protobuf-safe, no new dep, cloud free tier = zero VPS load.
```
ENABLE_LLM_OBS=1
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...        # secret — .env only
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
```
**Verify:** make a test call/chat → traces appear in Langfuse dashboard (provider/model/tokens/latency). **Rollback:** unset `ENABLE_LLM_OBS`.

**Path 2 — OTel → your Tempo (NEW; self-hosted, validate on staging).** LLM calls now emit `llm.<op>` spans (gen_ai.* attrs) into your existing Tempo/Grafana.
```
ENABLE_OTEL=1
OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317
```
Requires the otel libs in the image: `pip install -r requirements-otel.txt` as a Dockerfile layer, then `↻APP`.
> ⚠️ **Version-alignment caveat:** the lock has `opentelemetry-api==1.42.1` but `requirements-otel.txt` pins the 1.27.0 (protobuf-4-safe) line to protect your pinned `protobuf==4.25.9` (Gemini/Qdrant/fastembed). Keep api+sdk+exporter on the **same** line and **test on staging** before prod. If `setup_otel` can't init, it skips gracefully and the new LLM spans become a harmless no-op — your app is never affected.
**Verify:** Grafana → Tempo → search service `leadgen-app`, look for `llm.chat` spans. **Rollback:** unset `ENABLE_OTEL`.

### A3. Agent memory — cross-session lead recall (NEW) · ₹0 · risk: low
New `app/voice_agent/agent_memory.py` (native: your Qdrant + free LLM extraction). Brain hooks are inert until the flag is on.
```
AGENT_MEMORY=1
# optional:
AGENT_MEMORY_MIN_SIM=0.35
AGENT_MEMORY_RECALL_LIMIT=4
AGENT_MEMORY_MAX_FACTS=4
# optional real-mem0 backend (only if you later `pip install mem0ai`; else native):
# MEM0_BACKEND=mem0
```
**Per-lead memory:** the brain defaults the memory subject to `client_id`. For true per-lead recall, have the call session call `brain.set_memory_subject(lead_id_or_phone)` after creating the brain (one line; safe no-op when flag off).
**Verify:** `curl -s http://127.0.0.1:8000/metrics | grep leadgen_agent_memory` → `..._events_total{kind="stored"}` rises after calls, `..._recall_rate` > 0 on repeat leads. **QA:** run `scripts/agent_tester.py` after enabling (voice-path change). **Rollback:** unset `AGENT_MEMORY` (Qdrant `agent_memory` collection can stay; harmless).

### A4. DeepEval RAG eval-gate (NEW — advisory CI) · ₹0 · risk: none (CI-only)
`evals/test_rag_quality.py` + `evals/deepeval_judge.py` + a `deepeval` job in `.github/workflows/llm-eval.yml`. Runs on PRs touching `evals/**`, `app/voice_agent/**`, `app/llm/**`. Uses your **free** Cerebras key as judge; advisory (never blocks build yet).
**Enable:** ensure GitHub repo secret `CEREBRAS_API_KEY` is set (promptfoo already uses it). Nothing else.
**Local run:** `pip install -r requirements-dev.txt && CEREBRAS_API_KEY=... pytest evals/test_rag_quality.py -q`
**Make it a hard gate (later, when trusted):** remove `continue-on-error: true` from the `deepeval` job.
**Verify:** open a PR editing `evals/**` → "deepeval RAG quality (advisory)" check runs; download the `deepeval-results` artifact.

---

## PART B — Credential quick-wins (audit Section F)

### B1. Cloudflare Tunnel + Turnstile · ₹0 · risk: low · **highest ROI**
Already wired in `deploy/compose/docker-compose.edge.yml` (profile `edge`). Hides origin IP, adds free WAF/DDoS; Turnstile blocks bot form-spam on lead magnets.
1. Cloudflare dashboard → add `leadsgenai.in` → Zero Trust → Tunnels → create tunnel → copy token.
2. VPS `.env`: `CLOUDFLARE_TUNNEL_TOKEN=eyJ...`
3. Start: `docker compose -f deploy/compose/docker-compose.edge.yml --profile edge up -d` (outbound only — no new port opens).
4. Point the tunnel's public hostname → `http://127.0.0.1:8000` (your Caddy/app), move DNS to Cloudflare (proxied/orange-cloud).
5. **Turnstile:** create a widget, add the site-key to `/audit`, `/site-audit`, `/demo`, `/start` forms + verify the token server-side on submit.
**Verify:** `curl -I https://leadsgenai.in` shows `server: cloudflare`; origin IP no longer resolvable publicly. **Rollback:** `--profile edge down` + revert DNS.

### B2. Sentry error tracking · ₹0 · risk: none
`sentry-sdk==1.39.2` is already in the lock — just set the DSN.
```
SENTRY_DSN=https://...@oXXXX.ingest.sentry.io/XXXX
ENVIRONMENT=production
```
`↻APP`. **Verify:** trigger a harmless test exception (or check the Sentry "Issues" stream for the next real error). **Rollback:** unset `SENTRY_DSN`.

### B3. PostHog product analytics · ₹0 · risk: none
`app/analytics/posthog_client.py` is **REST-based** (no SDK dep needed) — just keys. Use **PostHog Cloud** (never self-host — ClickHouse would kill the VPS).
```
POSTHOG_API_KEY=phc_...
POSTHOG_HOST=https://us.i.posthog.com   # or eu.i.posthog.com
```
`↻APP`. **Verify:** PostHog → Activity → live events appear on the next site visit. **Rollback:** unset `POSTHOG_API_KEY`.

### B4. Razorpay LIVE keys + webhook · ₹0 · risk: medium · **revenue-blocking**
Current `.env` has placeholder keys — payments are dead until real `rzp_live_` keys are set (proven root cause; not a code bug).
```
RAZORPAY_KEY_ID=rzp_live_xxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxx           # secret — .env only
RAZORPAY_WEBHOOK_SECRET=xxxxxxxx       # secret — .env only
```
1. `↻APP`.
2. Razorpay dashboard → Webhooks → add `https://leadsgenai.in/api/billing/webhooks/razorpay`, set the same secret, subscribe to payment/subscription events.
3. **Test:** do a ₹1 live checkout end-to-end; confirm the webhook is received + invoice generated.
**Verify:** `/api/billing/...` checkout returns a real order; webhook log shows delivery. **Rollback:** revert to test keys (checkout disabled).

---

## Recommended activation order (lowest risk → highest value)
1. **B1 Cloudflare** + **B2 Sentry** + **B3 PostHog** (₹0, minutes, no code) → protection + visibility.
2. **A1 semantic cache** + **A4 DeepEval** (₹0, flags/secret only) → resilience + AI safety net.
3. **A2 LLM tracing (Langfuse cloud first)** → see your AI layer.
4. **B4 Razorpay live** → unblock revenue (do before first paid customer).
5. **A3 agent memory** → product depth (QA on web-call path first).
6. **A2 Path 2 OTel→Tempo** → only after staging validation of otel versions.

## One-shot verification after enabling
```bash
curl -s http://127.0.0.1:8000/metrics | grep -E "semcache|agent_memory|llm_provider"
curl -fsS http://127.0.0.1:8000/health | head
curl -s http://127.0.0.1:8000/api/growth/infra/flags | python3 -m json.tool | grep -iE "SEMANTIC_CACHE|AGENT_MEMORY|ENABLE_OTEL"
```
