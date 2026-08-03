# AI Workforce & Operating Workflow — LeadGenAI

> **Kya hai:** Is project ka **top-0.1%-org "org chart"** — kaun-kaun AI workers hain, kab kisko lagao, aur ek task end-to-end kaise flow karta. Banaya: 2026-06-28. Source-of-truth conflict → `CLAUDE.md` jeetta.
> **Do NOT confuse** the two AI tiers: **Claude subagents** (dev-time, dispatched in a coding session) vs **platform AI-staff** (runtime, scheduled, serve customers).

---

## Tier 1 — Claude Code Subagents (dev-time council, fan-out via Agent tool)

**11** specialist subagents (`.claude/agents/*/AGENT.md`). Each runs in an **isolated context** so the main thread stays clean and N can fan out in parallel. Read-only auditors find+prove (`file:line`); the one writer implements; the orchestrator (you, main thread) synthesizes.

| Agent | Lens | R/W | Dispatch when |
|-------|------|-----|---------------|
| **staff-engineer** | Implementation (Principal) | **WRITE** | "ye feature banao", parallel batch over disjoint files; bakes in the project quality-gate + gotchas |
| **qa-test-engineer** | QA & reliability | WRITE (`tests/` only) | "test coverage badhao", test-gap, after a behaviour change without a test |
| **code-reviewer** | Correctness / regression | read-only | BEFORE `/ship`; "review karo", "commit kar du?" — adversarial diff review |
| **security-auditor** | AppSec attack surface | read-only | auth/payment/public/telephony change; "is this safe", IDOR/SSRF/anon-leak |
| **database-architect** | Postgres/Redis/Qdrant/migrations | read-only | schema/migration/slow-query/scale; data-integrity |
| **frontend-ux-engineer** | UI craft + conversion | read-only | any visible page; "design dekho", "mobile toota", "conversion kam" |
| **infra-doctor** | VPS/Docker/Celery/observability | read-only | "site down", health-check, deploy-safety, scheduler resilience |
| **agent-workflow-auditor** | Agent loops/cost/eval | read-only | "loops healthy?", loop governance, before adding a loop |
| **harness-conformance-auditor** | C-01..C-15 / L1–L5 harness score | read-only | "self-certify loop", maturity level, control-matrix audit vs `agent-harness-standard` |
| **mcp-engineer** | `/mcp` + MCP-as-product | read+write (MCP only) | anything MCP / A2A card / Arya / key rotation |
| **revenue-strategist** | CSO/growth/moat | read-only | "advancement council", ROI roadmap, "kya banaye ab", go-no-go |

**Read-only by default; only `staff-engineer` (any file), `qa-test-engineer` (tests/), `mcp-engineer` (MCP files) write.** None deploy — live-VPS deploy needs EXPLICIT user authorization, always the orchestrator's call.

---

## Tier 2 — Platform AI-Staff Agents (runtime, scheduled, customer/ops-facing)

**31** canonical agents in `app/platform/team.py` + `team_scheduler.py` (governed by `agent_registry.py`). These RUN on the VPS worker/scheduler and do the actual business work. Full I/O: `docs/AGENT_REGISTRY.md` · UI `/app/team` · API `GET /api/platform/team`. **Do not invent new STAFF personas** — gaps are usually capabilities/flags, not missing names (Aditi explicitly rejected).

- **Marketing:** Isha (social/GBP) · Dev (KB/RAG) · Rohan (outreach/leads) · Ravi (SEO) · Neha (pipeline) · + CRM/social/cadence staff (Priya/Zara/Anika/Ira)
- **Voice:** Swara (telecaller) · Tara (telephony infra) · Arjun (QA) · Meera (trainer) · Ananya (booking) · Riya (inbound) · Lekha (analytics) · Raksha (escalation)
- **Platform:** Boss · Kavya (ops) · Hermes (infra) · Nikhil (revenue) · Vikram (code-upgrader) · Guru (skills) · Pranav (SRE) · Vidya (FinOps) · Arnav (security) · Arya (MCP) · Kabir (DBRE) · Aryan (deps-CVE) · Diya (data-integrity)

