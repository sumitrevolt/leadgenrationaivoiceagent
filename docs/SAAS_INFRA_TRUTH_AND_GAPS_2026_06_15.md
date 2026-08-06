# SaaS Infra â€” SOURCE OF TRUTH + Remaining Gaps (2026-06-15)

> **Ye doc 2 prior gap-analyses ko RECONCILE karta hai** aur unme jo dedup-errors the
> woh theek karta hai. Agar dobara "SaaS infra gap dhoondo" karna ho â€” **pehle ye padho**,
> 4th repeat se bacho.
>
> Reconciles: `Infra_BestStack_GapAnalysis_2026-06.md` (G1â€“G8) + `Infra_Upgrade_Activation_Runbook.md`
> + `SAAS_INFRA_GAP_ADDITIVE_2026_06_15.md`. Method: dono docs + ACTUAL repo grep/code-read
> (`.github/workflows`, `app/`, `docker-compose.*`, `evals/`) + 2 fresh repo-grounded research
> agents (top SaaS boilerplates + candidate validation).

---

## TL;DR (billionaire-lens, brutally honest)

1. **Tera INFRA layer SATURATED hai. Genuine infra gap = lagbhag ZERO.** Top SaaS blueprints jo
   recommend karte (CI/CD+health-gate+rollback, Trivy CVE+SBOM, SOPS secrets, full Prom/Grafana/
   Loki/Tempo obs + exporters + celery-exporter + Flower, durable Celery + event-sourced process-
   engine, Qdrant RAG, LLM-observability + promptfoo eval CI, semantic cache, plan-tier rate-limit,
   k6 load + chaos, Ansible rebuild, offsite backup, Cloudflare edge) â€” **sab pehle se code me hai**
   (kuch active, kuch gated-dormant). Iss layer pe aur token/paisa MAT jala.
2. **Asli remaining value 2 cheezein hain â€” NAYA infra nahi:**
   (a) **ACTIVATION** â€” bahut saari powerful cheezein OFF padi hain sirf tere account/creds/DNS ke
   intezaar me (Cloudflare, offsite R2/B2, PostHog, LLM-obs, Razorpay live keys). Ye build-karne ka
   nahi, switch-on karne ka kaam hai â€” aur yahi highest ROI hai.
   (b) **APP/SaaS layer white-space** (infra nahi) â€” boilerplate-repo research me yahi nikla:
   **MFA/2FA, magic-link + OAuth-social login, "login as customer" impersonation, customer-facing
   webhooks.** Ye genuinely absent + free + zyadatar no-creds hain.
3. **Iss session me 1 genuine INFRA gap SHIP hua** (niche Â§A) â€” baaki sab ya activation hai ya app-layer.

---

## Â§A â€” IS SESSION ME SHIPPED (genuine, creds-free, working)

### âœ… External off-VPS uptime watchdog â€” `.github/workflows/uptime.yml`
- **Kyun genuine gap tha:** saara monitoring (Gatus, Uptime-Kuma, Prometheus, Alertmanager,
  self-hosted ntfy) **VPS ke ANDAR** chalta hai. VPS hi mar jaaye (3 prod-downs ka exact scenario)
  to ye sab bhi mar jaate â€” bahar se KOI alert nahi. Dono research agents ne isà¥‡ **#1 ROI gap**
  confirm kiya ("monitor your monitoring from outside the host" = 2026 reliability best-practice).
- **Kya karta:** GitHub ke infra (VPS se independent) pe har ~10 min `leadsgenai.in/health` ko
  BAHAR se ping â†’ 200 + `environment:production` check â†’ 3x retry (flap-safe) â†’ fail pe GitHub
  khud repo-owner ko email karta (off-VPS channel jo VPS-down me bhi kaam karta). Optional: public
  `ntfy.sh` topic push (repo variable `NTFY_TOPIC` set karo). **Push hote hi live, zero creds.**
- **Proven:** probe-logic live site pe test ki â€” `http_code=200`, `"environment":"production"` matched.
- **Belt-and-suspenders (2-min, recommended):** GitHub cron ~5-15min jitter leta. Iske SAATH ek
  **UptimeRobot free** (50 monitors, 5-min, true off-host, email/push) `/health` pe laga de â€”
  research agent ne ise sabse reliable-free option bola. Dono milke proper external coverage.

---

## Â§A.2 â€” ROUND-2 deep-sweep (17-agent "kya MISS hua?" â€” found genuine deltas)

Exhaustive re-sweep (top SaaS blueprint repos + 2026 infra/AI-agent/data refs, adversarial absence-verify + completeness critic). 10 candidates â†’ 6 confirmed genuinely-new. **4 BUILT (flag-gated/additive), 3 deferred:**

| # | Item | Sev | Status |
|---|------|-----|--------|
| 1 | **Alembic migration-safety**: deploy `alembic upgrade head \|\| true` (silent fail) â†’ **hard-gated auto-rollback**; new `.github/workflows/migrations.yml` (Postgres round-trip + single-head + `alembic check` + Squawk DDL-lint, advisory) | HIGH | âœ… BUILT |
| 2 | **Public guardrails**: `guardrails.py` (PII-redact + injection-block) wired into public `chatbot.py` (was voice-only). Flag `PUBLIC_GUARDRAILS`, fail-open | MED | âœ… BUILT |
| 3 | **Qdrant snapshot backup**: live-dir tar â†’ consistent snapshot-API + `.sha256` (tar fallback) in `vps_backup.sh` | MED | âœ… BUILT |
| 4 | **PG restore-drill content-integrity**: `pg_restore_drill.sh` ab critical-table existence + non-empty core check ("backups green but empty" guard) + content metric | MED | âœ… BUILT |
| 5 | Fider feedback/roadmap board | LOW | â³ DEFER â€” zero paying customers yet; +1 container RAM. Once-you-have-customers lever |
| 6 | Pyrra SLO/error-budget | LOW | â³ DEFER â€” flat alerts solo single-VPS ke liye kaafi; +container. Tab jab alert-fatigue real ho |
| 7 | Postmaster Tools v2 spam-rate poller | LOW | â³ DEFER â€” activation-gated (service-account); volume-threshold tak silent |

