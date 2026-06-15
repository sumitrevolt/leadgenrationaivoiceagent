# Phase 7 Quick Start Guide

**For**: Developers, DevOps, admins wanting to understand or tune the deterministic feedback loops.

---

## TL;DR

Phase 7 adds **3 deterministic gates** that block expensive/low-ROI tasks in the self-improve loop:

1. **Budget Gate**: Don't spend more than daily cap ($50)
2. **Expensive + Risky Gate**: Don't bet $5+ on < 60% success
3. **Low ROI Gate**: Don't repeat failed approaches

Additionally, it computes an **outcome value score** (0-1) from lead quality + revenue - cost.

**Zero breaking changes**. All existing code works unchanged.

---

## Quick Configuration

### Disable a Gate
```python
# In app/agents/self_improve.py
DETERMINISTIC_GATES["expensive_risky"] = False  # Allow risky bets
```

### Change Budget Cap
```bash
# In .env or shell
export SELFIMPROVE_COST_CAP=100  # Increase to $100/day
```

### Tune Outcome Weights
```python
# In app/agents/self_improve.py
OUTCOME_WEIGHTS = {
    "lead_quality": 0.35,    # Decrease importance
    "revenue": 0.50,         # Increase importance
    "cost": -0.15,           # Reduce penalty
}
```

---

## What Gets Logged

Each run in `data/self_improve_runs.jsonl` includes:
```json
{
  "action": "seo_pages",
  "cost": 5.00,
  "outcome_value": 0.68,    # NEW: 0-1 score
  "ok": true,
  "detail": "2 pages",
  "at": "2026-06-14T10:30Z"
}
```

## What Gets Skipped (and Why)

```
[GATE: budget_exceeded ($20 left, task costs $25)]
  → Budget gate blocked expensive task

[GATE: expensive_risky (success=52%, cost=$5.00)]
  → Expensive + risky gate blocked uncertain task

[GATE: low_roi (outcome_value=0.35, cost=$3.00)]
  → Low ROI gate blocked repeated failure
```

---

## Checking Status

```python
from app.agents import self_improve

# Daily cost status
status = self_improve.cost_status()
print(f"Spent: ${status['spent']} / ${status['cap']}")
print(f"Remaining: ${status['remaining']}")

# Approval queue status (if enabled)
approvals = self_improve.approval_status()
print(f"Pending approvals: {approvals['pending_count']}")

# Loop status
loop_status = self_improve.status()
print(f"Recent runs: {loop_status['recent_runs'][-5:]}")
```

---

## Understanding Outcome Value

Formula:
```
value = 0.40 × lead_quality + 0.40 × revenue - 0.20 × cost

value → [0, 1], clamped
```

### Score Interpretation

| Score | Meaning | Example |
|-------|---------|---------|
| 0.90+ | Ideal | 20 hot leads + $1000 revenue + $1 cost |
| 0.60-0.90 | Good | 10 leads + $500 revenue + $2 cost |
| 0.40-0.60 | Neutral | 5 info leads + $0 revenue + $2 cost |
| 0.10-0.40 | Weak | 2 info leads + $0 revenue + $5 cost |
| 0.0 | Worst | 0 leads + $0 revenue + $10 cost |

---

## Tuning Strategy

### Week 1: Observe
- Leave gates ON (default)
- Watch gate trigger rates
- Note which actions get skipped

### Week 2: Measure
- Calculate cost per gate skip
- Calculate ROI of skipped tasks
- Identify false positives (good tasks skipped)

### Week 3: Adjust
- If gates too strict: lower thresholds
- If gates too loose: raise thresholds
- If weights off: adjust OUTCOME_WEIGHTS

### Ongoing: Monitor
- Watch outcome value distribution
- Track cost ROI trends
- Monthly review of gate effectiveness

---

## Example: Tuning Expensive + Risky Gate

**Initial problem**: Gate blocks too many tasks (50% skip rate)

**Analysis**:
```
Gate rule: success < 60% AND cost > $5
Current data: 10 actions, 5 have success < 60%
```

