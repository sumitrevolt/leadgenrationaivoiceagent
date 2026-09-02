# Phase 5: Automation Loop Auditing & Extension — Skills Summary

**Goal**: Make automation loops **auditable** + **extensible** without reading code.

**Deliverables**: 2 skills + 1 CLI tool, totaling ~1,400 lines of documentation.

---

## Skill 1: audit-automation (250 + 180 lines docs + 350 lines code)

**Purpose**: Daily/weekly/monthly health checks for self-improve loop.

**Includes**:
1. `SKILL.md` (250 lines)
   - When to run (daily, weekly, monthly)
   - 6-step health check (loop alive → budget → approvals → anomalies → next action → compliance)
   - Output format (human + JSON)
   - Escalation checklist
   - Daily standup script

2. `references/automation-checklist.md` (180 lines)
   - Daily 5-min checklist
   - Weekly 15-min checklist
   - Monthly 1-hour audit template
   - Compliance weekly checks
   - Quick reference escalation table

3. `scripts/automation_health_audit.py` (350 lines)
   - CLI tool
   - Flags: `--daily-check`, `--weekly-audit`, `--monthly-report`, `--anomalies`, `--approvals-pending`, `--dlq-status`, `--llm-status`, `--compliance-check`
   - Output: Human-readable console or JSON
   - Functions: `check_alive()`, `check_budget()`, `check_anomalies()`, etc.

**How to Use**:
```bash
# Daily standup (5 min)
python scripts/automation_health_audit.py --daily-check

# Weekly review (15 min)
python scripts/automation_health_audit.py --weekly-audit

# Investigate issues
python scripts/automation_health_audit.py --anomalies
python scripts/automation_health_audit.py --approvals-pending
```

**Expected Output** (6 sections):
```
1. LOOP ALIVE ✅ (heartbeat <10 min old)
2. BUDGET ✅ (spent $12.34 / $50.00)
3. APPROVALS ✅ (0 pending)
4. ANOMALIES ✅ (DLQ clean)
5. NEXT ACTION (harvest_leads running)
6. COMPLIANCE ✅ (DLT enabled, opt-outs enforced)

VERDICT: ✅ All green — loop healthy
```

---

## Skill 2: teach-agent-loop (280 + 150 lines docs)

**Purpose**: Guide for adding new agents & actions to self-improve loop.

**Includes**:
1. `SKILL.md` (280 lines)
   - When to add new action or agent
   - **6 steps to add NEW ACTION** (15 min, fastest path)
     - Define → Write code → Register → Skill library → Test → Enable
   - **6 steps to add NEW AGENT** (90 min, longer path)
     - Define → Create code → Add to roster → Wire coordinator → Add to self-improve → Test
   - Worked example: "Add LinkedIn DM Outreach" (applied all 6 steps)
   - Risk assessment matrix (auto-safe vs. approval-required)
   - Testing checklist (5 scenarios: happy path, empty, LLM down, timeout, concurrent)
   - Safety gates (import-safe, fail-open, gated, bounded, logged, tested)

2. `references/agent-extension-guide.md` (150 lines)
   - Agent code template (minimal, copy-paste)
   - 5 integration points (self-improve, coordinator, scheduler, API, dashboard)
   - Staff roster structure (team.py)
   - Self-improve bandit mechanism
   - Coordinator modes (sequential, parallel, hierarchical)
   - Scheduler integration (cron patterns)
   - Event logging & dashboard
   - API endpoint patterns
   - Testing patterns (unit, integration, coordinator)
   - 4 code patterns (research, draft, score, execute)

**How to Use**:
```bash
# Adding a new action (e.g., "sms_campaign_draft"):
# 1. Read SKILL.md Step 1-6
# 2. Copy code from references/agent-extension-guide.md Pattern 2 (Draft)
# 3. Follow testing checklist
# 4. Run automation_health_audit.py --weekly-audit to verify

# Adding a new agent (e.g., "Priya — Competitive Research"):
# 1. Read SKILL.md full guide (90 min)
# 2. Use worked example (LinkedIn DM Outreach) as template
# 3. Test in coordinator mode first
# 4. Then wire into self-improve
```

---

## Summary Table