> Tier-1 `database-architect` is the **dev-time** counterpart of Tier-2 **Kabir**; `agent-workflow-auditor` audits the Tier-2 loops; `revenue-strategist` mirrors **Nikhil**. Dev-time finds & designs; runtime executes.

---

## Tier 3 — Skills · Commands · Hooks (the playbooks)

- **Skills (`.claude/skills/`, 178):** ~67 PROJECT skills are enterprise-grade (additive operating-loop + risk-tier + fail-closed gates). The rest are **generic marketing packs + superpowers/process skills, intentionally left portable** (stamping them with project-loops would degrade their reusability — do NOT mass-restamp). Invoke a skill, don't re-derive it. Index: `skills-index.md` · parity `SKILLS_PARITY.md`.
- **Slash commands (`.claude/commands/`):** `/verify` `/ship` `/checkpoint` `/learn` `/optimize` `/test-expand` `/compact-check` `/council-advancement`.
- **Guard hooks (`.claude/hooks/`):** `guard.py` (DENY `git add -A`/force-push/`rm -rf /`/CLAUDE.md-bash-edit; ASK reset--hard/prune/DROP/live-container-stop) + `skill_reminder.py`. Deterministic, fail-open, boundary-anchored. Hook registration stays in `.claude/settings.local.json` (gitignored, self-mod gated). Tracked `.claude/settings.json` is plugin-policy only — `warp@claude-code-warp` OFF (ADR-WARP-PLUGIN-OFF).

---

## The Operating Workflow — how a task flows (top-0.1% loop)

```
        ┌─────────────────────────────────────────────────────────────┐
        │  ORCHESTRATOR (main thread)  —  Discover → Contract → Decide  │
        └─────────────────────────────────────────────────────────────┘
                 │ 1. context-first (parallel Grep/Read) + MEASURE LIVE
                 │    (prod_check / activation-summary / VPS flag-state —
                 │     code-default ≠ live; dispatchable ≠ dispatched)
                 ▼
   2. FAN-OUT AUDIT (parallel, read-only, isolated contexts)
      ├─ code-reviewer / security-auditor   (correctness + safety)
      ├─ database-architect / infra-doctor  (data + ops)
      ├─ agent-workflow-auditor             (loops/cost/eval)
      ├─ frontend-ux-engineer               (craft + conversion)
      └─ revenue-strategist                 (is this the right lever at all?)
                 │ each returns ranked, file:line-proven findings
                 ▼
   3. SYNTHESIZE + adversarially verify (orchestrator)
      reject stale/false findings — MEASURE-FIRST beats any single agent
      (e.g. "flip these flags" died here: flags were already live on VPS)
                 ▼
   4. IMPLEMENT (parallel, disjoint file-owners — never share a file)
      └─ staff-engineer × N  +  qa-test-engineer (tests)
                 │ each: additive · flag-gated INERT · verify with evidence
                 ▼
   5. PRE-SHIP REVIEW  →  /verify (prod_check + targeted tests + secrets)
      └─ code-reviewer / security-auditor on the diff
                 ▼
   6. SHIP (EXPLICIT user authorization)  →  /ship  →  health-gate + rollback
```

**Non-negotiables baked into every lane:** Windows = source-of-truth · additive + flag-gated INERT-by-default · compliance gates never disabled · free-stack only · DO-alag-products · secrets only in `.env` · "done" only with pasted green evidence · deploy only on explicit auth.

### When to reach for what
- One scoped change → **staff-engineer** (or just do it inline if trivial).
- "Is X safe / good / scalable?" → the matching **read-only auditor** (fan out several for a big surface).
- Strategy / "what to build / go-no-go" → **revenue-strategist** + `executive-council` skill (NOT a generic repo audit).
- Many disjoint features at once → fan out **staff-engineer** per file-owner (`parallel-batch-build` skill).
- Ambiguous high-stakes design fork → `llm-council-decision` skill / `POST /api/agents/council`.

---

## Why this is "top 0.1%", honestly

