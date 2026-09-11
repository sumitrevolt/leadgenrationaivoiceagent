# Deep Dive: Custom Agents & Extension Patterns

Advanced guide for extending the automation team and understanding integration points.

---

## Agent Architecture

### Agent as Code Template

Minimal agent (can be copy-pasted):

```python
"""Agent: [Name] — [Role].

Responsibilities:
  - [Task 1]
  - [Task 2]
  
Exports: [action_1], [action_2], ... (async functions)
Safe: [draft-only / auto-safe / approval-required]
"""

from __future__ import annotations

import asyncio
from typing import Any
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

async def action_name(param: str) -> dict[str, Any]:
    """[Human description of what this does].
    
    Returns: {ok: bool, detail: str, output: ...}
    """
    try:
        # Your code here
        result = "something"
        return {
            "ok": True,
            "detail": f"did something with {param}",
            "output": result,
        }
    except Exception as e:
        logger.warning(f"action_name failed: {e}")
        return {"ok": False, "detail": str(e)}
```

**Rules**:
- Async only (for event-loop safety)
- Always return `{ok: bool, detail: str}`
- Never raise — fail-open with ok=False
- Lazy imports inside function
- 240s hard timeout (self_improve watchdog)

### Integration Points

Agents plug into the system at 5 points:

```
[Coordinator] (multi-agent orchestration)
      ↓
[Self-Improve Loop] (task picking + cost tracking)
      ↓
[Scheduler / Celery Worker] (timing: on-demand vs. recurring)
      ↓
[API Endpoints] (user-triggered actions)
      ↓
[Dashboard / Team Roster] (visibility)
```

**New agent should integrate to at least 1–2 points**:

1. **Coordinator**: If orchestrating with other agents
2. **Self-Improve**: If task is repeatable (daily learning)
3. **Scheduler**: If task has recurring cadence
4. **API**: If user needs manual trigger
5. **Dashboard**: If tracking team activity

---

## Staff Roster Structure

**File**: `app/platform/team.py`

```python
STAFF: dict[str, dict[str, Any]] = {
    "sumit": {
        "name": "Sumit",
        "role": "Founder/CEO",
        "emoji": "👑",
        "capabilities": [],
        "product": "platform",
        "is_ai": False,
        "is_super": True,
    },
    
    "isha": {
        "name": "Isha",
        "role": "Marketing AI Agent",
        "emoji": "📣",
        "capabilities": ["content_pack", "social_drafts", "hashtags"],
        "product": "marketing",
        "is_ai": True,
        "is_super": False,
    },
    
    # New agent template:
    "priya": {
        "name": "Priya",
        "role": "Competitive Research Agent",
        "emoji": "🔍",
        "capabilities": ["competitor_research", "market_analysis"],
        "product": "growth",
        "is_ai": True,
        "is_super": False,
    },
}

def team_status() -> dict[str, Any]:
    """Live team state (who's working, what are they doing)."""
    # Returns active members + current activity
```

**Fields**:
- `name`: Human-readable name
- `role`: Job title (can be generic like "Agent")
- `emoji`: Visual identifier on dashboard
- `capabilities`: List of action_names this agent can do
- `product`: Which product domain (marketing/voice/growth/platform)
- `is_ai`: Is this an AI agent or human?
- `is_super`: Superadmin privileges? (usually False for AI)

---

## Self-Improve Bandit Mechanism

**How the loop picks tasks**:

```
1. Check manual queue (user-added goals) → pick first
2. If queue empty:
   a. Get funnel weakest stage (lead_supply / outreach / conversion / etc.)
   b. Get candidate actions for that stage
   c. Apply epsilon-greedy (30% random, 70% best success rate)
   d. Apply diversity guards (dedup recent, cooldown)
   e. Return action
3. Execute action via async function dispatch
4. Record outcome + cost
5. Every N runs: reflection (LLM learns lesson)
6. Update skill_library weights based on success rate
```

**Weakest stage detection** (`growth_optimizer.weakest_stage`):

```python
def weakest_stage(snapshot) -> dict:
    """Which funnel stage has most headroom for improvement?
    
    Returns: {stage: str, gap: int, action: str}
    """
    # Simplified logic:
    leads_converted = snapshot["leads_converted"]
    prospects_qualified = snapshot["prospects_qualified"]
    conversion_rate = leads_converted / prospects_qualified if prospects_qualified > 0 else 0
    
    if leads_converted < 10:
        return {"stage": "lead_supply", "gap": 50 - leads_converted}
    elif conversion_rate < 0.05:
        return {"stage": "conversion", "gap": gap_measure}
    # ... etc
```

**Skill library** (`skill_library.pick_action`):