**Completeness critic verdict:** FinOps (free-stack = ~â‚¹0 COGS, budget-guard covers runaway), DR game-day (chaos+pg-drill), incident/on-call (12 runbooks+ntfy), DPDP (consent ledger+privacy_ops) â€” **sab saturated**. Critic ke 2 follow-on (offsite-restore drill = activation-gated; PG content-integrity = built as #4). **Verdict: stack saturated; aage digging ki marginal value < build time.**

Round-2 verify: 54 tests green Â· shell `bash -n` OK Â· workflow YAML valid Â· chatbot import OK Â· 17-agent adversarial sweep (0 false-positive on the 6 confirmed).

---

## Â§B â€” DEDUP CORRECTIONS (prior docs me galat tha)

| Prior claim | Reality (verified) |
|---|---|
| `SAAS_INFRA_GAP_ADDITIVE` #1: "promptfoo â†’ koi match nahi, DeepEval+Promptfoo add karo" | **GALAT.** `evals/promptfooconfig.yaml` + `.github/workflows/llm-eval.yml` **pehle se hain** (commit 87ad474). Eval CI advisory-live hai. DeepEval add karna = duplicate-ish; bas promptfoo asserts bharo. |
| `SAAS_INFRA_GAP_ADDITIVE` Tier-3: "OTel tracing idle, activate" | OTel app-tracing **wired** (`app/observability_otel.py` + `requirements-otel.txt`); LLM-obs bhi `free_ai.py` + `structured.py` me wired (`observability_llm.py`). Bas `ENABLE_OTEL=1`/`ENABLE_LLM_OBS=1`. |
| Both docs treated semantic-cache as "to build" | **Ban chuka** â€” `app/cache/semantic_cache.py` + tests + `/metrics` + chatbot-wired (`SEMANTIC_CACHE` flag, OFF default). |

---

## Â§C â€” APP/SaaS-layer white-space (repo-grounded; 3 ab SHIPPED)

Repo-grounded research (open-saas, BoxyHQ, ixartz, supastarter, makerkit) â€” ye **infra docs me kabhi
nahi aaya** kyunki ye auth/account layer hai. Status (sab verified-absent the; 3 is session me ban gaye):

| Item | Top repos | Status | Flag (OFF default) |
|---|---|---|---|
| **"Login as customer" impersonation** | ixartz, makerkit, supastarter | âœ… **SHIPPED** â€” super_admin-only, 30-min token, har start/stop AuditLog, `/app/impersonate` UI, XSS-safe | `IMPERSONATION=1` |
| **Magic-link login** | open-saas, supastarter, makerkit | âœ… **SHIPPED** â€” single-use (redis NX) 15-min, no email-enumeration (body+timing), Hostinger SMTP, login.html UI | `MAGIC_LINK=1` |
| **LLM cost/budget governance** | AI-infra 2026 | âœ… **SHIPPED** â€” per-scope daily call+token caps + emergency hard-kill, free_ai wired, /metrics, fail-open | `LLM_BUDGET_GUARD=1` / `LLM_BUDGET_HARD_KILL=1` |
| **MFA / 2FA (TOTP)** | supastarter, makerkit, BoxyHQ | âš ï¸ **PARTIAL** â€” admin login me already hai (`ADMIN_TOTP_SECRET` + `app/utils/totp.py`). Customer-side 2FA baaki | `ADMIN_TOTP_SECRET` |
| **Customer-facing webhooks** ("subscribe to events") | BoxyHQ (Svix), open-saas | â³ **TODO** â€” sellable feature; tere outbox/idempotency primitives reuse | â€” |

**Shipped (is session) â€” verify:** 28/28 pytest green Â· py_compile + import OK Â· 5-finding adversarial
security review (0 false-positive) â€” sab fix. Sab flag OFF default = prod untouched jab tak enable na ho.
**Baaki:** customer-side 2FA + customer-facing webhooks (jab zaroorat ho).

---

## Â§D â€” ACTIVATION CHECKLIST (sabse zyada ROI â€” code ready, sirf switch ON)

Ye "gaps" nahi â€” ye **ready-but-OFF** hai. Yahi asli leverage hai:

1. **Razorpay live keys** (ðŸš¨ P0 â€” pehla paid customer se pehle MUST) â€” `.env` me asli `rzp_live_...`.
2. **Cloudflare free edge** (`deploy/compose/docker-compose.edge.yml`) â€” origin-IP hide + WAF + CDN + DDoS. CF account + tunnel token. **Single biggest free security+perf win.**
3. **Offsite backup** â€” R2/B2 (10GB free) bucket â†’ `RCLONE_REMOTE` set. `pg_backup.sh` already wired.
4. **LLM observability** â€” `ENABLE_LLM_OBS=1` (+ Langfuse cloud-free keys ya OTelâ†’Tempo). Code wired.
5. **PostHog** â€” product-analytics + session-replay + flags (cloud-free key). Code wired.
6. **UptimeRobot** â€” Â§A belt-and-suspenders (2-min signup).

---

## Â§E â€” Validated SKIP (dobara mat suggest karna â€” research-confirmed)

- **cosign image signing + SLSA provenance** â€” Trivy CVE + SBOM already; single-VPS pe koi
  signature-VERIFY karne wala downstream nahi (no k8s admission controller) â†’ ceremony without verifier.
  Revisit only at k8s/multi-node/enterprise.
- **DBOS Transact** â€” event-sourced `process_engine.py` + durable Celery already covers durability;
  migration-cost > marginal gain. Redundant.
- **Temporal/Windmill/Inngest, Coolify/Dokploy/Kamal, Renovate, pgBackRest/Barman, new auth stack
  (Keycloak/Authentik), self-host PostHog/Langfuse (ClickHouse/Kafka = VPS marega), SAML SSO+SCIM,
  i18n, dedicated feature-flag service** â€” sab duplicate ya over-engineering for solo single-VPS India SaaS.

---

## Sources (fresh repo-grounded research, 2026)
- Top SaaS boilerplates: [wasp-lang/open-saas](https://github.com/wasp-lang/open-saas) Â· [boxyhq/saas-starter-kit](https://github.com/boxyhq/saas-starter-kit) Â· [ixartz/SaaS-Boilerplate](https://github.com/ixartz/SaaS-Boilerplate) Â· [makerkit](https://makerkit.dev/nextjs-saas-starter-kit) Â· [supastarter](https://supastarter.dev/)
- "Monitoring the monitor" (off-host watchdog): https://dohost.us/index.php/2026/04/25/monitoring-the-monitor-who-watches-the-watchmen/
- cosign keyless GHA: https://www.qcecuring.com/blog/sigstore-cosign-keyless-github-actions
- DBOS Transact: https://www.dbos.dev/dbos-transact
- Runtime AI governance 2026: https://accuknox.com/blog/runtime-ai-governance-security-platforms-llm-systems-2026


---

# Appendix A - Folded from INFRA_DEEP_AUDIT_BILLIONAIRE_SCALE_2026_06_16.md (consolidated 2026-06-25)

# Billionaire-Scale Infrastructure Deep Audit & Gap Analysis
### leadsgenai.in (leadgenrationaivoiceagent) â€” June 16, 2026
**Lens:** SaaS architect Â· AI-infra strategist Â· hyperscaler cloud architect Â· VC technical due-diligence
**Method:** Full codebase + internal gap-doc digest (60+ docs) cross-referenced with 2025â€“26 external landscape research (agentic infra, LLMOps, vector/graph, event-driven, AI-native SaaS).

---

## Executive Summary (the one-page truth)

You do not have an *invention* problem. You have an **activation and focus** problem. This is the single most important finding of the audit.

Most "mature AI SaaS gap analyses" recommend adding Temporal, Langfuse, Kafka, Keycloak, a feature-flag service, k8s. You have already **evaluated and explicitly rejected** every one of those in your own docs â€” correctly, for a solo-founder single-VPS free-stack. So the standard playbook is useless here. The real leverage is in three places:

1. **Activation debt is your biggest hidden liability.** ~25 production-grade capabilities are *wired-but-OFF* (Cloudflare, Sentry, PostHog, LiteLLM, OTelâ†’Tempo, in-house LLM-obs, semantic cache, PITR, SOPS, plan-tier rate-limit, MinIO, Celery exporter/Flower). Code that is wired-but-untested-in-prod is not an asset â€” it is latent risk and unrealized ROI. The highest-return work for the next 30 days is *turning on and verifying what you already built*, not adding anything.

2. **Three genuine capability gaps remain** that your docs do *not* already cover: (a) a **dedicated agent-memory layer** (you have RAG, not memory); (b) **LLM tracing + CI-gated evals** wired into your *existing* Tempo/Grafana (zero new datastore); (c) **MCP-as-a-product + A2A interoperability** â€” your mounted MCP server is used only internally, leaving a new revenue surface and a distribution moat completely untapped.

3. **Your defensible moat is data and outcomes, not infrastructure.** 42 niches Ã— voice "qualified-lead" outcomes is a proprietary, hard-to-copy dataset. The infra moves that compound it (eval sets, outcome-based billing, memory) matter far more than any framework swap.

**If you do only five things this quarter:** (1) Activate Cloudflare Tunnel + Turnstile, (2) fix Razorpay live keys + turn on Sentry/PostHog, (3) add OpenLLMetryâ†’Tempo + DeepEval CI gate, (4) add Mem0 agent memory on your existing Qdrant, (5) ship a metered MCP endpoint + A2A Agent Card. Everything else is sequencing.

---

## SECTION A â€” Current Architecture (verified, not assumed)

This is grounded in the actual repo, not generic assumptions. Your stack is **well past** the maturity of a typical pre-seed AI SaaS.

**Compute / edge:** FastAPI monolith (`leadgen_app`, uvicorn `WEB_CONCURRENCY=2`) on a single Hostinger VPS (Mumbai, Ubuntu 24.04, ~16 GB/4-core), Docker Compose (~13 containers), Caddy host-proxy TLS â†’ `127.0.0.1:8000`. Image baked from `requirements.lock.txt` (`--no-deps`, py3.12) with ML assets baked (fastembed 241 MB, silero-vad, faster-whisper).

**Data plane:** Postgres 16 (tuned) + PgBouncer (session pool 25/1000) + Redis (broker/DLQ/state, AOF, noeviction) + a *second* Redis (evictable cache). Qdrant single-node vector (`kb_main`, per-niche/per-client/skills namespaces). WAL-archive volume mounted (PITR pre-wired, not activated).

**Async/scheduler:** Celery worker (concurrency 4, acks_late, heavy/light queue split) + Celery beat (12+ jobs) + a **dead-man trio** (heartbeat file + revive-beat + watchdog). DLQ in Redis with sweep.

**AI plane (all free):** Custom 5-provider LLM failover chain (Cerebras `gpt-oss-120b` â†’ Groq â†’ xAI â†’ OpenRouter â†’ Gemini) with a bespoke escalating circuit-breaker; Groq Whisper STT; EdgeTTS. Custom `llm_metrics` (per-provider ok-rate/latency/fallback â†’ Prometheus) and `budget_guard` (daily token/call caps + hard-kill). CRAG agentic-RAG ON; Instructor structured outputs ON; trafilatura web-extract active.

**Agent plane (bespoke, substantial):** Custom coordinator (plan/fanout/Reflexion/debate/hierarchical/engineering), event-sourced `process_engine` with deterministic gates + human breakpoints, `self_improve` Celery loop, 5-agent BANT `sales_team`, hybrid-autonomy `code_upgrader` (Tier-1 auto to skills, Tier-2 gated patch proposals), 14 named AI staff agents, 241-skill skill-pack. MCP server mounted at `/mcp`.

**Observability:** Prometheus + Grafana + Loki + Tempo + Alertmanager + Gatus + Uptime-Kuma + node/cAdvisor/postgres/redis exporters. Self-hosted ntfy + SearXNG. (Tempo container live but app not yet instrumented.)

**Growth/revenue automation:** Email outreach (warmup, MX-verify, follow-ups), Google Maps + OSM + SearXNG lead harvester, AI reply-triage, omnichannel cadence, sales engine + AI closer, dunning/lifecycle/health/revenue-digest, channel-experiments bandit, Telegram auto-post.

**Billing/compliance:** `packages.py` single-source-of-truth, GST Rule-46 invoicing, custom usage meter (lead quota + voice minute, fail-open), webhook idempotency (Redis SETNX). TRAI/DPDP-aware telephony (Exotel active, DND fail-closed, consent ledger). Razorpay code complete but **keys are placeholders**.

**Sec/CI:** JWT + 8-module RBAC + admin TOTP, security-headers/rate-limit/tenant middleware, GitHub Actions (buildâ†’GHCRâ†’SSH deployâ†’health-check; pytest non-blocking), Trivy/promptfoo/Alembic-drift workflows (advisory), pre-commit (ruff/bandit/detect-secrets/hadolint), self-heal cron, nightly pg_backup + monthly restore-drill, fail2ban + unattended-upgrades. SOPS/age scaffold present; live `.env` still plaintext.

**Verdict on A:** This is a **$1M-ARR-capable architecture being run at pre-revenue scale**. The engineering is ahead of the monetization. That asymmetry defines every recommendation below.

---

## SECTION B â€” Gap Analysis

### B.1 Method: three buckets

To honor your #1 rule (no duplicates), every candidate gap is sorted into:
- **ðŸŸ¢ Already on your radar** (documented in your own gap docs / rejected list) â€” *not re-recommended*, only sequenced.
- **ðŸŸ¡ Partially present** â€” built but off/unverified, or covered by a weaker custom version.
- **ðŸ”´ Genuine blind spot** â€” not meaningfully addressed anywhere in your docs.

### B.2 The genuine blind spots (ðŸ”´ â€” your real gaps)

| # | Gap | Why it's genuinely missing | Severity |
|---|-----|---------------------------|----------|
| 1 | **Dedicated agent memory** (cross-session, temporal, per-lead/per-client recall) | You have RAG (`kb_main`) and optional LightRAG, but no memory layer that records "what this lead said 3 weeks ago / how their intent changed." RAG â‰  memory. | High (product quality + moat) |
| 2 | **LLM tracing + CI-gated regression evals** | `agent_tester.py` is ad-hoc; promptfoo is advisory; `ENABLE_LLM_OBS` + OTelâ†’Tempo are wired-OFF. No span-level LLM trace in Grafana, no eval gate that *blocks* a bad prompt/RAG change. | High (reliability of the AI itself) |
| 3 | **MCP-as-a-product + A2A interop** | MCP server is internal-only. The 2026 MCP/A2A ecosystem (97M+ monthly SDK downloads, 150+ orgs on A2A) is a distribution + revenue channel you are not on. | High (revenue + moat) |
| 4 | **Per-tenant unit economics** (cost/LLM/minute attribution per customer) | Custom meter tracks usage, but there is no cost-per-customer view to defend gross margin on outcome-based pricing. | Medium (margin discipline) |
| 5 | **Cheap warm-DR / origin protection** | Single VPS = single point of failure. You know this and (correctly) defer a 2nd full VPS â€” but the *cheap* mitigations (Cloudflare origin-hide + logical-replication DR to a free/near-free target) are not in place. | High (survival risk) |

### B.3 Already on your radar (ðŸŸ¢ â€” do NOT re-recommend; just sequence)

Your own docs already cover, and in many cases correctly defer: HA/auto-failover & 2nd node (spend-blocked), PITR activation, R2/B2 offsite, SOPS secrets encryption, pytest-blocking CI gate + image-CVE gate, staging-in-pipeline, k6 load + chaos testing, Tempo/OTel instrumentation, Celery-exporter/Flower, customer-facing 2FA + webhooks, Alembic-as-sole-schema cutover, WAF (Cloudflare), DSAR endpoint, multi-carrier auto-failover, DLT/Exotel KYC. **These are execution items, not discoveries.** The audit's job is not to repeat them.

### B.4 The maturity map: what high-growth AI SaaS adds per stage

This places you on the industry curve. **You are at the $0â€“$10k MRR stage but already carrying $1M-ARR-stage engineering â€” your gap is the opposite of normal.**

**$0â€“$10k MRR (you are here):** single VPS + Compose, free-stack AI, Postgres/Redis/vector/Celery, Cloudflare free (DDoS/WAF), basic outreach, *working* payments, JSONL meter. â†’ *Your only true misses here: live payments, Cloudflare, error tracking.*

**$10kâ€“$100k MRR:** Cloudflare Pro WAF rules; vector consolidation (pgvector) or managed PG; PG replica / warm standby; product analytics (PostHog) + error tracking (Sentry) ON; entitlement enforcement as custom meter cracks; on-call escalation (BetterStack/PagerDuty) beyond Gatus; first eval gates.

**$1M ARR:** second region / dedicated box; Postgres HA (Patroni/managed); LiteLLM cost-routing ON; Stripe Tax/GST at scale; hardened authz; CDN for assets; DLT/KYC fully live.

**$10M ARR:** multi-AZ managed cloud (VPS retired); event streaming for billing audit (Redpanda/Kafka) at millions of events/day; dedicated metering (Orb/Metronome); SOC2 Type II + DPDP DPA tooling; feature-flag platform; infra team + SLOs.

The strategic read: **don't build $1M-ARR infra before $100k MRR.** Several of your wired-but-off systems are $1M-stage tools you pre-built; keeping them *off until the revenue stage that needs them* is the disciplined move, not a gap.

---

## SECTION C â€” Infrastructure Bottlenecks (ranked by blast radius)

1. **Single VPS = single point of failure (SPOF).** Every container shares one host: app, DB, RedisÃ—2, Qdrant, Celery, FreeSWITCH, 8 observability containers. One disk/kernel/noisy-neighbor event = total outage *and* observability blindness (your monitors die with the host). This is the #1 systemic risk. *Mitigation is cheap before it is expensive (see F).*
2. **RAM contention on a shared 16 GB host.** ~13 containers + baked ML (fastembed 241 MB, torch-CPU, faster-whisper) + Qdrant + 2Ã— Redis. Every new container (Phoenix, FalkorDB, MinIO, LiteLLM) competes for the same RAM. This is why "consolidate, don't add" beats "add a tool" almost every time here.
3. **Activation debt as reliability risk.** 25+ wired-but-off paths = untested-in-prod code. The first time `PLAN_RATE_LIMIT`, `REQUEST_GUARD`, or LiteLLM is switched on under load is a latent incident. Bottleneck = lack of a *staged activation + verification* discipline.
4. **LLM provider rate-limits (TPD) on heavy days.** Documented Groq/Cerebras daily-token exhaustion. The circuit-breaker handles failover, but without semantic cache ON and tracing, you can't see or pre-empt it. Caching + trace = direct resilience.
5. **Payments dead (Razorpay placeholder keys).** Not "infra" in the classic sense, but it is the literal bottleneck between all this engineering and â‚¹1 of revenue. Highest business-blast-radius item in the repo.
6. **Voice critical-path latency coupling.** STTâ†’LLMâ†’TTS on the same host as DB/Celery/observability means a Celery storm or backup job can add jitter to live calls. Per-process circuit-breaker/semaphore state (vs shared) is a known scaling edge you've deferred â€” correct for now, but it's the bottleneck that bites first when voice scales.

---

## SECTION D â€” Top 10 Repositories Worth Adopting

Scoring 1â€“10 (P=Production-readiness, S=Scalability, A=Automation, R=Reliability, M=Competitive-moat, C=Complexity â€” *lower C is better*). "Additive?" answers your duplicate test directly.

| # | Repo / Tool | P | S | A | R | M | C | Resource fit (16 GB VPS) | Verdict vs your stack | Additive or duplicate? |
|---|-------------|---|---|---|---|---|---|--------------------------|----------------------|------------------------|
| 1 | **cloudflare/cloudflared** (Tunnel + Turnstile) | 9 | 10 | 7 | 9 | 6 | 3 | ~50 MB, reuses Caddy | **ACTIVATE** (token already wired) | Additive â€” closes WAF/DDoS/origin-hide blind spot |
| 2 | **traceloop/openllmetry** (LLM OTel SDK) | 8 | 8 | 7 | 8 | 5 | 2 | 0 new container, rides existing Tempo | **ADOPT/COMPLEMENT** | Additive â€” fills LLM-trace gap, no new datastore |
| 3 | **confident-ai/deepeval** (CI eval) | 8 | 6 | 9 | 8 | 7 | 3 | runs in CI, free judge LLM | **ADOPT/COMPLEMENT** | Additive â€” RAG/LLM regression gate (â‰  promptfoo) |
| 4 | **mem0ai/mem0** (agent memory, Qdrant-only mode) | 8 | 8 | 7 | 8 | 7 | 5 | reuses existing Qdrant, low RAM | **ADOPT/COMPLEMENT** | Additive â€” you have no memory layer |
| 5 | **BerriAI/litellm** (LLM gateway) | 9 | 7 | 8 | 8 | 6 | 5 | ~500 MB, reuses PG+Redis | **ACTIVATE** (already on VPS) | Complement â€” per-tenant cost keys; *not* a circuit-breaker replacement |
| 6 | **pgvector + timescale/pgvectorscale** | 8 | 8 | 7 | 9 | 6 | 4 | inside existing PG, âˆ’1 container | **REPLACE Qdrant** (when corpus grows) | Additive-then-consolidating; cuts a container |
| 7 | **pydantic/pydantic-ai** (typed leaf agents) | 8 | 7 | 7 | 8 | 5 | 4 | in-process, FastAPI-native | **COMPLEMENT** (leaf-agent layer only) | Additive â€” does not touch your coordinator |
| 8 | **MCP billing gateway + A2A Agent Card** | 6 | 7 | 6 | 6 | 9 | 6 | small proxy container | **ADOPT** (new product surface) | Additive â€” monetizes existing MCP server |
| 9 | **HKUDS/LightRAG + FalkorDB** (graph RAG) | 7 | 7 | 6 | 7 | 7 | 6 | FalkorDB ~300 MB | **ACTIVATE + pilot one niche** | Additive â€” LightRAG already wired-off |
| 10 | **getsentry/sentry** + **PostHog (cloud free tier)** | 9 | 9 | 7 | 8 | 5 | 3 | Sentry SDK ~0; PostHog cloud = 0 VPS RAM | **ACTIVATE** (both wired) | Additive â€” error tracking + product analytics |

**Two non-obvious calls in this table:** (6) you should *eventually replace* Qdrant with pgvector to cut a container and unify backup/HA â€” but only once corpus/operational pain justifies the migration; the win is consolidation, not QPS (your RAG latency is LLM-bound). (10) run PostHog as **cloud free tier, never self-hosted** â€” self-host needs ClickHouse, which would kill your VPS (your docs already flagged this; the nuance is *cloud yes, self-host no*).

---

## SECTION E â€” Top 10 Repositories Worth Ignoring

These are the items a generic consultant *would* push and that you should keep rejecting. Most you already rejected â€” included here to confirm the reasoning is sound and current as of 2026.

| # | Repo / Category | Why ignore (for THIS stack) | Duplicate of what you have |
|---|-----------------|-----------------------------|----------------------------|
| 1 | **Temporal / Inngest / Windmill / DBOS** (durable execution) | Heavy server (or paid) for a problem your event-sourced `process_engine` + Celery already solves at this scale | `process_engine` + Celery + dead-man trio |
| 2 | **n8n / Dify** (visual workflow/agent builders) | You'd embed a heavier platform that *is* your product; net complexity, lock-in | Your coordinator + automation suite |
| 3 | **Self-hosted Langfuse** | Needs ClickHouse â†’ VPS-killer; OpenLLMetryâ†’Tempo gives you traces free | Tempo/Grafana + OpenLLMetry (D#2) |
| 4 | **Self-hosted PostHog** | ClickHouse again; use the cloud free tier instead | PostHog Cloud (D#10) |
| 5 | **Kafka / Redpanda / NATS** (event streaming) | Millions-of-events/day infra at pre-revenue; outbox+Redis+Celery is correct until $10M ARR | Transactional outbox + Redis |
| 6 | **pgmq / River** (Postgres queues) | No win unless you drop Redis (you can't â€” it's cache+state+consent too) | Celery + Redis broker/DLQ |
| 7 | **maximhq/bifrost** (Go LLM gateway) | 11 Âµs vs 8 ms gateway overhead is irrelevant when free providers add 500 ms+; LiteLLM wins on ecosystem | LiteLLM (D#5) |
| 8 | **Keycloak / Authentik** (auth) | Heavy IDP for a need met by your JWT + 8-module RBAC + admin TOTP | Your auth/RBAC stack |
| 9 | **k8s / k3s + Coolify / Dokploy / Kamal** | Orchestration tax with no payoff until multi-node ($1M ARR+); Compose is correct | Docker Compose |
| 10 | **Letta(MemGPT) / AutoGen / DSPy / Graphiti-on-Neo4j / LanceDB / Orb-Metronome-Lago-OpenMeter** | Wrong weight, rejected, or premature: Neo4j too heavy, MemGPT rejected, dedicated metering not needed < $50k MRR, LanceDB no migration win vs pgvector | Mem0 + custom coordinator + custom meter |

**Net:** your rejection instincts are correct and remain correct in 2026. The only refinement: Mem0 (not Graphiti-on-Neo4j) for memory, and pgvector (not LanceDB) as the eventual vector consolidation.

## SECTION F â€” Highest-ROI Infrastructure Upgrades

Ranked by leverage. Each carries your required 7-field evaluation. "Effort" is solo-founder days.

### F.1 â€” Activate Cloudflare Tunnel + Turnstile  Â·  Effort: ~0.5 day  Â·  Cost: â‚¹0
- **Why it matters:** Removes your single largest non-spend risk â€” origin-IP exposure + zero DDoS/WAF in front of a single VPS. Turnstile on `/audit`, `/site-audit`, `/demo`, `/start` kills bot form-spam that pollutes your lead pipeline.
- **Why now:** The token env is already wired; the only reason it's off is an unset value. It is the cheapest survival insurance you can buy and it protects the lead magnets that feed revenue.
- **Expected ROI:** Effectively infinite (â‚¹0 cost, prevents outage + junk-lead cost). Cleaner lead data also lifts every downstream conversion metric.
- **Operational impact:** +1 tiny container (~50 MB), no Caddy change, origin IP hidden. Reduces your attack surface and incident probability.
- **Revenue impact:** Indirect but real â€” protects uptime of the funnel and the quality of harvested leads (your core product).
- **Complexity cost:** Minimal (3/10). One DNS move + one env var.
- **Additive or duplicate:** Additive â€” closes a documented blind spot; nothing in your stack does edge WAF/DDoS today.

### F.2 â€” Unblock revenue: Razorpay live keys + Sentry + PostHog  Â·  Effort: ~1 day  Â·  Cost: â‚¹0
- **Why it matters:** Payments are the literal bottleneck between your engineering and cash. Sentry/PostHog are wired-off, so you are flying blind on errors and user behavior the day a customer arrives.
- **Why now:** First paid customer cannot transact without it. The proven root cause is placeholder keys, not a code bug â€” a pure config fix. Sentry/PostHog need only API keys.
- **Expected ROI:** Direct â€” enables 100% of monetization. PostHog funnel data typically finds 10â€“30% conversion lift opportunities in the first month.
- **Operational impact:** Sentry SDK = ~0 RAM; PostHog cloud free = 0 VPS RAM; Razorpay = config + webhook register.
- **Revenue impact:** Maximal â€” gates all revenue. Dunning/topup/checkout all dead until fixed.
- **Complexity cost:** Low (3/10).
- **Additive or duplicate:** Additive (activation). No duplication â€” you have no error tracker or product analytics live.

### F.3 â€” LLM tracing + eval gate: OpenLLMetryâ†’Tempo + DeepEval-in-CI  Â·  Effort: ~2 days  Â·  Cost: â‚¹0
- **Why it matters:** Your AI *is* the product, yet it's the least observed layer. You can see CPU but not why a niche script regressed. DeepEval gives you a *blocking* quality gate; OpenLLMetry gives span-level LLM traces in the Grafana you already run.
- **Why now:** You flagged formal evals as a real gap; `self_improve` and `code_upgrader` mutate behavior continuously â€” without an eval gate, autonomous changes can silently degrade quality. This is the safety rail for your own automation.
- **Expected ROI:** High â€” prevents quality regressions that churn customers; turns "it feels worse" into a number. Reuses existing Tempo (zero new infra).
- **Operational impact:** 0 new containers; ~5 lines in `free_ai.py` + ~10 CI test cases using your free judge LLM (Cerebras/Groq).
- **Revenue impact:** Retention/quality â€” protects the qualified-lead outcome you bill on.
- **Complexity cost:** Low (2â€“3/10).
- **Additive or duplicate:** Additive â€” DeepEval (RAG/output regression) is genuinely different from promptfoo (adversarial prompts); OpenLLMetry fills the trace gap your in-house module only partially covers.

### F.4 â€” Agent memory layer: Mem0 on existing Qdrant  Â·  Effort: ~3 days  Â·  Cost: â‚¹0
- **Why it matters:** "The agent remembers what this lead/client said before" is a product-quality and moat feature you cannot get from RAG over `kb_main`. It compounds your proprietary outcome data.
- **Why now:** Cheapest to add now while the data model is simple; retrofitting memory across 14 agents later is far harder. Runs in Qdrant-only mode on the Qdrant you already operate.
- **Expected ROI:** High on conversion (personalized follow-ups, voice continuity across calls) and a durable differentiator vs generic competitors.
- **Operational impact:** Reuses existing Qdrant; minimal RAM; one SDK + a write/read hook in the agent brain.
- **Revenue impact:** Direct on the voice "qualified-lead" product â€” memory lifts qualification and re-engagement rates.
- **Complexity cost:** Medium (5/10).
- **Additive or duplicate:** Additive â€” no memory layer exists; Mem0 (not heavy Graphiti-on-Neo4j) respects your VPS.

### F.5 â€” Cheap warm-DR + per-tenant cost via LiteLLM  Â·  Effort: ~3â€“4 days  Â·  Cost: ~â‚¹0â€“400/mo
- **Why it matters:** Two leverage points at once. (a) A *cheap* answer to the SPOF that isn't a full 2nd VPS: Postgres logical replication / nightly restore to a free-tier managed PG (Neon/Supabase free) or a â‚¹400 box = warm DR target + read replica. (b) Activating LiteLLM gives per-tenant virtual keys â†’ cost-per-customer in Postgres â†’ real gross-margin visibility for outcome-based pricing.
- **Why now:** DR is insurance you want *before* the first paying customer's data is irreplaceable. LiteLLM is already on the VPS.
- **Expected ROI:** DR = catastrophic-loss avoidance; LiteLLM cost attribution = margin protection on every deal (prevents underpricing a heavy niche).
- **Operational impact:** LiteLLM +500 MB (reuses PG+Redis); DR target is off-box (no VPS RAM). Note LiteLLM *complements*, does not replace, your free-stack circuit-breaker â€” run it as the gateway, keep your breaker logic.
- **Revenue impact:** Margin discipline â†’ defensible pricing; DR â†’ survival of billable data.
- **Complexity cost:** Medium (5â€“6/10).
- **Additive or duplicate:** Additive â€” no DR replica or per-tenant cost view exists; LiteLLM activation overlaps the breaker only partially (gateway vs failover policy).

### F.6 â€” Sequence (don't skip) the items already in your docs
PITR `--apply`, SOPS-encrypt the live `.env`, make pytest a *blocking* deploy gate + image-CVE scan, wire staging into the pipeline, turn on `SEMANTIC_CACHE` (rate-limit + latency win even with free LLMs) and add a cache hit/miss Prometheus counter. These are ðŸŸ¢ known â€” the ROI is in *finishing* them, and `SEMANTIC_CACHE` + SOPS are the two highest-value among them.

---

## SECTION G â€” Advanced Automation Opportunities

You already run rare automation (self-improve loop, code_upgrader, 14-agent staff). The gaps are *closed-loop quality and safety*, not more automation.

1. **Close the self-improvement loop with evals (highest leverage).** Today `self_improve` + `code_upgrader` change behavior; nothing automatically scores whether the change *helped*. Wire DeepEval (F.3) as the reward/gate signal: proposal â†’ eval on a frozen niche test set â†’ auto-accept only if score â‰¥ baseline, else auto-reject. This turns open-loop autonomy into a safe, compounding optimizer. *Additive, not duplicate â€” it's the missing feedback edge on systems you already run.*
2. **Eval-gated prompt/RAG canary.** Before a niche-script or KB change goes live, run it against the eval set + 5% shadow traffic; promote on win. Uses existing staging + DeepEval. Prevents the "silent regression" risk your autonomy creates.
3. **Cost-aware LLM routing via LiteLLM.** Route cheap/simple turns to the fastest free provider and reserve the strongest model for hard turns, using LiteLLM policies + your existing `budget_guard`. Automation that protects both latency and rate-limits.
4. **Auto-DR drill verification (extend, don't rebuild).** You have a monthly restore-drill; add an automated *content-integrity assertion* + alert + a quarterly failover rehearsal to the cheap warm-DR target. Converts backups into *tested* recoverability.
5. **MCP/A2A inbound automation.** Once the metered MCP endpoint exists (F/H), external agents can trigger your lead-gen/qualification flows programmatically â€” a fully automated B2B revenue channel with no human in the loop. This is the single most "billionaire-scale" automation available to you because it scales revenue without scaling your time.
6. **Activation-debt burndown as an automated checklist.** Encode the wired-but-off registry (`/api/growth/infra/flags`) into a scheduled "activation readiness" report that nags with a verify-checklist per flag. Turns latent risk into managed rollout.

---

## SECTION H â€” Recommended Engineer-Agent Team

You already have platform agents (Kavya=health, Hermes=infra, Vikram=code_upgrader, hostinger_hermes). So the test is strict: **add a specialized engineer agent only if it creates measurable operational leverage your current roster does not.** Verdict per discipline:

| Discipline | Build a dedicated agent? | Rationale (leverage test) |
|------------|--------------------------|---------------------------|
| **Reliability / SRE** | âœ… **Yes â€” highest value** | Kavya does health checks, but no agent owns DR drills, restore-integrity, capacity baselines, SLO/error-budget tracking. On a SPOF VPS this is the agent that prevents fatal outages. Measurable: MTTR, backup-verify pass-rate, capacity headroom. |
| **Cost / FinOps** | âœ… **Yes â€” revenue-linked** | No agent owns per-tenant unit economics. With LiteLLM keys (F.5) an agent can compute cost-per-customer, flag margin-negative niches, and recommend price/quota changes. Directly defends gross margin. |
| **Security / Compliance** | âœ… **Yes â€” India-specific** | Spread across pre-commit/Trivy today, but no agent owns DPDP/TRAI posture, secret-rotation, CVE triageâ†’patch proposal, DSAR handling. High regulatory blast radius (â‚¹10L TRAI penalties). |
| **Observability** | ðŸŸ¡ **Fold into SRE agent** | A standalone obs agent is premature; give the SRE agent ownership of dashboards/alert-tuning + OpenLLMetry trace review. Don't create a separate role. |
| **Data / Knowledge** | ðŸŸ¡ **Yes, lightweight** | One agent to own KB freshness, embedding drift, eval-set curation, and (new) memory hygiene. Justified by your RAG+memory roadmap; keep it part-time. |
| **DevOps / Release** | âŒ **No â€” covered** | `code_upgrader` + FDE + GitHub Actions already cover this. A new agent would duplicate. |
| **Performance** | âŒ **No â€” premature** | Real value only when voice traffic scales; fold perf checks into SRE agent until then. |
| **Infrastructure (provisioning)** | âŒ **No â€” covered** | Hermes/hostinger_hermes already own infra. Don't duplicate. |

**Recommended additions: exactly three new agents** â€” **SRE/Reliability**, **FinOps/Cost**, **Security/Compliance** â€” plus a lightweight **Knowledge/Memory** steward folded into existing cadence. Each maps to a measurable KPI (MTTR, gross-margin-per-tenant, compliance-posture score, eval-pass-rate). Resist a larger org chart: more agents = more token burn + coordination overhead, which your own CLAUDE.md warns against. *Additive, non-duplicative, KPI-bound â€” passes the leverage test; everything else is folded or deferred.*

---

## SECTION I â€” Future-Proof Architecture Blueprint

The target is **"consolidate the core, distribute only the risk, monetize the edge"** â€” not "add more boxes."

**Layer 1 â€” Edge (new, cheap):** Cloudflare in front of everything (Tunnel + WAF + Turnstile + cache). Origin IP hidden. This is your DDoS/bot moat and your first step toward multi-origin later.

**Layer 2 â€” Compute (unchanged philosophy):** FastAPI monolith on Compose. Stay here until $1M ARR. Add a *second cheap origin* only for warm-DR/read-replica, fronted by Cloudflare load-balancing when revenue justifies â€” a gradual path to HA without a k8s leap.

**Layer 3 â€” Data (consolidate):** Postgres as the gravity center â€” business data **+ vectors (pgvector/pgvectorscale)** + queue-of-record for billing events, with logical replication to an off-box DR target. Redis stays for cache/state/broker. Retire Qdrant *into* Postgres when corpus pain appears. Net: fewer containers, unified backup/PITR/HA. Optional FalkorDB only if graph RAG proves out on a pilot niche.

**Layer 4 â€” AI (gateway + memory + evals):** Keep the free-stack circuit-breaker as policy; put **LiteLLM** as the gateway (cost keys, routing); add **Mem0** memory on Qdrant/pgvector; instrument with **OpenLLMetryâ†’Tempo**; gate every change with **DeepEval**. This is the layer that compounds your moat.

**Layer 5 â€” Agents (closed-loop):** Existing coordinator/process_engine/self_improve, now with an **eval reward signal** and **Pydantic AI** typed leaf-agents for testability. Three new engineer agents (SRE/FinOps/Security).

**Layer 6 â€” Distribution & revenue (new moat):** Metered **MCP endpoint + A2A Agent Card** exposing your 42-niche qualification capability as a programmatic product. Outcome-based billing (already your voice model) extended platform-wide. This is the layer a competitor cannot copy because it sits on your proprietary outcome data.

**Layer 7 â€” Observability (finish it):** Activate OTelâ†’Tempo, Celery-exporter/Flower, semantic-cache metrics, payment-gateway probe. One Grafana pane spanning infra + LLM + cost + business KPIs.

**Design invariants:** every new capability must (a) reuse Postgres/Redis/Qdrant or run off-box, (b) survive single-host loss via the DR target, (c) be eval-gated if it touches AI behavior, (d) carry a kill-switch flag in the registry. These four rules keep complexity flat as capability grows.

---

## SECTION J â€” Final Optimized Billionaire-Scale SaaS Stack

The end-state, expressed as the minimum that maximizes leverage. **Bold = change from today.** Everything else = keep.

- **Edge:** **Cloudflare (Tunnel + WAF + Turnstile + CDN)** â†’ Caddy â†’ FastAPI.
- **Compute:** FastAPI monolith on Docker Compose (single origin now â†’ **+1 cheap warm-DR origin** at $10kâ€“100k MRR â†’ managed multi-AZ only at $10M ARR).
- **Datastore:** Postgres 16 (+ PgBouncer) as the core â€” business + **vectors (pgvector/pgvectorscale)** + billing queue-of-record + **logical-replication DR**; Redis Ã—2 (broker/state/cache); Qdrant **retired into pgvector when justified**; **FalkorDB only if graph-RAG pilot wins**.
- **Async:** Celery (worker+beat) + event-sourced `process_engine` + dead-man trio. **No Temporal/Kafka** until $10M ARR.
- **AI:** Free-stack failover breaker **+ LiteLLM gateway (cost keys/routing) + Mem0 memory + OpenLLMetry traces + DeepEval gate + semantic cache ON**. STT Groq Whisper, TTS EdgeTTS unchanged.
- **Agents:** Coordinator / process_engine / self_improve **closed-loop with eval reward** + **Pydantic AI leaf-agents** + 14 staff + **3 new engineer agents (SRE, FinOps, Security)** + lightweight Knowledge/Memory steward.
- **Distribution/Revenue:** Razorpay **live** + GST + custom meter + **per-tenant cost attribution** + **metered MCP endpoint + A2A Agent Card** + outcome-based billing.
- **Observability:** Prometheus/Grafana/Loki/Tempo/Alertmanager **fully instrumented (OTel + Celery-exporter + LLM traces + cost + business KPIs)** + Gatus/Uptime-Kuma + **off-box uptime + on-call escalation** at $10k+ MRR.
- **Security/Compliance:** JWT+RBAC+TOTP + **SOPS-encrypted secrets** + **blocking CI (pytest + image-CVE)** + DPDP/TRAI agent + **customer 2FA** at $10k+ MRR.

**The one-sentence thesis:** *Turn on what you've already built, add exactly five genuinely-missing capabilities (edge protection, agent memory, LLM evals/traces, cheap DR, MCP-as-product), keep rejecting the heavy generic tooling â€” and your moat becomes the 42-niche outcome data that no competitor can replicate, monetized through a programmatic channel that scales revenue without scaling your hours.*

---

## Prioritized 90-Day Roadmap (so this is executable, not theoretical)

**Week 1 (â‚¹0, unblock + protect):** Razorpay live keys + webhook Â· Cloudflare Tunnel + Turnstile Â· Sentry + PostHog ON. â†’ *Revenue possible + origin protected + visibility.*
**Weeks 2â€“3 (AI safety + cache):** OpenLLMetryâ†’Tempo Â· DeepEval CI gate Â· `SEMANTIC_CACHE` ON + metrics Â· SOPS-encrypt `.env`. â†’ *AI observed, gated, cached, secrets safe.*
**Weeks 4â€“6 (memory + margin + DR):** Mem0 on Qdrant Â· LiteLLM activate (cost keys) Â· warm-DR replica off-box Â· PITR `--apply`. â†’ *Product depth + margin view + survivable.*
**Weeks 7â€“10 (moat + agents):** Metered MCP endpoint + A2A Agent Card Â· SRE + FinOps + Security engineer agents Â· close the self-improve eval loop. â†’ *New revenue channel + safe autonomy.*
**Weeks 11â€“13 (finish + measure):** pytest blocking gate + image-CVE Â· Celery-exporter/Flower Â· pgvector migration spike (if corpus warrants) Â· single Grafana exec pane. â†’ *Hardened, consolidated, instrumented.*

---

## Sources (external landscape, 2025â€“26)

Agent memory & orchestration: Mem0 ([mem0ai/mem0](https://github.com/mem0ai/mem0), [$24M Series A](https://finance.yahoo.com/news/mem0-raises-24m-series-build-170000229.html), [self-host Docker](https://mem0.ai/blog/self-host-mem0-docker)) Â· Graphiti/Zep ([getzep/graphiti](https://github.com/getzep/graphiti), [FalkorDB integration](https://www.falkordb.com/blog/graphiti-falkordb-multi-agent-performance/), [arXiv 2501.13956](https://arxiv.org/abs/2501.13956)) Â· Cognee ([topoteretes/cognee](https://github.com/topoteretes/cognee)) Â· Hatchet ([hatchet-dev/hatchet](https://github.com/hatchet-dev/hatchet), [vs Celery](https://hatchet.run/versus/hatchet-vs-celery)) Â· Pydantic AI ([vs LangChain 2026](https://oss.vstorm.co/blog/pydantic-ai-vs-langchain/)) Â· MCP/A2A ([MCP ecosystem 2026](https://chatforest.com/guides/mcp-ecosystem-2026-state-of-the-standard/), [MCP gateways](https://www.mintmcp.com/blog/gateway-saas-with-mcp), [monetize MCP](https://godberrystudios.com/posts/how-to-monetize-mcp-servers-2026/), [A2A 150+ orgs](https://stellagent.ai/insights/a2a-protocol-google-agent-to-agent)).

LLMOps & observability: LiteLLM ([cost tracking](https://docs.litellm.ai/docs/proxy/cost_tracking), [virtual keys](https://successknocks.com/litellm-virtual-keys-best-practices-secure/)) Â· Bifrost ([maximhq/bifrost](https://github.com/maximhq/bifrost)) Â· OpenLLMetry ([traceloop/openllmetry](https://github.com/traceloop/openllmetry), [Grafana/Tempo integration](https://www.traceloop.com/docs/openllmetry/integrations/grafana)) Â· Arize Phoenix ([2026 guide](https://qaskills.sh/blog/arize-phoenix-llm-evaluation-guide)) Â· DeepEval ([deepeval.com](https://deepeval.com/), [vs promptfoo/ragas](https://genai.qa/blog/promptfoo-vs-deepeval-vs-ragas/)) Â· semantic caching ([2026 solutions](https://www.getmaxim.ai/articles/top-semantic-caching-solutions-for-ai-applications-in-2026/)).

Data, vector, billing & edge: pgvector/pgvectorscale vs Qdrant ([Encore 2026](https://encore.dev/articles/pgvector-vs-qdrant), [benchmarks 2026](https://callsphere.ai/blog/vector-database-benchmarks-2026-pgvector-qdrant-weaviate-milvus-lancedb)) Â· LanceDB ([lancedb/lancedb](https://github.com/lancedb/lancedb)) Â· Apache AGE ([Azure overview](https://learn.microsoft.com/en-us/azure/postgresql/azure-ai/generative-ai-age-overview)) Â· FalkorDB graph RAG ([falkordb](https://www.falkordb.com/news-updates/data-retrieval-graphrag-ai-agents/)) Â· pgmq ([pgmq/pgmq](https://github.com/pgmq/pgmq)) Â· usage billing 2026 ([solvimon](https://www.solvimon.com/blog/best-usage-based-billing-2026), [metered AI agents](https://www.buildmvpfast.com/blog/metered-billing-ai-agents-usage-based-pricing-agent-workload-2026)) Â· Cloudflare Tunnel/Turnstile ([guide](https://1vps.com/cloudflare-tunnel-vps-guide/), [Turnstile](https://davidmuraya.com/blog/cloudflare-turnstile-invisible-bot-protection/)) Â· self-hosting repos 2026 ([cognyx](https://www.cognyx.ai/blog/self-hosting-2026-top-github-repositories)) Â· SaaS ARR milestones ([baremetrics](https://baremetrics.com/blog/how-fast-saas-companies-hit-arr-milestones)).

*Internal grounding: CLAUDE.md + docs/SAAS_INFRA_TRUTH_AND_GAPS_2026_06_15.md, SAAS_INFRA_GAP_ADDITIVE_2026_06_15.md, Infra_BestStack_GapAnalysis_2026-06.md, Scale_Reliability_Audit_2026_06_15.md, INFRA_UPGRADE_2026.md, and the live docker-compose + requirements.lock.txt.*



---

# Appendix B - Folded from Scale_Reliability_Audit_2026_06_15.md (consolidated 2026-06-25)

# Scale & Reliability Audit â€” leadsgenai.in

**Date:** 2026-06-15 Â· **Auditor:** Backend systems review Â· **Scope:** Reliability + scalability of the live single-VPS stack
**Method:** Ground-truth code/config read (no theory). Har finding ke saath `file:line` evidence diya hai.

> **STATUS (2026-06-15): P0 + P1 + P2 (safe subset) IMPLEMENTED in repo** (deploy-pending).
> **P0** â€” `Dockerfile.lock` (proxy-headers), `app/middleware/__init__.py` (XFF), `docker-compose.vps.yml` (redis-cache + noeviction), `app/cache/__init__.py` (cache client + fail-soft), `.env.example`.
> **P1** â€” `docker-compose.vps.yml` (8 services pe mem/cpu limits, VPS 16GB/4-core), `app/models/base.py` (DB pool 50â†’10/process), `app/api/health.py` (`/metrics`: LLM provider-health + Celery queue-depth). Detail "P1 implementation notes".
> **P2** â€” `app/billing/lead_usage.py` (meter-failure observable+recoverable), `app/api/health.py` (`/metrics` CPU non-blocking), `app/main.py` (dev-only reload), `app/models/base.py` (`DB_CREATE_ALL` schema gate). Detail "P2 implementation notes". 2 P2 items DEFERRED-with-rationale (wahi section). Sab backwards-compatible. Deploy + rollback "Deploy handoff" me.

---

## TL;DR (verdict)

Foundation **strong hai** â€” async-clean code (httpx everywhere, sync I/O event-loop pe nahi), durable Celery config, fail-open degradation discipline, baked ML models, real health probes, Prometheus+Alertmanager wired, prod-down lessons code me visible. Yeh ek mature codebase hai.

Lekin **scale pe 2 latent landmines** hain jo aaj low-traffic pe chhupe hain aur **load badhte hi exactly tab fatenge jab tum scale karoge**:

1. **Ek hi Redis** broker + live-call-state + cache + rate-limit sab ke liye, `allkeys-lru` eviction ke saath â†’ memory pressure pe **queued Celery tasks aur live call-state silently evict** ho sakte (no error, just loss).
2. **Global rate-limiter proxy-IP pe key karta hai** (uvicorn me `--proxy-headers` nahi) â†’ poori site ek hi `100/min + 2000/hr` bucket share karti â†’ **hardware chahe kitna bhi ho, throughput yahà¥€à¤‚ capped**.

Dono ka fix chhota hai (~1 din total). Inke bina horizontal scaling ka koi matlab nahi â€” bottleneck hardware me nahi, in 2 jagah hai.

---

## Scorecard

| Dimension | Grade | One-line |
|---|---|---|
| Code-level async hygiene | **A** | httpx async, ML off-loop, sync-DB routes me nahi |
| Fault tolerance (app) | **B+** | Circuit-breaker + fail-open solid; state per-process |
| Data/state durability | **C** | Redis eviction broker/call-state ko risk me daalti |
| Horizontal scalability | **C-** | Rate-limit global-IP cap + over-sized DB pools |
| Resource isolation | **C** | Single VPS, **zero container mem/cpu limits** |
| Observability | **B-** | Stack wired, par RED metrics + LLM-health export missing, traces unwired |
| Ops readiness | **B** | Health probes, self-heal, backups; schema-mgmt drift |

---

## P0 â€” Fix before any scale-up / first paid load

### P0-1 Â· Single Redis with `allkeys-lru` = silent task & call-state loss
**Evidence:** `docker-compose.vps.yml:155-156` (`--maxmemory 512mb`, `--maxmemory-policy allkeys-lru`); broker+backend = same instance `app/worker.py:19-21` (`broker=settings.redis_url`); cache/rate-limit/lock/call-state sab `redis://redis:6379/0` (`docker-compose.vps.yml:56`, `app/cache/__init__.py:28-33`).

**Problem:** Ek hi Redis instance, ek hi logical DB (`/0`), 512MB cap, `allkeys-lru` policy. Yeh Redis simultaneously:
- Celery **broker** (queued tasks) + **result backend**
- **DLQ** (`dlq:failed_tasks`, `worker.py:176`)
- **Distributed call-state** (live phone/web calls)
- **Rate-limit** counters + **distributed locks** + **Cache**

`allkeys-lru` ka matlab: memory full hote hi Redis **kisi bhi key** ko evict karega â€” including queued Celery tasks aur live call-state. Celery + Redis broker pe eviction policy = **upstream-documented data-loss bug** (broker Redis hamesha `noeviction` hona chahiye). Aaj 512MB shayad bharti nahi, isliye chhupa hai â€” par traffic/cache badhte hi yeh **bina error ke** tasks aur calls khaa jayega.

**Fix (do-step):**
- **Quick (1 line, aaj):** broker Redis ko `--maxmemory-policy noeviction` karo. Cache keys pe already TTL hai (`Cache default_ttl=300`), to woh khud expire honge; broker/lock keys (no TTL) kabhi evict nahi honge. Saath me `Cache.set()` ko fail-soft wrap karo (OOM pe write-fail = cache-miss, raise nahi).
- **Proper (~half day):** alag `redis-cache` container (apna `allkeys-lru` + maxmemory) sirf `Cache` class ke liye (`CACHE_REDIS_URL`); existing Redis `noeviction` pe broker+call-state+rate-limit+DLQ ke liye reserved. Roles physically alag = eviction kabhi critical state ko touch nahi karti.

**Effort:** Quick 30 min Â· Proper 0.5 din. **Impact:** Eliminates silent task/call loss at scale.

---

### P0-2 Â· Global rate-limiter proxy-IP pe â€” poori site ek bucket me
**Evidence:** `app/middleware/__init__.py:193` (`client_ip = request.client.host`); uvicorn CMD me proxy-headers nahi â€” `Dockerfile.lock:72` (`uvicorn ... --workers ... --timeout-keep-alive 30`); repo-wide `--proxy-headers`/`forwarded-allow-ips` ka **zero** match.

**Problem:** App Caddy ke peeche hai (`127.0.0.1:8000`). Bina `--proxy-headers` ke, `request.client.host` = Docker gateway/Caddy ka IP â€” **sabhi external users ke liye ek hi constant IP**. `RateLimitMiddleware` (production pe active, `middleware/__init__.py:373-378`) us constant IP pe `100/min + 2000/hr` cap lagati. Matlab:
- **Poora platform collectively ~33 req/min pe throttled** (2000/hr / 60). Thode dashboard users (har page XHR-heavy) milke 429 trip kar denge â€” **VPS chahe khali ho**.
- Per-IP abuse protection bhi dead (sab ek bucket, attacker bhi legit users ke saath).

Note: dependency-based limiter (`app/api/ratelimit.py:31-39`) XFF **sahi** padhta hai â€” inconsistency confirm karta ki middleware galat hai.

**Fix:** uvicorn CMD me `--proxy-headers --forwarded-allow-ips="*"` add karo (safe: container port sirf `127.0.0.1` pe bound, sirf local Caddy pahunchta). Isse `request.client.host` = asli client IP ho jayega â€” middleware **aur** dependency limiter dono consistent. Defensively `RateLimitMiddleware._client_ip` me bhi XFF-first karo. Phir global cap (100/min) re-evaluate karo â€” authed dashboard API ke liye higher limit ya path-exempt.

**Effort:** 1 line + redeploy. **Impact:** Throughput ceiling hata, real per-IP protection wapas. **Verify:** do alag `X-Forwarded-For` se hit karo â€” counters alag hone chahiye.

---

## P1 â€” Fix in the next 1â€“2 weeks

### P1-1 Â· Zero container resource limits on a shared single VPS
**Evidence:** `docker-compose.vps.yml` me koi `mem_limit`/`cpus`/`deploy.resources` nahi (grep-confirmed). 13+ containers ek box pe.

**Problem:** Koi bhi ek container (ML load spike, memory leak, runaway job) saara RAM khaa ke **Postgres/Redis ko OOM-kill** kar sakta â€” cascading outage. Celery me `worker_max_memory_per_child=512MB` hai (`worker.py:100`) par woh **per-child** hai, container-level cap nahi.

**Fix:** Har service pe caps lagao, actual VPS RAM ke hisaab se (`free -h` dekho). Template (Compose v2 non-swarm):
```yaml
app:        { mem_limit: 1500m, cpus: "1.5" }
db:         { mem_limit: 1g,    cpus: "1.0" }   # shared_buffers 256m ke saath consistent
redis:      { mem_limit: 700m }                  # 512m maxmemory + overhead
worker:     { mem_limit: 1g,    cpus: "1.0" }
worker-heavy:{ mem_limit: 1500m, cpus: "1.0" }
```
Postgres ko OOM-killer se bachane ke liye uska limit reserved + generous rakho. **Effort:** 1â€“2 ghante (+ ek load test).

### P1-2 Â· SQLAlchemy pools PgBouncer/Postgres budget se 3-4x bade
**Evidence:** async `pool_size=20, max_overflow=30` (=50/process) `app/models/base.py:85`; sync `pool_size=10, max_overflow=20` (=30) `base.py:49`; PgBouncer `POOL_MODE=session, DEFAULT_POOL_SIZE=25` `compose:132-135`; Postgres `max_connections=100` `compose:99`.

**Problem:** **Session** pooling mode me PgBouncer multiplexing nahi deta â€” har held client-conn = ek server-conn. 2 web workers Ã— async-pool 20 persistent = **40 held conns > 25 server pool** â†’ PgBouncer pe queueing; aur worker/scheduler/migration pools milake Postgres ke 100 cap ke kareeb. Contention pe `pool_timeout` (default 30s) tak request hang, phir 500.

**Fix:** Pools ko budget ke andar size karo â€” session mode me chhota = sahi:
```python
kwargs.update(pool_size=5, max_overflow=5, pool_recycle=1800, pool_timeout=10)
```
2 workers Ã— 10 = 20 â‰¤ PgBouncer 25 â‰¤ PG 100, baaki celery/migration ke liye headroom. (Ya PgBouncer ko `transaction` mode + asyncpg `statement_cache_size=0` â€” zyada multiplexing, par jyada change.) **Effort:** ~half din with a quick load test.

### P1-3 Â· Observability: RED metrics + LLM-health export missing; traces unwired
**Evidence:** `/metrics` LLM block **legacy `vertex_client`** se padhta (`app/api/health.py:340-343`) jabki asli data `app/platform/llm_metrics.py` me record hota (`free_ai.py:428-430`) â€” exported nahi. `RequestTracingMiddleware` duration **log** karta par histogram export nahi (`middleware/__init__.py:117-122`). OTel/Tempo: Tempo container chalta hai par app me koi OTel instrumentation nahi (grep: sirf `ENABLE_OTEL` flag-string).

**Problem:** Sabse valuable scale-signals Prometheus me nahi: **per-endpoint request-rate / error-rate / p95-p99 latency** (RED), **free_ai provider ok-rate/latency**, **Celery queue-depth**, **DB pool saturation**. Exported LLM metrics galat source se (stale). Tempo idle resource khaa raha. Scale pe partially blind.

**Fix:**
- `/metrics` LLM block ko `app.platform.llm_metrics` pe point karo (sahi source).
- RED histogram add karo â€” `prometheus-fastapi-instrumentator` (1 line) ya middleware me `Histogram`.
- Celery queue-depth gauge (`redis llen` per queue) + DB pool gauge (`engine.pool.checkedout()`) export karo.
- Tempo ya to OTel-instrument karo (`opentelemetry-instrumentation-fastapi`) ya stack se hatao. Sentry traces (10%) ab APM cover karta â€” Tempo optional.

**Effort:** 0.5â€“1 din. **Impact:** Scale pe actual visibility (p95, error-rate, provider-health, queue-backlog).

---

## P2 â€” Backlog (correctness/cost hygiene)

- **Schema-management drift** â€” boot pe `Base.metadata.create_all` (`base.py:249`) + hardcoded `ALTER` dict (`base.py:226-238`) + Alembic (`main.py:134-136`) teeno saath. `create_all` column-changes handle nahi karta; teen mechanism aapas me lad sakte. **Fix:** Alembic ko single source banao; prod me `create_all` dev/test-only gate karo. *(careful, medium effort)*
- **Call-admission semaphore per-process** â€” `asyncio.Semaphore(max_concurrent_calls=10)` (`telephony/call_manager.py:106-107`) worker-local hai (comment line 100). WEB_CONCURRENCY=2 â†’ effective cap **20, na ki 10**. Single box + FREE real-time STT/TTS pe yeh CPU saturate kar sakta (P1-1 ke no-cpu-limit ke saath compounding). Voice DLT-gated hai isliye P2, par voice launch se pehle distributed admission counter (Redis) + capacity test zaroori.
- **FAIL-OPEN billing meter** â€” infra-fail pe usage meter nahi hota (revenue leak) jabki call chalti rehti. Reliability ke liye sahi default, par ek **daily reconciliation job** add karo (call-logs vs metered-usage diff â†’ alert) taaki silent leak na ho.
- **Circuit-breaker state per-process** â€” `free_ai.py:112-115` module-global; har uvicorn/celery process apna dead-provider alag se seekhà¤¤à¤¾ â†’ NÃ— wasted probing. **Fix (optional):** cooldown state Redis me share karo.
- **`/metrics` public + `psutil.cpu_percent(interval=0.1)`** har scrape pe 100ms block + unauthenticated (`health.py:454`). **Fix:** interval=0 (non-blocking) + internal-network restrict.
- **`__main__` me `reload=True`** (`main.py:1277`) â€” agar koi prod me `python app/main.py` chala de to footgun. Guard ya hata do.

---

## What's already done right (credit Ð³Ð´Ðµ due)

- **Async hygiene excellent** â€” httpx 47 files, sync `requests.<verb>(` sirf 1, ML load `run_in_executor` me (`main.py:183`), routes async-DB only (`Depends(get_db)` sync = **0**). Event-loop blocking ka classic killer yahan nahi hai.
- **Celery prod-grade** â€” `acks_late`, `reject_on_worker_lost`, `prefetch_multiplier=1`, `max_tasks_per_child`, time-limits, heavy/light queue split (`worker.py:91-122`).
- **Degradation discipline** â€” rate-limit/redis/DB sab fail-open, in-memory fallbacks, DLQ recorder, escalating circuit-breaker (`free_ai.py:122-142`).
- **Health probes correct** â€” `/health/live` (no deps), `/health/ready` (DB+Redis, 503), Docker healthcheck liveness pe (dependency-blip pe restart nahi) â€” yeh sahi design hai.
- **Prod-down lessons baked** â€” fastembed/silero models image me baked (`Dockerfile.lock:54-61`), KB prewarm off-loop, boot-grace guards.

---

## Remediation roadmap

**Week 1 (P0 â€” ~1 din total, scale ka prerequisite):**
1. uvicorn `--proxy-headers --forwarded-allow-ips="*"` (P0-2) â€” 1 line.
2. Broker Redis `noeviction` + `Cache.set` fail-soft (P0-1 quick) â€” 30 min.
3. (stretch) alag cache-Redis container (P0-1 proper).

**Week 2 (P1) â€” âœ… IMPLEMENTED (deploy-pending), see "P1 implementation notes":**
4. âœ… Container mem/cpu limits, VPS RAM ke hisaab se (P1-1).
5. âœ… DB pool re-size + recycle/timeout (P1-2).
6. âœ… llm_metrics + queue-depth export; RED via Loki LogQL (P1-3, multi-worker rationale notes me).

**Backlog (P2) â€” partial done (see "P2 implementation notes"):** âœ… billing meter-observability Â· âœ… `/metrics` hardening (non-blocking CPU) Â· âœ… dev-only reload guard Â· âœ… schema gate added (`DB_CREATE_ALL`; Alembic cutover deferred) Â· â¸ distributed call-admission (voice scale-up se pehle) Â· â¸ shared circuit-breaker (latency-risk, defer).

**Reality check:** Single VPS ka SPOF known + spend-blocked hai (CLAUDE.md) â€” woh yahan deliberately P0/P1 me nahi rakha. Par P0-1 aur P0-2 fix kiye bina 2nd server lena bekaar hai: load multiply hoga to woh bottleneck hardware me nahi, in 2 jagah hai.

---

## P1 implementation notes (2026-06-15)

**VPS facts** (`/health/deep` se live): **16 GB RAM, 4 cores**, ~2.8 GB used (17.6%), 50 GB disk free. Khoob headroom â€” limits protective hain, throttling nahi.

**P1-1 container limits** (`docker-compose.vps.yml`, non-swarm `mem_limit`/`mem_reservation`/`cpus` â€” `docker compose up` honor karta):

| Service | mem_limit | cpus | reason |
|---|---|---|---|
| app | 3g | 2.0 | embedder+torch Ã—2 uvicorn workers |
| db | 2g | 2.0 | generous â€” Postgres OOM-kill se bachao |
| worker | 2g | 1.5 | ML/scraping jobs |
| worker-heavy | 2.5g | 1.5 | heavy LLM/ML/bulk |
| redis | 512m | 1.0 | maxmemory 256m + AOF overhead |
| redis-cache | 384m | 0.5 | maxmemory 256m + overhead |
| pgbouncer | 256m | 0.5 | tiny |
| scheduler | 512m | 0.5 | beat only |

Sum of caps â‰ˆ 11.2g < 16g (obs-stack + host ke liye ~4.8g bachta). Deploy ke baad `docker stats` se tune karo.

**P1-2 DB pool** (`app/models/base.py`): async `pool_size 20+30 â†’ 5+5`, sync `10+20 â†’ 3+2`, + `pool_recycle=1800`, `pool_timeout=10`. Ab ~4 engine-processes Ã— 5 = 20 baseline â‰¤ PgBouncer 25 â‰¤ PG 100. Pehle 2 web Ã— 50 = 100+ potential = PgBouncer/PG exhaust risk.

**P1-3 observability** â€” `/metrics` me ab: `leadgen_llm_provider_ok_rate{provider}`, `_calls`, `_avg_latency_ms`, `leadgen_llm_fallback_rate` (REAL source `llm_metrics`, pehle legacy `vertex_client` empty tha) + `leadgen_celery_queue_depth{queue}`. Dono **shared-store** (file/redis) = multi-worker correct.

> **RED metrics ka decision:** `WEB_CONCURRENCY=2` (2 uvicorn processes, 1 `/metrics` port) ke saath **in-process counters reliable nahi** â€” har scrape random worker pe, `rate()` toot-ta hai. Isliye in-process HTTP counters ship NAHI kiye. Request rate/error/latency ka data `RequestTracingMiddleware` already structured logs me likhta (`status_code`, `duration_ms`) â†’ **Loki me hai**. Grafana LogQL se RED:
> ```logql
> # error-rate:   sum(rate({app="leadgen"} | json | status_code>=500 [5m]))
> # p95 latency:  quantile_over_time(0.95, {app="leadgen"} | json | unwrap duration_ms [5m])
> ```
> Agar dedicated Prometheus RED chahiye â†’ `prometheus-client` multiprocess mode (env `PROMETHEUS_MULTIPROC_DIR` + shared tmpfs) â€” naya dep + lock-refresh, alag task.

**Suggested alert** (`monitoring/alert_rules.yml` me add karo): `leadgen_llm_fallback_rate > 0.4 for 10m` (voice/content degraded) Â· `leadgen_celery_queue_depth > 500 for 10m` (worker stuck/starved).

**âš ï¸ Verify separately:** `/health/deep` ne `workers: 0` (degraded) dikhaya â€” ya to `inspect().active()` ka broadcast-timeout artifact hai (web container se), ya Celery worker genuinely down. Live check: `docker ps | grep -E "worker|scheduler"` + `docker exec leadgen_worker celery -A app.worker inspect active`. Agar sach me 0, durable scheduler process nahi ho raha (CLAUDE.md ke against) â€” alag se dekho.

---

## P2 implementation notes (2026-06-15)

**Implemented (safe subset):**
- **Billing meter observability** (`app/billing/lead_usage.py`) â€” fail-open meter ab SILENT nahi: `record_qualified_lead`/`add_topup_leads` ka write fail ho to ERROR log (Loki/alertable) + durable record main redis list `billing:meter_failures` (noeviction â†’ kabhi evict nahi). Replay/inspect: `redis-cli lrange billing:meter_failures 0 -1`. Call kabhi block nahi hoti (fail-open intact), par revenue-leak ab visible + recoverable.
- **`/metrics` CPU non-blocking** (`app/api/health.py`) â€” `psutil.cpu_percent(interval=0.1â†’None)` (har scrape pe 100ms event-loop block hata).
- **Dev-only reload** (`app/main.py`) â€” `reload=settings.is_development` (prod me accidental `python app/main.py` reload-storm na de).
- **Schema gate** (`app/models/base.py`) â€” `DB_CREATE_ALL` env (default `1` = aaj jaisa). Alembic-only cutover ke liye opt-in `0` (blind flip nahi â€” neeche).

**Why meter-observability instead of a reconciliation job:** ek sahi reconciliation ko billable-event ka INDEPENDENT source-of-truth chahiye + exact per-client/period attribution. DB me `LeadStatus.QUALIFIED` hai par voice-qualification se uska 1:1 mapping live-DB verify kiye bina pakka nahi â€” guess-based job = false alarms. Isliye immediate safe win = meter-failure ko observable+recoverable banana. Full reconciliation (meter vs DB lead-status, per-client) = future enhancement, live-DB attribution verify karke.

**DEFERRED (with rationale â€” blind nahi karna):**
- **Schema Alembic cutover** â€” code-gate add kiya (`DB_CREATE_ALL=0`), par flip NAHI kiya. `create_all` band karne se pehle Alembic migrations ko live DB ke against verify karna zaroori (`alembic upgrade head` clean, koi missing table/column nahi) â€” warna boot pe schema-gap. Cutover live-DB access ke saath, low-traffic window me.
- **Shared circuit-breaker** (`free_ai` cooldown â†’ Redis) â€” voice critical-path latency-sensitive hai; har LLM attempt pe Redis read add karna latency + coupling risk. Per-process breaker already fast converge karta (har process seconds me seekh leta). Tab karo jab multi-process dead-provider probing measurably waste dikhe â€” local-cache + async best-effort Redis sync pattern se.
- **Distributed call-admission** (per-process `Semaphore(10)` â†’ Redis counter) â€” abhi effective cap = NÃ—10 (per uvicorn worker). Voice DLT-gated hai = launch path nahi; voice scale-up se PEHLE Redis-based global admission + capacity test karo (single box + FREE real-time STT/TTS pe CPU saturation se bachne ke liye).

---

## Verification appendix (live confirm karne ke commands)

```bash
# P0-2: proxy-IP bug â€” 2 alag XFF se hit, dono counters alag hone chahiye (abhi same honge)
for ip in 1.1.1.1 2.2.2.2; do curl -s -H "X-Forwarded-For: $ip" https://leadsgenai.in/api/... ; done
# container ke andar uvicorn args confirm:
docker exec leadgen_app ps aux | grep uvicorn   # --proxy-headers present?

# P0-1: Redis eviction policy + role-mixing
docker exec leadgen_redis redis-cli config get maxmemory-policy   # expect: allkeys-lru (problem)
docker exec leadgen_redis redis-cli info keyspace                  # broker+cache+state ek hi db0 me?
docker exec leadgen_redis redis-cli info stats | grep evicted_keys # >0 = already losing data

# P1-1: container limits
docker stats --no-stream   # MEM LIMIT column "/ <host RAM>" dikhe = no per-container cap

# P1-2: connection pressure
docker exec leadgen_db psql -U leadgen -c "select count(*),state from pg_stat_activity group by state;"
```

*Yeh audit code-read pe based hai; upar ke commands se live-state confirm karke P0 se shuru karo.*

---

## Deploy handoff (P0-1 + P0-2)

**Kya badla:** `Dockerfile.lock` (uvicorn `--proxy-headers --forwarded-allow-ips='*'`) Â· `app/middleware/__init__.py` (`_real_client_ip` XFF) Â· `docker-compose.vps.yml` (naya `redis-cache` container + main redis `noeviction` + `CACHE_REDIS_URL` env) Â· `app/cache/__init__.py` (`get_cache_redis_client` + `Cache` fail-soft) Â· `.env.example`.

**Yeh image + topology change hai** (sirf code nahi) â€” `--no-deps app` se kaam NAHI chalega; naya container banana hai aur redis recreate hoga.

```bash
# 1) Local (Windows) â€” pipeline:
python scripts/prod_check.py
scripts\run_tests.bat          # pytest_run.log Read karo (~80+ green)
# git push (bat ke andar Windows git)

# 2) VPS (Git ka ssh):
cd /opt/leadgen && git pull
docker compose -f docker-compose.vps.yml build app            # naya Dockerfile CMD + cache code
docker compose -f docker-compose.vps.yml up -d                # redis-cache create + app/redis recreate
#   ^ NOTE: redis recreate = ~1-2s broker blip (AOF persist, Celery auto-reconnect). Acceptable.

# 3) Verify:
sleep 16
curl -fsS https://leadsgenai.in/health        # environment: production
docker exec leadgen_redis redis-cli config get maxmemory-policy        # noeviction
docker exec leadgen_redis_cache redis-cli config get maxmemory-policy  # allkeys-lru
docker exec leadgen_app ps aux | grep -- --proxy-headers               # flag present
# proxy-IP fix: do alag XFF se 100+ req â†’ alag-alag 429 (pehle saath trip hote)
```

**Rollback (sabse risky single change = redis noeviction):**
- Quick: `docker-compose.vps.yml` me main redis ko wapas `allkeys-lru` + `CACHE_REDIS_URL` lines hata do â†’ `docker compose -f docker-compose.vps.yml up -d` (code backwards-compatible, `CACHE_REDIS_URL` unset = purana behaviour).
- Full: `git revert <commit>` â†’ rebuild + `up -d`.
- proxy-headers rollback: Dockerfile CMD se flags hata ke `build app` + recreate.

**Deploy ke baad watch karo:** `docker exec leadgen_redis redis-cli info stats | grep -E "evicted_keys|keyspace"` â€” agar main redis pe `evicted_keys>0` ya OOM dikhe to `--maxmemory` 256mbâ†’384mb badhao (RAM allow kare to).
