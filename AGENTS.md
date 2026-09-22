# AGENTS.md — LeadGen AI Platform (CANONICAL agent instructions)

> **Single source of truth (2026-09-22).** LeadGen LeadGen AI project root ki yeh file = ONE editable canonical agent-instruction file. `CLAUDE.md` ab redirect stub hai jo yahan point karta hai. Deep body (legacy §0–§9.5 + Current State full) yahan nahi, alag doc me hai (`docs/AGENTS_REFERENCE.md`, tracked but NOT auto-loaded). Owner priority directive archived immutable at `docs/OWNER_DIRECTIVE_2026-09-22.md` (SHA-256 `803A4683B94F6B8CF41DCCB5CB6DA461B3DEF108C43794585D256F78A5CAB6EA`).
>
> **Token discipline:** Yeh file har turn load hoti hai — lean rakho (target ≤12 KB, current ~10 KB). Dated history → `docs/SESSION_LOG.md` (auto-load NAHI). Deep knowledge → `memory/INDEX.md` + relevant sub-doc. Build/incident logs YAHAN mat likho. **Code vs memory conflict = code wins — phir memory fix karo.**
>
> Naya session / cold-start? **`docs/HANDOFF.md`** = master handoff (infra map, sharp edges, SOP pointers).

## 0. PRECEDENCE — OWNER DIRECTIVE 2026-09-22

The owner-issued directive (M00–M17 + A01–A10 + original §§0–45 + U01–U14, archived verbatim at `docs/OWNER_DIRECTIVE_2026-09-22.md` — DO NOT EDIT) supersedes directly conflicting historical project text on:

- **MiniMax-primary model:** no hidden ChatGPT/Claude worker, subscription, or cost dependency. The `claude-omni-*` aliases in `scripts/claude_proxy.py` are CLIENT-COMPAT proxies that re-route to OmniRoute (MiniMax-primary upstream) — keep as alias layer, NOT as paid-Claude dependency.
- **Single canonical `AGENTS.md`:** `CLAUDE.md` retired when consumers safely migrate. Old `assert CLAUDE.md == AGENTS.md` byte-equality rule (in `tests/test_1000_engineers_skill.py` + `scripts/run_ship*.ps1`) is removed; AGENTS.md stands on its own.
- **TypeSafe multi-pass output engine** (§2.2 below) — repeated meaningful judgments at every relevant checkpoint (intake → planning → generation → intermediate QA → targeted revision → final delivery gate → real-world outcome → session continuation). Not "decorative single call".
- **Single canonical control plane** — `app/platform/automation_orchestrator.py` + `task_ledger` + 9 worker + 31 agent ids per `app/platform/agent_registry.py`. Local/VPS are two distinct environments; MiniMax decides placement from evidence (M03/M04).
- **One owner-visible Telegram control view** (M07) with the dual-bot local/VPS routing; not ntfy migration until consumer proof.

Non-conflicting legacy rules (loop-engineer mode, anti-mistakes, current-state discipline, memory protocol, landmines) continue to apply and are referenced below.

## 1. CURRENT STATE (sprint + live truth — pointer form)

**Sprint goal (2026-09-22):** GTM 0→1 — pehle paid Marketing customers. Mid-funnel bottleneck = Hot Queue `/app/inbox` + dialer sprint. 1 real paying customer (jiya makeover). MRR and net cash via `app/admin/services/task_ledger.py` (admin) + `/api/admin/revenue/*`.

**Live facts (must RE-VERIFY at session start):**
- Repo HEAD `35f4d33c` on `feat/auto-20260922-0e113f55`. `origin/main` `3698732e`.
- VPS = `srv1736379` (Hostinger Mumbai, Ubuntu 24.04). Port 8000 owner = Docker `leadgen_app` (NOT systemd). Canonical deploy = `scripts/deploy_vps.sh` ONLY.
- Production SHA only via `/health.version` — never from `git log` (4 different revisions run in one prod; see `memory/incidents.md` 2026-09-20).
- TypeSafe skill = `.claude/skills/typesafe-ai/SKILL.md` (always load). Status: `python scripts/typesafe_status.py --probe` (state only, never the value).
- Detailed Current State: `docs/AGENTS_REFERENCE.md` §Current State (legacy dump, preserved) + `docs/context/CURRENT_STATE.md` (live working doc).

**Action ladder (every session):** §0 priority block → §1 current state → §2 operating rules → load skill `thousand-engineers` (10 rules + 10-lens + 12 disciplines, `.claude/skills/thousand-engineers/SKILL.md`) + TypeSafe skill + verify creds → THEN plan → THEN execute.