```python
def pick_action(candidates: list[str], epsilon: float = 0.3) -> str:
    """Epsilon-greedy: explore 30%, exploit 70%."""
    stats = skill_library.stats()  # {action: {uses, ok, rate}}
    
    if random.random() < epsilon:
        return random.choice(candidates)  # Explore
    
    # Exploit: pick best success rate
    return max(candidates, key=lambda a: stats.get(a, {}).get("rate", 0.5))
```

**Cost tracking**:

```python
async def run_once() -> dict[str, Any]:
    # ... pick task ...
    
    start_cost = get_daily_cost()  # Sum of cost_usd from all runs today
    result = await _execute(action, task)
    end_cost = get_daily_cost()
    
    cost_delta = end_cost - start_cost
    
    # Check cap
    cap = float(os.getenv("SELFIMPROVE_COST_CAP", "50"))
    if start_cost + cost_delta > cap:
        logger.warning(f"Pausing loop: cost {cost_delta} would exceed cap {cap}")
        return {"ok": False, "paused": True}
    
    # Record
    record_run({
        "action": action,
        "ok": result["ok"],
        "cost": cost_delta,
        "detail": result["detail"],
    })
```

**To hook your agent**: Ensure each action:
1. Returns `{ok: bool, cost: float (optional), detail: str}`
2. Is fast (<180s typical, hard 240s)
3. Has low cost (if LLM-heavy, <$5/run)
4. Is in `_STAGE_ACTIONS` for appropriate stage
5. Can be deduped/cooldown-checked (no 2x in 20 min)

---

## Coordinator Modes & Agent Calling

**File**: `app/agents/coordinator.py`

### Sequential Mode (Linear Handoff)

```python
async def coordinate(goal: str, mode: str = "sequential") -> dict:
    """Orchestrate agents in sequence."""
    
    context = {"goal": goal, "prior_outputs": []}
    
    agents = ["Riya", "Dev", "Isha"]  # Order matters
    for agent_name in agents:
        handler = AGENT_HANDLERS.get(agent_name)
        
        result = await handler(goal, context)
        
        context["prior_outputs"].append(result)
        context[f"{agent_name.lower()}_output"] = result
    
    return {"status": "done", "outputs": context["prior_outputs"]}
```

**Your agent integration**:

```python
# In coordinator.py, add to AGENT_HANDLERS:
AGENT_HANDLERS = {
    "Riya": riya.research,
    "Dev": dev.competitive_analysis,
    "Isha": isha.draft_outreach,
    "Priya": priya.research_competitors,  # ← New agent
}
```

### Parallel Mode (Fan-Out)

```python
async def coordinate_parallel(goal: str, agents: list[str]) -> dict:
    """Orchestrate agents in parallel."""
    
    tasks = [AGENT_HANDLERS[a](goal) for a in agents]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return {"status": "done", "outputs": results}
```

### Hierarchical Mode (Team-Based)

```python
_TEAMS = {
    "growth": ["Rohan", "Isha"],  # prospect + content
    "sales": ["Riya", "Dev"],      # research + competitive
    "voice": ["Swara", "Arjun"],   # calls + QA
}

async def coordinate_hierarchical(goal: str) -> dict:
    """Orchestrate teams, then merge."""
    
    team_results = {}
    for team_name, members in _TEAMS.items():
        # Each team in parallel
        results = await asyncio.gather(
            *[AGENT_HANDLERS[m](goal) for m in members]
        )
        team_results[team_name] = results
    
    # Boss merges
    final = await boss.synthesize(goal, team_results)
    return {"status": "done", "synthesis": final}
```

**New agent in teams**:

```python
_TEAMS = {
    "growth": ["Rohan", "Isha", "Priya"],  # Added Priya to growth team
    # ...
}
```

---

## Scheduler Integration (Cron Patterns)

**File**: `app/platform/team_scheduler.py`

Auto-scheduled jobs (recurring):

```python
JOBS = {
    "growth": {
        "cadence": "0 */15 * * * *",  # Every 15 min
        "agent": None,  # Self-improve loop picks
        "action": "dynamic",
    },
    
    "content": {
        "cadence": "0 7 * * *",  # 7 AM IST daily
        "agent": "Isha",
        "actions": ["content_pack", "post_generator"],
    },
    
    "competitor_research": {  # New job
        "cadence": "0 9 * * MON",  # Monday 9 AM IST
        "agent": "Priya",
        "actions": ["competitor_research", "market_analysis"],
    },
}

async def _run_job(job_name: str) -> dict[str, Any]:
    """Run a scheduled job."""
    job = JOBS.get(job_name)
    agent_name = job.get("agent")
    actions = job.get("actions", [])
    
    if agent_name and actions:
        # Targeted agent
        handler = team.STAFF[agent_name]["handler"]
        for action in actions:
            result = await handler(action=action)
            # Log event
            team.log_event(agent_name, action, result)
    
    return {"ok": True}
```

