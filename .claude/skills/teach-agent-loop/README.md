# Skill: teach-agent-loop — Phase 5 Agent Extension

**Part of Phase 5**: Make automation loops **auditable** + **extensible** without reading code.

## What's Included

This skill package contains **2 components** for extending the automation team:

### 1. SKILL.md (280 lines)
Main skill guide. Covers:
- When to add new agents or actions
- **6 steps to add new action** (fastest path, 15 min)
- **6 steps to add new agent** (longer path, 30–90 min)
- Risk assessment matrix (auto-safe vs. approval-required)
- Worked example: "Add LinkedIn DM Outreach"
- Testing checklist (5 test scenarios)
- Safety gates checklist

**Read this when**: You want to automate a new task or add an AI agent to the team.

### 2. references/agent-extension-guide.md (150 lines)
Deep-dive architecture reference. Covers:
- Agent code template (minimal, copy-paste)
- Integration points (5 places agents plug in)
- Staff roster structure (team.py)
- Self-improve bandit mechanism (how actions are picked)
- Coordinator modes (sequential, parallel, hierarchical)
- Scheduler integration (recurring tasks)
- Event logging & dashboard
- API endpoints pattern
- Testing patterns (unit, integration, coordinator)
- Copy-paste code patterns

**Read this when**: You need architecture context or copy example code.

## Quick Start: Add New Action (15 min)

**Goal**: Automate a new task (e.g., "draft SMS campaigns").

**Steps**:

1. **Define** (1 min)
   - Name: `sms_campaign_draft`
   - Cost: Light (free-LLM)
   - Risk: Draft-only (humans send)

2. **Write Code** (5 min)
   - New file: `app/agents/sms_agent.py`
   - Function: `draft_sms_campaigns(niche: str) -> dict`
   - Returns: `{ok: bool, detail: str, output: ...}`

3. **Register in self_improve.py** (3 min)
   - Add to `ACTIONS` dict
   - Add execution in `_execute()`
   - Add to `_STAGE_ACTIONS`

4. **Register in skill_library** (1 min)
   - Auto-learns on first run (no manual action)

5. **Test** (3 min)
   - Happy path ✓
   - Empty data ✓
   - LLM down ✓
   - Timeout ✓
   - Concurrent ✓

6. **Enable & Monitor** (2 min)
   - No special env flag (draft-only)
   - Monitor via `automation_health_audit.py --weekly-audit`

**Next**: Read `SKILL.md` Step 1–6 for detailed walkthrough.

## Quick Start: Add New Agent (90 min)

**Goal**: Add a dedicated AI agent to the team (e.g., "Priya — Competitive Intelligence").

**Steps**:

1. **Define** (5 min)
   - Name: Priya
   - Role: Competitive Research
   - Responsibilities: 2–5 tasks

2. **Create Agent Code** (20 min)
   - New file: `app/agents/priya.py`
   - Functions: `research_competitors`, `analyze_pricing`, etc.

3. **Add to Team Roster** (5 min)
   - Edit `app/platform/team.py`
   - Add to `STAFF` dict

4. **Wire into Coordinator** (10 min)
   - Edit `app/agents/coordinator.py`
   - Add to `AGENT_HANDLERS`

5. **Add to Self-Improve** (20 min)
   - New actions in `self_improve.py`
   - Add to `ACTIONS`, `_execute()`, `_STAGE_ACTIONS`

6. **Test & Document** (30 min)
   - Coordinator test
   - Self-improve test
   - Dashboard verify

**Next**: Read `SKILL.md` Step 1–6 for detailed walkthrough with examples.

## Integration Points: Where Agents Live

```
[Team Roster]
    ↓ (defined in team.py)
[Self-Improve Loop] ← Picks actions for agent daily
    ↓
[Scheduler/Celery] ← Runs recurring tasks
    ↓
[Coordinator] ← Multi-agent orchestration
    ↓
[API Endpoints] ← User manual triggers
    ↓
[Dashboard] ← See agent activity
```

**Your agent should connect to at least 1–2**:
- **Self-Improve**: If task is repeatable (daily learning)
- **Coordinator**: If works with other agents (orchestration)
- **Scheduler**: If has recurring cadence
- **API**: If users need manual trigger
- **Dashboard**: If tracking team activity

## Key Concepts

### Action vs. Agent

- **Action** = Task the loop can pick (e.g., `scrape_leads`, `draft_social_posts`)
  - 15-min to add
  - Registered in self_improve.py
  - Self-improve learns success rates
  
- **Agent** = Dedicated staff member (e.g., "Isha — Marketing")
  - 90-min to add
  - Has 2–5 responsibilities
  - Shows on team roster + dashboard

### Self-Improve Bandit

The loop picks tasks using **epsilon-greedy**:
- 30% explore random action
- 70% pick best success-rate action

**Your action's success rate auto-learns** from outcomes:
- Week 1: 50–80% (learning phase)
- Week 2+: Stabilizes 75–95%

### Cost Tracking

Every run records cost. Loop stops if daily `SELFIMPROVE_COST_CAP` exceeded.

**Your action should**:
- Return `{cost: float}` in result
- Be fast (<180s typical, hard 240s)
- Low-cost (<$5/run for LLM-heavy)

### Safety Gates

Before enabling in prod:

