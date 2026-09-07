---
name: coordinator-orchestration
description: STAFF coordinator se ek specific multi-agent goal ABHI execute karo — sequential / parallel(fanout) / hierarchical / advanced(Reflexion) modes, draft-safe by default. Use when user says "ye goal run karo", "team se ye karwao", "research + draft + qualify ek saath", ya kisi 2-3 min ke ad-hoc multi-expert goal ke liye (NOT daily loop, NOT compliance workflow).
---

# Coordinator Orchestration

Orchestrate multi-agent goals using the lightweight STAFF coordinator (`app/agents/coordinator.py`, free-stack/Cerebras). Run a specific goal via 4 core modes (sequential, parallel/fanout, hierarchical, advanced); 2 specialist modes (`agentverse`, `engineering`) niche cases ke liye — see end.

## When to Use This Skill

- **NOW**: "Get leads + run qualification + draft outreach" (3-step goal requiring different experts)
- **Investigation**: "Research Pune market + get competitive intel + draft strategy" (parallel research)
- **Strategy**: "Analyze churn + propose 3 fix options + rank by ROI" (hierarchical + debate)
- **Improvement**: "Daily self-improve loop wants to improve quality" (advanced mode with reflection)

**vs. Other Loops**:
- **Self-Improve Loop** = "Run the best task today" (hands-off, daily bandit)
- **Coordinator** = "Execute THIS specific goal now" (hands-on, 1-3 min)
- **Process-Engine** = "Run deterministic workflow with human breakpoints" (explicit steps, approval gates)

## Problem This Solves

