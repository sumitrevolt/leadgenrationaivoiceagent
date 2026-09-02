# LeadGenAI — Enterprise AI Architecture Audit (2026-07-06)

> Method: 5 read-only, purpose-built auditor subagents fanned out over disjoint domains, each
> required to give `file:line` proof, mark N/A categories honestly, and NOT invent findings to
> fill a template category. Every Critical/High claim was spot-checked against real code before
> scoring (this repo has a documented hallucinated-finding history). Ground-truth state from
> `scripts/prod_check.py`. Nothing marked "done/complete" without code evidence.
>
> **One-line verdict:** This is a genuinely mature, incident-scarred, defensively-engineered
> production SaaS — not a prototype. It is densely wired (0 route/automation/orphan gaps), every
> autonomous loop is bounded + dead-man-watched, compliance gates are fail-closed, and the free-AI
> inference layer is production-grade. The real defects are narrow: **one latent all-tenant KB
> data-loss bug** and **one KB re-ingest dedup gap** (both fixed this session), plus hardening
> items and unverified runtime-activation of the alerting/DR chain.

---

## Scorecard

| Score | Value | Basis |
|---|---|---|
| **Production Readiness** | **86 / 100** | Live at leadsgenai.in, `prod_check` PASS, 0 wiring/orphan gaps, every domain ≥78. Residual: 1 latent data-loss bug (fixed here), single-node (no hot standby), runtime-activation of DR/alert chain unverified without SSH. |
| **AI Architecture** | **85 / 100** | Free-stack inference is production-grade (bounded awaits, escalating circuit-breaker, honest STT, int8 CPU whisper); RAG index-integrity gaps pull it down. |
| **Agentic AI** | **88 / 100** | Every loop bounded + journal-durable + dead-man-watched + eval-gated; only governance-precision gaps (cost estimates, rate-cap prod-value). |
| **SaaS** | **85 / 100** | Billing single-source-of-truth, DR restore *proven*, CI rollback-on-health-fail; capped by single-VPS scale ceiling + missing observability mem-limits. |
| **Security** | **90 / 100** | No exploitable anon-access / cross-tenant IDOR / fail-open compliance gap in the audited ~45-router surface. Honest caveat: ~50 `app/api/` files not opened this pass. |
| **Performance** | **84 / 100** | Hot path fully timeout-bounded + cached; per-process breaker/cache/key-rotation diverge under multi-worker; realtime LLM chain leads with a slower provider. |

**Per-domain (auditor) scores:** Security 90 · Agent-Loops 88 · LLM/Inference 88 · Infra/DR/CI 87 · Vector/RAG/DB 78.

**Ground truth (`prod_check.py`, 2026-07-06):** 1075 source files parsed · app imports OK · **1030 routes registered** · wiring **46 pages / 0 gaps · automation 0 gaps** · explorer graph **244 nodes / engine coverage 78-of-78 / 337 edges / 0 orphans** · API.md 1055 ops in sync · **ALL CHECKS PASSED**.

---

## Findings by AI-engineering concept (severity · root cause · impact · file · fix)

### 1. Transformers / model usage & routing — GOOD
- Local: faster-whisper STT `compute_type="int8"` on CPU (`vobiz_stream.py:288`) — correct CPU quantization; `HINGLISH_STT` swaps a baked CT2 model. fastembed 384-dim embeddings (local).
- Cloud LLM chain w/ escalating 60s→30min per-provider circuit-breaker, dead-model/403/402 forced to max cooldown (`free_ai.py:258-304`).
- **[LOW] Realtime chain leads with Mistral, not the fastest free provider** — `free_ai.py:572-577`. Voice turns run `profile="realtime"` (`telecaller_brain.py:2791`) but Mistral-first is typically slower than Groq/Cerebras → higher p50 first-token latency. Fix: reorder `groq → cerebras → mistral` for realtime, or reorder by observed `llm_metrics` p50. Order is data, not logic — low risk.

