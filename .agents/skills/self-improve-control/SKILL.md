---
name: self-improve-control
description: Monitor, audit, aur safely control the self-improve forever-loop — health/heartbeat, cost, approvals, lessons, pause/resume, eval_gate regression signal. Use when the user says "self-improve loop healthy?", "loop ne kya seekha", "loop ko pause/resume karo", "loop ne expensive task pick kiya", "selfimprove cost/approvals", "loop govern/audit karo", or for governance/incident on the automation loop.
---

# Self-Improve Loop Control

Monitor, audit, and safely control the automation self-improvement loop (`app/agents/self_improve.py`). Source-of-truth details: `self-improve-loop` skill (architecture) — yeh skill OPERATE/audit/govern pe focus karti hai.

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

> **Cost = NOTIONAL**: stack 100% free (Cerebras/Groq/Gemini free tiers). `$` figures = CostTracker ka internal estimate (LLM-heavy ≈ $2.5, light ≈ $0.5) jo budget/ROI gates drive karta — real paisa nahi katta. `SELFIMPROVE_COST_CAP` (default $50/day) = velocity throttle.

**What to look for**:
- Is the (notional) cost reasonable? cap ≈ $50/day, har run $0.5–$2.5
- Is the outcome linked to the task? (e.g., "scrape → leads" makes sense; "scrape → dunning" would be weird)
- Is the lesson credible? (does the reflected insight match the data?)

### 2. Inspect Deeper: Lessons + Skill Library

> **Store-naming note (important)**: LIVE loop ke REAL files = `data/skill_lessons.jsonl` (reflections/lessons), `data/skill_uses.jsonl` (per-action use+outcome), `data/self_improve_runs.jsonl` (run log w/ cost+outcome_value). The `selfimprove_audit.py` tool ka older view `agent_memory.jsonl`/`skill_library.jsonl`/`automation_audit.jsonl` expect karta hai (jab tak script align na ho, woh empty dikha sakta) — manual inspection ke liye REAL files neeche use karo.

**Goal**: See what the loop has learned cumulatively.

View the lessons (free-LLM reflections):
```bash
cat data/skill_lessons.jsonl | tail -5 | jq .
```

The audit tool's view (may differ until script aligned to live stores):
```bash
python scripts/selfimprove_audit.py --memory-audit
```

Lesson record shape (live, from `skill_library.record_lesson`):
```json
{
  "topic": "self_improve",
  "lesson": "email_outreach hot_leads (score >0.7) pe better — pehle qualify karo.",
  "source": "reflection",
  "agent": "meera",
  "at": "2026-06-15T09:20:30+00:00"
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

**To pause** (VPS = Docker; systemd `leadgen` DISABLED, recreate karo NOT systemctl):
```bash
# .env me flag set (VPS /opt/leadgen/.env)
echo "SELF_IMPROVE_LOOP=0" >> /opt/leadgen/.env
# loop Celery worker me chalta — worker (+scheduler) recreate karo
docker compose -f docker-compose.vps.yml up -d --no-deps worker scheduler
```

The loop will **not** pick a new task. Existing running tasks finish.

**To resume**:
```bash
sed -i '/SELF_IMPROVE_LOOP=/d' /opt/leadgen/.env
echo "SELF_IMPROVE_LOOP=1" >> /opt/leadgen/.env
docker compose -f docker-compose.vps.yml up -d --no-deps worker scheduler
```

**When to pause**:
- Loop cost exceeded budget
- Loop picked a task you don't trust (e.g., auto-calling without DLT approval)
- Outcome is degrading (e.g., lead quality dropped 20%)

### 4. Inject Manual Guidance (Advanced)

**Goal**: Tell the loop what to do next, overriding its bandit choice.

If the loop made a bad pick, queue a preferred task — loop ise auto-pick se PEHLE uthata hai (no `/hint` route exists; this IS the guidance path):
```bash
curl -X POST http://localhost:8000/api/growth/selfimprove/task \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "task": "hot_leads accumulated, prioritize deep-dive",
    "action": "sales_deepdive"
  }'
