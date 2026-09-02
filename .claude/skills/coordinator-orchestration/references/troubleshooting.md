> Verbatim troubleshooting guide for coordinator-orchestration. See SKILL.md for the core workflow.

## Troubleshooting

### Problem: Output Incoherent / Doesn't Match Goal

**Cause**: Goal too vague. Agents improvise wildly.

**Fix**:
```bash
# Bad goal
"Marketing stuff"

# Good goal
"5-email cold sequence for solar leads in Pune: Day 1 education, Day 3 case study, Day 7 urgency"
```

**Also try**: Advanced mode to let reflection tighten it up.

```bash
curl ... -d '{
  "goal": "5-email cold sequence for solar...",
  "mode": "advanced",
  "max_iterations": 2
}'
```

### Problem: Agent Picked Wrong Agent for Task

**Cause**: Goal is ambiguous; LLM-planner misclassified.

**Fix**: Be explicit about roles.

```bash
# Ambiguous
"Improve outreach"

# Explicit (now Dev+Rohan know their roles)
"Research solar market trends (Dev) + draft cold emails (Rohan)"
```

### Problem: Sequential Too Slow, Parallel Output Conflicts

**Cause**: Agents made different assumptions.

**Fix**: Try hierarchical mode with sub-teams.

```bash
curl ... -d '{
  "goal": "...",
  "mode": "hierarchical"
}'
```

Or provide explicit context in goal:

```bash
curl ... -d '{
  "goal": "Market research: compare Pune (Dev) vs Mumbai (Isha) vs Bangalore (Kavya) using SAME metrics (market size, lead quality, subsidy status)",
  "mode": "parallel"
}'
```

### Problem: Quality Score Low, Reflection Doesn't Improve

**Cause**: Goal itself unrealistic or critic too strict.

**Fix**: Raise quality_bar slightly or reduce iterations.

```bash
# Critic too strict (0.9 bar = perfection)
curl ... -d '{
  "goal": "...",
  "quality_bar": 0.7
}'

# vs. realistic (0.7 bar = good enough)
curl ... -d '{
  "goal": "...",
  "quality_bar": 0.7
}'
```

### Problem: "Error: dependency missing"

**Cause**: Agent tried to call tool but code path broken.

**Fix**: Retry with `execute=false` (draft mode). If still broken, check logs.

```bash
curl ... -d '{"goal": "...", "execute": false}'
```

If draft works but execute fails: report as bug in issue tracker.