**To add recurring task for your agent**:

```python
# In team_scheduler.py, add to JOBS:
JOBS = {
    # ...
    "priya_weekly_research": {
        "cadence": "0 9 * * MON",  # Mondays 9 AM IST
        "agent": "Priya",
        "actions": ["competitor_research"],
    },
}

# Then the scheduler will auto-run every Monday
```

---

## Event Logging & Dashboard

**File**: `app/platform/team.py`

```python
def log_event(agent: str, action: str, result: dict[str, Any]) -> None:
    """Log agent activity for dashboard + audit trail."""
    event = {
        "agent": agent,
        "action": action,
        "ok": result.get("ok"),
        "detail": result.get("detail", ""),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    # Writes to: agent_events table (DB) + real-time SSE stream
    db.agent_events.insert_one(event)
    publish_sse("agent_event", event)

def team_status() -> dict[str, Any]:
    """Live team state (for dashboard)."""
    status = {}
    for name, staff in STAFF.items():
        if staff.get("is_ai"):
            last_events = db.agent_events.find({"agent": name}).sort("at", -1).limit(3)
            status[name] = {
                "name": staff["name"],
                "role": staff["role"],
                "emoji": staff.get("emoji", ""),
                "status": "working" if last_events[0]["at"] > 20min_ago else "idle",
                "last_action": last_events[0].get("action") if last_events else None,
                "last_at": last_events[0].get("at") if last_events else None,
            }
    return status
```

**Dashboard auto-shows**:
- Agent name + emoji + role
- Status (working / idle)
- Last action + when
- Click to see full activity log

---

## API Endpoints for New Agent

Standard pattern (add to `app/api/growth.py` or similar):

```python
@router.post("/agents/{agent_name}/action/{action_name}")
async def trigger_agent_action(
    agent_name: str,
    action_name: str,
    current_user: User = Depends(require_admin),
) -> dict:
    """Manually trigger agent action."""
    
    # Validate
    if agent_name not in team.STAFF:
        raise HTTPException(404, "Agent not found")
    
    if action_name not in team.STAFF[agent_name]["capabilities"]:
        raise HTTPException(403, "Agent cannot do this action")
    
    # Execute
    handler = team.AGENT_HANDLERS.get(agent_name)
    if not handler:
        raise HTTPException(501, "Agent not executable")
    
    result = await handler(action=action_name)
    
    # Log
    team.log_event(agent_name, action_name, result)
    
    return {
        "ok": result.get("ok"),
        "detail": result.get("detail"),
        "output": result.get("output"),
    }

@router.get("/agents/status")
async def get_team_status() -> dict:
    """Get live team status."""
    return team.team_status()
```

---

## Testing Patterns for Custom Agents

### Unit Test (Action in Isolation)

```python
import pytest
from app.agents.priya import research_competitors

@pytest.mark.asyncio
async def test_research_competitors_happy_path():
    """Happy path: valid niche, returns output."""
    result = await research_competitors("solar")
    
    assert result["ok"] is True
    assert "detail" in result
    assert "narratives" in result
    assert len(result["narratives"]) > 0

@pytest.mark.asyncio
async def test_research_competitors_no_data():
    """Empty data: graceful error."""
    result = await research_competitors("nonexistent_niche_xyz")
    
    assert result["ok"] is False  # or True with fallback
    assert "detail" in result
    assert "error" in result["detail"] or "fallback" in result["detail"]

@pytest.mark.asyncio
async def test_research_competitors_llm_down(monkeypatch):
    """LLM provider fails: fallback or error."""
    async def mock_chat(*args, **kwargs):
        raise Exception("API 429")
    
    monkeypatch.setattr("app.voice_agent.free_ai.chat", mock_chat)
    
    result = await research_competitors("solar")
    
    # Should handle gracefully (fallback or error)
    assert isinstance(result, dict)
    assert "detail" in result
```

### Integration Test (In Self-Improve Loop)

```python
@pytest.mark.asyncio
async def test_action_in_self_improve():
    """Action registered and runs in self-improve."""
    
    # Register action
    assert "competitor_research" in self_improve.ACTIONS
    
    # Trigger via self-improve
    result = await self_improve._execute("competitor_research", "test")
    
    assert isinstance(result, dict)
    assert "ok" in result
    assert "detail" in result
    
    # Check skill_library recorded it
    stats = skill_library.stats()
    assert "competitor_research" in stats
    assert stats["competitor_research"]["uses"] > 0
```

### Coordinator Integration Test