| Deliverable | Purpose | Size | How to Use |
|-------------|---------|------|-----------|
| **audit-automation/SKILL.md** | Daily health checks guide | 250 lines | Read once, reference daily |
| **automation-checklist.md** | Quick standup checklists | 180 lines | Copy to spreadsheet/todo app |
| **automation_health_audit.py** | CLI tool | 350 lines | Run before standup/deploy |
| **teach-agent-loop/SKILL.md** | Adding actions/agents guide | 280 lines | Read when building new feature |
| **agent-extension-guide.md** | Architecture + code patterns | 150 lines | Copy code, follow patterns |

**Total**: ~1,400 lines of documentation + production-ready CLI.

---

## The 6-Step Health Check (audit-automation)

### 1. Loop Alive? (Heartbeat)
```
✅ <10 min:   Healthy
🟡 10-30 min: Slow (check LLM)
🔴 >30 min:   Stuck (restart)
```

### 2. Budget (Daily spend)
```
✅ <40%:  Normal
🟡 40-80%: Monitor
🔴 >80%:  Paused
```

### 3. Approvals (Queue status)
```
✅ ≤2 pending:   Flowing
🟡 3-5 pending:  Backlog
🔴 >5 pending:   Blocked
```

### 4. Anomalies (Task errors)
```
✅ All >70% success, DLQ clean
🟡 1-2 low actions
🔴 Multiple failures, DLQ >10
```

### 5. Next Action (Running + queued)
```
✅ Running, queue <3
🟡 Queue 3-5
🔴 Queue >10 or stuck >240s
```

### 6. Compliance (DLT, opt-out, retention)
```
✅ DLT ON, opt-outs fresh, retention active
🟡 Gaps pending resolution
🔴 No DLT, ignoring opt-outs
```

---

## The 6 Steps to Add New Action (teach-agent-loop)

1. **Define** (1 min)
   - Name, cost (LLM-heavy?), risk (auto-safe/draft/approval)

2. **Write Code** (5 min)
   - New file `app/agents/your_agent.py`
   - Async function returning `{ok, detail, output}`

3. **Register in self_improve.py** (3 min)
   - Add to `ACTIONS` dict
   - Add to `_execute()` dispatcher
   - Add to `_STAGE_ACTIONS`

4. **Register in skill_library** (1 min)
   - Auto-learns on first run (no manual action)

5. **Test** (3 min)
   - Happy path, empty data, LLM down, timeout, concurrent (5 scenarios)

6. **Enable & Monitor** (2 min)
   - No flag for draft-only
   - Monitor via `automation_health_audit.py`

**Total**: 15 min for new action.

---

## The 6 Steps to Add New Agent (teach-agent-loop)

1. **Define** (5 min)
   - Name, role, 2–5 responsibilities

2. **Create Code** (20 min)
   - New file `app/agents/your_agent.py`
   - 2–5 async functions

3. **Add to Team Roster** (5 min)
   - Edit `app/platform/team.py`
   - Add to `STAFF` dict

4. **Wire into Coordinator** (10 min)
   - Edit `app/agents/coordinator.py`
   - Add to `AGENT_HANDLERS`

5. **Add to Self-Improve** (20 min)
   - Register new actions
   - Add to `_STAGE_ACTIONS`

6. **Test & Document** (30 min)
   - Coordinator test
   - Self-improve test
   - Dashboard verify

**Total**: 90 min for new agent.

---

## Integration Points (Where Agents Live)

```
Team Roster (team.py)
    ↓
Self-Improve Loop ← Picks actions daily (self_improve.py)
    ↓
Scheduler/Celery ← Recurring tasks (team_scheduler.py)
    ↓
Coordinator ← Multi-agent orchestration (coordinator.py)
    ↓
API Endpoints ← Manual triggers (growth.py)
    ↓
Dashboard ← See activity (team.py)
```

Your action/agent should connect to **at least 1–2** of these.

---

## Testing Checklist (5 Scenarios)

All new actions must pass:

1. ✅ **Happy path**: Valid input → ok=True, output
2. ✅ **Empty data**: No data → ok=False (graceful)
3. ✅ **LLM down**: Provider fails → fallback (no crash)
4. ✅ **Timeout**: >240s → cancelled, not blocking
5. ✅ **Concurrent**: 2 workers → no race conditions

---

## Safety Gates (Before Prod)