**Solutions**:
```python
# Option 1: Raise success threshold
# OLD: if success_rate < 0.6
# NEW: if success_rate < 0.5
# Result: fewer blocks, slightly more risk

# Option 2: Raise cost threshold
# OLD: if cost_avg > 5
# NEW: if cost_avg > 7
# Result: only very expensive tasks blocked

# Option 3: Disable gate entirely
DETERMINISTIC_GATES["expensive_risky"] = False
# Result: trust epsilon-greedy only
```

Choose based on whether your *actual* skip rate matches your *expected* ROI loss.

---

## Debugging

### Gate Not Triggering (When It Should)

Check: Is gate enabled?
```python
from app.agents import self_improve
print(self_improve.DETERMINISTIC_GATES)  # Should show True
```

Check: Are thresholds being met?
```python
# Add logging to should_skip_task()
skip, reason = self_improve.should_skip_task("seo_pages", 30.0)
print(f"Skip: {skip}, Reason: {reason}")
```

### Gate Over-Triggering (Too Many Blocks)

Lower thresholds or disable gate:
```python
# Disable temporarily to measure impact
self_improve.DETERMINISTIC_GATES["expensive_risky"] = False
```

### Outcome Value Always ~0.5 (Neutral)

Check: Are actions returning metrics?
```python
# Actions must return in result dict:
result = {
    "ok": True,
    "lead_count": 18,
    "avg_lead_score": 0.64,
    "revenue_impact": 150,
}
# If missing, falls back to 0.5
```

---

## Integration with Other Systems

### Reflexion Loop
- Runs every 8 iterations
- **Unchanged** by Phase 7
- Returns LLM lessons

### Skill Library
- Tracks success_rate
- Phase 7 reads success_rate for gates
- Outcome value is **parallel** to success_rate

### Cost Tracking (Phase 6)
- Tracks daily budget
- Phase 7 gates **complement** budget tracking
- Both layers active

### Approval Queue (Phase 6)
- Gate for high-cost tasks
- Phase 7 gates **complement** approval queue
- Both layers active

---

## Monitoring Commands

### Check Daily Budget
```bash
# Via Python
from app.agents import self_improve
print(self_improve.cost_status())

# Via database query
SELECT action, cost FROM self_improve_runs WHERE date(at) = date('now');
```

### Check Gate Triggers
```bash
# Via log (search for [GATE:)
tail -f logs/*.log | grep "GATE:"

# Via data
jq 'select(.skipped == "gate_skip") | .gate_reason' data/self_improve_runs.jsonl
```

### Check Outcome Values
```bash
# Via data
jq '.outcome_value' data/self_improve_runs.jsonl | sort -n | uniq -c
```

---

## Common Questions

**Q: What if a gate is wrong?**  
A: Gates are best-effort. They prevent *obvious* bad decisions, not all bad decisions. Reflexion learning catches subtle patterns.

**Q: Can I disable all gates?**  
A: Yes:
```python
DETERMINISTIC_GATES["budget"] = False
DETERMINISTIC_GATES["expensive_risky"] = False
DETERMINISTIC_GATES["low_roi"] = False
```
Loop runs like Phase 6 only.

**Q: How do I adjust the daily budget?**  
A: Set environment variable:
```bash
SELFIMPROVE_COST_CAP=100
```

**Q: Do gates cost anything?**  
A: No. Gates are pure Python logic, no LLM calls.

**Q: What's the difference between Phase 6 and Phase 7 budget gates?**  
A: 
- **Phase 6** (`CostTracker`): Simple "spent < cap" check
- **Phase 7** (`DETERMINISTIC_GATES`): Granular "cost > remaining for this task" + "expensive + risky" + "low ROI"

Both active for layered safety.

---

## References

| Document | Purpose |
|----------|---------|
| `docs/PHASE7_DETERMINISTIC_LOOPS.md` | Full technical documentation |
| `references/feedback-loop-patterns.md` | Architecture patterns (hybrid LLM + gates) |
| `scripts/test_phase7_deterministic_loops.py` | Unit tests (17 test cases) |
| `app/agents/self_improve.py` | Implementation (lines 590-1019) |

---

**Questions?** Check `docs/PHASE7_DETERMINISTIC_LOOPS.md` for detailed explanation of each gate.
