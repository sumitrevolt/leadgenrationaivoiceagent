# Production Readiness Analysis — leadgenrationaivoiceagent

> **Analysis date:** 2026-06-24 · **Last updated:** 2026-06-25 (consolidated: merged the corrected analysis + marked code items shipped)
> **Live URL:** https://leadsgenai.in
> **VPS:** 72.61.245.204 (Mumbai, Hostinger)
> **Current State:** ~840 routes (839 registered / 865 API ops) · 0 automation gaps · prod_check PASS · `ready_for_first_paid_customer=true` (blocker_count=0)

---

## 1. Executive Summary

Project **already live** hai aur technically production-ready for the first paid customer. UPI payment path armed hai (`/api/public/pay-info` enabled). Docker stack 13+ containers chal raha hai. Celery scheduler + 24 staff jobs active. AI voice pipeline conversational hai (web-call free tuning, Vobiz stream phone-ready).

**Key correction (vs the first draft of this report):** Analytics DB binding aur customer webhooks payment/subscription emit dono actually **wired hain** — pehle draft me galat analysis tha (stale comments pe rely kiya gaya tha, code dekhne pe sab functional mila). Real remaining gaps = external paperwork + env activation only.

---

## 2. What's Already Production-Ready ✅

| Area | Status | Evidence |
|------|--------|----------|
| **Platform core** | ✅ LIVE | `/health` = production, ~840 routes, 0 gaps |
| **Docker + Postgres + Redis + PgBouncer** | ✅ LIVE | compose stack, backups nightly, offsite email backup verified |
| **Celery scheduler + 24 staff jobs** | ✅ LIVE | self-heal, dead-man trio, queue flood fixed |
| **UPI payments** | ✅ ARMED | VPA `8459012607@axl` set, `/api/public/pay-info` live |
| **GST invoicing** | ✅ ARMED | Rule-46 sequential, SAC 998313, unregistered = no tax (truth) |
| **Email outreach + warmup** | ✅ ARMED | 25/day cap, bounce auto-pause, MX-verify |
| **AI voice pipeline** | ✅ LIVE | Groq STT + Cerebras LLM + EdgeTTS, free stack, KB-grounded |
| **Security hardening** | ✅ DONE | IDOR closed, SSRF blocked, webhook sig fail-closed, consent ledger, DND fail-closed |
| **Customer portal** | ✅ LIVE | TOTP 2FA, invoices, webhooks |
| **Sentry** | ✅ ARMED (VPS) | `SENTRY_DSN` set per 2026-06-22 log |
| **Feature flags** | ✅ LIVE | 80+ flags, `/api/growth/infra/flags` registry |
| **RAG (Qdrant)** | ✅ LIVE | `kb_main` collection, 39 niches, per-client namespaces |
| **Automation loops** | ✅ LIVE | self_improve, process engine, sales team, cadence, dunning, nurture |
| **Customer webhooks** | ✅ WIRED | `lead.qualified`, `call.report.ready`, `payment.received`, `subscription.created/updated` — sab emit live (`billing.py` + `lead_usage.py` + `post_call_hooks.py`) |
| **Analytics DB binding** | ✅ FUNCTIONAL | `_db_calls()` + `_db_leads()` with DB query + in-memory fallback (stale TODO comments cleaned 2026-06-25) |

---

## 3. Critical Blockers (External — User Action Required) 🚨

> **Yeh code se solve nahi hote.** Sirf aap (owner) kar sakte ho.

### 3.1 DLT + Udyam Registration (Cold-Calling Gate)
- **Status:** BLOCKER for voice cold-calling
- **Detail:** DLT Principal Entity request REJECTED (individual). Udyam (MSME) certificate se Proprietorship re-apply karna hai. Fee ₹5,900. Approval 3-7 din.
- **Impact:** Bina DLT + 140-series number ke cold auto-calls = TRAI violation = ₹10L risk. Inbound auto-callback + web-call abhi chal raha hai.
- **Action:** udyamregistration.gov.in → MSME cert → DLT re-apply → 140 DID kharido
- **Ref:** `docs/SWARA_HANDOFF_SOP.md` Part E

