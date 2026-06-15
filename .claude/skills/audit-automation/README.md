# Skill: audit-automation — Phase 5 Automation Auditing

**Part of Phase 5**: Make automation loops auditable + extensible without reading code.

## What's Included

This skill package contains **3 components** for auditing the self-improve loop:

### 1. SKILL.md (250 lines)
Main skill guide. Covers:
- When to run (daily, weekly, monthly)
- 6-step health check (loop alive, budget, approvals, anomalies, next action, compliance)
- Output format (human-readable + JSON)
- Escalation checklist (what to do if red/yellow)
- Daily standup script example
- Common issues & fixes

**Read this first** if you want to understand automation health.

### 2. references/automation-checklist.md (180 lines)
Quick checklists for standup, weekly review, and monthly deep-dive.

- Daily (5 min): Loop alive? Budget ok? No high-error tasks?
- Weekly (15 min): Success rates stable? Lessons quality good? Compliance ok?
- Monthly (1 hour): Full audit + trends + recommendations
- Template for monthly report summary

**Use this daily** before standups.

### 3. scripts/automation_health_audit.py (350 lines)
CLI tool that runs all the checks.

**Usage**:
```bash
# Daily standup (5 min)
python scripts/automation_health_audit.py --daily-check

# Weekly review (15 min)
python scripts/automation_health_audit.py --weekly-audit

# When something's wrong
python scripts/automation_health_audit.py --anomalies
python scripts/automation_health_audit.py --approvals-pending
python scripts/automation_health_audit.py --dlq-status
python scripts/automation_health_audit.py --compliance-check

# Machine-readable output
python scripts/automation_health_audit.py --daily-check --format=json
```

**Output**: Human-readable console (default) or JSON for dashboards.

## The 6-Step Health Check

1. **Loop Alive?** (Heartbeat age)
   - ✅ <10m: Healthy
   - 🟡 10-30m: Slow (check LLM providers)
   - 🔴 >30m: Stuck (restart service)

2. **Budget** (Daily spend vs. cap)
   - ✅ <40%: Normal velocity
   - 🟡 40-80%: Approaching limit
   - 🔴 >80%: Exhausted, loop paused

3. **Approvals** (Queue status, if enabled)
   - ✅ ≤2 pending: Flowing smoothly
   - 🟡 3-5 pending: Backlog building
   - 🔴 >5 pending: Blocked

4. **Anomalies** (Task errors, low success rates)
   - ✅ All actions >70%, DLQ clean
   - 🟡 1-2 low actions (monitor)
   - 🔴 Multiple failures or DLQ >10

5. **Next Action** (What's running + what's queued)
   - ✅ Running + queue visible
   - 🟡 Queue backing up (5+ items)
   - 🔴 Task stuck >240s

6. **Compliance** (DLT, opt-out, retention, approvals)
   - ✅ All checks green
   - 🟡 DLT pending, opt-outs stale
   - 🔴 No DLT, ignoring opt-outs

## Quick Reference: When to Escalate

| Condition | Severity | Action |
|-----------|----------|--------|
| Heartbeat >30 min | 🔴 Critical | Restart service immediately |
| Budget >80% | 🔴 Critical | Pause loop, investigate spike |
| DLQ >10 | 🟡 High | Inspect errors, retry or remove |
| Success rate <50% | 🟡 High | Disable action, review logs |
| Compliance gap | 🔴 Critical | Fix immediately, block automation |
| Approval backlog >5 | 🟡 High | Assign approvers or reduce scope |

## Integration with Dashboards

- **Slack**: Watchdog job sends red checks to Slack
- **Grafana**: Metrics exported to Prometheus (if observability enabled)
- **API**: `GET /api/growth/infra/automation-health` for custom dashboards
- **Email**: Daily digest includes automation health score

## Testing the Audit Script

**Basic test** (no Docker needed):
```bash
cd C:\Users\Ratanshila\Documents\leadgenrationaiagent

# Test imports
python -c "from scripts.automation_health_audit import *; print('✅ Imports OK')"

# Test daily check (creates dummy JSON, returns gracefully)
python scripts/automation_health_audit.py --daily-check
# Expected: 6-section output (Loop Alive, Budget, Approvals, Anomalies, Next Action, Compliance)

# Test JSON output
python scripts/automation_health_audit.py --daily-check --format=json
# Expected: Valid JSON with checks object

# Test anomalies check
python scripts/automation_health_audit.py --anomalies
# Expected: Returns status (even if no data)
```

**Expected behavior**:
- All commands run without crashing
- Missing data files → graceful defaults
- Missing imports (automation_health) → fail-open
- JSON output is valid and parseable
- Human output has 6 sections with status icons

## Companion Skill: teach-agent-loop

This audit skill focuses on **monitoring** existing loops.

For **extending** the loop (adding new actions/agents), see:
- `.claude/skills/teach-agent-loop/SKILL.md` — 6-step guide to add new actions
- `.claude/skills/teach-agent-loop/references/agent-extension-guide.md` — Deep dive

## Files in This Package

```
.claude/skills/audit-automation/
├── SKILL.md                                  (250 lines, main guide)
├── references/
│   └── automation-checklist.md              (180 lines, quick checklists)
└── README.md                                (this file)

scripts/
└── automation_health_audit.py               (350 lines, CLI tool)
```

## How It Fits Into Phase 5

**Phase 5 Goal**: Make automation loops **auditable** + **extensible** without reading code.

- **Auditable** ← This skill (audit-automation)
  - See loop health without code
  - Daily standup + weekly review
  - Escalation checklist for problems
  
- **Extensible** ← Companion skill (teach-agent-loop)
  - Add new actions/agents in 6 steps
  - Testing checklist + safety gates
  - Examples + patterns

## See Also

- `docs/AUTOMATION.md` — 3-loop architecture (self-improve, coordinator, process-engine)
- `app/platform/automation_health.py` — Heartbeat mechanism (source)
- `app/agents/self_improve.py` — Task picking + cost tracking (source)
- `scripts/` — Other automation scripts (DLQ retry, skill audits, etc.)
