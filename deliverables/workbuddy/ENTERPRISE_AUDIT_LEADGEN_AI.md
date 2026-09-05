# LeadGen AI — Enterprise-Grade Audit & Admin Execution Roadmap

**Project:** `leadgenrationaivoiceagent` (FastAPI SaaS, live at https://leadsgenai.in — Hostinger VPS, Mumbai)
**Audit date:** 2026-08-30 (IST)
**Scope:** Full current-state audit (inventory, automation, agents, readiness) + admin-level fixes + 7-day / ₹5,00,000 / 1,000-engineer execution plan.
**Method:** Direct read-only inspection of the repo + live production probe. All numbers are reproducible from the cited paths.

---

## TL;DR (read this first — it changes the brief)

1. **The 7-day ₹5,00,000 sprint deadline is TODAY (2026-08-30 EOD), and `ops/owner_truth.yaml` shows `verified_collected_inr: null`, `paid_customers: 1`.** There is no verified revenue progress this sprint. This is the single most important fact.
2. **Production is 12 commits behind the repo HEAD** (`5919c379` live vs `4916353a` HEAD). The revenue-sprint hotfix is written but **not deployed**.
3. **The "9 inactive profiles" number in your brief does not reconcile with the code.** The source-of-truth state file (`workforce_rollout_state()`) gives a precise picture: **12 canary / 19 not-dispatchable (2 frozen + 7 AMBER-hold + 3 voice-hold + 7 green-hold) / 0 truly disabled.** Separately, **16 of 31 agents are behind env feature-flags that are ALL unset in `.env`**. I document the real numbers in §3.
4. **Only 9 of 304 required env vars are set** in `.env`. Whole subsystems (GSC SEO, CRM sync, security scan, DR, finops, DBRE, social posting, SMS/email cadence, journeys) are inert by configuration.
5. **The host automation layer has ZERO automations configured** — every scheduling claim in `owner_truth.yaml` depends on the VPS Celery worker, which is silent because the master `AGENT_RUNTIME` flag is unset.
6. **₹5,00,000 in 7 days via manual-UPI (one human confirms every payment) is mathematically not reachable.** I give you the honest achievable numbers and a tiered target set instead. Do not bet the business on the 5L number.

---

## 1. Project Inventory

### 1.1 What the product is
Two SaaS SKUs sold to small Indian local businesses:

| Product | Tiers | Price (₹/mo) | Notes |
|---|---|---|---|
| AI Automated Marketing | main / combo(advanced) / legacy growth(hidden) / trial | 1,999 / 5,999 / 2,999 / 0 | Annual = 10× monthly; min top-ups 100/250/500 = 1,499/3,499/5,999 |
| AI Voice Calling Agent | A / B / C (by niche band) | 4,999 / 9,999 / 19,999 | Flat per-band; standalone |

**Money path:** free lead magnets (`/audit`, `/site-audit`, `/demo`) + programmatic SEO + auto email outreach → inquiry → `/pricing` → `/start` → **manual UPI** (owner-confirmed) → subscription + top-up packs.
**Canonical payment rail = Manual UPI only** (`UPI_VPA`). There is **no payment gateway, no card, no subscription billing engine**. Every rupee requires a human (you) to confirm a credit.

### 1.2 Tech Stack (evidence: `pyproject.toml`, `docker-compose.vps.yml`, `requirements.lock.txt`, `app/config/providers.yaml`)

| Layer | Choice | Evidence |
|---|---|---|
| Language / runtime | Python 3.12 (FastAPI async) | `pyproject.toml`, `.venv` |
| Web framework | FastAPI (server-rendered HTML frontend) | `app/main.py`, `frontend/` |
| DB | PostgreSQL (+ PgBouncer :6432) | `docker-compose.vps.yml`, `alembic/` |
| Cache / broker | Redis :6379 (2 instances: broker + cache) | `docker-compose.vps.yml` |
| Vector store (RAG) | Qdrant :6333 (single `kb_main`, namespaced) | `docker-compose.vps.yml` |
| Workers / scheduler | Celery `worker`, `worker-heavy`, `worker-video`, `dsh-worker`, `scheduler` | `docker-compose.vps.yml`, `app/worker.py` |
| Telephony | FreeSWITCH + Vobiz SIP (India); Twilio = intl fallback | `app/telephony/`, `voice_stack/` |
| LLM (primary) | Mistral `mistral-small-latest` | `app/config/providers.yaml` |
| LLM fallback chain | Groq → Cerebras → Gemini → NVIDIA NIM → SambaNova → OpenRouter | `providers.yaml` |
| Voice LLM | Gemini 2.5-flash-lite (9-key rotation) | `owner_truth.yaml` |
| STT / TTS | Groq whisper-large-v3 → Gemini; EdgeTTS `hi-IN-SwaraNeural` | `providers.yaml` |
| Email | Hostinger SMTP/IMAP (`admin@leadsgenai.in`) | `README.md` |
| Prospecting | Google Maps Places (New) + self-host SearXNG | `README.md` |
| Push | ntfy (self-host) | `README.md` |
| WhatsApp | Meta Cloud + own WAHA :3111 | `README.md` |
| Observability | Prometheus / Grafana / Loki | `monitoring/` |
| Infra as code | `docker-compose.vps.yml` (canonical) + `Dockerfile.lock` | `README.md` |

**Note:** The entire AI stack runs on **free providers** (an explicit owner constraint — no paid STT/TTS/LLM). This caps concurrency and quality ceilings and is a scalability bottleneck (see §4).

### 1.3 Folder / Module Structure (key figures)

Repo: **4,060 tracked files**, **2,109 `.py`**, **~335,375 LOC in `app/`**.

| Module | Files | LOC | Purpose | Verdict |
|---|---:|---:|---|---|
| `app/api/` | 132 | 53,887 | HTTP routers (admin, billing, voice, analytics, agents, customer…) | Core; large surface |
| `app/platform/` | 192 | 101,158 | Engines, agent OS, routing, governance, autonomy | Largest; feature-rich but sprawling |
| `app/voice_agent/` | 65 | 28,281 | Real-time voice call logic | Heaviest R&D area |
| `app/marketing/` | 126 | 50,662 | SEO, content, social, outreach | Large |
| `app/agents/` | 37 | 20,856 | Coordinator, DAG/process engines, self-improve, harness | Many engines; harness INERT |
| `app/telephony/` | 24 | 11,929 | Vobiz/SIP/FreeSWITCH handlers | Critical path |
| `app/billing/` | 13 | 5,062 | Packages, promo, UPI | Small but money-critical |
| `app/security/` | 2 | 169 | Security middleware | **Critically thin** |
| `app/infrastructure/` | 3 | 472 | IAC helpers | Thin |
| `app/ml/`, `app/integrations/`, `app/automation/`, `app/services/` | — | ~22k | Support | OK |

**Config sprawl (flag it):** at repo root there are **6+ overlapping "knowledge/memory" dirs** — `memory/`, `.memory/`, `knowledge/` (11 numbered domains), `ops/`, `command_center/`, `docs/` (incl. `docs/archive/`), plus `.hermes/`, `.specify/`, `.freebuff/`, `_scratch/`, `scratch/`, `var/`, `analysis/`, `notebook_exports/`. Ownership/authority rules exist (`knowledge/` = pointers, `memory/` = archive) but the overlap invites contradiction. **1,288 `.md` files total** (see §4 Doc Quality).

### 1.4 Dependencies (evidence: `requirements.lock.txt`, `requirements*.txt`)
- Direct pinned deps: `requirements.lock.txt` exists (good). But there are **7 distinct requirement files** (`requirements.txt`, `requirements-core.txt`, `requirements-dev.txt`, `requirements-filtered.txt`, `requirements-otel.txt`, `requirements-dsh.lock.txt`, `requirements.lock.txt`). This fragmentation is a maintenance hazard.
- `pip-audit` is referenced in `SECURITY.md` but **not wired into CI** as a blocking gate (no `pip-audit` step in `security-scan.yml` flow that blocks merges — only advisory; see §3/§4 QA track).
- `.secrets.baseline` (63 KB, detect-secrets) present — good intent, but `.env` is only 9 keys so most secrets are simply undefined, not managed.

### 1.5 Data Flow (end-to-end)

```mermaid
flowchart LR
  A[Visitor: /audit /site-audit /demo] --> B[Lead capture widget + Hot Queue /app/inbox]
  B --> C[Google Maps + SearXNG prospecting]
  C --> D[Qdrant RAG + scoring /app/agents/rescore]
  D --> E[Outreach: email/WhatsApp/SMS via Celery]
  E --> F[Reply classification -> Hot Queue]
  F --> G[Voice call (FreeSWITCH+Vobiz) STT->LLM->TTS]
  G --> H[Post-call offer -> WhatsApp UPI link]
  H --> I{MANUAL UPI - OWNER CONFIRMS}
  I --> J[Workspace provisioning + subscription]
  J --> K[Postgres ledger + invoices.jsonl]
  %% EVERY arrow depends on Celery worker + feature flags; many are no-op today
```

**Single points of failure (SPOF):** one VPS hosts app+DB+Redis+Qdrant+FreeSWITCH. No replica, no read replica, no HA. `owner_truth.yaml` lists "HA 2nd server" as an EXTERNAL blocker (not done). The manual-UPI step is a **human SPOF** — you are the bottleneck on every rupee.

---

## 2. Automation Status

### 2.1 What is (nominally) automated
- **68 Celery beat entries** defined in `app/worker.py:393` (lead scraping, call queue, voice follow-ups, daily/weekly reports, CRM sync, brain-training, and 40+ `staff-*` jobs covering ops, revenue, SEO, pipeline, QA, finops, security, DBRE, deps, MCP, readiness).
- **11 GitHub Actions workflows** (CI, tests, security-scan, deploy-vps, migrations, uptime, llm-eval, dsh-runtime, pr-factory-gate-a, pr-factory-ci-repair, auto-merge).
- **Compliance calling** is LIVE under gates (DND fail-closed, 9–19 IST, AI-disclosure, concurrency=1).

### 2.2 What is actually running — and the critical gap
**The master `AGENT_RUNTIME` flag is NOT set in `.env`** (verified: `grep AGENT_RUNTIME .env` → not found). Per `app/platform/agent_runtime.py` and `app/tasks/staff_jobs.py`, every `staff-*` job early-returns as a **no-op when its flag (or the master flag) is OFF**. So the 68 beat entries exist but **do not execute behaviour** on the VPS today. Same for the agent OS dispatch path.

**`.env` has 9 keys; `.env.example` has 304.** Every subsystem behind an unset flag is INERT:

| Subsystem | Flag | State |
|---|---|---|
| SEO rank tracking (GSC) | `GSC_ENABLED` | INERT (creds present, flag unset) |
| CRM sync (HubSpot/Zoho) | `CRM_SYNC` | armed but no provider wired |
| Social auto-post | `SOCIAL_ENGINE` | armed, no Postiz/WAHA backend |
| Email/SMS/WhatsApp cadence | `CADENCE_ENGINE` | INERT |
| Journey automation | `JOURNEY_ENGINE` | INERT |
| Code upgrader | `CODE_UPGRADER` | OFF |
| Infra handler watchdog | `INFRA_HANDLER` | OFF |
| SRE/DR | `SRE_AGENT` | OFF |
| FinOps margin digest | `FINOPS_AGENT` | OFF |
| Security posture scan | `SECURITY_AGENT` | OFF |
| DB reliability | `DBRE_AGENT` | OFF |
| Data integrity | `DATA_INTEGRITY_AGENT` | OFF |
| Dependency CVE audit | `DEPS_AGENT` | OFF |
| MCP engineer | `MCP_ENGINEER` | OFF |
| Campaign optimizer | `CAMPAIGN_OPTIMIZER` | OFF |
| Agent harness (self-improve) | `AGENT_HARNESS` | INERT by default |
| Boss autonomy (owner-free decisions) | `BOSS_FULL_AUTONOMY`+`BOSS_DECISION_GOVERNANCE` | OFF unless both set |

### 2.3 The host automation layer — ZERO automations
The WorkBuddy automation system (this session) has **no automations configured** (`automation_update list` → empty). Daily digests, ntfy pushes, and the Hot-Queue owner pack that `owner_truth.yaml` lists as "LIVE" all depend on the VPS worker that is currently silent. **There is no fallback scheduler outside the VPS.**

### 2.4 Automation Gaps (prioritised)

| Gap ID | Gap | Current state | Evidence | Priority |
|---|---|---|---|---|
| A1 | Manual UPI confirmation is the only revenue rail → you are the bottleneck on every ₹ | 100% manual, you confirm each credit | `owner_truth.yaml` `payment_verification` | **High** |
| A2 | 16/31 agents + 40+ staff jobs inert (master flag unset) | No autonomous ops running | `.env` (9 keys), `app/worker.py` | **High** |
| A3 | Deploy drift: 12 commits not in prod | Manual deploy never re-run post-sprint | `/health.version` 404; `owner_truth.yaml` last_known_sha | **High** |
| A4 | No payment gateway / subscription billing | Manual reconciliation only | `app/billing/` (no gateway) | **High** |
| A5 | GSC organic inbound dormant | Flag unset | `owner_truth.yaml` `gsc_tracking: INERT` | **Medium** |
| A6 | CRM sync armed but provider missing | Leads not pushed to client CRMs | `app/platform/automation_health.py:508` | **Medium** |
| A7 | Email warmup cap 25/day blocks scale | No scale path until warmed | `memory/integrations.md` | **Medium** |
| A8 | No host-level (WorkBuddy) automations | Single point of failure on VPS cron | `automation_update list` empty | **Medium** |
| A9 | Doc sprawl (1,288 md, 6+ overlapping KB dirs) | Hard to navigate, contradiction risk | `docs/`, `memory/`, `knowledge/`, `ops/` | **Low** |
| A10 | 89 uncommitted/untracked files + 20 stale branches | Repo hygiene drift | `git status` | **Low** |
| A11 | 90 MB `omniroute_storage_temp.sqlite` + `nul` (60 B) committed at root | Hygiene | repo root | **Low** |

---

## 3. Agents Directory

### 3.1 The "9 inactive profiles" — reconciliation (you asked specifically)

Your brief says **9 profiles inactive**. The code gives a **different, precise** number. Here is the truth from `app/platform/agent_runtime.py` (`PILOT_AGENTS`) and `agent_runtime_workforce.py` (`workforce_rollout_state()`):

| Cohort | Count | Agents | Dispatchable today? |
|---|---:|---|---|
| **Canary (pilot)** | 12 | kavya, isha, zara, hermes, pranav, vidya, arnav, kabir, diya, aryan, arya, nikhil | Only if `AGENT_RUNTIME` ON (currently **OFF**) |
| Frozen (intentionally disabled) | 2 | swara, ananya | No — RED lane |
| AMBER hold | 7 | rohan, kiran, priya, anika, ira, riya, raksha | No |
| Voice hold | 3 | arjun, meera, tara | No |
| Green hold (capability ready, not promoted) | 7 | manager, lekha, neha, ravi, dev, guru, vikram | No |
| **Total not-dispatchable** | **19** | — | — |
| Truly "disabled" | 0 | — | (none flagged disabled; 2 frozen + 17 held) |

**So the real answer:** 12 canary / **19 not-dispatchable** / 0 disabled. The "9" in your brief likely conflates one of these: (a) the **9 Hermes bots** named in `owner_truth.yaml` vs the **8** actually defined in `HERMES_AGENT_ROSTER.yaml` (a doc contradiction), or (b) a subset of gated agents. **It does not match the code.** The actionable truth: **19 of 31 agents are held/frozen**, and the 12 canary agents do nothing because the master `AGENT_RUNTIME` flag is unset.

### 3.2 Roles, responsibilities, permissions (full 31)

Mapping (agent → product → primary duty → writes prod? → contacts customers? → gate):

| Agent | Product | Role | Writes prod | Contacts Cust | Gate flag |
|---|---|---|:--:|:--:|---|
| manager | platform | Supervisor / work routing (LangGraph) | no | no | (core) |
| swara | voice | Telecaller | yes | yes | — (frozen) |
| ananya | voice | Appointment booker | yes | yes | — (frozen) |
| riya | voice | AI receptionist | yes | yes | (AMBER) |
| dev | marketing | Data analyst / KB seed | yes | no | (green) |
| rohan | marketing | Leads manager | no | no | (AMBER) |
| arjun | voice | QA engineer | no | no | (voice-hold) |
| meera | voice | Trainer / QA | no | no | (voice-hold) |
| lekha | voice | Call-analytics lead | no | no | (green) |
| raksha | voice | Human escalation | yes | yes | CALL_TRANSFER (AMBER) |
| kavya | platform | Ops monitor | no | no | (pilot) |
| hermes | platform | Infra handler / watchdog | no | no | INFRA_HANDLER |
| isha | marketing | Marketing exec (social copy) | no | no | (pilot) |
| tara | voice | Voice infra ops | no | no | (voice-hold) |
| nikhil | platform | Revenue ops / dunning | no | no | (pilot) |
| vikram | platform | Code upgrader | yes* | no | CODE_UPGRADER |
| guru | platform | Skill trainer / KB steward | yes | no | SKILL_PACK |
| pranav | platform | SRE / reliability / DR | no | no | SRE_AGENT |
| vidya | platform | FinOps / margin | no | no | FINOPS_AGENT |
| arnav | platform | Security / compliance | no | no | SECURITY_AGENT |
| kabir | platform | DB reliability | no | no | DBRE_AGENT |
| diya | platform | Data-integrity | no | no | DATA_INTEGRITY_AGENT |
| aryan | platform | Dependency / supply-chain | no | no | DEPS_AGENT |
| arya | platform | MCP engineer | no | no | MCP_ENGINEER |
| ravi | marketing | SEO scout | no | no | (green) |
| neha | marketing | Pipeline ops | no | no | (green) |
| kiran | marketing | Campaign optimizer | no | no | CAMPAIGN_OPTIMIZER |
| priya | marketing | CRM sync | yes | no | CRM_SYNC |
| zara | marketing | Social media manager | yes | yes | SOCIAL_ENGINE |
| anika | marketing | Cadence manager | no | no | CADENCE_ENGINE |
| ira | marketing | Journey automation | no | no | JOURNEY_ENGINE |

(* = with owner approval for core code; safety skills auto.)

### 3.3 Coordination flow (as designed) vs as-running

**Designed:** `Owner` → `manager` (supervisor) → **8 Hermes bots** (owner_orchestrator, revenue_cro, lead_intelligence, outreach_conversation, voice_swara, marketing_content, engineering_sre, qa_analytics_finance) → 31 agents. Admin agents (pranav/arnav/kabir/diya/aryan/hermes/vidya) report to the engineering_sre + qa bots; the Boss-autonomy layer (`boss_autonomy.py`) is supposed to advance non-delegable decisions to `needs_owner`.

**As-running:** `BOSS_FULL_AUTONOMY`/`BOSS_DECISION_GOVERNANCE` are OFF (no `upi_owner_only` automation). The 8 Hermes "bots" are **documentation only** — there is no runtime process implementing them; they are a routing metaphor in `HERMES_AGENT_ROSTER.yaml`. Real coordination is: you → manual `/app/inbox` + ntfy → 12 canary agents (silent) → nothing. **Escalation path exists on paper (P0→owner immediately) but the agents that would raise it are held/frozen.**

```mermaid
flowchart TD
  O[Owner] --> M[manager supervisor]
  M --> H1[owner_orchestrator]
  M --> H2[revenue_cro]
  M --> H3[lead_intelligence]
  M --> H4[outreach_conversation]
  M --> H5[voice_swara]
  M --> H6[marketing_content]
  M --> H7[engineering_sre]
  M --> H8[qa_analytics_finance]
  H7 --> AD[admin agents: pranav arnav kabir diya aryan hermes vidya]
  H8 --> AQ[arjun QA]
  note right of AD: 7 of these are GATED + OFF
  note right of H1: Hermes bots are DOCS only, no runtime
  O -. manual UPI confirm .-> K[every payment]
```

### 3.4 Kanban replacement
The legacy `.hermes/tasks/leadgen_kanban.json` (747 B, 6 stale cards, status `pending`) is abandoned. **Recommendation: GitHub Projects (board) + Issues with automation** — it already sits next to your 11 workflows and 20 branches, supports labels/columns/WIP limits, and can be driven by `pr-factory-*` and issue templates. Migration: import the 6 cards as issues, define columns `Backlog → In Progress (WIP 5) → Review → Done`, add a `P0/P1/P2` label set, and a daily auto-issue for the Hot-Queue owner pack. Alternative if you want zero-new-tool: a `work-queue.yaml` in-repo generated nightly by a (currently inert) `staff-*` job — but that still needs the flag flipped, so **GitHub Projects is the faster win**.

---

## 4. Enterprise-Grade Readiness Assessment (1–10, with evidence)

| Dimension | Score | Evidence | Justification |
|---|---:|---|---|
| **Security** | 5/10 | `app/api/auth_deps.py` (JWT + 2FA wired), `app/security/` only **169 LOC**, `.secrets.baseline` + `check_secrets.py` present, `SECURITY.md` claims VPC/private-DB/Secret-Manager (but infra is a single public VPS) | Auth framework exists (good). But security logic is 2 files/169 LOC for a system handling PII + call recordings; `pip-audit` not a CI gate; `SECURITY.md` describes GCP infra (VPC, Secret Manager) that contradicts the actual single-Hostinger-VPS reality — documentation overstates posture. |
| **Scalability** | 3/10 | `docker-compose.vps.yml` (1 VPS, 11 services), single Postgres, PgBouncer, free LLM providers, `platform_dial_limit: 100` | No horizontal scaling, no replicas, no HA. Free-provider LLM/STT/TTS caps concurrency. 100-call/day cap. Cannot absorb 1,000 engineers or 5L volume. |
| **Reliability** | 4/10 | 11 restart policies + 11 healthchecks in compose; `monitoring/` + `incidents/` + DR drills referenced; but SPOF single VPS, `owner_truth.yaml` "HA 2nd server" = EXTERNAL blocker, deploy drift 12 commits | Resilient *within* one host, but a host failure = total outage. No verified backup-restore proof in repo. |
| **Monitoring & Observability** | 5/10 | `monitoring/` (Prometheus/Grafana/Loki rules), `app/observability_otel.py` + `requirements-otel.txt`, ntfy, `automation_health.py` (armed-but-no-backend detector) | Tooling present and thoughtful (e.g. armed-but-dead detector). But with master flag OFF, dashboards have no live data; no SLO/error-budget definitions found. |
| **CI/CD pipeline** | 6/10 | 11 workflows; `deploy-vps.yml` gate-only (`DEPLOY_ENABLED` unset); **10 `continue-on-error` steps** across deploy/llm-eval/migrations; `auto-merge.yml` merges w/o review | Gates exist but are advisory: 10 neutered steps, auto-merge without human review, prod deploy is manual. No coverage/lint/type gate enforced. |
| **Documentation quality** | 4/10 | 1,288 `.md`; `AGENTS.md`≡`CLAUDE.md` (byte-identical 35 KB); `ops/owner_truth.yaml` good; but 6+ overlapping KB dirs, `docs/archive/`, unreconciled "9 bots vs 8 bots" | Rich but sprawling and partly contradictory; a newcomer cannot find the single source of truth quickly. |
| **Test coverage** | 7/10 | **847 test files, 8,499 test functions**; only 2 trivial-pass, 1 assert-true, 56 no-assert, 12 skipped, 0 xfail; `pytest --collect-only` clean (2 skips: playwright missing, load off) | Genuinely substantial suite (voice compliance, injection guards, kill-fail-closed, webhook retry). But **no `fail_under` / coverage gate** in `pyproject.toml`; no coverage % recorded; suite is NOT run in CI as a merge blocker. |
| **Compliance** | 6/10 | DND fail-closed, TRAI 9–19 IST, AI disclosure, consent ledger, DLT, 90-day retention, grievance officer, `/privacy`; DPDP referenced; "SOC2 in progress", GDPR claimed | Telecom-compliance engineering is a real strength (fail-closed by design). But `SECURITY.md` claims SOC2/GDPR as "implemented/in progress" with no evidence artifacts; DPDP is India-specific and mostly honoured in code, not documented as a control framework. |

**Overall weighted readiness: ~4.8 / 10.** Verdict: a *feature-rich, compliance-aware single-tenant MVP* with strong test discipline and a thoughtful agent design — but **not enterprise-grade**: it is a single-server, manually-operated, partially-configured system whose automation is mostly dormant and whose revenue rail is a human bottleneck.

---

## 5. Improvement Roadmap (per-gap fixes)

| Gap | Fix | Priority | Effort | Impact | Owner role | Success criteria |
|---|---|---|---|---|---|---|
| A1 Manual UPI | Add an owner-approval queue + auto-provisioning on confirm; explore a real PG (Razorpay) for scale | P0 | M | H | Owner + billing eng | <2 min owner action per payment; 0 manual SQL |
| A2 Agents inert | Set `AGENT_RUNTIME=1` + flip the 16 gates you actually want; promote 7 green-hold to canary | P0 | S | H | Owner (flags) + SRE | 12 canary agents execute; dashboard shows activity |
| A3 Deploy drift | Re-run canonical `scripts/deploy_vps.sh` with `APP_VERSION=<sha>`; verify `/health.version` | P0 | S | H | DevOps | Prod SHA == HEAD; version endpoint 200 |
| A4 No billing engine | Razorpay/Pg integration (compliant) for non-UPI paths | P1 | L | H | Billing eng | Automated subscription + invoice |
| A5 GSC dormant | Flip `GSC_ENABLED=1` after read-only cred check | P1 | S | M | SEO agent | Rank tracking in dashboard |
| A6 CRM sync dead | Wire HubSpot/key or disable claim | P1 | S | M | Integrations | Qualified leads push or claim removed |
| A7 Email warmup | Stagger warmup; raise cap post-warm | P2 | M | M | Outreach | >25/day safely |
| A8 No host automations | Configure WorkBuddy daily digest + dead-man alert | P2 | S | M | Owner | Daily ntfy + alert on VPS down |
| A9 Doc sprawl | Collapse to `docs/` as source; `knowledge/` pointers only; delete dupes | P2 | M | L | Tech writer | Single INDEX; 0 contradictions |
| A10 Repo hygiene | Commit/push; prune 20 stale branches; `.gitignore` the sqlite/`nul` | P2 | S | L | DevOps | Clean `git status` |
| A11 Secrets/CI | Wire `pip-audit` + `detect-secrets` as blocking CI gate; remove 10 `continue-on-error` | P1 | M | H | Security eng | Merge blocked on vuln/secret |

**Step-by-step execution (you can follow directly):**
1. **Today (P0):** `git pull` → confirm HEAD `4916353a`; edit VPS `.env` to add `AGENT_RUNTIME=1` + the 16 gates you want live; re-run `scripts/deploy_vps.sh APP_VERSION=4916353a`; confirm `/health` 200 and agent dashboard activities.
2. **Day 1:** Wire owner UPI-approval queue; triage Hot Queue (42 cards); flip `GSC_ENABLED`; fix CRM-sync claim.
3. **Day 2–3:** Add `pip-audit`/`detect-secrets` CI gate; remove `continue-on-error`; prune branches.
4. **Week 1:** Razorpay eval; GitHub Projects board; doc collapse; DR drill.
5. **Month 1:** HA second server; telemetry/SLO; SOC2 evidence pack.

---

## 6. Critical Admin-Level Execution — ₹5,00,000 in 7 Days with 1,000 Engineers

### 6.1 Honest feasibility verdict (this is the part that protects you)
- **Baseline:** `verified_collected_inr: null`, `paid_customers: 1` (₹1,999). No verified revenue this sprint.
- **The rail:** Manual UPI, **you confirm every credit**. Realistic human throughput ≈ **20–40 confirmations/day** (each needs a bank-check + workspace provision). At the highest SKU (₹19,999), 40/day × 7 = ₹5.6M — *theoretically* possible **only if** you can generate 40 qualified, high-ACV buyers/day who pay via UPI you manually verify. At the realistic blended price (~₹4,000), 40/day × 7 = ₹1.12M. At the actual observed rate (1 paying customer in the whole sprint), ₹5L is **not reachable in 7 days**.
- **Email ceiling:** warmup cap **25/day** until warmed — top-of-funnel volume is throttled by design.
- **1,000 engineers in 7 days:** Impossible to hire+onboard+make productive. A single VPS cannot absorb 1,000 concurrent committers; review span-of-control caps a lead at ~5–8. Realistic *sourced roster* in 7 days ≈ 150–250; *productive PRs* from new hires ≈ 20–40.
- **Conclusion:** ₹5,00,000 in 7 days with manual UPI is **not achievable as stated**. Do not stake the business on it. Below is the **achievable plan** plus the **structural plan** to make ₹5L/month a steady state.

### 6.2 Tiered target set (use this instead)

| Tier | Window | Realistic target | How |
|---|---|---:|---|
| **Committed (P0)** | 7 days | **₹40,000–₹1,20,000** | 10–30 paid conversions at blended ₹4k via manual UPI you can actually verify; activate the 12 canary agents + GSC + cadence to fill the funnel |
| **Stretch (P1)** | 30 days | **₹3,00,000–₹5,00,000** | Add Razorpay (kill the human bottleneck), warm email to 100+/day, 2nd server for HA, reseller/agency channel (5–10 agencies × 10 clients) |
| **Structural (P2)** | 90 days | **₹5,00,000 / month recurring** | Recurring subscriptions via gateway + voice-band-C at scale + agency network; 1,000-talent roster as a *marketplace*, not 1,000 employees |

### 6.3 7-Day execution plan (toward the Committed target)

| Day | Objective | Must-do (3–5) | Owner (role) | Deadline | Success criteria | Revenue checkpoint |
|---|---|---|---|---|---|---|
| 0 (today) | Unblock systems | Flip `AGENT_RUNTIME`+gates; deploy HEAD; build UPI-approval queue | Owner + SRE | EOD | Agents firing; prod==HEAD | baseline reset |
| 1 | Funnel on | Flip GSC; arm cadence (compliant); Hot-Queue triage 42 | Marketing + Owner | EOD | Inbound + sequences live | 2–5 paid |
| 2 | Conversion | Trial→paid nudges; Jiya upsell; personalise outreach | Revenue CRO | EOD | 1 upsell + 3 trials | ₹10–20k |
| 3 | Channel scale (safe) | Scale WhatsApp only if suppression OK; raise email to 50/day post-warm | Outreach | EOD | 0 spam/complaints | +₹15–30k |
| 4 | Optimise | A/B CTA/offer; plug biggest drop-off | Growth opt | EOD | winning variant | +₹15–30k |
| 5 | Reactivate | Win-back stale leads; referrals | CRM sync | EOD | 1 reactivation | +₹10–20k |
| 6 | Scale winners | Pour volume into proven ICP/channel | All | EOD | CAC stable | +₹20–40k |
| 7 | Close+collect | Hot leads, open offers, pending UPI, renewals | Owner | EOD | All UPI verified | ₹40k–1.2L cumulative |

### 6.4 1,000-engineer plan (realistic design)
- **Model:** a *talent roster/marketplace*, not 1,000 employees. Funnel: Sourced → Screened → Onboarded → Productive. Conversion: 1,000 sourced → ~250 screened → ~120 onboarded → ~40 first-PR in 7 days.
- **Role distribution (for a 1,000 roster):** Builders 55% (550: Python/FastAPI, VoIP, React/HTML, QA), Reviewers 15% (150), Ops/SRE 10% (100), Data/Leads 8% (80), Security/Compliance 5% (50), Technical Writing/Docs 4% (40), Sales/Closers 3% (30). Span of control: 1 lead per 8 → ~125 leads.
- **Hiring/onboarding:** Indian talent via LinkedIn/Instahyre/referrals; screen bar = 1 small PR to a safe `good-first-issue`; day-0→day-2 sequence: env setup → read `CLAUDE.md` + `ops/owner_truth.yaml` → first PR to a branch (never main); access = **fork+PR only, no direct prod/VPS access** (security: 1,000 people with VPS access is untenable).
- **Kanban alternative:** GitHub Projects board (see §3.4).
- **Coordination redesign (activate the 19 held agents + seamless flow):**
  ```mermaid
  flowchart LR
    O[Owner] --> BOSS[Boss autonomy ON: BOSS_FULL_AUTONOMY=1 + GOVERNANCE=1]
    BOSS --> MGR[manager supervisor]
    MGR --> BOTS[8 Hermes bots = routing layer in code, not docs]
    BOTS --> A31[31 agents: promote 19 held -> canary]
    A31 --> ADMIN[admin agents raise P0 -> ntfy + Hot Queue]
    ADMIN --> O
    O -. UPI confirm only .-> PAY[every payment]
  ```
  Concrete steps to "activate" the 19: (1) set `AGENT_RUNTIME=1`; (2) promote the 7 green-hold to canary (they have capability registered); (3) flip the 16 env gates for the functions you want; (4) keep `swara`/`ananya` frozen until voice QA sign-off; (5) turn `BOSS_FULL_AUTONOMY`+`BOSS_DECISION_GOVERNANCE` ON so non-delegable decisions auto-route to `needs_owner` instead of stalling.

### 6.5 Key metrics / KPIs & daily tracking
- **North-star:** verified collected revenue (₹), source = ledger + owner UPI confirm.
- **Funnel KPIs:** visitors → lead-magnet → inquiry → demo → proposal → UPI sent → **UPI confirmed** → onboarded. Daily targets to hit ₹5L (stretch): ~125 inquiries/day, ~25 demos, ~10 paid.
- **Tracking plan:** owner dashboard `/app/office` + daily 09:00 IST ntfy brief (currently inert — flip `staff-hot-queue-owner-pack-daily`); go/no-go gate = revenue vs checkpoint at EOD; trigger replan if <50% of day target by 18:00 IST.
- **Risk register (top 5):** (1) UPI human bottleneck — mitigate: Razorpay eval Day 2; (2) email warmup cap — mitigate: stagger; (3) compliance ban (cold WA) — mitigate: cold WA OFF (already); (4) prod drift — mitigate: deploy today; (5) agent mis-fire — mitigate: canary + kill switches fail-closed.

---

## 7. Consolidated Admin Action Plan (highest priority on top)

### 7.1 Top fixes (do these first)
1. **P0 — Deploy the sprint (today).** Prod is 12 commits behind; re-run `scripts/deploy_vps.sh APP_VERSION=4916353a`. Without this, nothing else matters.
2. **P0 — Flip `AGENT_RUNTIME=1` + the 16 agent/env gates.** 19 of 31 agents and 40+ jobs are silent. This is the cheapest 10× leverage you have.
3. **P0 — Build the owner UPI-approval queue** so each payment is <2 min and auto-provisions. You are the only revenue bottleneck.
4. **P1 — Wire `pip-audit` + `detect-secrets` as blocking CI gates; remove the 10 `continue-on-error` steps** (security + CI integrity).
5. **P1 — Fix the GSC/CRM-sync claims** (flip `GSC_ENABLED`; either wire CRM key or stop claiming CRM sync is live).

### 7.2 First-3-days execution sequence
- **Day 0 (today):** `git pull` → confirm HEAD `4916353a` → edit VPS `.env` (`AGENT_RUNTIME=1`, the 16 gates, `GSC_ENABLED=1`) → run `scripts/deploy_vps.sh APP_VERSION=4916353a` → confirm `/health` 200 + agent dashboard activity → stand up UPI-approval queue.
- **Day 1:** Triar Hot Queue (42 cards); arm cadence (compliant, suppression-aware); verify GSC rank tracking live; prune 5 stale git branches.
- **Day 2:** Add CI security gates (pip-audit/detect-secrets, kill `continue-on-error`); evaluate Razorpay; send trial→paid + Jiya upsell; GitHub Projects board created from the 6 stale kanban cards.

### 7.3 Immediate owner decision required
Your ₹5,00,000/7-day target **expires today with null verified revenue**. Choose now:
- **(A)** Accept the **Committed 7-day target (₹40k–₹1.2L)** and execute §6.3, OR
- **(B)** Re-baseline to the **30-day ₹5L stretch** (requires Razorpay + HA + agency channel), OR
- **(C)** Keep chasing 5L/7d manually — *not recommended; the math does not support it.*

I recommend **(A) now, (B) as the real plan.** Tell me which and I will generate the exact `.env` diff and the GitHub Projects board setup next.

---

*Audit produced by direct inspection of `C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent` + live probe of https://leadsgenai.in on 2026-08-30. All figures reproducible from cited files. No project files were modified.*