```

`action` must be a valid ACTIONS key (sales_deepdive, harvest_leads, seo_pages, etc. — see `GET /selfimprove/actions`). On the **next cycle** (gap ≈180s), the loop pops this queued task first. Doesn't bypass guards; queued task abhi bhi cost/approval gates se guzarta hai.

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

### 6. eval_gate — Close-the-Loop Regression Signal (F.3)

**Goal**: Catch when an action's quality silently drifts down.

Har iteration ke baad loop `eval_gate.score_and_gate("self_improve", <action>, current_score=1.0|0.0)` call karta hai. eval_gate har action ka **rolling median baseline** rakhta hai; agar aaj ka score baseline se neeche gira (e.g. `harvest_leads` last-20 runs me 0.9 tha, aaj 0.3) to decision = **reject** → run record me `regression: true` + `baseline` likha jaata hai.

- **INERT by default**: `EVAL_GATE` unset = sirf no-op (project ethos: gated, fail-open). Set `EVAL_GATE=1` to start recording baselines (observe-only).
- `EVAL_GATE_HARD=1` (sirf baseline trusted hone ke baad) = regression `detail` me `[REGRESSION baseline=X.XX]` mark dikhta hai. **Auto-rollback NAHI** — successful-but-low-baseline action bhi useful hai; yeh drift FLAG karta hai, kaam block nahi.
- Bursts of rejects → `OPS_ALERTS` ntfy page kar sakta hai (`OPS_ALERT_EVAL_REJECT_BURST`/`_WINDOW`).

**Where to look**: `data/self_improve_runs.jsonl` me `regression`/`baseline` fields; eval_gate ka apna store (`app/agents/eval_gate.py`). Source-of-loop-truth: `self-improve-loop` skill.

---

## Safety Checklist

Before running the loop unsupervised, check:

- [ ] **Cost budget**: Is `SELFIMPROVE_COST_CAP` set? (default: $50/day)
- [ ] **Approval mode**: Is `SELF_IMPROVE_APPROVAL` set? (OFF = no human gate; ON = requires admin approval)
- [ ] **Skill library**: Are all ACTIONS (in `self_improve.py` ACTIONS dict) ones you trust? (success rates: `data/skill_uses.jsonl` via `GET /skills/library`)
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
- Check success rates: `GET /api/growth/skills/library` (or `selfimprove_audit.py --skill-stats`). Note: loop me already 2-tier diversity guard hai (last-6 dedup + 20-min cooldown).
- If one task has high success + others low, epsilon-greedy bandit correctly favors it (30% explore still rotates)
- To diversify: queue a different action via `POST /selfimprove/task {task, action}`
- Or down-weight: `data/skill_uses.jsonl` me us action ke recent `ok:true` rows kam karo (Laplace rate recompute hoga)

**"Reflection logic is wrong (lesson doesn't match data)"**
- This is a free-LLM hallucination (rare but possible)
- Check the lesson + recent runs: `tail data/skill_lessons.jsonl` + `tail data/self_improve_runs.jsonl`
- If obviously wrong, delete that lesson line: `jq -c 'select(.lesson != "bad lesson text")' data/skill_lessons.jsonl > tmp && mv tmp data/skill_lessons.jsonl`
- Loop will re-learn on next reflection (har 8 runs)

**"Can I manually add a skill/task to the loop?"**
- New ACTION = code change: `self_improve.py` ACTIONS dict + `_execute()` elif + `_STAGE_ACTIONS` (step-by-step → `teach-agent-loop` skill)
- Project skill (knowledge, not action) = `POST /api/growth/skills/pack/author` (skill_pack store; `study_skills` action ise padhta)
- Manual lesson inject: `POST /api/growth/skills/lesson {topic, lesson}`

---

## Enterprise gate

- **Operating loop**: Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). Architecture source-of-truth = `self-improve-loop`; yeh skill OPERATE/govern hai.
- **Risk-tier: High** (live-VPS runtime control). Pause/resume/cap-change = production `.env` mutation + worker recreate = blast-radius poora automation. Isliye `careful`-mode mindset: change se pehle current state read (`GET /selfimprove/status` + cost-status), `.env` backup, **explicit user-auth** for any live-VPS write (infer mat karo).
- **Compliance (fail-CLOSED)** — step-6 health-check ka governance angle: loop KABHI call/SMS auto-send na kare bina DLT + opt-in; hallucinated DND-bypass lesson (`"ignore DND-listed"`) = turant delete + loop audit. Recording-retention + DPDP purge active rakho.
- **Rollback (NAMED)**: pause = `SELF_IMPROVE_LOOP=0` + `docker compose -f docker-compose.vps.yml up -d --no-deps worker scheduler` (already documented above) · bad lesson = jq-filter out of `data/skill_lessons.jsonl` · cost runaway = `SELFIMPROVE_COST_CAP=<lower>` + recreate.
- **Evidence (govern action done)**: `GET /selfimprove/status` (loop ticking / paused as intended) + `docker exec leadgen_app printenv SELF_IMPROVE_LOOP` (flag value confirm) + `data/self_improve_runs.jsonl` next-tick row reflects the change (regression/cost/approval as expected).

## Related

- `docs/AUTOMATION.md` — Self-improve pattern overview
- `references/self-improve-safety.md` — Risk matrix (which tasks are auto-safe)
- `scripts/selfimprove_audit.py` — Inspection tool (used in this skill)
- `.claude/skills/orchestrate-goal/` — When to use coordinator vs. self-improve