### 2. Agent Loops — GOOD (88)
- self_improve dead-man trio complete: heartbeat + Redis-NX single-chain revive lock + Celery-only revive + separate beat watchdog (`self_improve.py:187-206, 929-967`; `staff_jobs.py:205-220`).
- process/DAG engines are journal-sourced (event-sourced, crash-safe resume) with bounded `max_steps` + gate-retry budget so a failing retry can't spin forever (`process_engine.py:269-284`, `dag_engine.py:356-363`).
- coordinator advanced/agentverse patterns hard-capped `min(3, …)` iterations + neutral-score fallback on parse failure (`coordinator.py:553, 877, 512-514`).
- eval_gate wired into the one loop that autonomously mutates (`self_improve.run_once` → `eval_gate.score_and_gate`, `self_improve.py:1380-1398`); `code_upgrader` correctly does *not* self-apply (human-approve + git deploy).
- **[LOW] Coordinator has no durable $/run cap** — `coordinator.py:159-181`; only an inert-by-default per-minute rate cap. Blast radius is small (all `/api/agents/*` are `require_admin` + rate-limited; only recurring caller `AGENT_STANDUP` default-OFF). Fix: confirm/set `COORDINATOR_LLM_CAP_PER_MIN` in prod `.env`. (Note: corrected a *stale MEDIUM* claim in the old `PRODUCTION_AUDIT_REPORT.md:116` down to LOW.)
- **[LOW] `CostTracker` is an in-memory per-process estimate** (`$2.5`/`$0.5` constants), resets on worker restart — `self_improve.py:1060-1106, 1287`. The *real* durable guard is `max_per_day()` run-count (file-state). Fix: label `cost_status()` as "estimated, per-process" or persist into `self_improve_state.json`.

### 3. Hooks — GOOD
- App lifecycle `lifespan` (`main.py:113-314`); event-hook registry with SSRF-safe target check + gated auto-fire (`app/agents/lifecycle_hooks.py:71,111,171`); post-call hooks (`app/telephony/post_call_hooks.py`).
- Claude dev-time hooks: `PreToolUse` guard + `Stop` reward_capture (`.claude/settings.json`, `.claude/hooks/`).
- No missing critical hook found.

### 4. PRD / product-truth & feature completeness — GOOD
- Single source of truth `app/marketing/packages.py`; public = Main ₹1,999 + Combo ₹5,999 + ₹0 trial; Growth ₹2,999 legacy-hidden via `get_public_packages()` (`packages.py:282`). Voice = flat-per-band. No pricing drift; billing-truth contract test is a hard CI gate.
- ~110 gated automations registered in `app/api/automation_flags.py` (self-improve, RAG variants, semantic cache, agent-memory, budget-guard, even an inert `OLLAMA_PRIMARY` self-host path) — all default-OFF / inert-without-creds.

### 5. Agent Harness (orchestration / isolation / memory / delegation / recovery) — GOOD
- Explicit 3-queue Celery routing (`worker.py:263,316`; light pool + isolated `-Q heavy --concurrency=1`), matches `task_routes`.
- Shared memory via Qdrant `skills`/`client:<id>` namespaces + `agent_memory` (deterministic-ID dedup, DPDP purge).
- Failure recovery: DLQ bounded (`MAX_ATTEMPTS=3`, unknown tasks → `dlq:dead` not blind-retried, queue-flood backpressure — `dlq_retry.py:118-205`); idempotency-wrapped re-dispatch (`staff_jobs.py:230`).

### 6. Chain-of-Thought / reasoning — GOOD
- Bounded everywhere: agentic-RAG corrective `while True` capped by `max_rewrites` + `asyncio.wait_for` at every call site (`agentic_rag.py`, `telecaller_brain.py:2710-2715`); streaming token loop has per-token + wall-clock budget (`free_ai.py:980`).

### 7. Context Window Management — GOOD
- History truncated to `_MAX_HISTORY_TURNS=8` at prompt build; FACTS word-boundary trimmed to ~450 chars; repeated-question/reply dedup (`telecaller_brain.py:2589-2614`).
- Voice conversation is intentionally in-memory per WS-lifetime (a call = one socket); cross-session recall is the separate gated `AGENT_MEMORY` path — not a gap.

### 8. Tool Calling — GOOD
- `ToolRegistry.execute` validates required params + never raises (`function_calling.py:174-205`); every handler degrades to a spoken fallback on failure; PII-redacted logs; `run_tool_turn` timeout-wrapped + never-raises (`voice_tools.py:185-235`); anti-fake guard rejects hallucinated "booked!" without a real CALL at both prompt and code level.

