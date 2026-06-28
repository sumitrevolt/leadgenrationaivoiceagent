# AI Workforce & Operating Workflow — LeadGenAI

> **Kya hai:** Is project ka **top-0.1%-org "org chart"** — kaun-kaun AI workers hain, kab kisko lagao, aur ek task end-to-end kaise flow karta. Banaya: 2026-06-28. Source-of-truth conflict → `CLAUDE.md` jeetta.
> **Do NOT confuse** the two AI tiers: **Claude subagents** (dev-time, dispatched in a coding session) vs **platform AI-staff** (runtime, scheduled, serve customers).

---

## Tier 1 — Claude Code Subagents (dev-time council, fan-out via Agent tool)

10 specialist subagents (`.claude/agents/*/AGENT.md`). Each runs in an **isolated context** so the main thread stays clean and N can fan out in parallel. Read-only auditors find+prove (`file:line`); the one writer implements; the orchestrator (you, main thread) synthesizes.

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
| **mcp-engineer** | `/mcp` + MCP-as-product | read+write (MCP only) | anything MCP / A2A card / Arya / key rotation |
| **revenue-strategist** | CSO/growth/moat | read-only | "advancement council", ROI roadmap, "kya banaye ab", go-no-go |

**Read-only by default; only `staff-engineer` (any file), `qa-test-engineer` (tests/), `mcp-engineer` (MCP files) write.** None deploy — live-VPS deploy needs EXPLICIT user authorization, always the orchestrator's call.

---

## Tier 2 — Platform AI-Staff Agents (runtime, scheduled, customer/ops-facing)

17 agents in `app/platform/team.py` + `team_scheduler.py` (24 IST-scheduled jobs). These RUN on the VPS worker/scheduler and do the actual business work. Full I/O: `docs/AGENT_REGISTRY.md` · UI `/app/team` · API `GET /api/platform/team`.

- **Marketing (5):** Isha (social/GBP) · Dev (KB/RAG) · Rohan (outreach/leads) · Ravi (SEO) · Neha (pipeline)
- **Voice (4):** Swara (telecaller) · Tara (telephony infra) · Arjun (QA) · Meera (trainer)
- **Platform (9):** Boss · Kavya (ops) · Hermes (infra) · Nikhil (revenue) · Vikram (code-upgrader) · Guru (skills) · Pranav (SRE) · Vidya (FinOps) · Arnav (security) — plus Arya (MCP), Kabir (DBRE), Aryan (deps-CVE), Diya (data-integrity) gated.

> Tier-1 `database-architect` is the **dev-time** counterpart of Tier-2 **Kabir**; `agent-workflow-auditor` audits the Tier-2 loops; `revenue-strategist` mirrors **Nikhil**. Dev-time finds & designs; runtime executes.

---

## Tier 3 — Skills · Commands · Hooks (the playbooks)

- **Skills (`.claude/skills/`, 178):** ~67 PROJECT skills are enterprise-grade (additive operating-loop + risk-tier + fail-closed gates). The rest are **generic marketing packs + superpowers/process skills, intentionally left portable** (stamping them with project-loops would degrade their reusability — do NOT mass-restamp). Invoke a skill, don't re-derive it. Index: `skills-index.md` · parity `SKILLS_PARITY.md`.
- **Slash commands (`.claude/commands/`):** `/verify` `/ship` `/checkpoint` `/learn` `/optimize` `/test-expand` `/compact-check` `/council-advancement`.
- **Guard hooks (`.claude/hooks/`):** `guard.py` (DENY `git add -A`/force-push/`rm -rf /`/CLAUDE.md-bash-edit; ASK reset--hard/prune/DROP/live-container-stop) + `skill_reminder.py`. Deterministic, fail-open, boundary-anchored. settings.json gitignored/local (self-mod gated).

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
