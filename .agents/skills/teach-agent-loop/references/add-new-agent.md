> Verbatim 6-step guide: add a new AI AGENT (staff member). See SKILL.md for when/risk/testing/safety.

## 6 Steps to Add New Agent (Longer Path)

### Step 1: Define the Agent

**Decide**:
- **Name**: Human first name + last initial (e.g., "Vikram P" → "Vikram")
- **Role**: What's their job? (e.g., "AI Copywriter", "Voice QA Engineer")
- **Responsibilities**: 2–5 specific tasks (not generic)
- **Skills**: Which actions can they execute? (e.g., ["sales_deepdive", "content_pack"])

**Example**:
```
Name: Priya (پریا — reverse research specialist)
Role: Competitive Intelligence Agent
Responsibilities:
  1. Research competitor market moves
  2. Analyze pricing + positioning
  3. Draft differentiation narratives
  
Skills: ["competitor_research", "market_analysis", "narrative_draft"]
```

### Step 2: Create Agent Code

**File**: `app/agents/priya.py`

```python
"""Priya — Competitive Intelligence Agent.

Responsibilities:
  - Research competitor market moves
  - Analyze pricing + positioning  
  - Draft differentiation narratives
  
Safe: draft-only, no auto-post/email.
"""

async def research_competitors(niche: str, city: str = None) -> dict[str, Any]:
    """Research competitors for niche + city."""
    try:
        from app.platform.prospector_store import competitors_for_niche
        from app.voice_agent.free_ai import chat
        
        # Get competitor list
        comps = await competitors_for_niche(niche)
        
        # Draft analysis
        prompt = f"""Niche: {niche}
Competitors: {len(comps)}
List: {', '.join([c['name'] for c in comps[:5]])}

Analyze: positioning, pricing, unique angles. Draft 3 differentiation narratives."""
        
        analysis = await chat(prompt, system="You are market analyst.")
        
        return {
            "ok": True,
            "detail": f"analyzed {len(comps)} competitors",
            "narratives": analysis.split("\n\n"),
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}


async def analyze_pricing(niche: str) -> dict[str, Any]:
    """Analyze competitor pricing."""
    # Similar pattern
    pass


async def draft_differentiation(our_positioning: str, market_analysis: str) -> dict[str, Any]:
    """Draft how we're different."""
    # Similar pattern
    pass
```

### Step 3: Add to Team Roster

**Edit**: `app/platform/team.py`

Find `STAFF` dict (line ~20):

```python
STAFF: dict[str, dict[str, Any]] = {
    "sumit": {"name": "Sumit", "role": "Founder/CEO", ...},
    "isha": {"name": "Isha", "role": "Marketing", ...},
    # ... existing ...
    "priya": {
        "name": "Priya",
        "role": "Competitive Research",
        "emoji": "🔍",
        "capabilities": ["competitor_research", "market_analysis", "narrative_draft"],
        "product": "growth",  # which product domain
        "is_ai": True,
        "actions_allowed": ["competitor_research", "market_analysis"],
    },
}
```

### Step 4: Wire Into Coordinator

**Edit**: `app/agents/coordinator.py`

Add to agent dispatcher (wherever agents are called):

```python
AGENT_HANDLERS = {
    "Riya": riya.research,
    "Dev": dev.competitive_analysis,
    "Priya": priya.research_competitors,  # ← Add here
    "Isha": isha.draft_outreach,
    # ...
}
```

### Step 5: Add to Self-Improve Actions

**Edit**: `app/agents/self_improve.py`

```python
ACTIONS: dict[str, tuple[bool, str]] = {
    # ...
    "competitor_research": (True, "research competitors via Priya (LLM-heavy)"),
}

async def _execute(action: str, task: str) -> dict[str, Any]:
    # ...
    if action == "competitor_research":
        from app.agents.priya import research_competitors
        
        # Pick a niche from recent deals/analysis
        niche = await _pick_niche_from_context()
        res = await research_competitors(niche)
        return {"ok": res.get("ok"), "detail": res.get("detail", "")}
```

Add to stage bias:
```python
_STAGE_ACTIONS = {
    # ...
    "scale": ["competitor_research", ...],  # Help with scaling
}
```

### Step 6: Test & Document

**Test**:
- Coordinator mode="sequential" calling Priya
- Self-improve picking "competitor_research"
- Agent events logged to database
- Team roster `/app/team` shows Priya

**Document**:
- Update team.py docstring with Priya's role
- Add to `docs/TEAM_ROSTER.md` (if exists)
