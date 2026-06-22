# Phase 7: Deterministic Feedback Loops + Cost-Aware Bandit Optimization

**Date**: 2026-06-14  
**Status**: IMPLEMENTED  
**Related**: `app/agents/self_improve.py`, `app/platform/skill_library.py`, `docs/AUTOMATION.md`

## Problem Statement

### Current State (Phase 6)
The self-improve loop uses **epsilon-greedy bandit** task picking based solely on **success_rate**:
- Picks high-success actions (70% of time)
- Explores random actions (30% of time)
- Records cost but doesn't use it in decision-making

### Issue: Cost Blind Bandit
Without cost-aware optimization, the loop can pick expensive tasks with neutral outcomes:

```
Action: seo_pages
  success_rate: 0.80 (high)
  cost: $5.00/run
  last 5 outcomes: 2 hot leads, 3 "informational" (neutral)
  
→ Loop picks it anyway (success_rate high)
→ Cost: $5 × neutral outcome = $5 wasted
→ No ROI improvement, budget burned
```

**Result**: Loop may exhaust daily budget ($50) on low-ROI work.

## Solution: Hybrid Approach

Keep the **free-LLM Reflexion** learning intact. Add three layers:

### Layer 1: Outcome Value Computation (Deterministic)
Instead of binary `ok: true`, compute a **weighted score** (0-1) combining:
- **Lead quality** (40%): `avg_lead_score` → relevance/hotness
- **Revenue** (40%): `revenue_impact` ($) → expected deals
- **Cost** (-20%): penalty for expensive runs

**Formula**:
```python
score = 0.40 * lead_quality + 0.40 * revenue_normalized - 0.20 * cost_normalized
```

Outcome ranges:
- `1.0` = hot leads + revenue - cheap → ideal
- `0.5` = neutral (info, no revenue, normal cost)
- `0.0` = failure + expensive → worst

### Layer 2: Deterministic Gates (Blocking)
Three rules that **skip** expensive low-ROI tasks:

#### Gate 1: Budget
```
IF (remaining_budget < estimated_cost):
  SKIP (reason: budget_exceeded)
```
- Remaining = daily_cap - spent_so_far
- Prevents overspend

#### Gate 2: Expensive + Risky
```
IF (success_rate < 60% AND cost > $5):
  SKIP (reason: expensive_risky)
```
- Example: seo_pages (success 55%, cost $5) → skip
- Protects against risky bets

#### Gate 3: Low ROI + Expensive
```
IF (last_outcome.value_score < 0.5 AND cost > $3):
  SKIP (reason: low_roi)
```
- Example: content_pack (neutral last run, cost $3) → skip next
- Prevents repeating failed approaches

### Layer 3: Cost-Aware Picking (Biasing)
When epsilon-greedy picks, add **cost penalty**:

```python
weighted_score = success_rate * recency_boost + cost_penalty

if cost > remaining_budget:
  cost_penalty = -0.5  # strong disincentive
elif cost > $5:
  cost_penalty = -0.2  # mild disincentive
else:
  cost_penalty = 0     # cheap actions neutral
```

Result: Cheap-high-success actions prioritized naturally.

## Implementation Details

### File: `app/agents/self_improve.py`

#### Constants
```python
OUTCOME_WEIGHTS = {
    "lead_quality": 0.40,
    "revenue": 0.40,
    "cost": -0.20,
}

DETERMINISTIC_GATES = {
    "budget": True,            # Enable/disable
    "expensive_risky": True,
    "low_roi": True,
}
```

#### Function: `compute_outcome_value(outcome_dict)`
Input:
```python
{
    "lead_count": 18,
    "avg_lead_score": 0.64,      # from lead_scoring
    "revenue_impact": 150,       # $ expected from deals
    "cost": 2.31,                # $ spent
    "success": True
}
```

Output: `0-1` score (clamped)

Example calculations:
```
1. High quality + revenue + cheap:
   lead_quality=0.9, revenue=$1000→1.0, cost=$1→0.1
   → 0.40*0.9 + 0.40*1.0 - 0.20*0.1 = 0.98 ✅ ideal

2. Neutral (info lead, no revenue):
   lead_quality=0.3, revenue=$0→0.0, cost=$2→0.2
   → 0.40*0.3 + 0.40*0.0 - 0.20*0.2 = 0.12 - 0.04 = 0.08 ⚠️ weak

3. Expensive failure:
   lead_quality=0.0, revenue=$0→0.0, cost=$10→1.0
   → 0.40*0.0 + 0.40*0.0 - 0.20*1.0 = -0.20 → clamped 0.0 ❌ worst
```

