# Automation Loop Architecture

This document explains how the three core automation loops work: **self-improve**, **coordinator**, and **process-engine**. For step-by-step control, see `.claude/skills/self-improve-control/SKILL.md`.

---

## Overview: Three Loops, One Goal

Your automation runs on three nested patterns:

```
┌─ SELF-IMPROVE LOOP (daily, 180s cycle) ────────────────────┐
│  Picks best task for today → executes → learns from outcome  │
│                                                               │
│  ┌─ COORDINATOR (on-demand or self-picked) ──────────────┐  │
│  │  Orchestrates multi-agent goal (e.g., "Pune solar")   │  │
│  │  Mode: Sequential / Parallel / Hierarchical / Reflex  │  │
│  │  Executes 4 staff agents in handoff pattern           │  │
│  │                                                        │  │
│  │  ┌─ PROCESS-ENGINE (deterministic workflows) ──────┐ │  │
│  │  │  "Process-as-code" with breakpoints              │ │  │
│  │  │  E.g.: lead_campaign (harvest→score→deep-dive)  │ │  │
│  │  │  Pause points for human approval                 │ │  │
│  │  └────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Result: Lead scored / Email drafted / Callback queued      │
│  Lesson: "Solar + high-population cities = best ROI"       │
└──────────────────────────────────────────────────────────────┘
```

---

## Pattern 1: Self-Improve Loop

**Location**: `app/agents/self_improve.py`

**Cycle** (runs every 180s, 480x/day = 8h sustained):

1. **Pick task** — Epsilon-greedy bandit over `skill_library` (weighted by success_rate + recency)
2. **Execute** — Call the task (e.g., `prospector.scrape`, `sales_team.analyze`)
3. **Record outcome** — Cost + result (e.g., "18 leads, $2.31 spent")
4. **Learn** — Reflexion: free-LLM reads outcome, writes lesson to `agent_memory.jsonl`
5. **Sleep** — Wait 180s, repeat

**Key parameters** (in `.env`):

- `SELF_IMPROVE_LOOP=1` — Enable/disable loop
- `SELFIMPROVE_COST_CAP=50` — Daily budget cap ($)
- `SELF_IMPROVE_APPROVAL=0` — Require human approval per task (1=ON)

**Output files**:
- `data/automation_audit.jsonl` — Every task pick + cost + approval status
- `data/skill_library.jsonl` — Task registry (action, success_rate, recent_outcomes)
- `data/agent_memory.jsonl` — Lessons learned (event-sourced journal)