```
[ ] 1. Import-safe (no side effects on import)
[ ] 2. Fail-open (returns {ok: false} instead of raising)
[ ] 3. Gated (behind env flag if sensitive)
[ ] 4. Bounded (cost cap, timeout watchdog)
[ ] 5. Logged (skill_library tracks outcome)
[ ] 6. Tested (5 test scenarios pass)
```

## Risk Assessment

| Action Type | Risk | Example | Mitigation |
|-------------|------|---------|-----------|
| Read-only | 🟢 Low | scrape_leads | OSM+Places API only |
| Draft-only | 🟢 Low | social_drafts | Free-LLM, humans send |
| LLM-heavy | 🟡 Medium | sales_deepdive | Cost cap per run |
| High-volume | 🟡 Medium | sms_campaign | DLT-gated, opt-in verified |
| Execute/Send | 🔴 High | auto_email_bulk | Approval gate required |
| Platform ops | 🔴 High | cold_calls | DLT-required, compliance audit |

**For 🔴 High-risk**:
- Require `SELF_IMPROVE_APPROVAL=1`
- Add compliance audit (DLT, opt-in, retention)
- Set low initial cap (5/day)
- Test in staging first

## Testing Checklist (5 Scenarios)

All new actions must pass:

1. **Happy path**: Valid input → ok=True, meaningful output
2. **Empty data**: No data found → ok=False (graceful)
3. **LLM down**: Provider fails → fallback or error (no crash)
4. **Timeout**: Task >240s → cancelled, logged, not blocking
5. **Concurrent**: 2 workers simultaneously → no race conditions

## Code Patterns (Copy & Adapt)

### Pattern 1: Research Agent
```python
async def research_market(niche: str) -> dict[str, Any]:
    try:
        data = await get_data(niche)
        analysis = await free_ai.chat(f"Analyze {niche}")
        return {"ok": True, "detail": f"analyzed {len(data)}", "output": analysis}
    except Exception as e:
        return {"ok": False, "detail": str(e)}
```

### Pattern 2: Draft Agent
```python
async def draft_content(niche: str, content_type: str) -> dict[str, Any]:
    try:
        content = await free_ai.chat(f"Draft {content_type} for {niche}")
        return {"ok": True, "detail": f"drafted {content_type}", "output": content}
    except Exception as e:
        return {"ok": False, "detail": str(e)}
```

### Pattern 3: Score/Classify Agent
```python
async def score_leads(niche: str) -> dict[str, Any]:
    try:
        leads = await get_leads(niche)
        scored = [{"lead": l, "score": score_lead(l)} for l in leads]
        top = sorted(scored, key=lambda x: x["score"], reverse=True)[:5]
        return {"ok": True, "detail": f"scored {len(leads)}", "output": top}
    except Exception as e:
        return {"ok": False, "detail": str(e)}
```

### Pattern 4: Execute Agent (High-Risk, Gated)
```python
async def send_emails(niche: str) -> dict[str, Any]:
    # Gate 1: Feature flag
    if not os.getenv("AUTO_EMAIL_OUTREACH", "0").lower() in ("1", "true"):
        return {"ok": False, "detail": "feature not enabled"}
    # Gate 2: Budget
    if get_today_spend() > budget * 0.8:
        return {"ok": False, "detail": "budget exhausted"}
    # Execute
    try:
        result = await send_batch(niche)
        return {"ok": result.get("ok"), "detail": f"sent {result.get('count')} emails"}
    except Exception as e:
        return {"ok": False, "detail": str(e)}
```

## Files in This Package

```
.claude/skills/teach-agent-loop/
├── SKILL.md                                  (280 lines, main guide)
├── references/
│   └── agent-extension-guide.md             (150 lines, deep dive)
└── README.md                                (this file)
```

## How It Fits Into Phase 5

**Phase 5 Goal**: Make automation loops **auditable** + **extensible** without reading code.

- **Auditable** ← Companion skill (audit-automation)
  - See loop health without code
  - Daily standup + weekly review
  
- **Extensible** ← This skill (teach-agent-loop)
  - Add new actions/agents in 6 steps
  - Testing checklist + safety gates
  - Risk assessment + examples

## See Also

- `.claude/skills/audit-automation/SKILL.md` — Monitor automation health
- `docs/AUTOMATION.md` — 3-loop architecture
- `app/platform/team.py` — Staff roster (source)
- `app/agents/self_improve.py` — Task picking (source)
- `app/agents/coordinator.py` — Multi-agent orchestration (source)
- `app/platform/skill_library.py` — Learning mechanism (source)

## Common Questions

**Q: How long does it take to add a new action?**
A: 15–30 min. Read SKILL.md Step 1–6.

**Q: How long does it take to add a new agent?**
A: 60–90 min. Read SKILL.md full guide + examples.

**Q: What's the easiest action to start with?**
A: Read-only actions (scrape, research). No risk, fail-open easily.

**Q: Can I test locally without Docker?**
A: Yes. New action just needs async function + return dict. See SKILL.md Step 5.

**Q: What if my action costs money?**
A: Add cost tracking + daily budget check. See Pattern 4 in reference guide.

**Q: What if the action fails sometimes?**
A: That's OK! Skill library learns success rate. Aim for >70%.

**Q: How do I disable an action if it's failing?**
A: Remove from `_STAGE_ACTIONS` in self_improve.py, or reduce weight in skill_library.
