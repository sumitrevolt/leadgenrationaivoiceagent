# Self-Improve Loop Control

Monitor, audit, and safely control the automation self-improvement loop.

## When to Use This Skill

- **Morning standup**: "Is the self-improve loop healthy? What did it learn yesterday?"
- **Incident**: "The loop picked an expensive task. Why? Can I pause it?"
- **Onboarding**: "How does the self-improve loop actually work?"
- **Governance**: "What approvals happened? What was the cost?"

## Problem This Solves

The self-improve loop (`agents/self_improve.py`) runs unattended, picking tasks daily and learning from outcomes. But it's a **black box** — you can't see why a task was chosen, what it cost, or whether it's making good decisions.

This skill pulls back the curtain: it teaches you to **read** the loop's decisions, **understand** its safety, and **control** it when needed.

## Prerequisites

- Access to the app's data/ directory and API keys (you have these)
- Basic understanding of skill_library and growth_ideas (see references/)
- Comfort reading JSON audit logs

## Steps

### 1. Check Loop Health (30 seconds)

**Goal**: Understand what the loop chose yesterday, and why.

Run the audit script:
```bash
python scripts/selfimprove_audit.py --last-run
```

This outputs:
```
LAST RUN: 2026-06-15 14:22 UTC
Task picked: prospector.scrape (niche rotation)
Reason: bandit score 0.78 (Kolhapur×solar highest-Q leads)
Cost: $2.31 (Groq STT + free-LLM classify)
Outcome: 18 new prospects (14 email, 4 phone) — hot_lead_score avg 0.64
Lesson recorded: "solar×Kolhapur combines high-volume+high-quality; rotate here more"
Status: SUCCESS

Next task: (pending approval? if SELF_IMPROVE_APPROVAL=1)
```

**What to look for**:
- Is the cost reasonable? (typically ≤$5/day)
- Is the outcome linked to the task? (e.g., "scrape → leads" makes sense; "scrape → dunning" would be weird)
- Is the lesson credible? (does the reflected insight match the data?)

### 2. Inspect Deeper: Lessons + Skill Library

**Goal**: See what the loop has learned cumulatively.

View the episodic memory:
```bash
cat data/agent_memory.jsonl | tail -5 | jq .
```

This shows the **last 5 reflections** the loop made. Example:
```json
{
  "run_id": "2026-06-15_092030",
  "lesson": "email_outreach works better on hot_leads (score >0.7) than cold. consider qualifying first.",
  "evidence": ["jun-12: 0/8 cold emails → 1 reply", "jun-13: 4/5 hot leads → 3 replies"],
  "confidence": 0.82,
  "action_next": "reduce_cold_email_fraction"
}
```

Check the skill library (what tasks does the loop know about, and their success rates?):
```bash
python scripts/selfimprove_audit.py --skill-stats
```

Output:
```
Task Success Rates (last 30 days)
---
prospector.scrape              0.85 (18/21 runs, $68 total spend)
cadence.run_due                0.92 (12/13 runs, $12)
email_outreach.run_auto        0.68 (17/25 runs, $156)  ⚠️ HIGH SPEND, OK OUTCOME
call_manager.handle_callbacks  1.00 (4/4 runs, $0)
sales_team.run_analysis        0.78 (7/9 runs, $71)
---
```

**What to look for**:
- Tasks with high spend ($) + low success (<60%) = candidates to pause
- Tasks with high success + low spend = candidates to run more
- Anomalies: did a task suddenly drop in success? (May indicate data quality issue or drift)

### 3. Pause / Resume (if Needed)

**Goal**: Stop the loop temporarily if something looks wrong.

**To pause**:
```bash
# Set environment variable
echo "SELF_IMPROVE_LOOP=0" >> .env
# Restart app
systemctl restart leadgen
```

The loop will **not** pick a new task. Existing running tasks finish.

**To resume**:
```bash
# Remove or set to 1
sed -i '/SELF_IMPROVE_LOOP=/d' .env
echo "SELF_IMPROVE_LOOP=1" >> .env
systemctl restart leadgen
```

**When to pause**:
- Loop cost exceeded budget
- Loop picked a task you don't trust (e.g., auto-calling without DLT approval)
- Outcome is degrading (e.g., lead quality dropped 20%)