### 9. Vector Embeddings / RAG — WEAKEST DOMAIN (78) — 2 real defects (FIXED this session)
- **[CRITICAL/data-loss · narrow trigger] Silent full `kb_main` wipe on embedder-dim drift** — `knowledge_base.py:488-496`. `_EMBED_CANDIDATES` mixes 384/768/1024-dim models; if the 384 candidates fail to load on a restart and it falls through to a bigger-dim model, the next client init sees `dim != 384` and `delete_collection(kb_main)` inside `except: pass` — **wipes every client's KB, every namespace, every niche script, silently, no log, no alert.** → **FIXED:** default now PRESERVES data + logs `logger.error`; destructive recreate only under explicit `KB_ALLOW_DIM_WIPE=1`.
- **[HIGH/grounding-accuracy] KB re-ingest never dedupes** — `knowledge_base.py:566-585` used `id=uuid.uuid4()` per point, so the weekly `KB_WEEKLY_REFRESH` re-seed accumulates duplicate chunks forever AND never deletes stale chunks → when a client's website content changes (e.g. new pricing), old + new co-exist and either can win top-k → **voice agent can quote stale pricing.** → **PARTIALLY FIXED:** deterministic `uuid.uuid5(namespace+text)` point id (mirrors `agent_memory.py:243`) makes **byte-identical** re-ingests OVERWRITE instead of accumulate → bounds `kb_main` growth on the re-seed of *unchanged* content. **This does NOT fix the stale-content case:** changed text → different hash → different id → the old chunk is *orphaned, not overwritten* (both survive). Closing that needs **delete-before-reseed** (drop the namespace's/source's old points before re-adding) — see roadmap P1. Also: existing prod points carry random `uuid4` ids, so the dedup benefit only starts from the *second* post-deploy re-ingest, and realizing it on the live collection needs a one-time purge/reseed. The `skills` namespace uses the same `add()` path so is likely covered by the same change (unverified — not personally traced).
- GOOD: cross-tenant RAG isolation traced across *every* `namespace=` call-site (all derive `client:<id>` server-side from JWT/DB, never raw request param); LightRAG KG is opt-in + fail-safe; DPDP purge wired into vector memory.

### 10. Inference Pipeline — GOOD (with a multi-worker caveat)
- **All hot-path awaits bounded** — STT per-provider timeouts, local-whisper hard deadline, LLM `_CALL_TIMEOUT_S=8.0`, streaming first-token/idle/wall deadlines + `stream.aclose()` on abort, reply hard-cap, KB thread-offload `_KB_TIMEOUT_S=1.5`. The 3 documented event-loop prod-downs are visibly encoded as fixes.
- Streaming safety: never restarts a half-streamed reply on another provider (avoids garbled speech).
- **[MEDIUM] Provider circuit-breaker, LLM cache, and Gemini key-rotation index are per-process module globals** — `free_ai.py:231-234, 484`; `gemini_keys.py:36`. Under `WEB_CONCURRENCY=2` + worker conc=4 each process holds an independent copy → a quota-tripped provider is re-probed fresh by other processes; key round-robin diverges; cache hits don't cross processes. Bounded (self-heals per cooldown) but a real latency/quota tax. Fix: back cooldown/key-index with Redis (already a dependency) or document as a known limit. Recommend documenting for now (free-stack, 1-customer scale).

### 11. Quantization — mostly N/A (honest)
- faster-whisper `int8` on CPU = correct quantization choice (`vobiz_stream.py:288`). **GGUF/llama.cpp = N/A** (no such path). **GPU/CUDA = N/A by design** (CPU single-VPS; code auto-detects CUDA but prod is `device="cpu"`). **Ollama = wired-but-inert** (`OLLAMA_URL`/`OLLAMA_PRIMARY`-gated self-host path exists, off unless URL set). No demand for a GPU stack — deliberate free-CPU architecture.