```python
@pytest.mark.asyncio
async def test_agent_in_coordinator():
    """Agent works within coordinator orchestration."""
    
    # Sequential mode
    result = await coordinator.coordinate(
        goal="Analyze Pune solar market",
        mode="sequential",
        agents=["Riya", "Dev", "Priya"],  # Includes new agent
        execute=False,  # Draft-only
    )
    
    assert result["status"] == "done"
    assert len(result["outputs"]) >= 3
```

---

## Common Patterns: Copy & Adapt

### Pattern 1: Research Agent

```python
async def research_market(niche: str) -> dict[str, Any]:
    """Research market for niche."""
    try:
        from app.platform.prospector_store import by_niche
        from app.voice_agent.free_ai import chat
        
        data = await by_niche(niche, limit=10)
        
        prompt = f"""Niche: {niche}
Data: {len(data)} prospects
Task: Summarize market conditions, opportunities, threats."""
        
        analysis = await chat(prompt)
        
        return {
            "ok": True,
            "detail": f"analyzed {len(data)} prospects",
            "research": analysis,
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}
```

### Pattern 2: Draft Agent

```python
async def draft_content(niche: str, content_type: str) -> dict[str, Any]:
    """Draft content (posts, emails, etc.)."""
    try:
        from app.voice_agent.free_ai import chat
        
        system = f"You are {content_type} copywriter"
        user = f"Draft {content_type} for {niche}"
        
        content = await chat(user, system=system)
        
        return {
            "ok": True,
            "detail": f"drafted {content_type}",
            "content": content,
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}
```

### Pattern 3: Score/Classify Agent

```python
async def score_leads(niche: str) -> dict[str, Any]:
    """Score and classify leads for niche."""
    try:
        from app.platform.prospector_store import by_niche
        from app.platform.lead_scoring import score_lead
        
        leads = await by_niche(niche)
        
        scored = [
            {"lead": l, "score": score_lead(l)}
            for l in leads
        ]
        
        top = sorted(scored, key=lambda x: x["score"], reverse=True)[:5]
        
        return {
            "ok": True,
            "detail": f"scored {len(leads)} leads",
            "top_leads": top,
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}
```

### Pattern 4: Execute Agent (High-Risk, Gated)

```python
async def send_emails(niche: str) -> dict[str, Any]:
    """Send bulk emails (gated, high-risk)."""
    
    # Gate 1: Feature flag
    if not os.getenv("AUTO_EMAIL_OUTREACH", "").lower() in ("1", "true"):
        return {"ok": False, "detail": "AUTO_EMAIL_OUTREACH not enabled"}
    
    # Gate 2: Cost budget
    daily_budget = float(os.getenv("SELFIMPROVE_COST_CAP", "50"))
    today_spent = get_today_spend()
    if today_spent > daily_budget * 0.8:
        return {"ok": False, "detail": "daily budget almost exhausted"}
    
    # Gate 3: Approval check (if enabled)
    if os.getenv("SELF_IMPROVE_APPROVAL", "").lower() == "1":
        return {"ok": False, "detail": "requires human approval"}
    
    # Execute
    try:
        from app.platform import auto_outreach
        
        result = await auto_outreach.send_batch(niche, limit=10)
        
        return {
            "ok": result.get("ok"),
            "detail": f"sent {result.get('count', 0)} emails",
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}
```

---

## Debugging Tips

### Agent Not Picked by Self-Improve

1. Check action registered: `"action_name" in self_improve.ACTIONS`
2. Check stage bias: action in `_STAGE_ACTIONS[some_stage]`?
3. Check diversity guard: hasn't run in last 20 min?
4. Check success rate: too low? Disable for learning phase
5. Check LLM health: provider degraded → light actions only

### Agent Errors in DLQ

1. Check logs: `grep agent_name logs/*.log | tail -20`
2. Inspect DLQ: `python scripts/automation_health_audit.py --dlq-status`
3. Retry manually: `POST /api/growth/infra/dlq/retry`
4. Check imports: `python -c "from app.agents.agent_name import action_name"`
5. Check timeouts: Is action taking >240s?

### Coordinator Not Calling Agent

1. Check AGENT_HANDLERS: agent in dict?
2. Check capabilities: action in agent's capabilities?
3. Check async: is handler async function?
4. Check mode: sequential/parallel/hierarchical all call?
5. Check execute flag: draft=False but should be True?

---

## See Also

- `teach-agent-loop/SKILL.md` — Step-by-step guide (this is deeper dive)
- `app/agents/coordinator.py` — Source code
- `app/agents/self_improve.py` — Source code
- `app/platform/team.py` — Source code
- `app/platform/skill_library.py` — Bandit + learning
