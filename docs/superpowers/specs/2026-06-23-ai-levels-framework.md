# The 5 Levels of AI Agents — And Where LeadsGenAI Lives

> A builder's framework for understanding the real capability gap between a weekend automation project and an enterprise-grade AI platform. Each level is real — and each one is provable in this codebase.

---

## The Spine Metaphor

There's a moment every builder recognizes: you cross what I call "the spine" — the point where your system stops being something you manage and starts being something that manages itself. Below the spine, you are the loop. Above it, the system is the loop and you are the orchestrator.

Most builders stay below Level 3. This document maps exactly where LeadsGenAI sits — and why reaching Level 5 is what lets you *sell* what you've built.

---

## Level 1 — Basic Automation

> "Your first agents are just scheduled tasks. They run. They don't think."

You replace manual work with code. Someone fills a form → a record gets saved. A cron job fires → an email goes out. The system does exactly what you told it, when you told it, with no awareness of whether it's working.

**What this looks like in this codebase:**
- Static FastAPI routes handling form submissions and storing leads to `data/`
- `email_sender.py` firing Hostinger SMTP on a trigger — same template, every time
- `niches.py` returning static niche data with no adaptation

**Why it matters:** You replaced a spreadsheet and a VA. That's real. But the system can't adapt, can't recover, and can't learn. Every failure is silent unless you happen to look.

---

## Level 2 — Keyword Agents / Personalized

> "Agents react to what's happening — but only on rails you pre-defined."

You graduate from scripts to named agents with roles. Each agent has a context: a niche, a client, a task type. The system dispatches to them based on what triggered it. It feels like a team — because it *is* a team, just one you wired by hand.

**What we built:**

| Agent | File | What it does |
|-------|------|-------------|
| **Rohan** (Leads Manager) | `platform/team.py` | Dispatches outreach plan, qualification criteria per niche |
| **Isha** (Marketing) | `platform/team.py` | Generates social posts, festival content, GBP tips |
| **Dev** (Data Analyst) | `platform/team.py` | Seeds knowledge base per new client — KB grounded per niche |
| **Arjun** (QA) | `platform/team.py` | Runs voice agent testing suite against scripted personas |

Supporting modules:
- `niches.py` — 39 built-in niches, `lead_band()` routes each to Band A/B/C pricing
- `qa_checks.py` — pure regex/heuristics (no LLM), India-specific discipline: checks for pushy-after-soft-no, talk/listen ratio, missing permission opener, literal translation artifacts
- `self_improve.py` (task queue mode) — static action queue dispatches to 13 growth actions

**Why it matters:** The system feels like a team, not a script. But it's still on rails — it does what you pre-defined per trigger. It can't detect that an entire funnel stage is broken and reroute around it.

---

## Level 3 — Dynamic Hooks / "Crossing the Spine"

> "Your system responds to what's *actually* happening in real time — not what you predicted."

This is the crossing point. The system now observes its own state and adjusts. It's not just reacting to inputs — it's detecting signals, closing loops, and healing itself. You built dynamic hooks: the system is connected to its own outputs.

**What we built:**

**Real-time voice intelligence** (`telephony/vobiz_stream.py`):
Live WebSocket session — VAD (Silero, 16k) → Groq Whisper STT → free-stack LLM chain → EdgeTTS — all in one streaming bidirectional connection. The agent isn't playing a recording; it's thinking in real time. If the caller interrupts (barge-in), `BARGE_GUARD` distinguishes cough/backchannel from real interruption before yielding the floor.

**Weakest-stage self-routing** (`platform/self_improve.py`):
Every N=8 runs, the system calls `growth_optimizer.funnel_snapshot()`, identifies the lowest-converting stage, and routes its next task toward fixing it. Not random action selection — weighted toward what's actually broken. Diversity guard prevents any one action from monopolizing runs (20-min cooldown per action type).

**LLM circuit breakers** (`voice_agent/free_ai.py`):
6 provider chain (Mistral → Groq → Cerebras → Gemini → SambaNova → OpenRouter). Each provider has an escalating cooldown on 429/quota: 60s → 120s → 240s → ... → 30min cap. "Per day limit reached" → instant 30min skip. Success resets. The system reroutes around failure automatically.

**Live automation flags** (`/api/growth/infra/flags`):
30+ feature switches observable and toggleable at runtime — no redeploy. `OBSIDIAN_SYNC`, `SELF_IMPROVE_LOOP`, `FLOW_RUNNER`, `METER_ALERTS`, etc. The system's behavior adapts to environment state.

