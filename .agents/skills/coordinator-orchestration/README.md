# Coordinator Orchestration Skill Package

Complete skill set for orchestrating multi-agent goals in LeadGenAI.

## Overview

The **Coordinator Orchestration** skill teaches you how to:
1. Run **on-demand multi-agent goals** (now, not automated)
2. Choose between **4 coordination modes** (sequential, parallel, hierarchical, advanced)
3. **Verify quality** and **learn from outcomes**
4. **Audit and troubleshoot** coordinator runs

This is different from the **Self-Improve Loop** (daily hands-off) and **Process-Engine** (deterministic workflows).

---

## Files in This Package

### Main Skill
- **`SKILL.md`** (570 lines) — Complete usage guide
  - When to use coordinator
  - 4 modes explained with examples
  - 5-step workflow
  - 3 worked examples (lead campaign, market analysis, strategy)
  - Troubleshooting guide
  - API reference
  - Safety notes

### References
- **`references/coordinator-patterns.md`** (390 lines) — Decision tree + mode cards
  - Quick decision tree: which mode to use?
  - Detailed mode cards (A=Sequential, B=Parallel, C=Hierarchical, D=Advanced)
  - Comparison table
  - 4 decision examples
  - Episodic memory explanation

- **`references/coordination-schema.md`** (362 lines) — Data format reference
  - Structure of coordinator runs in `data/coordination_runs.jsonl`
  - Sequential / Parallel / Hierarchical / Advanced mode schemas
  - Debate mode schema
  - Query examples (Python snippets)
  - Error handling guide
  - Retention policy

---

## Quick Start

### 1. Choose Your Goal

```bash
# Good goal
"Get 20 solar leads in Pune + draft cold-email sequence"

# Bad goal
"Marketing stuff"
```

### 2. Pick the Right Mode

```
Goal simple (1-2 steps)?        → Sequential (Mode A)
Goal has independent tasks?     → Parallel (Mode B)
Goal spans multiple domains?    → Hierarchical (Mode C)
Need quality + learning?        → Advanced (Mode D)
```

### 3. Run Coordinator (Draft First)

```bash
curl -X POST http://localhost:8000/api/agents/coordinate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Get 20 solar leads in Pune + draft cold-email sequence"
  }'
```

### 4. Review Output

Look at `results` — does output match goal?

### 5. Execute or Iterate

```bash
# If good, execute with real tools
curl ... -d '{"goal": "...", "execute": true}'

# If weak, try advanced mode
curl ... -d '{"goal": "...", "mode": "advanced", "quality_bar": 0.8}'
```

---

## CLI Tool: coordinator_audit.py

Monitor and audit coordinator runs from `data/coordination_runs.jsonl`.

**Location**: `scripts/coordinator_audit.py`

**Commands**:

```bash
# Last run
python scripts/coordinator_audit.py --last-run

# Last N runs (summary)
python scripts/coordinator_audit.py --runs 10

# Success rate by mode
python scripts/coordinator_audit.py --mode-stats

# Cost estimate (LLM calls proxy)
python scripts/coordinator_audit.py --cost-report

# Validate agent chain in a run
python scripts/coordinator_audit.py --validate-chain <run_id>
```

**Example output**:
```
LAST COORDINATOR RUN

  Run ID:     pqr345stu678
  Goal:       Design 30-day strategy
  Mode:       reflexion
  Execute:    False
  Time:       2026-06-14T12:00:00Z
  Steps:      3
  Agents:     dev(1), isha(1), rohan(1)
  Quality:    0.82
  Iterations: 2

  Summary:
    Strategy ready. High confidence....
```

---

## 4 Coordination Modes

### Mode A: Sequential (Linear Handoff)

**When**: Goal has natural ordering (research → outreach → marketing)

**Example**: "Get leads + draft emails + create social post"

**Cost**: $1-2

**Speed**: Slow (sequential)

**Best for**: Simple ordered goals

---

### Mode B: Parallel (Fan-Out)

**When**: Goal can split into independent tasks

**Example**: "Compare solar in Pune vs Mumbai vs Bangalore"

**Cost**: $1-2

**Speed**: Fast (3-4x faster than sequential)

**Best for**: Research + comparison

---

### Mode C: Hierarchical (Sub-Teams)

**When**: Goal spans multiple teams/domains

**Example**: "Q3 launch: grow leads + improve ops health"

**Cost**: $2-3

**Speed**: Fast (parallel teams)

**Best for**: Complex, multi-domain goals

---

### Mode D: Advanced (Reflexion + Memory)

**When**: Need quality guarantees + learning

**Example**: "Design 30-day strategy with 0.8 quality score"

**Cost**: $3-4

**Speed**: Slower (1-3 iterations)

**Best for**: Strategic decisions, important goals

