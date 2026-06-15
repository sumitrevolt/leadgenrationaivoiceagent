# Phase 5 Quick Start — Audit & Extend Automation Loops

Choose your path below:

---

## 👀 "I want to monitor the automation loop" 
→ Use **audit-automation** skill

**Time**: 5–60 min depending on frequency
**Tools**: `automation_health_audit.py` CLI

**Get Started**:
```bash
# Daily standup (5 min)
python scripts/automation_health_audit.py --daily-check

# Weekly review (15 min)
python scripts/automation_health_audit.py --weekly-audit

# Troubleshoot issues (10 min)
python scripts/automation_health_audit.py --anomalies
```

**Read First**: `.claude/skills/audit-automation/SKILL.md` (15 min)

**Keep Handy**: `.claude/skills/audit-automation/references/automation-checklist.md` (copy to todo app)

---

## 🔧 "I want to add a new action to the loop"
→ Use **teach-agent-loop** skill (fastest path)

**Time**: 15 min
**Example**: Add "sms_campaign_draft" to self-improve

**Steps**:
1. Read: `.claude/skills/teach-agent-loop/SKILL.md` (6 steps to add action)
2. Write code: `app/agents/your_agent.py`
3. Register in: `app/agents/self_improve.py`
4. Test: 5 scenarios (copy-paste from guide)
5. Enable & monitor via `automation_health_audit.py`

**Read First**: `.claude/skills/teach-agent-loop/SKILL.md` (20 min)

**Copy Patterns From**: `.claude/skills/teach-agent-loop/references/agent-extension-guide.md`

---

## 👥 "I want to add a new AI agent to the team"
→ Use **teach-agent-loop** skill (longer path)

**Time**: 90 min
**Example**: Add "Priya — Competitive Research" agent

**Steps**:
1. Read: `.claude/skills/teach-agent-loop/SKILL.md` (full guide + worked example)
2. Create code: `app/agents/priya.py` (20 min)
3. Add to roster: `app/platform/team.py` (5 min)
4. Wire coordinator: `app/agents/coordinator.py` (10 min)
5. Add to self-improve: `app/agents/self_improve.py` (20 min)
6. Test: Coordinator + self-improve + dashboard (30 min)

**Read First**: `.claude/skills/teach-agent-loop/SKILL.md` (full, with worked example)

**Deep Dive**: `.claude/skills/teach-agent-loop/references/agent-extension-guide.md` (architecture)

---

## 🆘 "Something's wrong with the automation"
→ Use **audit-automation** to diagnose

**Quick Diagnosis** (2 min):
```bash
python scripts/automation_health_audit.py --daily-check

# Look for red sections (🔴)
# Possible issues:
#   - Loop not alive? → Restart service
#   - Budget exceeded? → Pause loop
#   - High error rate? → Check logs
#   - Compliance gap? → Fix immediately
```

**Full Diagnosis** (10 min):
```bash
python scripts/automation_health_audit.py --anomalies
python scripts/automation_health_audit.py --dlq-status
python scripts/automation_health_audit.py --compliance-check
```

**Escalation Guide**: `.claude/skills/audit-automation/SKILL.md` (Escalation Checklist section)

---

## 📚 "I want to understand the architecture"
→ Read **teach-agent-loop** deep-dive

**Key Concepts**:
- Self-improve loop picks actions daily (bandit algorithm)
- Actions are defined in code, learned from outcomes
- Agents are dedicated team members with 2–5 actions
- Coordinator orchestrates multi-agent goals
- Skill library tracks success rates

**Read**: `.claude/skills/teach-agent-loop/references/agent-extension-guide.md`

Also: `docs/AUTOMATION.md` (3-loop architecture overview)

---

## ✅ Checklist: First Week

### Day 1 (30 min)
- [x] Read audit-automation/SKILL.md
- [x] Read teach-agent-loop/SKILL.md intro
- [x] Bookmark automation-checklist.md

### Day 2 (5 min)
- [x] Run: `python scripts/automation_health_audit.py --daily-check`
- [x] Share output with team

### Day 3 (15 min)
- [x] Run: `python scripts/automation_health_audit.py --weekly-audit`
- [x] Check against automation-checklist.md
- [x] Document any issues