**Eval gate** (`voice_agent/eval_gate.py`):
After every self-improve run, score is compared to a rolling median baseline. Regression detected → action flagged → loop self-corrects before degradation compounds. Wired into `self_improve` + DeepEval CI.

**Why it matters:** You are no longer required to notice failures. The system notices them, adjusts, and tells you only when it can't recover alone. This is "the spine."

---

## Level 4 — End-to-End Orchestration

> "Agents enforce plans, log every hiccup, and self-correct along the way. You are the orchestrator."

The system now runs multi-agent plans with memory, critic feedback loops, human approval gates before risky actions, and a fully event-sourced audit trail. You review outputs — you don't manage inputs.

**What we built:**

**Coordinator with Reflexion + Hierarchical + Debate** (`agents/coordinator.py`):
- `coordinate_advanced()`: recall episodic memory → plan → execute → MAR critic grades output (0-1, weaknesses, fixes) → reflect → retry (bounded rounds)
- `coordinate_hierarchical()`: Boss → 3 parallel sub-teams → merge (AgentVerse-style dynamic recomposition per round)
- `debate()`: Rohan (pro) vs Kavya (con) → Boss judges with verdict tracing
- Episodic memory (CoALA): verbal reflections + scores stored; top-k retrieved by keyword overlap for Reflexion hint

**LLM Council — Karpathy 3-stage consensus** (`agents/llm_council.py`):
- Stage 1: 4 providers (Mistral/Groq/Cerebras/Gemini) answer in parallel, independently
- Stage 2: anonymized peer ranking — Response A/B/C, no one knows who wrote what (kills halo bias)
- Stage 3: Chairman (Mistral) synthesizes from rankings + disagreements into one actionable verdict
- Live at `POST /api/agents/council` → UI at `/app/agents`

**Process engine with event-sourced journal** (`agents/process_engine.py`):
Every state transition is an immutable JSONL event. State is always derived by replaying the journal — crash-safe resume guaranteed. Human approval breakpoints pause execution before risky steps (email outreach, content publish). Per-step 240s hard cap. Celery worker advances processes; `approve()`/`reject()` are the only human inputs required.

**24-job scheduler with dead-man watchdog** (`platform/team_scheduler.py`):
Single-instance lock (heartbeat mtime, cross-process). Boot-grace: heavy daily jobs skip if their window is active at boot (prevents restart-storm duplicates). `automation_health.record_run()` wraps every job — overdue alert fires if job stalls. 24+ jobs covering: blog, content, digest, outreach, followups, QA, trainer, KB refresh, pipeline ops, evening wrap, weekly marketing, Saturday hygiene, and more.

**Platform orchestrator** (`platform/orchestrator.py`):
`PlatformOrchestrator` runs the full platform automatically — lead scraping, campaigns, calls, appointments, billing — as a unified loop. `PlatformStats` tracks platform-wide KPIs (leads scraped, calls made, appointments, revenue) with health checks.

**Why it matters:** The platform runs itself. You review outputs, not inputs. If a campaign underperforms, the system detects it, rescores leads, and adjusts outreach — before you check your dashboard.

---

## Level 5 — Enterprise Hardening

> "A team of agents plays devil's advocate before you ship anything. The system doesn't just run — it *defends*."

This is what separates a product you can sell from a product that will get you a 2am call. At Level 5, your system has adversarial testing before production, legal compliance gates, revenue integrity guarantees, persistent memory across sessions, and dedicated engineer agents with KPI mandates. You can hand this to a paying customer with confidence.

**What we built:**

### Devil's Advocate & Adversarial Testing

**Persona-driven eval suite** (`voice_agent/eval_suite.py`):
Scripted customer personas run against the voice agent before any change reaches production. Each persona has a `next_line()` callback (scripted but varied — pushy-after-soft-no, Hindi robustness, objection escalation) and a `success_criteria()` judge. Pure heuristics — no LLM, no false positives. Catches India-telecalling failure modes before a real customer encounters them.

**Council debate pattern** (`agents/coordinator.py` debate mode):
Rohan argues pro, Kavya argues con — Boss judges with a traceable verdict. Every strategic decision can be pressure-tested before it becomes an action.

**Anonymized peer ranking** (`agents/llm_council.py` Stage 2):
Kills confirmation bias at the architectural level — no model sees its own label during ranking.

### Engineer KPI Agents (always-on, scheduled)

