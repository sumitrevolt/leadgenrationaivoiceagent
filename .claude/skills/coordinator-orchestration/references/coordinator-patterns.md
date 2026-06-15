# Coordinator Patterns: Decision Tree + Mode Cards

Which coordination mode should you use? Use this decision tree and mode cards to pick.

---

## Decision Tree

```
START: I have a goal

  ├─ Is the goal simple (1-2 steps)?
  │  └─ YES → Use SEQUENTIAL (Mode A)
  │
  ├─ Does the goal have independent sub-goals (can split into parallel tasks)?
  │  └─ YES → Use PARALLEL (Mode B)
  │
  ├─ Is the goal complex, spanning multiple teams/domains?
  │  └─ YES → Use HIERARCHICAL (Mode C)
  │
  └─ Do I need quality guarantees + learning from iterations?
     └─ YES → Use ADVANCED (Mode D)
```

---

## Mode Card: A — Sequential (Linear Handoff)

**When to use**:
- Goal has natural ordering (research → outreach → marketing)
- Output of one agent needed by next agent
- Small teams (2-4 agents)

**Example goals**:
- "Get 10 solar leads in Pune + draft cold-email sequence + create social post"
- "Analyze competitor + summarize + draft response"
- "Research market + plan pricing + create landing page copy"

**Pros**:
- Natural workflow
- Context flows from agent to agent
- Deterministic (always same plan)

**Cons**:
- Slowest (agents wait sequentially)
- If one agent fails, downstream breaks

**Cost**:
- ~$1-2 (5-6 LLM calls)

**Example API call**:
```bash
curl -X POST http://localhost:8000/api/agents/coordinate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "goal": "Pune solar prospects — 20 leads for sales + cold-email draft",
    "execute": false,
    "max_steps": 5
  }'
```

**Expected flow**:
```
Dev researches Pune solar market
  ↓ (output: market size, consumer profile, subsidy info)
Rohan drafts 5-email sequence (uses Dev research)
  ↓ (output: email copy, timing, CTA)
Isha creates social content (uses Rohan's structure)
  ↓ (output: caption, hashtags, image ideas)
Boss merges into unified strategy
```

---

## Mode Card: B — Parallel (Fan-Out)

**When to use**:
- Goal can split into independent tasks (no dependencies)
- Multiple agents can work simultaneously
- You want speed (3-4x faster than sequential)

**Example goals**:
- "Compare solar opportunity in Pune vs Mumbai vs Bangalore"
- "Research 3 competitor strategies simultaneously"
- "Assess health across ops + growth + sales teams"

**Pros**:
- Fast (concurrent execution)
- Agents don't block each other
- Good for research/analysis

**Cons**:
- Outputs may conflict (different assumptions)
- Needs good goal framing (make tasks independent)
- Merge step is manual (Boss synthesizes)

**Cost**:
- ~$1-2 (same calls as sequential, concurrent)

**Example API call**:
```bash
curl -X POST http://localhost:8000/api/agents/fan-out \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "goal": "Solar market comparison: Pune vs Mumbai vs Bangalore — which city best ROI?",
    "agents": ["dev", "isha", "kavya"],
    "max_agents": 3
  }'
```

**Expected flow**:
```
Dev researches Pune   ─┐
Isha researches Mumbai ├─ (all parallel, 3x speed)
Kavya researches Bangalore ┘
  ↓
Boss merges: "Pune best (high-subsidy awareness), Mumbai ok (price-sensitive), Bangalore hardest (competitive)"
```

---

## Mode Card: C — Hierarchical (Sub-Teams)

**When to use**:
- Goal spans multiple domains/teams
- Want to scale beyond 2-3 agents
- Need organized accountability (team leads)

**Example goals**:
- "Launch Q3 growth initiative: growth team + ops team"
- "Product launch: engineering + marketing + sales"
- "Solve churn: retention team + product team + support team"

**Pros**:
- Scales to large goals
- Teams work in parallel
- Clear accountability (team leads)
- Organized output (team summaries merge cleanly)

**Cons**:
- Most LLM calls
- Needs good team definitions
- More complexity

**Cost**:
- ~$2-3 (8-12 LLM calls, parallel)

**Teams defined in code**:
```python
_TEAMS = {
  "growth": ["dev", "rohan", "isha"],  # research + outreach + marketing
  "ops": ["kavya", "arjun", "meera"],  # health + QA + training
  "sales": ["rohan", "swara"],         # outreach + close
}
```

**Example API call**:
```bash
curl -X POST http://localhost:8000/api/agents/coordinate-hierarchical \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "goal": "Q3 initiative: grow leads + improve ops health",
    "execute": false
  }'
```

**Expected flow**:
```
Growth team (parallel):
  Dev → channels research
  Rohan → outreach planning
  Isha → content calendar
  ↓ (team summary: "3-channel plan ready, 180 leads target")

Ops team (parallel):
  Kavya → system health check
  Arjun → QA scorecard
  Meera → training plan
  ↓ (team summary: "health 90/100, 3 gaps identified")

Boss merges both summaries
```

---

## Mode Card: D — Advanced (Reflexion + Memory)

**When to use**:
- Need quality guarantees (goal must score ≥0.7)
- Want loop to improve through iterations
- Important strategic decisions
- Willing to wait 2-3 min for better output

**Example goals**:
- "Design 30-day growth strategy with 0.8 quality score"
- "Churn analysis: root causes + 3 solutions ranked by ROI"
- "New market entry plan: 0.8 quality confidence"

