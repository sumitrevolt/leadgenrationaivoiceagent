# Activation Runbook — F + G + H + I + J Tracks (2026-06-16)

> Everything shipped this session is **flag-gated INERT** by default. This is
> the single ordered checklist for switching on each capability — `.env` keys,
> verify steps, rollback. Follow top-down; later items depend on earlier ones.
>
> SSH: `C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204`
>
> Recreate after `.env` edit (used as `↻APP` below):
> ```bash
> cd /opt/leadgen
> docker compose -f docker-compose.vps.yml up -d --no-deps app
> sleep 14 && curl -fsS http://127.0.0.1:8000/health | head
> ```

---

## Phase 1 — Survival (do first, ₹0 cost, ~30 min)

### 1.1 Razorpay live keys + webhook (revenue gate)
```
RAZORPAY_KEY_ID=rzp_live_xxxxxxxx
RAZORPAY_KEY_SECRET=<live secret — .env only>
RAZORPAY_WEBHOOK_SECRET=<webhook signing secret>
```
1. `↻APP`.
2. Razorpay dashboard → Webhooks → add `https://leadsgenai.in/api/billing/webhooks/razorpay`
3. Test with ₹1 checkout end-to-end.
4. **Verify:** `curl -s http://127.0.0.1:8000/api/activation/readiness` → `razorpay` item `status: OK`.

### 1.2 Sentry error tracking
```
SENTRY_DSN=https://...@oXXXX.ingest.sentry.io/XXXX
ENVIRONMENT=production
```
`↻APP`. **Verify:** trigger a test exception → check Sentry Issues stream.

### 1.3 PostHog product analytics (cloud free tier — never self-host)
```
POSTHOG_API_KEY=phc_...
POSTHOG_HOST=https://us.i.posthog.com   # or eu.i.posthog.com
```
`↻APP`. **Verify:** PostHog → Activity → live events on next site visit.

### 1.4 Cloudflare Tunnel + Turnstile (origin-hide + bot-block on lead-magnets)
```
CLOUDFLARE_TUNNEL_TOKEN=eyJ...
TURNSTILE_SITE_KEY=0x4AAA...
TURNSTILE_SECRET_KEY=0x4AAA...   # .env only
```
1. Cloudflare → Zero Trust → Tunnels → create → copy token.
2. Cloudflare → Turnstile → create widget → copy both keys.
3. `docker compose -f deploy/compose/docker-compose.edge.yml --profile edge up -d`
4. Point tunnel hostname → `http://127.0.0.1:8000`, move DNS to Cloudflare (proxied).
5. **Verify:**
   - `curl -I https://leadsgenai.in` shows `server: cloudflare`
   - `curl http://127.0.0.1:8000/api/public/turnstile/config` → `{enabled: true, site_key: "..."}`

---

## Phase 2 — Visibility (AI safety + observability, ₹0)

### 2.1 Semantic cache (LLM rate-limit insurance)
```
SEMANTIC_CACHE=1
SEMANTIC_CACHE_MIN_SIM=0.97
SEMANTIC_CACHE_TTL_S=21600
```
**Verify:** `curl -s http://127.0.0.1:8000/metrics | grep leadgen_semcache_hit_rate`.

### 2.2 LLM observability (Langfuse cloud or OTel→Tempo)
```
ENABLE_LLM_OBS=1
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
```
**Verify:** make a test call → traces in Langfuse dashboard.

### 2.3 Agent memory (cross-session lead recall — F.4)
```
AGENT_MEMORY=1
AGENT_MEMORY_MIN_SIM=0.35
```
**Verify:**
- `curl -s http://127.0.0.1:8000/metrics | grep leadgen_agent_memory`
- `curl -s http://127.0.0.1:8000/api/agent-memory/stats` → enabled: true.
- DPDP: opt-out via `consent_ledger.record_opt_out(phone)` auto-purges (C5 bridge).

### 2.4 Eval Gate (close self_improve open-loop — F.3 + C2)
```
EVAL_GATE=1
# Leave HARD off until baseline is trusted (~2 weeks of self_improve runs):
# EVAL_GATE_HARD=0
```
**Verify:** `curl -s http://127.0.0.1:8000/api/eval-gate/summary` → enabled: true.
After ~20 self_improve runs, baselines populate; flip `EVAL_GATE_HARD=1` to
make rejections actually block.

CI side (zero env needed): the workflow `.github/workflows/llm-eval.yml`
auto-records every DeepEval run and uploads `eval_gate_summary.json`
artifact with regression decisions.

---

## Phase 3 — AI Staff Awakening (engineer agents + alerting, ₹0)

### 3.1 Engineer agents (F.5)
```
SRE_AGENT=1
FINOPS_AGENT=1
SECURITY_AGENT=1
```
Scheduler windows (already wired in C1):
- Pranav SRE: hourly at :45
- Vidya FinOps: daily 09:00-10:00 IST
- Arnav Security: daily 09:30-10:30 IST

**Verify:** `curl -s http://127.0.0.1:8000/api/engineer-agents/all -H "Authorization: Bearer $TOKEN"`.

### 3.2 ntfy + ops_alerts (G.1 — turn signals into actual notifications)
```
NTFY_URL=http://ntfy:80
NTFY_TOPIC=leadgen-ops
OPS_ALERTS=1
# Tunable thresholds (defaults shown):
# OPS_ALERT_ENGINEER_THRESHOLD=60
# OPS_ALERT_EVAL_REJECT_BURST=3
# OPS_ALERT_EVAL_REJECT_WINDOW=86400
```
**Verify:** `curl -X POST http://ntfy:80/leadgen-ops -d "test from runbook"`
should arrive on ntfy app. Then force a low engineer score (e.g. delete
`/opt/leadgen/data/pg_backup.log`) and wait for the hourly Pranav run.