Not because of agent count — because of the **discipline**: independent specialist inspection → adversarial synthesis that rejects its own agents when the evidence says so (measure-first) → isolated parallel execution that can't truncate shared files → evidence-gated ship with explicit human authorization on anything irreversible. The roster is the easy part; the **measure-first + adversarial-verify + fail-open-by-default** loop is the moat.

---

## Voice Production Council — requested 30-agent architecture → THIS workforce (2026-06-28)

A "production voice agent" exec/eng/voice council was requested (30 roles). Audit verdict: **~85% already exists** — formalized here as a council that USES the existing agents; only **2 were genuinely missing** and were added (Lekha, Raksha). NO duplication.

### Executive Council (on-demand: `coordinator.py` / `POST /api/agents/council` / `executive-council` skill)
| Role | Owner(s) |
|------|----------|
| CEO — strategy/product/pricing | `manager` (Boss) + **revenue-strategist** subagent |
| CRO — conversion/objections/follow-up | `nikhil` (Revenue Ops) + `rohan` (Leads Mgr) + `sales_team.py` |
| COO — workflow/queue/escalation | `kavya` (Ops Monitor) + `hermes` (Infra Handler) |

### Engineering Council (runtime staff + dev-time subagents)
| Role | Owner(s) |
|------|----------|
| Principal Voice AI Architect | `tara` (Voice Infra Ops) + voice_agent design |
| Staff Backend | **staff-engineer** subagent |
| Telephony/SIP | `tara` + `telephony/*` |
| Conversation Designer | `meera` (Trainer) |
| AI Evaluation | `arjun` (QA) + `eval_gate` + `voice_metrics`/`eval_suite` |
| MLOps / Self-Improvement | `self_improve.py` loop + `vikram` (Code Upgrader) |
| Security & Compliance | `arnav` + **security-auditor** subagent |
| QA Automation | `arjun` + **qa-test-engineer** subagent |
| Data / CRM | `diya` (Data-Integrity) + `dev` (KB) |
| Product Reliability | `pranav` (SRE) + **infra-doctor** subagent |

### Voice Product Agents (runtime)
| Role | Owner |
|------|-------|
| Marketing Caller | `swara` (Telecaller) |
| Appointment Booking | `ananya` + real `calendar_booking.py` (book + **reschedule**, VOICE_TOOLS=1) |
| AI Receptionist | `riya` (inbound; interactive-stream pending an inbound DID — see below) |
| Lead Qualification / Objection | `sales_team.py` (Veer qualify, Arjun objections) |
| CRM Update | `post_call_hooks.apply_qualified_downstream` + `crm_sync` |
| Follow-up | `nikhil` + `cadence.py` |
| Call QA Supervisor | `arjun` + `meera` |
| **Analytics** (was MISSING → NEW) | **`lekha`** — `app/voice_agent/call_analytics.py`, `GET /api/admin/web-calls/kpis` |
| **Human Escalation** (was MISSING → NEW) | **`raksha`** — owns `app/telephony/call_transfer.py` (gated `CALL_TRANSFER`) |

### Live workflow (lead → call → booking → CRM → follow-up → learn)
`compliance gate (DND/9-19h, fail-closed)` → `carrier_router place_call (retry failover)` → **conversation** (`platform_pitch` answers questions first → `telecaller_brain` qualify/objection) → intent: **book/reschedule** (`calendar_booking`, persists `data/bookings/`) · **escalate** (`call_transfer`) · **not-now** (`cadence`) → `post_call_hooks` (recording+transcript+audit, qualify→CRM, metering, `call.completed` webhook) → `crm_sync` → `cadence` follow-up → **self-improve** (`web_call_learn` → eval_gate regression → promote IF score≥baseline; never blind-writes prod prompts).

### Status (2026-06-28 program)
- ✅ **LIVE+verified:** call-quality (pitch dodge fixed, STT turbo, EdgeTTS), **real booking + reschedule** (VOICE_TOOLS=1), Lekha analytics, Raksha (call_transfer).
- ⏳ **Pending:** per-call self-improve promotion-gate formalization; interactive inbound receptionist is **EXTERNALLY BLOCKED** (needs an inbound DID + DLT) — until then the existing missed-call-capture + gated callback (`webhooks.py`) covers the realistic path.