### Week 2 (30 min)
- [x] Plan: "Which action could I automate?"
- [x] Read: teach-agent-loop SKILL.md Step 1–6
- [x] Pick a small, safe action (read-only, no side effects)

### Week 3+ (15–90 min)
- [x] Implement your first action or agent
- [x] Test with 5 scenarios
- [x] Monitor via automation_health_audit.py

---

## 🎯 Common Tasks

### Monitor Loop Health
```bash
python scripts/automation_health_audit.py --daily-check
python scripts/automation_health_audit.py --weekly-audit
```
Read: audit-automation/SKILL.md

### Add SMS Campaign Action
```bash
# Define → Code → Register → Test → Enable (15 min)
# Example in teach-agent-loop/SKILL.md Step 1–6
```

### Investigate Budget Overage
```bash
python scripts/automation_health_audit.py --daily-check
# Look at "Budget" section
# See which actions are expensive
```
Read: audit-automation/SKILL.md (Budget section)

### Check Compliance Status
```bash
python scripts/automation_health_audit.py --compliance-check
# Verify DLT, opt-outs, retention active
```

### Add Competitive Research Agent
```bash
# Define → Code → Roster → Coordinator → Self-Improve → Test (90 min)
# Worked example in teach-agent-loop/SKILL.md
```

### Debug Approval Bottleneck
```bash
python scripts/automation_health_audit.py --approvals-pending
# See how many tasks stuck waiting for approval
# Review approval gates, consider auto-approval for low-risk
```

---

## 📖 File Guide

| Need | File | Time |
|------|------|------|
| Daily health check | audit-automation/SKILL.md | 5–15 min |
| Weekly review template | automation-checklist.md | 15 min |
| CLI tool | scripts/automation_health_audit.py | Run-only |
| Add new action (15 min) | teach-agent-loop/SKILL.md | 20 min |
| Add new agent (90 min) | teach-agent-loop/SKILL.md full | 20 min |
| Architecture deep-dive | agent-extension-guide.md | 30 min |
| Copy-paste code | agent-extension-guide.md patterns | Ref only |
| Overview | PHASE5_SKILLS_SUMMARY.md | 15 min |

---

## 🚀 Success Criteria

You'll know Phase 5 is working when:

1. ✅ **Daily audit runs before standup** (5 min, no friction)
2. ✅ **Weekly review identifies trends** (success rates, cost patterns)
3. ✅ **You can add a new action in 15 min** (with guide)
4. ✅ **You can add a new agent in 90 min** (with guide)
5. ✅ **Team roster reflects actual AI staff** (visible on dashboard)
6. ✅ **Escalation checklist prevents surprises** (red alerts caught early)

---

## 🤔 FAQ

**Q: Do I need to modify existing code?**
A: No! Skills are pure documentation + optional CLI. No code changes required.

**Q: What if I just want to monitor, not extend?**
A: Perfect. Use audit-automation skill. Stop there. :)

**Q: How often should I run the audit?**
A: Daily (5 min) before standup. Weekly (15 min) for trends.

**Q: Can I run the CLI on my laptop?**
A: Yes. Script reads local data/ directory. No Docker needed.

**Q: What if something breaks?**
A: Use escalation checklist in audit-automation/SKILL.md. Clear remediation path.

**Q: How do I know if an action is safe to add?**
A: Check risk assessment table in teach-agent-loop/SKILL.md. Follow safety gates.

---

## 📞 Next Steps

1. **This week**: Run daily audit 3 times. See the pattern.
2. **Next week**: Do a full weekly review. Compare to baseline.
3. **Week 3**: Plan your first extension (action or agent).
4. **Week 4**: Implement + test + monitor.

---

## 📚 See Also

- `docs/AUTOMATION.md` — 3-loop architecture overview
- `docs/PRODUCTION_READINESS_2026.md` — Safety + compliance
- `app/agents/self_improve.py` — Task picking (source code)
- `app/platform/skill_library.py` — Learning mechanism (source code)

---

**Ready?** Start with audit-automation/SKILL.md. Takes 15 min, unlocks everything.