### 4. Inject Manual Guidance (Advanced)

**Goal**: Tell the loop what to do next, overriding its bandit choice.

If the loop made a bad pick, you can suggest a better task:
```bash
curl -X POST http://localhost:8000/api/growth/selfimprove/hint \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "preferred_action": "sales_team.run_analysis",
    "reason": "hot_leads accumulated, prioritize deep-dive"
  }'
```

On the **next cycle** (180s later), the loop respects this hint in its Reflexion pass. Doesn't bypass the loop; guides it.

**When to use**:
- You spotted an opportunity the bandit missed (e.g., "we have 50 hot leads, run sales_team analysis")
- You want to test a hypothesis (e.g., "run this 3 days in a row, measure outcome")

### 5. Read the Audit Trail (Compliance)

**Goal**: Answer "What did the automation loop do, when, and why?"

View the full audit log:
```bash
cat data/automation_audit.jsonl | jq '.[] | {timestamp, task, cost, approval, outcome}'
```

Example (with SELF_IMPROVE_APPROVAL=1):
```json
{"timestamp": "2026-06-15T14:22Z", "task": "prospector.scrape", "cost": 2.31, "approval": "auto", "status": "executed", "outcome": "18 leads"}
{"timestamp": "2026-06-16T09:15Z", "task": "sales_team.run_analysis", "cost": 5.20, "approval": "pending", "status": "waiting", "approved_by": null}
{"timestamp": "2026-06-16T10:30Z", "task": "sales_team.run_analysis", "cost": 5.20, "approval": "admin:sumit", "status": "executed", "outcome": "4 hot leads qualified"}
```

Use this for:
- **Audits** (compliance / cost tracking)
- **Debugging** (was this task actually run?)
- **Tuning** (measure cost vs. outcome per task type)

---

## Safety Checklist

Before running the loop unsupervised, check:

- [ ] **Cost budget**: Is `SELFIMPROVE_COST_CAP` set? (default: $50/day)
- [ ] **Approval mode**: Is `SELF_IMPROVE_APPROVAL` set? (OFF = no human gate; ON = requires admin approval)
- [ ] **Skill library**: Are all actions in `skill_library.jsonl` ones you trust?
- [ ] **DLT / compliance**: Does the loop ever make calls/SMS? (If yes, must have DLT approval + opt-in tracking)
- [ ] **Monitor daily**: Are you checking the audit log at least weekly?

See references/self-improve-safety.md for risk matrix.

---

## Troubleshooting

**"Loop picked an expensive task and cost me $50 in one run"**
- Set `SELFIMPROVE_COST_CAP=10` (or your budget)
- Loop will skip tasks that exceed the cap
- Existing large-spend tasks will be deprioritized by bandit

**"Loop seems stuck (same task every day)"**
- Check skill_library success rates: `python scripts/selfimprove_audit.py --skill-stats`
- If one task has 100% success + others <50%, bandit correctly favors it
- To diversify: manually inject a hint (`preferred_action=different_task`)
- Or reduce that task's weight: `data/skill_library.jsonl` edit success_rate down (reset after N runs)

**"Reflection logic is wrong (lesson doesn't match data)"**
- This is a free-LLM hallucination (rare but possible)
- Check evidence in `data/agent_memory.jsonl`
- If obviously wrong, delete that lesson: `jq 'select(.run_id != "bad_id")' data/agent_memory.jsonl > tmp && mv tmp data/agent_memory.jsonl`
- Loop will re-learn on next run

**"Can I manually add a skill/task to the loop?"**
- Yes: add to `skill_library.jsonl` manually (copy an existing entry, change task name + metadata)
- Or use the `/api/growth/skills/pack` endpoint to register a new one
- See `.claude/skills/teach-agent-loop/SKILL.md` for step-by-step

---

## Related

- `docs/AUTOMATION.md` — Self-improve pattern overview
- `references/self-improve-safety.md` — Risk matrix (which tasks are auto-safe)
- `scripts/selfimprove_audit.py` — Inspection tool (used in this skill)
- `.claude/skills/orchestrate-goal/` — When to use coordinator vs. self-improve