### 3.2 Vobiz Recharge + DID Purchase
- **Status:** BLOCKER for phone AI calls
- **Detail:** Trial balance ~₹25 khatam. DID nahi hai → `VOBIZ_CALLER_ID` = trial number (auto-remove hoga recharge pe). Real outbound calls untestable.
- **Impact:** Phone AI demo nahi de sakte. Web-call demo chal raha hai (free tuning).
- **Action:** console.vobiz.ai → KYC complete → balance recharge → Indian DID kharido → `VOBIZ_CALLER_ID=+91<DID>` update + restart
- **Ref:** `docs/PENDING_PLANS.md` Section P3

### 3.3 First Paid Customer (UPI Path Test)
- **Status:** ARMED but untested end-to-end
- **Detail:** UPI VPA configured, checkout QR live, but koi real transaction nahi hui. Manual UPI process hai (Stripe international backup, India me UPI primary).
- **Impact:** First customer ke payment pe process friction ho sakti hai.
- **Action:** Apne aap ko first customer banao (₹1 test) → UPI collect → invoice generate → verify GST + email delivery

---

## 4. High-Priority Warnings (Recommended, Not Blocking) ⚠️

> **Yeh project chalega bina, par customer trust/ops me gap rahega.**

### 4.1 Turnstile Bot Protection (F.1)
- **Status:** WARN — keys missing (env/config check; per 2026-06-24 log Turnstile ARMED via CF API — verify)
- **Detail:** Cloudflare Turnstile lead-magnet forms (audit, inquiry, demo) pe bot-protection. Spam abuse risk if off.
- **Action:** Cloudflare dashboard → Turnstile → create widget → `TURNSTILE_SITE_KEY` + `TURNSTILE_SECRET_KEY` .env me → `↻APP`
- **Verify:** `curl https://leadsgenai.in/api/public/turnstile/config` → `{enabled: true, site_key: "..."}`

### 4.2 PostHog Product Analytics
- **Status:** WARN — key missing (env/config check)
- **Detail:** User behavior tracking nahi hai. Funnel drop-off, conversion path ka pata nahi.
- **Action:** PostHog Cloud free tier → `POSTHOG_API_KEY` + `POSTHOG_HOST` .env me → `↻APP`
- **Verify:** PostHog dashboard pe live events dikhe site visit pe

### 4.3 Track B Admin Panels (Production Only)
- **Status:** WARN in prod — `CLIENT_TIMELINE`, `SYS_HEALTH_DETAIL` abhi OFF; `REVENUE_TRENDS` already `=1` (2026-06-24)
- **Detail:** Admin dashboard me MRR/churn/LTV history (live), client timeline, system health detail nahi dikhega.
- **Action:** VPS pe `.env` me `CLIENT_TIMELINE=1 SYS_HEALTH_DETAIL=1` (REVENUE_TRENDS already on)

### 4.4 Qdrant RAG URL (Docker Trap)
- **Status:** ✅ RESOLVED — `docker-compose.vps.yml` already uses service name `http://qdrant:6333` (not `127.0.0.1`). No action needed.
- **Detail:** Container ke andar `127.0.0.1:6333` unreachable hota — repo me already service-name use ho raha hai (verified 2026-06-25, 3 occurrences in compose).
- **Verify:** `docker exec leadgen_app curl -s http://qdrant:6333/healthz` → `{"status":"ok"}`

### 4.5 Engineer Agents (F.5)
- **Status:** WARN — `SRE_AGENT=1`, `FINOPS_AGENT=1`, `SECURITY_AGENT=1` abhi OFF/default (env/config check)
- **Detail:** 3 KPI-bound agents (Pranav SRE, Vidya FinOps, Arnav Security) scheduled hain par inactive. Production monitoring/alerting me gap.
- **Action:** `.env` me teeno `=1` → `↻APP` → verify `/api/engineer-agents/all`

### 4.6 ntfy Ops Alerts (G.1)
- **Status:** WARN — `OPS_ALERTS=1` but `NTFY_URL`/`NTFY_TOPIC` missing (env/config check)
- **Detail:** Engineer low-score, eval reject burst, readiness digest alerts phone pe nahi jayenge.
- **Action:** `NTFY_URL=http://ntfy:80` + `NTFY_TOPIC=leadgen-ops` + `OPS_ALERTS=1` → ntfy app install → test push
- **Verify:** `curl -X POST http://ntfy:80/leadgen-ops -d "test"` → phone notification

---

## 5. Medium-Priority Gaps (Operational Polish) 🔧

