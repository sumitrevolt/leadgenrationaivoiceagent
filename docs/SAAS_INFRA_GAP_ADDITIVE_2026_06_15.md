# SaaS Infra — Genuinely-Additive Upgrade Plan (Gap Analysis)

> **Date:** 2026-06-15 · **Scope:** infrastructure + backend + AI-automation · **Budget rule:** free-first (chhota spend OK)
> **Goal:** sirf woh upgrades jo (a) tere stack mein NAHI hain, aur (b) tune pehle reject bhi nahi kiye. Zero duplicates.

---

## TL;DR — top 3 picks (agar sirf 3 hi karne ho)

1. **LLM/Agent Eval & Regression Harness — DeepEval (+ Promptfoo red-team)** → 2026 ka sabse under-built layer (89% teams ke paas observability hai, sirf 52% ke paas evals). Tere paas ad-hoc `agent_tester.py` hai, formal eval-as-CI nahi. Free, pytest-native, free-LLM ko judge bana sakta hai.
2. **Container supply-chain scan in active CI — Trivy + Syft (SBOM) + cosign (sign)** → tera live `deploy-vps.yml` image build karke GHCR pe push + deploy karta hai **bina kisi CVE gate ke**. bandit/safety/detect-secrets hain, par image-CVE/SBOM/signing nahi. Sab free, GitHub-Actions-native.
3. **Load + Chaos testing — k6 + Pumba** → tune khud yeh gap flag kiya (R8#7/R9#2/R9#3). Voice scale-up + "distributed call-admission counter" decision se PEHLE load numbers chahiye. k6 teri Grafana se integrate hota hai; Pumba tere docker containers pe chaos (kill/latency) karta hai.

Teeno **free** aur teri current stack mein clean fit hain.

---

## Method (kaise dedupe kiya — taaki bharosa rahe)

- **16 infra/reliability/automation docs** padhe (`COMPETITOR_INFRA_GROWTH_BLUEPRINT_2026`, `Scale_Reliability_Audit_2026_06_15`, `Backend_Reliability_EngineerAgents_2026_06_15`, `Backup_DR_Observability_2026_06_15`, `CICD_Dependabot_2026_06_15`, `PRODUCTION_HARDENING_GAP_2026`, etc.) + `AGENTS.md`.
- **Real configs + code** map kiye: `docker-compose.*`, `infrastructure/terraform/`, `.github/workflows/*`, `requirements.lock.txt`, `monitoring/*`, `app/` reliability+automation modules.
- **Repo grep** se confirm kiya har candidate tool absent hai: `promptfoo, deepeval, trivy, cosign, k6, dbos, gptcache, semantic-cache` → **koi match nahi** (app/, .github/, requirements.lock, pyproject).
- **Web research (2026)**: modern SaaS stack, AI-agent infra ke 5 layers, durable-execution (Temporal/Restate/DBOS), eval frameworks, supply-chain scanning, load/chaos.
- **Excluded:** jo tune already DONE kiya, ya RESEARCHED-and-rejected kiya, ya spend/external pe BLOCKED hai.

---

## Tera current posture (1 para)

Honestly — yeh hobby project nahi, yeh production-grade hai. Terraform IaC, 6 CI/CD workflows (GHCR→SSH auto-rollback, health-gated), Alembic, staging compose, SOPS+age scaffold, pre-commit (ruff/black/bandit/detect-secrets/hadolint/tflint), full observability (Prometheus/Grafana/Alertmanager/Loki/Tempo/Gatus/Uptime-Kuma + node/cAdvisor/postgres/redis exporters), dual-Redis (noeviction broker + LRU cache), PgBouncer, nightly pg_dump + monthly restore-drill + backup-staleness alerts, transactional outbox + webhook idempotency + DLQ, Celery durable scheduler + dead-man trio, multi-agent coordinator + process-engine + self-improve + langgraph (gated), free multi-provider LLM chain with escalating circuit-breaker. **Iss base pe genuinely naya add karna mushkil hai — isliye list chhoti aur sharp hai.**

---

## Tier 1 — High value · clear white-space · free

### 1) LLM/Agent Eval & Regression Harness — **DeepEval** (primary) + **Promptfoo** (red-team)
**Kyun additive:** AI-agent stack ka sabse upar-wala moat = *evals as infrastructure* (PR pe fast-checks → nightly LLM-judge regression → prod drift alerts). Tere paas voice ke liye `agent_tester.py` scorecard hai (double/empty/repeat/long/slow) — par yeh ad-hoc hai, CI-wired regression-gate + LLM-as-judge + drift nahi. Yeh **Langfuse se alag** cheez hai (woh tracing/observability tha, tune reject kiya — sahi kiya; eval ≠ tracing).
- **DeepEval** = "pytest for LLMs", 50+ metrics (G-Eval LLM-judge, hallucination, faithfulness, answer-relevancy), local/OpenAI-compatible model support → **tera free Cerebras/Groq judge ban sakta hai**, aur teri existing pytest CI mein seedha plug.
- **Promptfoo** bonus = 50+ red-team plugins (prompt-injection, PII-leak, jailbreak) → yeh tera flagged **`/api/ai/command` LLM-abuse surface** test karega. (Runtime guardrail nahi — testing; isliye NeMo/Guardrails-AI rejection se conflict nahi.)
- **Kaise fit:** `tests/evals/` folder → golden Q/A set per niche (telecaller_brain, niche_scripts). CI mein 2 jobs: (1) fast assertion-checks har PR pe, (2) nightly `deepeval` regression LLM-judge → score Prometheus textfile metric → Grafana panel + alert agar score gir jaaye. Self-improve/code-upgrader loops ke output ko bhi yahi harness gate karega.
- **Impact:** High (quality moat + regression safety net for autonomous loops) · **Effort:** Low-Med · **Cost:** Free.

### 2) Container Supply-Chain Scan in active CI — **Trivy** + **Syft (SBOM)** + **cosign (sign)**
**Kyun additive:** tera *active* path `deploy-vps.yml` image banata, GHCR pe bhejta, deploy karta — par **image CVE scan / SBOM / signing kuch nahi**. (Legacy GCP `ci-cd.yml` mein gcloud scan tha, par woh path use nahi hota.) Tere paas bandit/safety/detect-secrets/hadolint/dependabot hai — yeh source-level hai, **image-level nahi**.
- **Trivy** (Apache-2.0) = ek hi tool mein image-CVE + IaC-misconfig + secrets + license scan. **Syft** → SBOM (CycloneDX/SPDX). **cosign** → Sigstore image signing (deploy pe verify).
- **Kaise fit:** `deploy-vps.yml` build ke baad: `trivy image --exit-code 1 --severity HIGH,CRITICAL` (gate), `syft` se SBOM artifact, `cosign sign` GHCR digest. ~30-40 lines CI.
- **Impact:** High (security + DPDP posture; pehla paid customer se pehle achha) · **Effort:** Low · **Cost:** Free.

### 3) Load + Chaos Testing — **k6** (+ **Pumba** chaos)
**Kyun additive:** tune khud flag kiya (R8#7 load, R9#2 perf-budget, R9#3 chaos) — abhi tak unbuilt. Voice scale-up aur **distributed call-admission counter** (per-process Semaphore = N×10 cap) ka decision lene se pehle real numbers chahiye. "Automated capacity baselines" bhi tera flagged gap hai — k6 wahi deta hai.
- **k6** (open-source, Go, Docker-easy) → teri **already-running Grafana** se integrate; HTTP + scenario load tests; perf-budget thresholds CI mein.
- **Pumba** → Docker-native chaos: container kill/pause/network-latency/packet-loss. Tere docker-compose VPS pe seedha chalega — self-heal cron + dead-man trio ko actually test karega.
- **Kaise fit:** `tests/load/*.js` k6 scripts (audit/demo/widget/webhook endpoints) → staging pe nightly + pre-scale manual run. Pumba se monthly "game-day" (db/redis kill karke recovery verify).
- **Impact:** High (de-risks scale + HA decisions ko data deta) · **Effort:** Med · **Cost:** Free.

---

## Tier 2 — Strong, par honest caveat ke saath

### 4) **DBOS Transact** — Postgres-backed durable execution (library, server NAHI)
**Kyun additive:** tere outreach / reply→book→pay state machines abhi **`.jsonl` best-effort** hain (tera flagged gap). Tune **Temporal reject kiya** kyunki "heavy 4GB server, single-VPS over-engineering" — bilkul sahi. **DBOS ulta hai:** MIT-license **library** jo teri *maujooda Postgres* ko durability layer banaata, koi extra server nahi, 2-4 lines mein durable workflow + queue. Crash pe last completed step se auto-resume (exactly-once).
- **Caveat (honest):** yeh tere hand-rolled `process_engine.py` (event-sourced journal) se thoda overlap karta. Isliye **`process_engine` replace mat karo** — sirf un specific `.jsonl` best-effort revenue flows pe DBOS pilot karo (e.g. reply→book→pay). Ek flow pe try, phir decide.
- **Impact:** Med-High (revenue-path durability) · **Effort:** Med · **Cost:** Free (MIT, existing Postgres).

### 5) **LLM Semantic Response Cache** (build small, adopt nahi)
**Kyun additive:** tune "LLM general response cache" ko free-to-add gap likha (abhi sirf greeting-audio cached). Semantic cache = query embed → vector similarity → cached answer serve → latency↓ + free-tier token burn↓ (Groq TPD pressure jo tune note kiya).
- **Caveat:** GPTCache 2026 mein weakly-maintained — naya dep mat lo. Tere paas **Qdrant + Redis + fastembed already hai** → ek thin semantic-cache khud bana (embed→Qdrant cosine→threshold→Redis store). ~1 module.
- **Impact:** Med (latency + free-tier headroom) · **Effort:** Low-Med · **Cost:** Free.

---

## Tier 3 — "Activate what you already have" (naya stack nahi, par highest ROI/effort)

Yeh duplicates NAHI hain — yeh tere paas hai par **OFF/idle** pada hai. Effort kam, impact bada:

- **OTel app-tracing** → Tempo container chal raha hai par **idle** (app instrumented nahi). otel pkgs `requirements.lock.txt` mein add + rebuild → FastAPI→DB→LLM→TTS spans live. Tune yeh khud flag kiya.
- **Cloudflare free edge (WAF + CDN + DDoS + Tunnel)** → `INFRA_HARDENING_GUIDE` mein poora scoped hai, sirf tere CF-account banane pe blocked. **Single highest free security+perf win** — origin IP hide + edge cache + DDoS.
- **SOPS-encrypt live `.env`** → module + `.sops.yaml` ready, par VPS pe `.env` abhi plaintext. Tere apne docs mein "biggest free security win" likha hai.

---

## Explicitly NOT recommending (dedup proof)

**Already DONE** → outbox, webhook idempotency, DLQ, circuit-breaker, rate-limit (tier-aware multipliers bhi mile `ratelimit.py` mein), PgBouncer, restore-drill, backup-staleness alerts, exporters suite, Sentry, dead-man trio, multi-agent coordinator/process-engine/self-improve, staging, Alembic scaffold, dependabot, pre-commit, Gatus/Uptime-Kuma.

**Tune RESEARCHED-and-REJECTED (dobara nahi suggest kar raha)** → Temporal, Langfuse/AgentOps, OpenHands, SWE-agent, NeMo Guardrails, Guardrails-AI, n8n, pgBackRest, AutoGen/DSPy/MemGPT.

**Spend/external BLOCKED (decided-deferred)** → HA 2nd-node, managed Postgres replica, Redis cluster, multi-region, R2/B2 offsite creds, DLT, Exotel KYC, paid LLM key.

**Already tera Phase-1/2 radar pe** → PostHog, Metabase, Umami, Windmill (inko naya gap nahi maan raha).

**Borderline / optional (low priority):** dedicated feature-flag service (Flipt/Flagsmith/Unleash). Tere paas env-flag registry + `/api/growth/infra/flags` hai — solo founder ke liye flag-service abhi over-engineering. Sirf tab lena jab gradual % rollouts/A-B zaroori ho.

---

## Suggested sequence (effort vs impact)

| # | Upgrade | Impact | Effort | Cost | Tier | Status |
|---|---------|--------|--------|------|------|--------|
| 1 | Trivy + Syft + cosign in `deploy-vps.yml` | High | **Low** | Free | 1 | additive |
| 2 | OTel tracing activate (Tempo idle) | High | **Low** | Free | 3 | activate |
| 3 | SOPS-encrypt live `.env` | High | **Low** | Free | 3 | activate |
| 4 | Cloudflare free edge | High | Low* | Free | 3 | activate (CF acct) |
| 5 | DeepEval + Promptfoo eval/regression harness | High | Med | Free | 1 | additive |
| 6 | k6 + Pumba load/chaos | High | Med | Free | 1 | additive |
| 7 | LLM semantic cache (build on Qdrant/Redis) | Med | Low-Med | Free | 2 | additive |
| 8 | DBOS pilot on reply→book→pay | Med-High | Med | Free | 2 | additive |

*Cloudflare effort low, par tujhe account/DNS karna padega.

**Pehla din:** #1, #2, #3 (teeno low-effort, high-impact, ek hi deploy cycle mein). Phir #5/#6 (eval + load) — yeh tere autonomous loops aur scale decisions ko data dete hain.

---

## Sources (web research, 2026)
- O'Reilly — The AI Agents Stack (2026 Edition): https://www.oreilly.com/radar/the-ai-agents-stack-2026-edition/
- Augment Code — Agentic Infrastructure: What Actually Goes in the Stack: https://www.augmentcode.com/guides/agentic-infrastructure-stack
- DeepEval vs PromptFoo (2026): https://scrolltest.com/deepeval-vs-promptfoo-llm-evaluation-framework-2026/
- DeepEval (official): https://deepeval.com/ · Promptfoo: https://www.promptfoo.dev/
- Trivy vs Grype 2026 / Syft vs Trivy: https://lucaberton.com/blog/trivy-vs-grype-2026/ · https://appsecsanta.com/sca-tools/syft-vs-trivy
- Container Vulnerability Scanning 2026 (Trivy/Grype/SBOM/cosign): https://vucense.com/dev-corner/container-vulnerability-scanning-2026/
- DBOS Transact (MIT, Postgres durable execution): https://github.com/dbos-inc/dbos-transact-py · https://www.dbos.dev/dbos-transact
- Durable Execution — Temporal vs Restate vs DBOS: https://devstarsj.github.io/2026/04/03/durable-execution-temporal-restate-dbos-distributed-workflows-2026/
- Grafana k6: https://k6.io/ · Pumba (Docker chaos): https://github.com/alexei-led/pumba · k6-chaos: https://github.com/grafana/k6-chaos