**Safety**:
- Cost cap prevents runaway spend
- Fail-open (errors don't crash the loop)
- Flags gate external actions (CADENCE_ENGINE, AUTO_EMAIL_OUTREACH, etc.)

**Monitoring**:
```bash
python scripts/selfimprove_audit.py --last-run
python scripts/selfimprove_audit.py --skill-stats
python scripts/selfimprove_audit.py --anomalies
```

**When to use**:
- You want daily optimization without explicit direction ("run the best thing today")
- Your task list is stable and outcomes are measurable
- You can afford to let it explore (cost cap prevents disasters)

**When NOT to use**:
- You need instant action (180s cycle is slow)
- Task success is hard to measure (loop can't learn)
- Compliance-critical (DLT calls, tax invoices) — use process-engine instead

---

## Pattern 2: Coordinator (Multi-Agent Orchestration)

**Location**: `app/agents/coordinator.py`

**Purpose**: Execute a goal by orchestrating multiple staff agents in parallel or sequence.

**Example**: "Pune solar leads — prioritize for sales"
→ Riya researches solar market
→ Isha drafts outreach sequence
→ Dev competitive analysis
→ Boss summarizes + next steps

**4 Modes**:

### Mode A: Sequential (Linear Handoff)

```
Goal → [Riya research] → [Dev compete] → [Isha outreach] → [Boss summary]
                          (context flows →)
```

Use when: Each agent needs prior output (research informs competitive analysis informs copy).

```python
coordinator.coordinate(
    goal="Pune solar: research market + draft outreach",
    mode="sequential",
    execute=True  # False = dry-run drafts
)
```

### Mode B: Parallel (Fan-Out / Fan-In)

```
         ┌→ [Riya research]
Goal → ─┤→ [Dev compete]    → Boss merges
         └→ [Isha outreach]
```

Use when: Agents work independently, then merge.

```python
coordinator.coordinate(
    goal="Analyze this prospect from 3 angles",
    mode="parallel",
    agents=["Riya", "Dev", "Isha"]
)
```

### Mode C: Hierarchical (Team-Based)

```
Goal → Boss
       ├─ [Growth team: Rohan prospect + Isha content]
       └─ [Sales team: Swara voice + Arjun QA]
       (sub-supervisors coordinate within teams, Boss merges)
```

Use when: Teams handle sub-goals independently, then report up.

```python
coordinator.coordinate(
    goal="Full lead campaign: source + qualify + close",
    mode="hierarchical"
)
```

### Mode D: Reflexion + Critic (Self-Improving)

```
Plan → Execute → [Critic: score output 0-100 + feedback]
  ↑                        ↓
  └── Reflect ← [Reflexion: "score < bar, let's retry with..."]
```

Use when: Output quality matters (e.g., sales strategy must be sharp).

```python
coordinator.coordinate(
    goal="Strategic plan for Pune market entry",
    mode="advanced",  # Includes Reflexion + critic
    quality_bar=0.8,  # Critic scores vs. this threshold
    max_iterations=3
)
```

**Parameters**:

- `execute=True/False` — Actually run tasks, or draft-only?
- `quality_bar` — Critic score needed to accept output (0-1)
- `max_iterations` — Max Reflexion loops (prevents infinite retries)

**Output**:
- `data/coordination_runs.jsonl` — Full transcript (goal → plan → steps → results)
- Staff agent events logged to `agent_events` table

**When to use**:
- You have a specific goal (not open-ended exploration)
- Multiple perspectives help (sales + voice + marketing)
- You want to **see the work** (unlike self-improve, coordinator is transparent)

**When NOT to use**:
- Task is simple (one agent is better; coordinator adds overhead)
- Output quality doesn't matter (self-improve is faster)
- You need speed (<30s needed; coordinator takes 2-5 min)

---

## Pattern 3: Process-Engine (Deterministic Workflows)

**Location**: `app/agents/process_engine.py`

**Purpose**: Define workflows in code, not prompts. Each step is deterministic (no LLM guessing).

**Example**: Lead campaign process

```python
LEAD_CAMPAIGN_PROCESS = [
    ("harvest", {"niche": "solar", "city": "Pune"}, 
     min_count=10, max_cost=5),  # deterministic gate
    
    ("score", {"leads_list": None}, 
     outcome_metric="hot_lead_count"),  # measure result
    
    ("deep_dive", {"lead_ids": None}, 
     max_parallel=3),  # parallel execution
    
    # BREAKPOINT: human can approve/reject before next step
    ("BREAKPOINT", {"label": "Review 3 deep-dives"}, 
     required_approval="admin"),
    
    ("cadence_enroll", {"qualified_ids": None}, 
     sequence_type="omnichannel"),
]
```

**Process flow**:

1. **Run step**: Execute code (not LLM)
2. **Gate check**: If `min_count=10`, do we have 10 prospects? If not, fail gracefully
3. **Breakpoint**: If marked, pause and wait for human approval API
4. **Next step**: Human approves → continue to next step

**Event-sourced journal** (`data/process_runs/<process_id>.jsonl`):

```json
{"step": 1, "action": "harvest", "status": "completed", "count": 18, "cost": 2.50}
{"step": 2, "action": "score", "status": "completed", "results": {...}}
{"step": 3, "action": "breakpoint", "status": "waiting_approval", "label": "Review..."}
{"step": 3, "action": "breakpoint", "status": "approved_by": "admin:sumit"}
{"step": 4, "action": "cadence_enroll", "status": "completed", "enrolled": 15}
```

**Deterministic vs. LLM**: Process-engine uses LLM **only inside steps** (e.g., sales_team deep-dive). The *workflow itself* is code.

**When to use**:
- High-stakes workflows (revenue, compliance)
- You need approval gates
- Workflow is repeatable (same steps, different parameters)

**When NOT to use**:
- Ad-hoc exploration (self-improve better)
- Workflow keeps changing (code churn)

---

## Decision Tree: Which Loop Should I Use?

```
I want to:

1. Run the best automated task daily (learn from outcomes)
   → SELF-IMPROVE LOOP
   env: SELF_IMPROVE_LOOP=1, run scripts/selfimprove_audit.py daily

2. Execute a multi-step goal (research → analysis → draft)
   → COORDINATOR (mode: sequential or parallel)
   API: coordinator.coordinate(goal="...", mode="...", execute=True)

3. Build a repeatable high-stakes workflow (harvest → score → approve → enroll)
   → PROCESS-ENGINE + breakpoints
   Define in agents/process_engine.py, call process_engine.run_process(...)

4. Combine all three (self-improve picks coordinator, coordinator uses process-engine)
   → ORCHESTRATOR (skill-pack decides which to call)
   See .claude/skills/orchestrate-goal/SKILL.md
```

---

## Compliance + Safety Notes

**Self-Improve**:
- Cost cap prevents runaway spend: `SELFIMPROVE_COST_CAP=50`
- Approval mode available: `SELF_IMPROVE_APPROVAL=1` (requires human click)
- Safety matrix: `.claude/skills/self-improve-control/references/self-improve-safety.md`

**Coordinator**:
- `execute=False` by default (drafts, no action)
- Set `execute=True` only after reviewing draft
- Reflexion mode adds cost (Critic + Reflexion = 2 LLM calls)

**Process-Engine**:
- Breakpoints enforce human review: "step_name: BREAKPOINT"
- Deterministic steps (code gates) prevent LLM hallucinations
- Event journal is append-only (audit trail)

**Common pattern**: 
- Self-improve picks a process → calls coordinator → coordinator steps use process-engine
- Every external action (email, call, invoice) is gated by flag or approval

---

## Troubleshooting

**"Loop is stuck picking the same task"**
- Check `skill_library.jsonl` success rates
- Manually reduce weight: `skill_pack.update_weight(task_name, 0.5)`
- Or use self_improve_audit.py to inspect

**"Coordinator output is incoherent"**
- If `mode=sequential`, check data flows (prior output → next input)
- If `mode=advanced`, lower `quality_bar` (critic may be too strict)
- Try `mode=parallel` instead (no chain dependencies)

**"Process-engine breakpoint stuck forever"**
- Check `/api/growth/process/{id}/run/{step_id}/approve` endpoint
- Breakpoint waits for human. Call approve API to continue

**"Cost spiked unexpectedly"**
- Run `python scripts/selfimprove_audit.py --cost-report`
- Check which task spiked (look for high-cost LLM tasks like sales_team)
- Pause loop: `SELF_IMPROVE_LOOP=0`
- Review & re-enable

---

## Further Reading

- `.claude/skills/self-improve-control/SKILL.md` — Monitor + control self-improve
- `.claude/skills/coordinator-orchestration/SKILL.md` — Use coordinator effectively
- `.claude/skills/orchestrate-goal/SKILL.md` — Decide which loop to use
- `docs/PRODUCTION_READINESS_2026.md` — Safety, compliance, deployment
