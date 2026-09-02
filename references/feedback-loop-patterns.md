# Feedback Loop Patterns: Deterministic + LLM-Based Learning

**Author**: Phase 7 Research  
**Date**: 2026-06-14  
**Tags**: architecture, automation, decision-making, learning

## Overview

Effective feedback loops combine **deterministic logic** (transparent rules) with **LLM-based learning** (pattern discovery). This document explores patterns used in leadgeneration self-improve loop.

## Pattern 1: Deterministic Gates (Blocking Layer)

**Purpose**: Prevent obvious bad decisions fast, without LLM.

**Structure**:
```
Input → Gate Check 1 → Gate Check 2 → ... → Gate Check N → Output
        (rule-based)  (rule-based)          (rule-based)
```

**Characteristics**:
- Fast: O(1) to O(n) computation
- Transparent: Rules visible in code
- Predictable: Same input → same decision
- Auditable: Why skipped? Check gate #3.
- Safe: No hallucinations

**Example (Phase 7)**:
```python
def should_skip_task(task, cost_remaining, last_outcome):
    # Gate 1: Budget
    if task.cost > cost_remaining:
        return True, "budget_exceeded"
    
    # Gate 2: Expensive + Risky
    if task.success_rate < 0.6 and task.cost > $5:
        return True, "expensive_risky"
    
    # Gate 3: Low ROI + Expensive
    if last_outcome.value < 0.5 and task.cost > $3:
        return True, "low_roi"
    
    return False, ""
```