**Pros**:
- Quality-gated (loops until meets bar)
- Self-improves via reflection
- Episodic memory persists learnings
- Best output quality

**Cons**:
- Slowest (multiple iterations)
- Most LLM calls
- Higher cost ($3-4)

**Cost**:
- ~$3-4 (10-15 LLM calls, multiple iterations)

**Iteration pattern**:
```
Iteration 1: Plan → Execute → Verify (score 0.45)
  "Too generic. No niche focus."
  ↓ REFLECT
  "Next: focus on solar-subsidy angle"

Iteration 2: Plan (with hint) → Execute → Verify (score 0.68)
  "Better. Missing ROI projections."
  ↓ REFLECT
  "Next: add customer lifetime value calculations"

Iteration 3: Plan (with hints) → Execute → Verify (score 0.82) ✓
  "Complete plan. Confident."
```

**Example API call**:
```bash
curl -X POST http://localhost:8000/api/agents/coordinate-advanced \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "goal": "30-day Q3 growth plan: high-confidence strategy",
    "execute": false,
    "max_iterations": 3,
    "quality_bar": 0.8,
    "max_steps": 4
  }'
```

**Expected output** (partial):
```json
{
  "ok": true,
  "pattern": "reflexion",
  "iterations": [
    {"iteration": 0, "score": 0.45, "weak": ["Too broad", "No prioritization"], "steps": 3},
    {"iteration": 1, "score": 0.68, "weak": ["Missing timeline"], "steps": 3},
    {"iteration": 2, "score": 0.82, "weak": [], "steps": 3}
  ],
  "final_score": 0.82,
  "critique": {
    "score": 0.82,
    "weak": [],
    "fixes": []
  },
  "summary": "30-day plan ready. Focus: 3 verticals × 3 cities. Week-by-week execution. ROI: 180 leads → 30 qualified → 6 customers."
}
```

---

## Quick Comparison Table

| Aspect | Sequential (A) | Parallel (B) | Hierarchical (C) | Advanced (D) |
|--------|---|---|---|---|
| **Best for** | Simple ordered goals | Independent research | Complex multi-domain | Strategic + quality |
| **Speed** | Slow | Fast (3x) | Fast (parallel) | Slower (iterations) |
| **Cost** | $1-2 | $1-2 | $2-3 | $3-4 |
| **LLM calls** | 5-6 | 4-6 | 8-12 | 10-15 |
| **Max agents** | 2-4 | 3-4 | 6-8 | 4-5 |
| **Quality** | Good | Good | Good | Best (gated) |
| **Learning** | No | No | No | Yes (memory) |
| **Example** | Solar email sequence | Compare 3 cities | Launch initiative | 30-day strategy |

---

## Decision Examples

### Example 1: "I need solar leads + cold emails"

**Decision tree**:
```
Is goal simple (1-2 steps)? → YES (get leads + draft emails)
→ Use SEQUENTIAL (Mode A)
```

**Command**:
```bash
curl -X POST http://localhost:8000/api/agents/coordinate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"goal": "Get 20 solar leads in Pune + draft cold-email sequence"}'
```

---

### Example 2: "Compare Pune vs Mumbai vs Bangalore solar markets"

**Decision tree**:
```
Can split into independent tasks? → YES (3 cities, separate research)
→ Use PARALLEL (Mode B)
```

**Command**:
```bash
curl -X POST http://localhost:8000/api/agents/fan-out \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"goal": "Compare solar markets: Pune vs Mumbai vs Bangalore"}'
```

---

### Example 3: "Launch Q3 with growth + ops improvements"

**Decision tree**:
```
Spans multiple teams? → YES (growth + ops)
→ Use HIERARCHICAL (Mode C)
```

**Command**:
```bash
curl -X POST http://localhost:8000/api/agents/coordinate-hierarchical \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"goal": "Q3 launch: grow leads + fix ops health"}'
```

---

### Example 4: "Design 30-day growth strategy with confidence"

**Decision tree**:
```
Need quality + learning? → YES (strategic, iterative refinement)
→ Use ADVANCED (Mode D)
```

**Command**:
```bash
curl -X POST http://localhost:8000/api/agents/coordinate-advanced \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "goal": "30-day Q3 strategy: high-confidence plan",
    "quality_bar": 0.8,
    "max_iterations": 3
  }'
```

---

## Advanced Mode: Episodic Memory

Advanced mode (Mode D) learns via reflection. Each iteration's lesson is stored in `data/agent_memory.jsonl`:

```json
{
  "topic": "solar market planning",
  "reflection": "Solar + Pune combination high-ROI; focus subsidy awareness angle. Skip generic channels.",
  "score": 0.68,
  "at": "2026-06-15T10:22:30Z"
}
```

When you run another advanced goal with similar topic, memory is **recalled** and used as a hint to the planner.

**Clear memory** (optional):
```bash
rm data/agent_memory.jsonl  # Start fresh
```

---

## Safety Defaults

All coordinator runs:
- Default to `execute=false` (draft mode, no side-effects)
- Never auto-send emails or dials calls
- Cost-tracked (monitor via `/api/growth/infra/llm`)
- Logged to `data/coordination_runs.jsonl`

Only these agents can execute (with `execute=true`):
- **isha** (post generation)
- **dev** (research)
- **kavya** (health check)
- **arjun** (QA)
- **meera** (training)

**rohan** and **swara** remain draft-only (cold-email and voice are human-approved).