```
[ ] 1. Import-safe (no side effects)
[ ] 2. Fail-open (returns {ok: false} not raise)
[ ] 3. Gated (env flag if sensitive)
[ ] 4. Bounded (cost cap + timeout)
[ ] 5. Logged (skill_library tracks)
[ ] 6. Tested (5 scenarios pass)
```

---

## Risk Assessment

| Action | Risk | Example | Mitigation |
|--------|------|---------|-----------|
| Read-only | 🟢 Low | scrape_leads | OSM+Places only |
| Draft | 🟢 Low | social_drafts | Free-LLM, humans send |
| LLM-heavy | 🟡 Med | sales_deepdive | Cost cap |
| High-volume | 🟡 Med | sms_bulk | DLT, opt-in, daily cap |
| Execute | 🔴 High | auto_email | Approval gate |
| Platform | 🔴 High | cold_calls | DLT+compliance audit |

---

## File Structure

```
.claude/skills/
├── audit-automation/
│   ├── SKILL.md (main guide)
│   ├── references/automation-checklist.md (quick checklists)
│   └── README.md (package summary)
│
├── teach-agent-loop/
│   ├── SKILL.md (main guide)
│   ├── references/agent-extension-guide.md (deep dive)
│   └── README.md (package summary)
│
└── PHASE5_SKILLS_SUMMARY.md (this file)

scripts/
└── automation_health_audit.py (CLI tool)
```

---

## How to Get Started

### Day 1: Read the Docs
```bash
# Read once, bookmark for reference
cat .claude/skills/audit-automation/SKILL.md      # 15 min
cat .claude/skills/teach-agent-loop/SKILL.md      # 15 min
```

### Day 2: Try Daily Audit
```bash
# Before standup
python scripts/automation_health_audit.py --daily-check
# Copy output to Slack / team chat
```

### Day 3: Weekly Review
```bash
# Monday morning
python scripts/automation_health_audit.py --weekly-audit
# Use automation-checklist.md to verify
```

### Month 1: Add First Action
```bash
# Pick a small, safe action to add
# Follow teach-agent-loop SKILL.md Step 1-6
# Test with 5 scenarios
# Monitor via automation_health_audit.py
```

### Month 2+: Build Team
```bash
# Add more agents as needed
# Use teach-agent-loop for guidance
# Audit weekly via automation_health_audit.py
```

---

## See Also

- `docs/AUTOMATION.md` — 3-loop architecture (self-improve, coordinator, process-engine)
- `app/agents/self_improve.py` — Task picking logic (source code)
- `app/platform/skill_library.py` — Bandit + learning (source code)
- `app/agents/coordinator.py` — Multi-agent orchestration (source code)
- `app/platform/team.py` — Staff roster (source code)

---

## Checklist: Phase 5 Complete

- [x] **audit-automation/SKILL.md** (250 lines, 6-step health check)
- [x] **automation-checklist.md** (180 lines, daily/weekly/monthly)
- [x] **automation_health_audit.py** (350 lines, CLI tool)
- [x] **teach-agent-loop/SKILL.md** (280 lines, 6 steps to extend)
- [x] **agent-extension-guide.md** (150 lines, architecture + patterns)
- [x] **README.md** files (packaging + quick start)
- [x] **PHASE5_SKILLS_SUMMARY.md** (this file, integration guide)

**Total**: ~1,400 lines of documentation + production CLI.

**Status**: ✅ **COMPLETE** — Ready to deploy.

---

## Author Notes

**Rationale**:
- **audit-automation**: Automation loops are black boxes. This skill makes them transparent.
- **teach-agent-loop**: New features = new code. This skill demystifies the extension process.
- **CLI tool**: Checklists are great, but a tool that runs daily checks removes friction.

**Philosophy**:
- No code changes to existing systems (skills are documentation + optional CLI)
- Everything is gradual — daily standup → weekly review → monthly strategy
- Risk assessment up-front (safety gates before enabling)
- Testing checklist enforced (5 scenarios, not "works for me")

**Next Steps** (after Phase 5):
- Phase 6: Approval gates + cost tracking UI (dashboard for human review)
- Phase 7: Deterministic feedback loops (self-improve improves itself)
- Phase 8: Multi-worker coordination (true distributed automation)

---

End of Phase 5 Skills Summary.