### 12. Prompt quality & injection defense — GOOD (one 2nd-order gap)
- 3-layer injection defense on caller utterances: pre-LLM deflect + post-LLM obeyed-discard (reuses the self-test's own judge so CI/prod never drift) + sanitize/truncate (`telecaller_brain.py:1562, 1692, 123-145`). Compliance backstops (PII-leak discard + AI-disclosure) now on the live per-turn path.
- **[MEDIUM] Learned/KB content injected into the *system prompt* is NOT injection-sanitized** — `telecaller_brain.py:744-776` (trainer hints, admin-promoted `voice_learned` replies, obsidian notes) + KB facts at `_build_prompt`. Caller utterances are guarded; content assembled *into* the system prompt from the learning loop / KB is trusted verbatim → a poisoned KB doc or learned-reply row ("ignore your instructions") enters above the guard layer (2nd-order injection). Partly mitigated by the post-LLM `_obeyed_injection` backstop. Fix: run the existing sanitize/strip pass over trainer/learned/obsidian/KB strings before appending. **Recommended next fix.**

### 13. Auth / Authorization / RBAC / API security — GOOD (90)
- No global auth middleware (deliberate) but self-gating is *consistently* applied across ~45 routers; billing IDOR guard, Stripe/Twilio webhook signature fail-closed, 3 independent SSRF blocks, Pollinations `sk_` proxy-only, studio-media IDOR-safe, admin-DB-explorer read-only + super-admin + redaction, impersonation audited + gated, RBAC self-escalation blocked, reverse-proxy IP-spoof defended (rightmost XFF).
- **[LOW] Booking cancel has no ownership second-factor** — `booking.py:144-156`. Capability-URL pattern (unguessable `bk_` id + rate-limited); hardenable, not exploitable today. Fix: require original phone on `/cancel`.
- **Honest caveat:** ~50 `app/api/*` files (reseller, combo_product, activation, segments, agents, voiceai, office_hq, team, campaigns, …) were *not opened* this pass — absence of search, not confirmed-clean.

### 14. Infra / Scheduler / Workers / Queue / DR / CI-CD — GOOD (87)
- Dead-man switch parity complete (every `STAFF_JOBS` entry has an `EXPECTED_GAP_MIN`); boot-grace prevents restart-storm; beat schedule persisted to `/app/data` (not ephemeral `/tmp`); broker-Redis `noeviction` vs cache-Redis `allkeys-lru` on separate containers; DLQ bounded + backpressured; CI deploy auto-rolls-back on migration/health failure; layered backups with a *monthly automated restore drill* wired to alerts; external GitHub-hosted uptime dead-man's switch.
- **[MEDIUM] 7 observability containers lack `mem_limit`** — `docker-compose.observability.yml` (prometheus/loki/tempo/grafana/alertmanager/uptime-kuma/gatus). On a shared 16GB VPS where the revenue app/db carry hard caps *specifically* to prevent OOM-kill, an unbounded Prometheus/Loki leak is a soft spot in that same threat model. Fix: add `mem_limit` (config-only, zero behavior risk).
- **[LOW · dormant] Unreachable 900s timeout in the gated `trainer` job** under Celery's 600s hard task limit — `worker.py:104` vs `team_scheduler.py:307`. Inert (`ML_NIGHTLY_TRAINING` OFF). Fix: cap `wait_for` ≤540s.
- **[INFO] Runtime activation unverifiable without SSH** — `DLQ_AUTO_RETRY` / `AUTOMATION_HEALTH_ALERTS` default `0`; 3 compose stacks + 5 host crons must be up for full DR/alert coverage. Recommend a one-time SSH pass: `crontab -l`, `docker ps`, health-status, grep prod `.env`.
- **RTO/RPO:** RPO ≈ 24h (nightly) unless PITR activated (WAL volume provisioned; activation unverifiable statically); RTO hours-scale single-node (HA 2nd server externally blocked). **N/A: Kubernetes** (single-VPS deliberate; `data/*.jsonl` + filesystem scheduler-lock would need re-architecting first). **N/A: SQLite-in-prod** (Postgres+PgBouncer is prod; SQLite = rollback only).

### 15. Database consistency & migrations — GOOD
- PgBouncer `session` mode deliberately chosen for asyncpg; `try/finally` close on both sync+async deps; enum-vs-VARCHAR bug already root-caused + retrofitted with a forensic migration (`010_enum_columns_to_varchar.py`); linear migration chain, single head, no autogenerate drift; `agents.role` reconciled across both create_all + Alembic paths.

---

## Requested checklists

### Missing Features
- **None missing at the product level.** Advertised features map to live code (feature_groups threaded packages→PricingPlan; hands-free automations tested). The gaps are *quality/robustness*, not missing capability.

### Missing AI Components
- Cross-process shared LLM state (Redis-backed circuit-breaker / key-rotation / semantic-cache) — currently per-process. *Enhancement, not missing.*
- Real (measured token) cost accounting for the self-improve/coordinator loops — currently estimated constants.

### Missing Agent Loops
- **None.** All expected loops present + bounded. RL flywheel is deliberately Phase-0 logging-only (ADR-015), not missing.

### Missing Tool Calls
- **None broken.** Tool-calling layer is fully defensive (validate + never-raise + spoken fallback + anti-fake guard).

### Missing Memory Features
- KB re-ingest dedup (identical-chunk collapse) — **shipped this session.**
- **Delete-before-reseed — REQUIRED to actually fix stale-grounding, NOT shipped** (P1 #3): the dedup fix does not remove a chunk when a page's content changes (different text → different id → old chunk orphaned). Dropping the namespace's/source's old points before a full re-seed is the missing half.
- Redis-backed cross-process semantic cache (flag `SEMANTIC_CACHE` exists, default OFF) — enhancement for scale.

### Missing Automation
- **None missing.** ~110 automations registered + gated. Gap is *verification of which flags are ON in prod*, not missing automations.

---

## Prioritized Roadmap to "true enterprise-grade autonomous AI platform"

**P0 — data integrity (DONE this session):**
1. ✅ Stop the silent all-tenant KB wipe on embedder-dim drift (`KB_ALLOW_DIM_WIPE`-gated + loud log).
2. ✅ Deterministic KB point IDs → collapse **byte-identical** re-ingests (bounds growth). ⚠️ Does NOT clear stale chunks on content change — that's P1 #3 below.

**P1 — cheap, high-value hardening (S-tier, mostly config):**
3. **Delete-before-reseed** (`_seed_kb_from_website` / `kb_refresh`): drop a namespace's/source's existing points before re-adding — this is the part that actually closes KB stale-grounding (the shipped deterministic-ID dedup only bounds *identical*-chunk growth; changed content still orphans the old chunk). Plus a one-time purge/reseed to migrate existing random-`uuid4` points so the dedup benefit is realized on the live collection.
4. Add `mem_limit` to the 7 observability containers.
5. Sanitize learned/trainer/obsidian/KB strings before they enter the voice system prompt (close the 2nd-order injection gap).
6. One-time SSH verification pass: crons installed? all 3 compose stacks up? `DLQ_AUTO_RETRY` / `AUTOMATION_HEALTH_ALERTS` / `COORDINATOR_LLM_CAP_PER_MIN` set in prod `.env`? PITR activated?

**P2 — robustness at scale:**
6. Redis-back the LLM circuit-breaker + Gemini key-rotation + semantic cache (cross-process correctness).
7. Reorder the realtime LLM chain by measured p50; cap the gated trainer `wait_for` ≤540s.
8. Persist real (measured) cost accounting for self-improve/coordinator; label estimates in the UI.
9. Booking-cancel ownership second-factor.

**P3 — scale ceiling (only when growth demands):**
10. jsonl→Postgres migration for the hotter stores; make the scheduler lock cluster-safe; then (and only then) consider multi-node / HA 2nd server. Kubernetes remains unnecessary at current scale.

**Coverage debt:** ~50 `app/api/*` routers were not opened in the security pass — schedule a second disjoint-batch security sweep to reach full-repo coverage before claiming a repo-wide security number.

---

## What was NOT verified (honesty ledger)
- Live prod `.env` flag states (`DLQ_AUTO_RETRY`, `AUTOMATION_HEALTH_ALERTS`, `KB_WEEKLY_REFRESH`, `COORDINATOR_LLM_CAP_PER_MIN`, PITR) — need SSH.
- Host crontab / all-3-compose-stacks-up — need SSH.
- ~50 `app/api/*` routers (security) — not opened this pass.
- Runtime latency numbers (p50/p95) — inferred from code structure + timeouts, not measured live.