## 2. MANDATORY AGENT OPERATING RULES

### 2.1 Language + canary
- **Hinglish (Roman) me HI reply** — concise, kam formatting. Reproduction of CLAUDE.md rule.
- **Canary:** har reply ke END me akeli line `🐦 pelican` (model-emitted — context-drift check).

### 2.2 TypeSafe multi-pass output engine (M00A condensed — full text in `docs/OWNER_DIRECTIVE_2026-09-22.md`)

TypeSafe = ACTIVE multi-pass engine, not a single decorative call. At every relevant checkpoint:
1. **Intake** — source/evidence sufficiency, task fit, candidate selection.
2. **Planning/routing** — next-best action, capability match, priority.
3. **Generation guidance** — TypeSafe judges candidate briefs/outlines; MiniMax/approved tool produces the artifact.
4. **Intermediate QA** — inspect drafts (code, copy, email, WA, call summary, research) for relevance/grounding/fit.
5. **Targeted revision** — pass defects back, bounded retry, re-judge. Abstain/escalate on poor evidence.
6. **Final delivery gate** — new judgment before deploy/publish/send action.
7. **Real-world outcome** — independently observe provider/test/customer/payment evidence; re-invoke where semantics help.
8. **Session continuation** — re-evaluate on new evidence / changed state / revised deliverable.

**Exempt (no extra call):** greetings, exact arithmetic, rote status reads, deterministic gates (RED/HARD_OFF/frozen/compliance, permission, exact schema).
**Required trace per consumed call:** `decision_id`, `task_id`, `tenant_scope`, `purpose`, `state_hash`, `evidence_refs`, requested/resolved model (`jev-latest` default), primitive (Choice/Noul/Score), result, downstream branch, side-effect ID, observed outcome.

**Architectural NO-NOs:** do not duplicate `typesafe_*` modules (bridge, executor, integration, services, schemas, session_policy, telephony, middleware, scraper all in `app/platform/`). Do not introduce a second SDK, key pool, secret store, or bridge. Reuse the four-slot KeyManager; verify each key's live health rather than claim "four healthy" from history. Verify provider failure does NOT bypass any compliance/frozen gate.

### 2.3 Loop Engineer mode (triggers: /loop /audit /fix /harden /production-ready /scheduler /agent-loop)

Process = **inspect → plan → implement → test → verify → record → fix → repeat.** Eight hats per loop: Principal SaaS Architect · Staff Backend Engineer · AI Agent Architect · Voice AI Engineer · SRE · Security Engineer · QA Lead · Product Engineer. Full spec = `docs/LOOP_ENGINEER.md`.
- Never "done" without exit-code evidence; never stop at audit/planning.
- Never weaken compliance (§3 below) or security. A "fix" that weakens a compliance gate = **ABORT**, not a fix.

After every loop: `## Loop Run` block in `progress.md` (Date / Goal / Inspected / Problems Found / Changed / Tests Run / Verification Evidence / Risks / Remaining / Next Highest Priority). Reply in canonical 9-field format.

### 2.4 MiniMax primary + non-fake Claude/ChatGPT removal (M01)
- **Active primary model = `MiniMax-M3`**. No new ChatGPT/Claude worker, subscription, or cost dependency.
- `scripts/start-claude-omniroute.ps1` + `scripts/claude_proxy.py` = CLIENT-COMPAT alias layer (`claude-omni-*` ⇒ `leadgen-*` ⇒ OmniRoute ⇒ MiniMax-primary upstream). Keep as alias, NOT as paid-Claude dependency. Auth = key-accepted OR 200-anonymous both work (loopback-only `:22000`).
- Anthropic/OpenAI SDK still in repo (`app/voice_agent/free_ai.py` line ~420 chain) — verify each is configured to OmniRoute fallback, NOT to a paid Claude/GPT plan.
- Boss/Manager = control surfaces, NOT 32nd agent.

### 2.5 Anti-mistake + work-quality gates (`docs/AGENT_WORK_RULES.md`)

R1 primitive evidence (status ≠ diagnosis, body padho) · R2 falsify hypothesis · R3 A/B equalize env · R4 test preconditions · R5 no broad `-k` · R6 done = exit code · R7 Read-before-Edit, never `git add -A` · R8 compliance/frozen = owner permission (green tests NOT enough) · R9 scratch cleanup before commit · R10 deploy only via `deploy_vps.sh`.