### 5.1 Analytics TODO Comments — ✅ DONE (2026-06-25)
- **Location:** `app/api/analytics.py`
- **Detail:** 14 `TODO: bind to <Model> when a DB is added` comments + stale module/class docstrings (jo galat keh rahe the "No relational DB / SQLAlchemy models exist") — DB binding actually pehle se present hai (`_db_calls()` + `_db_leads()`, in-memory fallback ke saath). Comments misleading the new devs ke liye.
- **Resolution:** Sab TODO comments accurate `Data source: … DB rows with in-memory store fallback` me update; module + `AnalyticsStore` docstrings corrected; ek **dead duplicate `_week_trends`** function (shadowed) bhi remove kiya. prod_check PASS, import OK.

### 5.2 Request Guard (Load Shedding)
- **Status:** OFF (`REQUEST_GUARD=0`) — env flag
- **Detail:** Per-request timeout (55s) + per-worker in-flight limit (200) + load-shed (503) inactive hai. High traffic pe single worker overwhelm ho sakta hai.
- **Action:** Staging pe test karo (`REQUEST_GUARD=1`) → prod pe enable. Long paths (WS, streaming) already skipped.

### 5.3 Plan Rate Limiting
- **Status:** OFF (`PLAN_RATE_LIMIT=0`) — env flag
- **Detail:** Starter/Growth/Advanced tier-wise RPM limits (60/200/500) inactive. Abuse protection nahi hai.
- **Action:** `PLAN_RATE_LIMIT=1` → test with load → verify 429 responses on over-limit

### 5.4 Alembic Migration Discipline
- **Status:** `DB_CREATE_ALL=1` still active (boot pe auto-create) — env flag
- **Detail:** Alembic stamped head hai (`005`), par `DB_CREATE_ALL=1` fallback still on. True migration discipline nahi hai — schema drift risk in multi-dev.
- **Action:** `DB_CREATE_ALL=0` set karo (prod pe) → future schema changes = `alembic revision --autogenerate` → `upgrade head`

### 5.5 Eval Gate Baseline Population
- **Status:** `EVAL_GATE=0` (off) — env flag
- **Detail:** Self-improve loop ka close-the-loop reward signal nahi hai. 20+ runs ke baad baseline populate hoga, tab `EVAL_GATE_HARD=1` possible.
- **Action:** `EVAL_GATE=1` → 2 hafte observe karo → `EVAL_GATE_HARD=1`

### 5.6 Semantic Cache (LLM Rate-Limit Insurance)
- **Status:** OFF (`SEMANTIC_CACHE=0`) — env flag
- **Detail:** Same/similar LLM queries pe cache hit = cost savings + faster response. Free-tier quota choke pe insurance.
- **Action:** `SEMANTIC_CACHE=1` + `SEMANTIC_CACHE_MIN_SIM=0.97` → verify metrics

### 5.7 Agent Memory (Cross-Session Recall)
- **Status:** OFF (`AGENT_MEMORY=0`) — env flag
- **Detail:** Same lead dobara call pe pichli baat yaad nahi rahegi. Voice agent "human-like" feel kam.
- **Action:** `AGENT_MEMORY=1` → Qdrant `agent_memory` collection verify

---

## 6. Low-Priority / Nice-to-Have 🌱

| Item | Status | Detail |
|------|--------|--------|
| **Cloudflare Tunnel** | NEUTRAL | `CLOUDFLARE_TUNNEL_TOKEN` missing. Origin-hide + WAF valuable but not blocker. Caddy already handling TLS. |
| **Warm-DR Replica** | NEUTRAL | `DR_REPLICA_URL` missing. Neon/Supabase free tier pe logical replication possible. SPOF mitigation. |
| **LiteLLM Cost Tracking** | NEUTRAL | `LITELLM_COSTS=0`. Per-tenant LLM spend tracking. Overhead jab scale ho. |
| **MCP-as-Product** | NEUTRAL | `MCP_PRODUCT=0`. Metered API revenue surface. API platform ready, needs marketing. |
| **SOPS/Secrets Management** | DEFERRED | `.env` single point of loss. Offsite email backup partially mitigates. SOPS+age documented but not adopted. |
| **Docker Rollout (Zero-Downtime)** | DEFERRED | `lb_try_duration 25s` covers most. Blue-green deploy deferred. |
| **Secondary Cold-Email Domain** | DEFERRED | Warmup restart + inbox rotation. Current domain ke reputation risk. |

---

## 7. Corrected Action Plan (Priority Order)

