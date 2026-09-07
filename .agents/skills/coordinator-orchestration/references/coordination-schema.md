# Coordinator Run Schema

Reference: Understand the structure of coordinator runs stored in `data/coordination_runs.jsonl`.

---

## File Location

```
data/coordination_runs.jsonl
```

Each line is a complete coordinator run (JSON object).

---

## Base Run Structure

```json
{
  "ok": true,
  "run_id": "a7f2c1b3d9e5",
  "goal": "Pune solar prospects — prioritize for sales outreach",
  "execute": false,
  "at": "2026-06-15T10:22:30Z"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ok` | boolean | Yes | Success flag (true = goal met, false = error) |
| `run_id` | string | Yes | Unique 12-char hex ID |
| `goal` | string | Yes | Original goal string |
| `execute` | boolean | Yes | Was execute mode ON (true) or draft (false)? |
| `at` | ISO8601 string | Yes | Timestamp (UTC) |
| `error` | string | No | If ok=false, error message |

---

## Sequential Mode

**Pattern**: Linear agent handoff with shared context.

```json
{
  "ok": true,
  "run_id": "a7f2c1b3d9e5",
  "goal": "Pune solar prospects — 20 leads + cold-email draft",
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
      "output": "Pune solar market: 2000+ active consumers...",
      "provider": "groq"
    },
    {
      "agent": "rohan",
      "task": "Draft cold-email sequence",
      "mode": "draft",
      "output": "Day 1: Awareness email...\nDay 3: Case study...",
      "provider": "cerebras"
    },
    {
      "agent": "isha",
      "task": "Social media angles + content ideas",
      "mode": "executed",
      "output": {
        "caption": "₹3L subsidy + 25yr warranty = solar kitna sasta? 🌞",
        "hashtags": ["#PuneSolar", "#SolarSubsidy"],
        "image_idea": "Before/after rooftop install"
      },
      "provider": "groq"
    }
  ],
  "summary": "Team ke research + outreach plan taire hai...",
  "at": "2026-06-15T10:22:30Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `mode` | string | Always "sequential" |
| `plan` | list[dict] | Ordered list of agent tasks |
| `plan[].agent` | string | Agent key (dev, rohan, isha, etc.) |
| `plan[].task` | string | Task description for agent |
| `results` | list[dict] | Output from each agent |
| `results[].mode` | string | "draft" (no execution) or "executed" (real tool ran) |
| `results[].output` | string or object | Agent output (string for LLM draft, dict for real tool) |
| `results[].provider` | string | LLM provider used (groq, cerebras, etc.) |
| `summary` | string | Boss-generated summary (3-4 lines Hinglish) |

---

## Parallel Mode

**Pattern**: Multiple agents run simultaneously.

```json
{
  "ok": true,
  "run_id": "b8e3d2c1f4g6",
  "goal": "Compare solar opportunity: Pune vs Mumbai vs Bangalore",
  "mode": "parallel",
  "agents": ["dev", "isha", "kavya"],
  "results": [
    {"agent": "dev", "mode": "draft", "output": "Pune solar...", "provider": "groq"},
    {"agent": "isha", "mode": "draft", "output": "Mumbai solar...", "provider": "groq"},
    {"agent": "kavya", "mode": "draft", "output": "Bangalore solar...", "provider": "cerebras"}
  ],
  "summary": "Pune > Mumbai > Bangalore. Pune: high-subsidy...",
  "at": "2026-06-15T10:25:10Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `mode` | string | Always "parallel" |
| `agents` | list[string] | Agent keys that ran |
| `results` | list[dict] | Results (no order guarantee, concurrent) |

---

## Hierarchical Mode

**Pattern**: 2-level hierarchy (sub-teams → Boss).

```json
{
  "ok": true,
  "run_id": "c9f4e3d2a5h7",
  "goal": "Q3 launch: grow leads + improve ops health",
  "pattern": "hierarchical",
  "teams": [
    {
      "team": "growth",
      "objective": "Grow leads for Q3",
      "members": ["dev", "rohan", "isha"],
      "results": [
        {"agent": "dev", "mode": "draft", "output": "..."},
        {"agent": "rohan", "mode": "draft", "output": "..."},
        {"agent": "isha", "mode": "executed", "output": {...}}
      ],
      "summary": "3-channel growth plan ready..."
    },
    {
      "team": "ops",
      "objective": "Improve ops health for Q3",
      "members": ["kavya", "arjun", "meera"],
      "results": [
        {"agent": "kavya", "mode": "draft", "output": "..."},
        {"agent": "arjun", "mode": "draft", "output": "..."},
        {"agent": "meera", "mode": "draft", "output": "..."}
      ],
      "summary": "Health 90/100, 3 gaps identified..."
    }
  ],
  "summary": "Growth + Ops plans coordinated. Q3 ready.",
  "at": "2026-06-15T10:30:45Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `pattern` | string | Always "hierarchical" |
| `teams` | list[dict] | Sub-team results |
| `teams[].team` | string | Team name (growth, ops, sales) |
| `teams[].objective` | string | Sub-goal for this team |
| `teams[].members` | list[string] | Agents in team |
| `teams[].results` | list[dict] | Agent results (sequential within team) |
| `teams[].summary` | string | Team-level summary (Hinglish) |

---

## Advanced Mode (Reflexion)

**Pattern**: Multiple iterations with quality scoring and reflection.

```json
{
  "ok": true,
  "run_id": "d0g5f4e3b6i8",
  "goal": "30-day Q3 growth plan: high-confidence strategy",
  "pattern": "reflexion",
  "iterations": [
    {
      "iteration": 0,
      "score": 0.45,
      "weak": ["Too broad (23 cities × 5 niches = 115 combos)", "Missing prioritization"],
      "steps": 3
    },
    {
      "iteration": 1,
      "score": 0.68,
      "weak": ["Missing timeline"],
      "steps": 3
    },
    {
      "iteration": 2,
      "score": 0.82,
      "weak": [],
      "steps": 3
    }
  ],
  "final_score": 0.82,
  "critique": {
    "score": 0.82,
    "weak": [],
    "fixes": []
  },
  "results": [
    {"agent": "dev", "mode": "draft", "output": "..."},
    {"agent": "rohan", "mode": "draft", "output": "..."},
    {"agent": "isha", "mode": "executed", "output": {...}}
  ],
  "summary": "30-day plan ready. Focus: 3 verticals × 3 cities...",
  "memory_used": 2,
  "at": "2026-06-15T10:35:20Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `pattern` | string | Always "reflexion" |
| `iterations` | list[dict] | One entry per iteration (1-3) |
| `iterations[].iteration` | int | Iteration number (0-indexed) |
| `iterations[].score` | float | Quality score (0.0-1.0) from critic |
| `iterations[].weak` | list[string] | Weaknesses identified by critic |
| `iterations[].steps` | int | Number of agent steps in this iteration |
| `final_score` | float | Score from final iteration |
| `critique` | dict | Final critique {score, weak, fixes} |
| `results` | list[dict] | Results from LAST (best) iteration |
| `memory_used` | int | Number of prior reflections recalled |

---

## Debate Mode

**Pattern**: Pro vs con arguments, Boss verdict.

```json
{
  "ok": true,
  "run_id": "e1h6g5f4c7j9",
  "goal": "Should we launch voice product or focus on marketing?",
  "question": "Should we launch voice product or focus on marketing?",
  "rounds": [
    {
      "round": 0,
      "pro": "Voice = new revenue stream + margin. Market ready. 3 competitors only.",
      "con": "Voice = complex + compliance. Marketing = proven profitable. Spreads team."
    },
    {
      "round": 1,
      "pro": "Can hire. Voice product = 50k MRR potential in 6mo.",
      "con": "No data. Marketing = 20k MRR in 3mo guaranteed. Less risk."
    }
  ],
  "verdict": "Launch Marketing-first (Q1-Q2), build voice (Q3). Marketing ROI proves market demand, reduces voice risk.",
  "at": "2026-06-15T10:40:15Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `question` | string | Original debate prompt |
| `rounds` | list[dict] | Pro/con rounds (1-2) |
| `rounds[].round` | int | Round number (0-indexed) |
| `rounds[].pro` | string | Pro argument (Hinglish, 2-3 lines) |
| `rounds[].con` | string | Con argument (Hinglish, 2-3 lines) |
| `verdict` | string | Boss verdict (Hinglish, 3-4 lines) |

---

## Query Examples

### Get all sequential runs

```python
import json

with open("data/coordination_runs.jsonl") as f:
    for line in f:
        run = json.loads(line)
        if run.get("mode") == "sequential":
            print(f"{run['run_id']}: {run['goal']}")
```

### Calculate average quality for advanced runs

```python
scores = []
with open("data/coordination_runs.jsonl") as f:
    for line in f:
        run = json.loads(line)
        if "final_score" in run:
            scores.append(run["final_score"])

avg = sum(scores) / len(scores) if scores else 0
print(f"Average quality: {avg:.2f}")
```

### Find slowest run (most iterations)

```python
slowest = None
with open("data/coordination_runs.jsonl") as f:
    for line in f:
        run = json.loads(line)
        iters = len(run.get("iterations", []))
        if slowest is None or iters > len(slowest.get("iterations", [])):
            slowest = run

if slowest:
    print(f"Slowest: {slowest['run_id']} ({len(slowest['iterations'])} iterations)")
```

---

## Error Handling

If `ok=false`, inspect `error`:

```json
{
  "ok": false,
  "error": "goal bahut chhota hai",
  "at": "2026-06-15T10:45:00Z"
}
```

**Common errors**:
- `goal bahut chhota hai` — Goal too short (< 3 chars)
- `dependency missing` — Agent tool not installed
- Provider timeout — LLM quota exceeded

---

## Cleanup / Retention

The file grows indefinitely. **Optional cleanup**:

```bash
# Keep last 1000 runs
python -c "
import json
with open('data/coordination_runs.jsonl') as f:
    runs = [json.loads(line) for line in f if line.strip()]
with open('data/coordination_runs.jsonl', 'w') as f:
    for run in runs[-1000:]:
        f.write(json.dumps(run) + '\n')
"
```

**Retention policy**: Keep all (disk cheap). If >10MB, archive to `data/coordination_runs.archive.jsonl.gz`.