Work Quality Gate (each task): context-first (parallel Grep/Glob + full Read) → Read-before-Edit → copy neighbour convention → `/verify` green = done → skills: `task-observer` (multi-step) / `fable-operating-manual` (non-trivial) / `context-first` / `systematic-debugging` / `llm-council-decision` (ambiguous) → decide-and-ship dormant wireable gaps → Discover→Contract→Execute→Self-review→Evidence (idempotency + retry/DLQ + metrics + rollback + runbook).

### 2.6 Reference pointers (deep body NOT auto-loaded)
- **Legacy body** (legacy §§0–§9.5 + Current State full + sprint decisions): `docs/AGENTS_REFERENCE.md`.
- **Memory protocol + INDEX:** `memory/INDEX.md` (decisions/incidents/playbooks/backlog/glossary/integrations).
- **Graphify token-saving protocol:** `docs/GRAPHIFY.md` (graph query FIRST, raw source verify second).
- **Owner directive (immutable):** `docs/OWNER_DIRECTIVE_2026-09-22.md`.
- **Session startup** (`docs/context/CURRENT_STATE.md` + `ACTIVE_WORK.md` + `SESSION_HANDOFF.md`) per `docs/context/AI_OPERATING_PROTOCOL.md`.
- **Architecture map, COMMANDS, code standards, landmines (full):** `docs/AGENTS_REFERENCE.md` §2/§3/§4/§7.

## 3. CRITICAL INVARIANTS (NEVER BREAK — full text: `docs/AGENTS_REFERENCE.md` §5)

- **TRAI/telecom:** DND scrub **fail-CLOSED** (lookup fail = promotional BLOCK) · AI-disclosure at call start ("ek AI assistant") · promo calling-window **9am–7pm** (code-conservative; TRAI actual 9–9) · consent ledger opt-out = INSTANT cross-channel suppression · foreign trunks (Twilio etc.) India-domestic = ILLEGAL · cold auto-calls bina DLT = NAHI (sirf inbound auto-callback) · pure minutes-resale = Telegraph Act violation; legal = SaaS bundle, DLT/140 CLIENT ke naam.
- **DPDP Act 2023:** purpose limitation + data minimisation + consent basis for first contact · 90-din recording retention · purge API + Grievance Officer in /privacy · tenant isolation (no cross-client leak).
- **Billing truth:** `app/marketing/packages.py` = single source; pricing change = packages.py + `test_billing_truth_2026.py` SAATH; growth ₹2,999 LEGACY hidden via `get_public_packages()`; GST sirf `GST_GSTIN` set pe; invoice Rule-46 sequential `INV/2026-27/0001`. **Stripe + Razorpay BOTH REMOVED** — manual UPI = ONLY rail (owner 2026-08-05); `PROVIDER_VERIFIED` is unreachable BY DESIGN; `/api/billing/webhooks/stripe` is fail-closed stub.
- **Secrets sirf `.env`** (gitignored) — kabhi committed file/CLAUDE.md/scripts me nahi. `sk_` Pollinations key KABHI URL me nahi (proxy route only). State only via `python scripts/typesafe_status.py --probe` (fingerprint, never value).
- **Ban-safety:** WhatsApp **cold/bulk** auto-send = number ban (`SALES_AUTOPILOT_WHATSAPP_ENABLED` OFF; campaign 1-click human default). ToS-blocked auto-scrape (justdial/indiamart/sulekha/linkedin/fb/insta) REFUSED.
- **platform_dial FULL CAMPAIGN LIVE (owner go-ahead 2026-08-02):** `PLATFORM_DIAL_DAILY=1` (boolean) · `PLATFORM_DIAL_LIMIT=100` (cap/run). Compliance spine ACTIVE: DND fail-closed · TRAI window · AI-disclosure · consent · DLT_APPROVED=1 · phone-type gate · IVR blocklist · circuit breaker · 30-call training pause · recording gate · concurrency=1.
- **FastAPI first-route-wins** — naya route add karne se pehle duplicate grep (saare split routers me). Web process KABHI heavy job (Celery only). Never write prod DB from local. VPS pe `reset --hard`/blind rebuild KABHI nahi (surgical deploy only).

## 4. MEMORY PROTOCOL

Read `memory/INDEX.md` first. Load ONLY task-relevant files. Write-back same session: naya decision → `memory/decisions.md` (append-only ADR), incident → `memory/incidents.md`, procedure → `memory/playbooks.md`, parked idea → `memory/backlog.md`. **No secrets ever** (env var NAMES ok, values never). Every entry dated YYYY-MM-DD + atomic. Code vs memory disagree = code wins, phir memory fix. Tiers: `## Current State` (hot cache ≤40 lines, monthly prune) · `memory/` · `docs/SESSION_LOG.md` (archive) · agent session memory.