### Week 1 — Revenue Unblock (Critical)
1. [ ] **DLT + Udyam** — MSME cert apply → DLT re-submit → 140 DID
2. [ ] **Vobiz recharge + DID** — console.vobiz.ai → KYC → recharge → DID → `VOBIZ_CALLER_ID` update
3. [ ] **First UPI transaction test** — Apne aap ko customer banao → ₹1 → full flow verify (invoice + email + GST)

### Week 2 — Trust + Visibility (High)
4. [ ] **Turnstile** — keys verify/set in `.env` → verify forms
5. [ ] **PostHog** — Signup → key → `.env` → verify events
6. [ ] **Track B flags** — `CLIENT_TIMELINE=1 SYS_HEALTH_DETAIL=1` → VPS enable (REVENUE_TRENDS already on)
7. [x] **Qdrant URL** — already service-name in compose (verified 2026-06-25)

### Week 3 — Ops Automation (High)
8. [ ] **Engineer agents** — `SRE_AGENT=1 FINOPS_AGENT=1 SECURITY_AGENT=1` → verify alerts
9. [ ] **ntfy ops alerts** — `OPS_ALERTS=1` + topic → phone test
10. [ ] **Request Guard** — staging test → `REQUEST_GUARD=1` prod
11. [ ] **Plan Rate Limiting** — `PLAN_RATE_LIMIT=1` → abuse test

### Week 4 — AI Polish + Config (Medium)
12. [x] **Analytics TODO cleanup** — stale comments updated + dead dup removed (2026-06-25)
13. [ ] **Eval Gate** — `EVAL_GATE=1` → observe → `EVAL_GATE_HARD=1`
14. [ ] **Semantic Cache** — `SEMANTIC_CACHE=1` → cost savings
15. [ ] **Agent Memory** — `AGENT_MEMORY=1` → cross-session recall

### Ongoing — Business
- [ ] **GTM:** Roz 10 WhatsApp pitches (kit se) → demo → close
- [ ] **Voice tuning:** Web-call pe free QA → phone sirf final verify
- [ ] **Content:** Blog + social auto-post via scheduler (already wired)

---

## 8. Verification Commands (Copy-Paste)

```bash
# Health check
ssh -i ~/.ssh/id_rsa root@72.61.245.204 'curl -s http://127.0.0.1:8000/health/ready | python3 -m json.tool'

# Activation readiness (no auth needed for summary)
curl -s https://leadsgenai.in/api/activation/summary

# Prod check (VPS pe)
docker exec leadgen_app python scripts/prod_check.py

# Automation flags
curl -s https://leadsgenai.in/api/growth/infra/flags | python3 -m json.tool

# Telephony readiness
curl -s https://leadsgenai.in/api/telephony/readiness
```

---

## 9. Honest Assessment (CORRECTED)

**Code-level production readiness = 95%+.** First draft me 2 galat claims the, dono corrected:

1. **Analytics = mock** ❌ → Actually `_db_calls()` + `_db_leads()` DB binding functional hai, in-memory fallback ke saath. 14 stale TODO comments + dead duplicate function 2026-06-25 ko cleaned.
2. **Payment/subscription webhooks = not wired** ❌ → Actually `_emit_billing_customer_webhook()` in `billing.py` handles all payment/subscription events: `payment.received`, `subscription.created`, `subscription.updated`.

**Real remaining gaps = external paperwork + env activation only.**

- **User action blockers (3):** DLT/Udyam, Vobiz recharge, first transaction test
- **Config activation (~10):** Turnstile (verify), PostHog, Track B flags (CLIENT_TIMELINE/SYS_HEALTH_DETAIL), engineer agents, ntfy, Request Guard, Plan Rate Limiting, Eval Gate, Semantic Cache, Agent Memory
- **Code work:** ✅ none remaining — Analytics TODO cleanup shipped 2026-06-25; Qdrant URL already correct.

**Bottom line:** Pehla paid customer aaj aa sakta hai (UPI armed). Full polish + paperwork = 2-3 hafte. Code kaam kar raha hai, bas env keys aur paperwork baki hai.

---

*Report generated from: AGENTS.md, docs/SESSION_LOG.md, docs/PENDING_PLANS.md, app/api/activation.py, app/api/analytics.py (code-level verification), app/api/billing.py (webhook wiring verified), app/billing/lead_usage.py, app/telephony/post_call_hooks.py, docker-compose.vps.yml, and codebase audit. Consolidated 2026-06-25 (merged corrected analysis, removed superseded draft).*