#### Function: `should_skip_task(task_name, cost_remaining, last_outcome)`
Returns: `(skip: bool, reason: str)`

Example gates in action:
```
# Gate 1: Budget
should_skip_task("seo_pages", cost_remaining=1.5)
→ (True, "budget_exceeded ($1.50 left, task costs $5.00)")

# Gate 2: Expensive + Risky
success_rate=0.55, cost=$5.50
→ (True, "expensive_risky (success=55%, cost=$5.50)")

# Gate 3: Low ROI + Expensive
last_outcome.value_score=0.4, cost=$3.50
→ (True, "low_roi (outcome_value=0.40, cost=$3.50)")
```

#### Updated Loop: `run_once()`
Order:
1. **Pick** task (epsilon-greedy bandit + cost bias)
2. **Estimate cost**
3. **Deterministic gates** (budget, expensive_risky, low_roi)
4. **Cost gate** (Phase 6, Phase 7 complements)
5. **Approval gate** (Phase 6, if enabled)
6. **Execute**
7. **Compute outcome_value** (NEW)
8. **Record** cost + outcome_value
9. **Learn** (skill_library.record_use + Reflexion)

Return now includes:
```python
{
    "action": "seo_pages",
    "ok": True,
    "cost": 5.00,
    "outcome_value": 0.68,  # NEW: weighted score
    "cost_status": {
        "spent": 12.50,
        "remaining": 37.50,
        "pct_used": 25.0
    },
    "at": "2026-06-14T10:30Z"
}
```

### Data: `data/self_improve_runs.jsonl`
Each run now includes:
```json
{
  "id": "a1b2c3d4e5",
  "action": "seo_pages",
  "ok": true,
  "cost": 5.00,
  "outcome_value": 0.68,
  "detail": "2 pages generated",
  "ms": 12500.0,
  "at": "2026-06-14T10:30Z"
}
```

## Backward Compatibility

✅ **No breaking changes**:
- `compute_outcome_value()` = new function, doesn't affect existing code
- `should_skip_task()` = new function, doesn't affect existing code
- Gates can be disabled individually via `DETERMINISTIC_GATES` dict
- If `cost_budget=None`, gates don't trigger (safe default)
- Existing Reflexion loop untouched — LLM learning continues

✅ **Opt-in**:
- New gates require no env vars (ON by default)
- Can disable gates by setting `DETERMINISTIC_GATES["<gate>"]=False`
- Outcome value calculation = fallback to 0.5 on error

## Tuning Parameters

### Daily Budget
```bash
SELFIMPROVE_COST_CAP=50.0  # $ per day (default)
```

### Gate Thresholds
Edit `DETERMINISTIC_GATES` dict in `self_improve.py`:
```python
DETERMINISTIC_GATES = {
    "budget": True,            # Always check budget
    "expensive_risky": True,   # Skip high-cost + low-success
    "low_roi": True,           # Skip neutral outcomes
}
```

### Success Threshold (expensive_risky gate)
```python
# In should_skip_task()
if success_rate < 0.6 and cost_avg > 5:  # tunable thresholds
    return True, "expensive_risky..."
```

### Cost Thresholds
```python
OUTCOME_WEIGHTS = {
    "lead_quality": 0.40,      # adjust quality importance
    "revenue": 0.40,           # adjust revenue importance
    "cost": -0.20,             # adjust cost penalty
}
```

## Examples

### Scenario 1: Expensive Risky Task (SKIPPED)

```
Loop state:
  today_cost: $30
  daily_cap: $50
  remaining: $20

Picks: seo_pages (LLM-heavy, cost $5)
  success_rate: 0.52 (low)
  last 5 runs: 3 passed, 2 failed

Gates:
  budget? $5 < $20 ✓ pass
  expensive_risky? 0.52 < 0.6 AND $5 > $5 ✗ SKIP
  
Action: SKIP (expensive_risky)
Reason: "expensive_risky (success=52%, cost=$5.00)"
Remaining: $20 (preserved)
```

### Scenario 2: Low ROI Task (SKIPPED)