You have a goal that needs multiple staff agents (Dev, Isha, Rohan, etc.) working together. But:
- Running agents sequentially is slow (no parallelism)
- Running them blind loses context (they don't see what others did)
- No way to verify output quality (did we actually solve the goal?)
- Hard to learn and improve (outcomes disappear)

The coordinator solves this: **orchestrate staff agents in 4 modes, trace every step, verify quality, and learn.**

## Prerequisites

- Access to FastAPI `/api/agents/*` endpoints (admin token)
- Goal that's **clear and measurable** (e.g., "get 20 solar leads in Pune")
- Comfort with JSON (API responses are structured)

## The 4 Modes Explained

### Mode A: Sequential (Linear Handoff)

**When**: Goal needs ordered steps, each building on prior.

```
Goal: "Draft cold-email sequence for solar leads in Pune"

Dev (research) → "Solar subsidy + local regs for Pune"
Rohan (outreach) → "Emails: Day 1 edu, Day 3 CTA, Day 7 urgency" (uses Dev's data)
Isha (marketing) → "Subject lines + hashtag strategy" (uses Rohan's structure)
Boss → "Summary + next-action"
```

**Pros**: Natural workflow, context flows, progressive refinement.
**Cons**: Slow (agents wait), bottleneck at each step.
**Cost**: ~5-6 LLM calls (free-stack = paisa nahi, sirf latency + quota).
**Execute mode**: 2 agents (isha=post, dev=research); others draft.

### Mode B: Parallel (Fan-Out)

**When**: Goal can split into independent sub-tasks.

```
Goal: "Assess market opportunity in 3 cities"

Dev → researches Pune market (parallel)
Isha → researches Mumbai market (parallel)
Kavya → researches Bangalore market (parallel)
Boss → merges into unified strategy
```

**Pros**: Fast (3x speedup), agents don't block each other.
**Cons**: Outputs may conflict, harder to merge.
**Cost**: ~same LLM calls as sequential, just concurrent (faster wall-clock).
**Execute mode**: None (all draft); results merged by Boss.

### Mode C: Hierarchical (Sub-Teams)

**When**: Goal is complex and spans multiple domains.

```
Goal: "Launch Q3 growth initiative"

Growth Team (parallel):           Ops Team (parallel):
 Dev researches channels         Kavya audits health
 Isha plans content              Arjun runs QA
 Rohan outreach strategy         Meera trains team

Boss merges both strategies
```

**Pros**: Scales to complex goals, teams work in parallel, organized accountability.
**Cons**: Most LLM calls, needs good team definitions.
**Cost**: most LLM calls of any mode, but parallel so wall-clock OK.
**Execute mode**: Same (2 agents per team execute).

### Mode D: Advanced (Reflexion + Memory)

**When**: Goal needs quality + learning.

```
Iteration 1: Plan → Execute → VERIFY (0.62 score) → Weak? "Too generic, no niche focus"
  ↓ REFLECT → "Next: focus on solar-specific subsidy programs"
Iteration 2: Plan (with reflection hint) → Execute → VERIFY (0.85 score) ✓ DONE
```

**Pros**: Quality-gated (loops until quality_bar met), learns from reflection, episodic memory (`data/agent_memory.jsonl`).
**Cons**: Slower (multiple iterations), uses more LLM calls.
**Cost**: 2-3 iterations × per-mode calls (early-stop jab quality_bar hit).
**Execute mode**: Same as sequential. Critic = Arjun persona (parse-fail → 0.6 neutral, infinite-loop guard).

---

## 5-Step Workflow

### Step 1: Define Your Goal (Clear, Measurable)

**Bad goals**: "Marketing stuff", "Do research", "Fix things"
**Good goals**: "Get 20 solar leads in Pune + score them", "Draft 5-email cold sequence for solar+"

Rule: If you can't measure success, it's not a goal.

```bash
curl -X POST http://localhost:8000/api/agents/coordinate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Pune solar prospects — prioritize for sales outreach"
  }'
```

### Step 2: Choose Mode

Use the **decision tree** in `references/coordinator-patterns.md`:

- **Sequential**: "Need ordered steps" → Goal naturally flows Dev → Rohan → Isha
- **Parallel**: "Independent research" → Split Pune/Mumbai/Bangalore market analysis
- **Hierarchical**: "Complex goal spanning teams" → Growth + Ops initiatives together
- **Advanced**: "Need quality + learning" → Marketing strategy with 0.8 quality bar

```bash
# Mode A: Sequential (default)
curl ... -d '{"goal": "...", "execute": false, "max_steps": 5}'

# Mode B: Parallel
curl ... -d '{"goal": "...", "mode": "parallel"}'

# Mode C: Hierarchical
curl ... -d '{"goal": "...", "mode": "hierarchical"}'

# Mode D: Advanced (Reflexion)
curl ... -d '{
  "goal": "...",
  "mode": "advanced",
  "max_iterations": 2,
  "quality_bar": 0.75,
  "execute": false
}'
```

### Step 3: Execute (Safe by Default)

**Always start with `execute=false`** (draft mode). This:
- Plans the goal
- Runs agents (but real tools OFF)
- Shows you the output

Once you verify the output looks good, re-run with `execute=true`:

```bash
# DRAFT (safe) — see what coordinator wants to do
curl ... -d '{"goal": "...", "execute": false}'

# EXECUTE (real) — actually run agent tools
curl ... -d '{"goal": "...", "execute": true}'
```

**Executable agents** (side-effect safe):
- **Isha** (marketing): real post generation + hashtag research
- **Dev** (data): real competitor + hashtag research
- **Kavya** (ops): real health snapshot
- **Arjun** (QA): real agent scorecard
- **Meera** (trainer): real transcript analysis

**Draft-only agents** (to prevent accidental sends):
- **Rohan** (outreach): cold-email drafts (never auto-sends)
- **Swara** (voice): call scripts (never dials)

### Step 4: Review Output

API returns:

```json
{
  "ok": true,
  "run_id": "a7f2c1b3d9e5",
  "goal": "Pune solar prospects — prioritize for sales outreach",
  "execute": false,
  "mode": "sequential",
  "plan": [
    {"agent": "dev", "task": "Research Pune solar market + subsidies"},
    {"agent": "rohan", "task": "Draft cold-email sequence"},
    {"agent": "isha", "task": "Social media angles + content ideas"}
  ],
  "results": [
    {
      "agent": "dev",
      "task": "Research Pune solar market + subsidies",
      "mode": "draft",
      "output": "Pune solar market: 2000+ active consumers, PM Surya subsidy ₹3L cap..."
    },
    {
      "agent": "rohan",
      "task": "Draft cold-email sequence",
      "mode": "draft",
      "output": "Day 1: Awareness email...\nDay 3: Case study...\nDay 7: Urgency..."
    },
    {
      "agent": "isha",
      "task": "Social media angles + content ideas",
      "mode": "executed",
      "output": {
        "caption": "₹3L subsidy + 25yr warranty = solar kitna sasta? 🌞",
        "hashtags": ["#PuneSolar", "#SolarSubsidy", ...],
        "image_idea": "Before/after rooftop install"
      }
    }
  ],
  "summary": "Team ke research + outreach plan taire hai. 3 solar niches Pune me high-potential: residential(cost-sensitive), commercial(ROI-driven), agriculture(subsidy-aware). Cold sequence 7-email, Day-1 edu focus. Social angle: subsidy awareness.",
  "at": "2026-06-15T10:22:30Z"
}
```

**Read the summary**: Does it make sense? Did agents understand the goal?

### Step 5: Iterate

Look at `results` — did output meet your expectation?

**If good**: Execute with `execute=true` or use the drafts manually.

**If weak**: Iterate:
- Rephrase goal (too vague? → be specific)
- Try different mode (sequential too slow? → parallel)
- Use advanced mode (need quality? → add quality_bar)

```bash
# If first attempt weak, try advanced mode
curl ... -d '{
  "goal": "Pune solar prospects — prioritize for sales outreach",
  "mode": "advanced",
  "max_iterations": 3,
  "quality_bar": 0.8,
  "execute": false
}'
```

---

## 2 Specialist Modes (niche use)

Beyond the 4 core modes, `coordinator.py` has two more:
- **`agentverse`** (`POST /api/agents/coordinate-agentverse`): task-tailored experts ko DYNAMICALLY recruit → collaborate → solver-synth → critic EVALUATE → feedback se team RE-COMPOSE (rounds tak), best-of kept. Use jab fixed STAFF roster goal pe fit na ho.
- **`engineering`** (`POST /api/agents/coordinate-engineering`): Architect → Engineer → Reviewer → Tester crew → design + impl-plan + review + test-plan. **DRAFT-ONLY (code auto-apply NAHI)** — `code_upgrader` (Vikram) ka goal→design complement.

---

## References

Detailed material moved to `references/` to keep this guide lean:

- See `references/worked-examples.md` for 3 full worked examples (lead campaign / market analysis / strategy-with-learning), with commands and output summaries.
- See `references/troubleshooting.md` for troubleshooting (incoherent output, wrong agent picked, parallel conflicts, low quality score, dependency errors).
- See `references/api-reference.md` for the full API reference (sequential, fan-out, hierarchical, advanced endpoints + request/response shapes).
- See `references/coordinator-patterns.md` for the mode decision tree and per-mode cards.
- See `references/coordination-schema.md` for the structure of runs stored in `data/coordination_runs.jsonl`.
- **Related**: `automation-control-center` skill (see all automation loops in one place).
- **Code**: `app/agents/coordinator.py` (internals — read for deep understanding).

---

## Quick Command Cheat Sheet

```bash
# Draft (always start here)
curl -X POST http://localhost:8000/api/agents/coordinate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"goal": "Your goal here"}'

# Parallel research
curl -X POST http://localhost:8000/api/agents/fan-out \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"goal": "Compare 3 markets: Pune vs Mumbai vs Bangalore"}'

# Hierarchical strategy
curl -X POST http://localhost:8000/api/agents/coordinate-hierarchical \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"goal": "Launch Q3 initiative: growth + ops both"}'

# Advanced with quality bar
curl -X POST http://localhost:8000/api/agents/coordinate-advanced \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "goal": "Design 30-day growth plan",
    "quality_bar": 0.8,
    "max_iterations": 3
  }'

# Engineering crew (draft design+plan+tests, no auto-apply)
curl -X POST http://localhost:8000/api/agents/coordinate-engineering \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"goal": "Design webhook retry queue", "context": "existing customer_webhooks.py"}'

# Roster + recent runs (no /runs endpoint — use roster) | episodic memory
curl -X GET http://localhost:8000/api/agents/roster -H "Authorization: Bearer $ADMIN_TOKEN"
curl -X GET http://localhost:8000/api/agents/memory?limit=10 -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## Enterprise gate (running a goal NOW)

Run the operating loop — Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). Ad-hoc `execute=false` goal = **Standard tier**; `execute=true` (real tools fire) = **High-risk** — diff the draft, then authorize. Sab `/api/agents/*` routes `require_admin` + rate-limited (council 5/60).

- **Draft-safe kill-switch:** ALWAYS start `execute=false` (plans + runs draft, real tools OFF). `execute=true` sirf draft verify ke baad. Executable agents = isha/dev/kavya/arjun/meera; **rohan(email) + swara(voice) draft-ONLY — never auto-send/dial** even on `execute=true` (compliance fail-closed; real sends only via gated auto_outreach caps / DLT-DND call queue).
- **Bounded:** `max_steps`/`max_iterations` set karo; advanced mode max-3 iters early-stop on `quality_bar`; long goals = process-engine, not coordinator. free_ai chain fallback on provider 429 (no hang).
- **Observability:** every run → `run_id` + `data/coordination_runs.jsonl` + `agent_events` → `/app/agents` Events. Verify the `summary` makes sense (Step 4) before acting on drafts.
- **Idempotency:** drafts are side-effect-free; if you hand a draft to a real engine, that engine owns dedupe — don't re-fire the same goal expecting no duplicates.
- **Rollback (NAMED):** drafts = nothing to undo (just discard). If a tool wrote (isha post / kavya ops), revert via that feature's flag/admin. No prod deploy here — this is runtime, not code.
- **Evidence (done):** `ok:true` + coherent `summary` matching the goal; for any `execute=true` run, the executed agent's output verified human-readable. Council goals → Chairman verdict captured. No deploy/test gate (read/runtime), but a wrong-summary run = re-run advanced mode, don't ship the draft.