**When to use**:
- Simple rules (if/and/or logic)
- Frequent decisions (latency critical)
- High-stakes choices (need transparency)
- Unknown unknowns (can't train LLM on edge cases)

**Pitfalls**:
- Rules too strict → over-blocking
- Rules too loose → doesn't protect
- Rules hard to tune (threshold Hell)
- Rules don't adapt (no learning)

---

## Pattern 2: LLM-Based Reflection (Learning Layer)

**Purpose**: Find subtle patterns, extract lessons, improve future decisions.

**Structure**:
```
Recent Run 1 ──┐
Recent Run 2 ──┤
Recent Run 3 ──├→ LLM Reflection → Lesson → Skill Library
...            │
Recent Run N ──┘
               (+ project playbook context)
```

**Characteristics**:
- Adaptive: Finds patterns human didn't code
- Contextual: Can reference domain knowledge
- Expressive: Outputs natural language lessons
- Slow: Needs LLM inference (seconds to minutes)
- Risky: Hallucination/drift possible

**Example (Phase 5+)**:
```python
async def _reflect():
    runs = read_recent_runs(12)
    digest = "\n".join(
        f"- {r['action']}: ok={r['ok']} {r['detail']}" 
        for r in runs
    )
    
    lesson = await free_ai.chat(
        "Find 1 concrete lesson from recent runs. Max 2 sentences.",
        [{"role": "user", "content": digest}]
    )
    
    skill_library.record_lesson("self_improve", lesson)
    return lesson
```

**When to use**:
- Complex patterns (hard to codify)
- Infrequent decisions (LLM latency acceptable)
- Low-stakes choices (hallucination tolerable)
- Learning critical (patterns change over time)

**Pitfalls**:
- Hallucination: LLM makes up "lessons"
- Drift: Lessons change meaning over time
- Slow: Can't react to urgent failures fast
- Cost: LLM calls add up

---

## Pattern 3: Outcome Weighting (Valuation Layer)

**Purpose**: Combine multiple metrics into single comparable score.

**Structure**:
```
Metric 1: lead_quality ─┐
Metric 2: revenue      ├→ Weighted Sum → Outcome Score (0-1)
Metric 3: cost         ─┤
Metric N: ...          ─┘
```

**Formula** (general):
```
score = ∑(weight_i × metric_i) / ∑(weight_i)

Clamped to [0, 1] for comparability.
```

**Example (Phase 7)**:
```python
WEIGHTS = {
    "lead_quality": 0.40,      # importance
    "revenue": 0.40,
    "cost": -0.20,             # negative = penalty
}

def compute_outcome_value(metrics):
    lead_quality = metrics["avg_lead_score"]  # 0-1
    revenue = metrics["revenue"] / 1000       # normalize
    cost = metrics["cost"] / 10                # normalize
    
    score = (
        0.40 * lead_quality +
        0.40 * revenue +
        (-0.20) * cost
    )
    return clamp(score, 0, 1)
```

**Characteristics**:
- Deterministic: Same inputs → same score
- Comparable: Enables ranking (best vs worst)
- Interpretable: Weights show priority
- Tunable: Adjust weights to fit values

**When to use**:
- Multi-criteria decisions
- Need to rank alternatives
- Want transparency (not black-box ML)
- Weights stable (don't change often)

**Pitfalls**:
- Weight choice arbitrary ("why 0.40 not 0.35?")
- Non-linear metrics forced into linear formula
- Ignores correlations between metrics
- Doesn't capture urgency/context

---

## Pattern 4: Hybrid: Gates + Reflexion (Combined)

**Purpose**: Fast + adaptive = logic-driven base layer + learning overlay.

**Structure**:
```
Decision Point
    ↓
[Deterministic Gates] ← FAST, TRANSPARENT
    ↓ (if pass)
[Execution]
    ↓
[Record Outcome + Cost]
    ↓
[LLM Reflection] ← PERIODIC, ADAPTIVE
    ↓
[Update Skill Library]
    ↓
[Next iteration uses lessons in prompts]
```

**Benefits**:
- Fast: Gates don't call LLM
- Safe: Gates prevent obvious mistakes
- Learning: Reflection finds patterns
- Adaptive: Future decisions use lessons

**Example (Phase 7 self-improve)**:
```python
async def run_once():
    # Pick task
    picked = await _pick_next()
    action = picked["action"]
    
    # Fast deterministic gates
    skip, reason = should_skip_task(action, cost_remaining)
    if skip:
        return {"skipped": reason}  # instant, no LLM
    
    # Execute
    result = await _execute(action)
    cost, outcome_value = record_outcome(result)
    
    # Periodic LLM reflection (every 8 runs)
    if total % 8 == 0:
        await _reflect()  # LLM extracts lessons
    
    return {"action": action, "cost": cost, "value": outcome_value}
```

**Order matters**:
1. Gates first (fast, prevent obvious mistakes)
2. Execute (do work)
3. Record (capture data)
4. Reflect (periodic LLM learning)

**Don't reverse**: Never do expensive LLM in gate (defeats purpose).

---

## Pattern 5: Epsilon-Greedy Bandit (Exploration-Exploitation)

**Purpose**: Balance trying new things (explore) vs using best-known (exploit).

**Formula**:
```
if random() < epsilon:
    pick = random_action()   # Explore (try new)
else:
    pick = best_action()     # Exploit (use known best)
```

**Typical epsilon**: 0.3 (30% explore, 70% exploit)

**Why it matters**:
- Pure exploit → stuck at local optimum
- Pure explore → wasteful randomness
- Epsilon-greedy → good balance

**Combines with gates**:
```python
# Pick: epsilon-greedy (may pick any action)
picked = pick_epsilon_greedy(actions, epsilon=0.3)

# Gate: deterministic (may reject picked)
skip, reason = should_skip_task(picked, cost_remaining)
if skip:
    # Try next best instead
    return continue_to_next_iteration

# Execute if passed gates
result = await execute(picked)
```

**Lesson**: Gates don't remove exploration, just redirect it.

---

## Pattern 6: Cost-Aligned Optimization

**Purpose**: Prioritize actions by ROI, not just success rate.

**Simple version (unaligned)**:
```python
best_action = max(actions, key=lambda a: success_rate[a])
# Picks highest success, ignores cost
```

**Aligned version (Phase 7)**:
```python
best_action = max(
    actions, 
    key=lambda a: (
        success_rate[a] * 
        (1.0 - cost_penalty[a])  # reduce score if expensive
    )
)
# Picks high-success AND cheap
```

**Cost penalty formula**:
```python
if cost > remaining_budget:
    penalty = 0.5  # strong: 50% score reduction
elif cost > $5:
    penalty = 0.2  # mild: 20% score reduction
else:
    penalty = 0.0  # free: no reduction
```

**Result**: Cheap high-success naturally prioritized.

**Example**:
```
Action 1: success=0.90, cost=$1    → score = 0.90 * (1.0 - 0.0) = 0.90 ✅
Action 2: success=0.85, cost=$10   → score = 0.85 * (1.0 - 0.5) = 0.425 ⚠️
Action 3: success=0.80, cost=$0.50 → score = 0.80 * (1.0 - 0.0) = 0.80

Best: Action 1 (cheap + high success)
Worst: Action 2 (expensive + medium success)
```

---

## Anti-Patterns: What NOT to Do

### Anti-Pattern 1: Pure LLM Decision-Making (no gates)
```python
# ❌ Bad: Single LLM call for all logic
async def decide(action):
    decision = await llm.chat(
        f"Should we run {action}? Consider all factors. Yes or no?"
    )
    return decision.lower().startswith("y")
```
**Problem**: Slow, hallucination-prone, non-transparent, expensive.

**Fix**: Use gates first, LLM for learning.

---

### Anti-Pattern 2: Hardcoded Thresholds Everywhere
```python
# ❌ Bad: Magic numbers scattered
if cost > 4.7 and success < 0.615:  # where do 4.7, 0.615 come from?
    skip()
```
**Problem**: Unmaintainable, hard to tune, unexplained.

**Fix**: Named constants, document reasoning.

```python
# ✅ Good:
MIN_SUCCESS_FOR_EXPENSIVE = 0.60
MAX_COST_RISK = 5.00
if cost > MAX_COST_RISK and success < MIN_SUCCESS_FOR_EXPENSIVE:
    skip()
```

---

### Anti-Pattern 3: Learning Without Acting
```python
# ❌ Bad: Reflect but never change decisions
lessons = await llm.reflect(runs)
skill_library.record(lessons)
# ... next run still uses old logic
```
**Problem**: Learning is useless if not acted on.

**Fix**: Reflection → lesson → condition future prompts/picking.

---

### Anti-Pattern 4: Gates Too Strict
```python
# ❌ Bad: Gates block everything
if cost > $0:          # only free actions
    skip()
if success_rate < 1.0: # only perfect actions
    skip()
if not in_happy_hour:  # only Tuesday 3pm
    skip()
```
**Problem**: Loop never runs.

**Fix**: Gates should protect, not paralyze. Allow risky if potential high.

---

## Tuning Strategy

### Phase 1: Loose Gates
Start permissive. Let loop run and gather data.
```python
GATES = {
    "budget": True,             # always respect budget
    "expensive_risky": False,   # disabled — explore
    "low_roi": False,
}
```

### Phase 2: Gather Metrics
Watch outcome values, cost distribution:
```
Cost: [$0.50-$10] per run
Outcome value: [0.10-0.95], median=0.55
Best actions: harvest_leads ($0.50, v=0.85)
Worst actions: seo_pages ($5, v=0.15)
```

### Phase 3: Tighten Gates
Enable gates based on observed cost-ROI curve.
```python
# Data shows: cost>$5 + success<0.60 = always v<0.3
GATES["expensive_risky"] = True

# Data shows: neutral outcome + cost=$3 = 80% fail next
GATES["low_roi"] = True
```

### Phase 4: Tune Thresholds
Adjust weights + cutoffs based on monthly review:
```python
# Was rejecting too many: success threshold 0.60 → 0.50
MIN_SUCCESS_FOR_EXPENSIVE = 0.50

# Cost sensitivity high: increase outcome weight on revenue
OUTCOME_WEIGHTS["revenue"] = 0.50  # was 0.40
```

---

## Summary: When to Use Each Pattern

| Pattern | Speed | Transparent | Adaptive | Use When |
|---------|-------|-------------|----------|----------|
| Deterministic Gates | ⚡⚡⚡ | ✅ | ❌ | Frequent decisions, simple rules |
| LLM Reflection | 🐌 | ❌ | ✅ | Infrequent, complex patterns |
| Outcome Weighting | ⚡ | ✅ | ❌ | Multi-metric ranking |
| Hybrid Gates+Reflection | ⚡ + 🐌 | ✅ | ✅ | Best of both (recommended) |
| Epsilon-Greedy | ⚡ | ✅ | ~~ | Exploration needed |
| Cost-Aligned Picking | ⚡ | ✅ | ❌ | Budget-aware tasks |

---

## References

- Phase 7 Implementation: `docs/PHASE7_DETERMINISTIC_LOOPS.md`
- Self-Improve Loop: `app/agents/self_improve.py`
- Bandit algorithms: Sutton & Barto "Reinforcement Learning" Ch.2
- Cost-aware ML: "Cost-Sensitive Learning" (domain adaptation)