```
Loop state:
  today_cost: $35
  daily_cap: $50
  remaining: $15

Picks: content_pack (cost $3)
  last_outcome: {
    "value_score": 0.35,      # neutral (no leads converted)
    "cost": $3
  }

Gates:
  budget? $3 < $15 ✓ pass
  expensive_risky? 0.60 > 0.60, cost N/A ✓ pass
  low_roi? 0.35 < 0.5 AND $3 > $3 ✗ SKIP

Action: SKIP (low_roi)
Reason: "low_roi (outcome_value=0.35, cost=$3.00)"
Remaining: $15 (preserved)
```

### Scenario 3: Cheap High-ROI Task (EXECUTED)

```
Loop state:
  today_cost: $20
  daily_cap: $50
  remaining: $30

Picks: harvest_leads (cost $0.50, free-stack)
  success_rate: 0.92 (high)
  last_outcome: {
    "value_score": 0.85,       # hot leads found
    "cost": $0.50
  }

Gates:
  budget? $0.50 < $30 ✓ pass
  expensive_risky? 0.92 > 0.6 ✓ pass
  low_roi? 0.85 > 0.5 ✓ pass

Action: EXECUTE
Cost: $0.50
Outcome: 18 leads, avg_score=0.72
Outcome_value: compute({
  lead_quality: 0.72,
  revenue: $240→0.24,
  cost: $0.50→0.05
}) = 0.40*0.72 + 0.40*0.24 - 0.20*0.05 = 0.368 → round to 0.37 ✅ good

Total cost today: $20.50
```

## Testing

See `scripts/test_phase7_deterministic_loops.py`:

- `test_outcome_value_computation()` — weighting formula
- `test_cost_aware_budget()` — budget gate works
- `test_skip_expensive_risky()` — expensive_risky gate works
- `test_skip_low_roi()` — low_roi gate works
- `test_hybrid_reflexion()` — LLM learning unaffected
- `test_gates_can_disable()` — gates can be toggled

All tests ✅ PASS.

## Integration with Existing Systems

### Skill Library (unchanged)
- `skill_library.stats()` → success_rate still used for picking
- New outcome_value doesn't replace success_rate (parallel)
- Gates read success_rate to make decisions

### Reflexion (unchanged)
- `_reflect()` still runs every 8 iterations
- LLM lesson learning unaffected
- Outcome value ≠ LLM learning (complementary)

### Cost Tracking (Phase 6, unchanged)
- `CostTracker.can_afford()` still gates budget
- Phase 7 gates add more granular checks
- Both work together: Phase 6 simple budget, Phase 7 cost-ROI trade-off

### Approval Queue (Phase 6, unchanged)
- Approval gate still present for LLM-heavy actions
- Gates are orthogonal (all can be ON)
- Order: pick → Phase 7 gates → Phase 6 cost/approval → execute

## Performance Impact

- `compute_outcome_value()` = O(1), negligible
- `should_skip_task()` = O(actions) stat lookup, ~100ms max
- No additional LLM calls
- No network I/O

**Overhead**: <200ms per `run_once()` iteration (already 240s timeout)

## Future Extensions

1. **Dynamic gate thresholds**: Learn from historical skip-rates
2. **Multi-objective optimization**: Pareto frontier (lead quality vs cost)
3. **Outcome predictor**: ML model to estimate outcome_value before execution
4. **A/B test gates**: Run with/without gates, measure ROI difference
5. **Per-action cost models**: More granular cost estimation

## Lessons Learned

### Why Outcome Value (not just success_rate)?
- **Binary success is coarse**: Pass/fail doesn't capture quality
- **Revenue alignment**: Outcome value includes $ impact
- **Cost-aware**: Expensive tasks penalized even if "successful"
- **Reflective**: Combines multiple metrics like human would

### Why Deterministic Gates (not pure LLM)?
- **Transparent**: Rules clear and auditable
- **Fast**: No LLM calls, instant decision
- **Predictable**: Same gate always triggers for same input
- **Safe**: Won't drift like LLM could (hallucination risk)
- **Hybrid**: Still use LLM for Reflexion (learn from patterns)

### Why Hybrid (Gates + Reflexion)?
- **Gates**: Prevent obvious mistakes (expensive + risky)
- **Reflexion**: Find subtle insights (why did X fail?)
- **Together**: Logic + learning = superior judgment

---

**Next Phase**: Monitor outcome_value distribution + cost ROI trends → adjustive gates (Phase 8).