| Agent | File | Schedule | What it watches |
|-------|------|---------|----------------|
| **Arnav** (Security) | `platform/team.py` | Daily 09:30 IST | DPDP posture, TRAI compliance, secret rotation, CVE triage, DSAR handling |
| **Pranav** (SRE) | `platform/team.py` | Hourly | DR drills, backup integrity, capacity headroom, SLO tracking |
| **Vidya** (FinOps) | `platform/team.py` | Daily 09:00 IST | Per-tenant unit economics, margin-negative niche flags, LLM spend trends |

### Compliance Gates

- **`dpdp.py` + `data_privacy.py`**: DPDP Act 2023 — Right-to-Access export, Right-to-Erasure (atomic JSONL rewrite + DB anonymize), sha256 audit log (never plaintext PII), destructive gate requires `DATA_ERASURE=1` + `confirm=True`
- **`consent_ledger.py`**: Opt-out → instant cross-channel suppression. 90-day recording retention enforced.
- **DND fail-CLOSED**: Lookup failure = promotional block (never pass). TRAI compliance is not optional.
- **Calling window**: Promo calls 09:00–19:00 IST (conservative; TRAI actual is 09:00–21:00).

### Revenue Integrity

- **`gst_invoice.py`**: Sequential `INV/2026-27/0001` (Rule 46 CGST, SAC 998313). Intra-state CGST+SGST, inter-state IGST, unregistered = no tax. Append-only `data/invoices.jsonl`, atomic file-lock, deduped via `on_payment_success()` single choke-point.
- **`dunning.py`**: Day-0 Hinglish email + WhatsApp link → Day-3 reminder → Day-7 urgent → Day-14 win-back. Research benchmark: 40–70% automated recovery. Period-deduped, fail-open, reuses existing email_sender.
- **`lead_usage.py`**: Append-only billing ledger for qualified leads. Fail-open (never blocks calls). Meter failures → Redis `billing:meter_failures` for ops replay.

### Release Quality

- **`prod_check.py`**: 6-gate pre-deploy check: source parse (every .py, no null bytes) → stale .pyc removal → full app import → router registration → env sanity → frontend wiring (every onclick handler defined, every fetch path routed). CI blocks deploy on failure.
- **`scripts/cross_path_audit.py`**: Cross-path parity guard — ensures hooks wired in one telephony path (Vobiz stream) are also wired in all active paths. Runs in `final_integration_check`.

### Persistent Agent Memory

- **`platform/memory_vault.py`**: Per-prospect/client markdown timelines in `data/memory/`. Events compound; timeline auto-compacts at 80 entries → 30 recent. LLM summary optional (async, 25s timeout). Never on hot-path.
- **`voice_agent/agent_memory.py`**: Cross-session recall via Qdrant — facts extracted from calls, stored, retrieved on next call. Recall hit/miss/error tracked. Fail-open: recall errors never block voice path.

### Multi-Tenant Isolation

- **`middleware/tenant.py`**: Subdomain + custom domain white-label. `agencyname.leadsgenai.in` resolves to reseller branding. Fail-open.
- **`platform/rbac.py`**: 8 module grants (marketing, growth, leads, agents, clients, billing, telephony, analytics). Fail-closed on unmapped routes. Stored in `users.preferences` JSON — no migration needed.
- Per-namespace Qdrant KB, per-client mini-sites (`/b/{slug}`), per-client content packs.

**Why this matters — the real answer:**

> If you try to sell something that hasn't been enterprise hardened, you're at risk of damaging your reputation, losing money, and potential lawsuits.

The reason Level 5 is the money level isn't features — it's *trust surface*. A paying customer hands you their leads, their brand, their billing, and their compliance exposure. Level 5 is the infrastructure of trust: they can audit it, you can prove it, and when something breaks at 2am the system already caught it, logged it, alerted ops, and recovered before they woke up.

**LeadsGenAI is at Level 5.** The code is the proof.

---

## Summary

| Level | Name | LeadsGenAI evidence |
|-------|------|-------------------|
| 1 | Basic Automation | Static routes, SMTP, form captures |
| 2 | Keyword Agents | 23 named staff, niche routing, QA heuristics |
| 3 | Dynamic Hooks / The Spine | Vobiz WS stream, weakest-stage self-routing, LLM circuit breakers, eval gate |
| 4 | End-to-End Orchestration | Reflexion coordinator, Karpathy council, event-sourced process engine, 24-job scheduler |
| 5 | Enterprise Hardening | Persona adversarial testing, 3 KPI engineer agents, DPDP/TRAI compliance, GST invoicing, dunning recovery, multi-tenant RBAC, persistent cross-session memory |

The spine (Level 3) is where most builders stop. Reaching Level 5 is what transforms a demo into a product.