---

## Decision Tree

```
START: I have a goal

├─ Is goal simple (1-2 steps)?
│  └─ YES → Mode A (Sequential)
│
├─ Can goal split into independent tasks?
│  └─ YES → Mode B (Parallel)
│
├─ Goal spans multiple domains?
│  └─ YES → Mode C (Hierarchical)
│
└─ Need quality + learning?
   └─ YES → Mode D (Advanced)
```

**See** `references/coordinator-patterns.md` for detailed decision tree + mode cards.

---

## Safety

- **Default**: `execute=false` (draft mode, no side-effects)
- **Never auto-sends**: Emails and calls always require human approval
- **Executable agents**: Isha, Dev, Kavya, Arjun, Meera (safe side-effects)
- **Draft-only agents**: Rohan, Swara (no auto-send/call, even with `execute=true`)
- **Cost**: ~$1-4 per run (LLM calls only)
- **Logged**: All runs saved to `data/coordination_runs.jsonl`

---

## API Endpoints

### Sequential
```
POST /api/agents/coordinate
Body: {"goal": "...", "execute": false, "max_steps": 5}
```

### Parallel
```
POST /api/agents/fan-out
Body: {"goal": "...", "agents": ["dev", "isha"], "max_agents": 4}
```

### Hierarchical
```
POST /api/agents/coordinate-hierarchical
Body: {"goal": "...", "execute": false}
```

### Advanced (Reflexion)
```
POST /api/agents/coordinate-advanced
Body: {
  "goal": "...",
  "execute": false,
  "max_iterations": 3,
  "quality_bar": 0.8,
  "max_steps": 4
}
```

### List Recent Runs
```
GET /api/agents/runs?limit=20
```

### Get Roster
```
GET /api/agents/roster
```

---

## Related Skills

- **`orchestrate-goal`** (separate skill): Decision tree for "which loop?" (self-improve vs coordinator vs process-engine vs manual)
- **`self-improve-loop`**: Daily hands-off task execution with learning
- **`automation-control-center`**: Dashboard showing all loops (self-improve, coordinator, process-engine, etc.)
- **`agent-loop-design`**: Design custom agent loops

---

## FAQ

**Q: When should I use Coordinator vs Self-Improve Loop?**
A: Coordinator = now (specific goal, 1-3 min). Self-Improve = daily (repeating task, hands-off).

**Q: Can I save coordinator outputs?**
A: Yes, all runs saved to `data/coordination_runs.jsonl`. Use `coordinator_audit.py` to inspect.

**Q: What if output is incoherent?**
A: Try advanced mode with `quality_bar=0.8`. Loop iterates until quality improves.

**Q: What if I forget which mode to use?**
A: Check `references/coordinator-patterns.md` decision tree.

**Q: How much does a run cost?**
A: $1-4 (LLM calls). Sequential/Parallel = $1-2. Hierarchical = $2-3. Advanced = $3-4.

---

## Examples

### Example 1: Lead Campaign

```bash
curl -X POST http://localhost:8000/api/agents/coordinate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"goal": "Kolhapur grocery store leads for delivery app pitch"}'
```

**Result**: Dev researches → Rohan drafts emails → Isha creates social → Boss summarizes.

### Example 2: Market Comparison

```bash
curl -X POST http://localhost:8000/api/agents/fan-out \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"goal": "Compare solar: Pune vs Mumbai vs Bangalore"}'
```

**Result**: All 3 cities researched in parallel (3x speed), merged into recommendation.

### Example 3: Quality-Gated Strategy

```bash
curl -X POST http://localhost:8000/api/agents/coordinate-advanced \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "goal": "Design 30-day growth strategy",
    "quality_bar": 0.8,
    "max_iterations": 3
  }'
```

**Result**: Loop runs 1-3 iterations, stops when quality ≥ 0.8. Learns via reflection.

---

## Troubleshooting

**Output incoherent**: Goal too vague → be specific. Try advanced mode.
**Wrong agent picked**: Goal ambiguous → be explicit about roles.
**Slow**: Sequential is slow → try parallel or hierarchical.
**Low quality**: Quality bar too strict → lower it or increase iterations.

See SKILL.md "Troubleshooting" section for detailed guidance.

---

## File Locations

```
.claude/skills/coordinator-orchestration/
├── SKILL.md (main teaching skill)
├── README.md (this file)
└── references/
    ├── coordinator-patterns.md (decision tree + mode cards)
    └── coordination-schema.md (data format reference)

scripts/
└── coordinator_audit.py (audit CLI tool)
```

---

## Version

Created: 2026-06-14
Updated: 2026-06-14

Coordinator code: `app/agents/coordinator.py`
Schema: `data/coordination_runs.jsonl` (JSONL, one run per line)