---

## Phase 4 — Sellable Capabilities (revenue features, ₹0)

### 4.1 Customer-facing webhooks (H.1 + J.1)
```
CUSTOMER_WEBHOOKS=1
# Safety: leave the SSRF guard ON (default)
# CUSTOMER_WEBHOOK_DENY_PRIVATE=1
```
**Verify:** `curl -s http://127.0.0.1:8000/api/customer/webhooks/_meta` →
`enabled: true`.

Customer UI at `/app/customer` "📡 Webhooks" section: register URL +
event types + test + see deliveries + delete. HMAC-SHA256 signed
deliveries with 3-retry backoff.

Currently wired emit points: `lead.qualified` from
`app/billing/lead_usage.record_qualified_lead` (I.2).
TODO emit points (after billing.py M-track lands):
- `payment.received` from Razorpay webhook handler
- `subscription.{activated,cancelled}` from billing manager

### 4.2 Customer 2FA TOTP (H.2 + I.5)
No env to activate — opt-in per customer via their dashboard.
Customer UI at `/app/customer` "🔒 Surakhsha" section: 3-step enrol
(QR/otpauth URI + recovery codes + 6-digit confirm), then disable
gate with TOTP or recovery code.

Optional: `TOTP_CHALLENGE_KEY=<32+ bytes hex>` to make login-challenge
tokens consistent across app restarts (otherwise a fresh random per
process — fine for single-VPS, breaks if you ever go HA).

### 4.3 MCP-as-product + A2A (H.3)
```
MCP_PRODUCT=1
```
1. **Verify metered surface:** `curl -s http://127.0.0.1:8000/api/mcp-product/v1/discover`
   → `enabled: true`.
2. **Verify A2A Agent Card:** `curl -s https://leadsgenai.in/.well-known/agent.json`
   → returns capability list.
3. Issue first key from `/app/dashboards` MCP card (J.2) — save the
   plaintext secret ONCE. Try a metered call:
   ```bash
   curl -s -H "X-LeadGen-Key: lgmcp_XXXX" \
     http://127.0.0.1:8000/api/mcp-product/v1/niches
   ```
   Expected: `200 OK` + niche list + `meter_remaining: 999`.
4. Revoke keys via the same dashboard card (J.2).

---

## Phase 5 — Margin Discipline + Survival (H.4)

### 5.1 LiteLLM gateway + per-tenant cost
```
LITELLM_MASTER_KEY=<32-char random>
LITELLM_GATEWAY_URL=http://litellm:4000
LITELLM_COSTS=1
```
1. `docker compose -f deploy/compose/docker-compose.edge.yml --profile gateway up -d`
2. `curl http://litellm:4000/health` → 200.
3. Issue virtual keys per customer via LiteLLM admin UI.
4. Populate `/opt/leadgen/data/litellm_keymap.jsonl`:
   ```json
   {"vkey": "sk-customer-a", "client_id": "client_abc", "niche": "salon"}
   ```
5. **Verify:** `curl -s http://127.0.0.1:8000/api/h4/litellm-spend?hours=24 -H "Authorization: Bearer $TOKEN"`.
6. Vidya FinOps agent (3.1) auto-picks up the data — `kpis.litellm_unmapped_spend_usd`
   surfaces as an action item when any vkey lacks a `client_id` mapping.

### 5.2 Warm-DR replica (Postgres logical replication to free PG)
```
DR_REPLICA_URL=postgres://user:pass@neon.tech/dbname  # pragma: allowlist secret (placeholder sample)
DR_LAG_WARN_S=60
DR_LAG_FAIL_S=600
```
1. Sign up for Neon / Supabase free tier; create DB.
2. Configure publication on primary (`leadgen_db`), subscription on replica.
3. **Verify:** `curl -s http://127.0.0.1:8000/api/h4/dr-status -H "Authorization: Bearer $TOKEN"`
   → `status: OK, lag_s: <small>`.
4. SRE agent (3.1) auto-picks up the lag for its score.

---

## Unified operator pane: `/app/dashboards` (H.5)

Single HTML at `/app/dashboards` surfaces every readiness signal:
- Activation Readiness (F.2) — `ready_for_first_paid_customer` ribbon
- Engineer Agents (F.5) — Pranav/Vidya/Arnav scores + top actions
- Eval Gate (F.3) — decision tallies + per-suite baseline drift
- Agent Memory (F.4) — counters
- MCP Keys (H.3 + J.2) — list + revoke + issue inline
- DR + LiteLLM (H.4) — worst-of-3 ribbon
- Customer Webhooks (H.1) — flag state + supported events
- Turnstile (F.1) — armed/inert

Auth: paste admin JWT into the banner; stored in `localStorage.adminToken`.
Auto-refresh 30s.

---

## Quick smoke after any activation

```bash
curl -s http://127.0.0.1:8000/api/activation/readiness | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/growth/infra/flags | python3 -m json.tool | grep -E '"(TURNSTILE|EVAL_GATE|AGENT_MEMORY|OPS_ALERTS|CUSTOMER_WEBHOOKS|MCP_PRODUCT|LITELLM)"'
```

`ready_for_first_paid_customer: true` is the single boolean that tells
you the platform is revenue-ready.