## 5. KNOWN LANDMINES (full list: `docs/AGENTS_REFERENCE.md` §7, `memory/incidents.md`)

- Naya `@app.get` page-route → **stale .pyc 404** = hard reload (pycache purge ya container recreate). `set -o pipefail` (build pipe `| tail` exit-code mask karta).
- Windows file-tools = source of truth; CLAUDE.md/SESSION_LOG bash-append KABHI NAHI (mid-file corruption). `USE_SILERO_VAD=0` rakho. EdgeTTS `>=7.2.0`. port = `8080` in-network, `8000` host (compose publish `8080->127.0.0.1:8000`). `:latest` = UNKNOWN-provenance prod (`/health.version` = drift detector).
- VPS pe `docker compose` bina `-f docker-compose.vps.yml` = LEGACY stack (8 min prod 502 postmortem 2026-07-18). HAR compose command me `-f docker-compose.vps.yml` explicit.
- Rate limits: Groq TPD content-heavy days pe khatam · Cerebras 429-prone · NVIDIA 40 RPM + ~5k LIFETIME (deep-tail) · Gemini free quota → 9-key rotation · email outreach cap 25/day + warmup · `PROSPECT_MAX_LOOKUPS=60`/run.
- Function-level imports startup gates ko DHOKA deta hai (2026-07-14 incident) — pricing/shared helper retire karne se pehle saare callers grep.
- Compose service `worker-heavy` (hyphen) — galat naam = `up` ABORT. `requirements.lock.txt` hi truth, edge-tts floor `>=7.2.0` (lock 7.2.8).
- Causal-claim discipline: "Errors the → maine deploy kiya → errors gaye" ≠ causation. Verify error series END timestamp before claiming credit.

## 6. ACTIVE PROJECT CONSTRAINTS

- **Free AI stack only** — koi paid STT/TTS/LLM add nahi (user mandate).
- **Max 3 overlapping code-change worktrees** (not 3 background tasks). All 9 independent business lanes may run in parallel within CPU/RAM/GPU/DB/provider/cost limits.
- **Bot/CLI scripts** (`scripts/run_ship*.ps1` 8 variants) used to `Copy-Item CLAUDE.md → AGENTS.md` and verify byte-equality. **MIGRATION UPDATE (2026-09-22):** the AGENTS_SYNC byte-equality check is removed; AGENTS.md is canonical on its own; `CLAUDE.md` is now a redirect stub. Tests (`tests/test_1000_engineers_skill.py`) updated accordingly. Older commit-history references to byte-copy rule remain harmless.
- **Commit/push/merge/deploy ONLY on explicit owner instruction** (§8 §3 of legacy body + this rule).

## 7. UPGRADE OWNER REPORT — REQUIRED FIELDS (M13)

Any owner checkpoint output must include machine-separated fields: `MINIMAX_PRIMARY` · `PLAN_VS_API_ENTITLEMENT` · `LOCAL_COMPUTER` · `VPS_PRODUCTION` · `GITHUB_CI_RELEASE` · `AGENTS_MD_AND_CLAUDE_MD_MIGRATION` · `CHATGPT_CLAUDE_WORKER_REASSIGNMENT` · `CANONICAL_LEDGER_9_WORKERS_31_AGENTS` · `TYPESAFE_FOUR_SLOTS_ACTUAL_HEALTH_AND_CONSUMED_OUTPUT` · `LOCAL↔VPS_TELEGRAM_TASK_ROUTING` · `REAL_CUSTOMER_VALUE_NET_COLLECTED_CASH` · `TESTS/ROLLBACK` · `EXACT_BLOCKER` · `NEXT_AUTHORIZED_EXECUTION`. Local test results MUST NEVER blend into VPS production success claim.

---

> **Migration note (2026-09-22):** AGENTS.md reduced from ~42 KB / 125 lines to ~10 KB. 32 KB of legacy body (legacy §0/§2-§4/§5/§6-§9.5 + full Current State + sprint decisions) extracted to `docs/AGENTS_REFERENCE.md`. Two-file sync rule (`scripts/run_ship*.ps1` + `tests/test_1000_engineers_skill.py:67`) removed. `CLAUDE.md` is now a 3-line redirect pointer. Owner directive archived at `docs/OWNER_DIRECTIVE_2026-09-22.md`.
