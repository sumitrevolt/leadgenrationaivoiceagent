> Verbatim end-to-end worked example: add "LinkedIn DM Outreach". See SKILL.md for the general process.

## Worked Example: Add "LinkedIn DM Outreach"

**Step 1: Define**
```
Name: linkedin_dm_outreach
Cost: Light (free-LLM to draft, no API cost for DM)
Risk: Draft-only (humans send manually via LinkedIn UI)
Description: Draft personalized LinkedIn DMs for prospects
```

**Step 2: Write Code**

File: `app/agents/linkedin_outreach.py`
```python
async def draft_linkedin_dms(niche: str, max_prospects: int = 5) -> dict[str, Any]:
    """Draft personalized LinkedIn DMs for prospects in niche."""
    try:
        from app.platform.prospector_store import by_niche
        from app.voice_agent.free_ai import chat
        
        leads = await by_niche(niche, limit=max_prospects)
        
        dms = []
        for lead in leads:
            prompt = f"""LinkedIn connection request + message.
Person: {lead.get('name')} (Title: {lead.get('title')})
Company: {lead.get('company')}
Niche: {niche}

Draft a personalized 1-2 sentence LinkedIn message (no generic stuff). Include
light ask or value prop. Make it feel human."""
            
            msg = await chat(prompt, system="You are LinkedIn outreach expert.")
            dms.append({
                "prospect": lead.get('name'),
                "title": lead.get('title'),
                "message": msg,
            })
        
        return {
            "ok": True,
            "detail": f"{len(dms)} DMs drafted for {niche}",
            "dms": dms,
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}
```

**Step 3: Register in self_improve.py**
```python
ACTIONS = {
    # ...
    "linkedin_dm_draft": (True, "draft LinkedIn DMs for prospects (light LLM)"),
}

if action == "linkedin_dm_draft":
    from app.agents.linkedin_outreach import draft_linkedin_dms
    
    res = await draft_linkedin_dms(max_prospects=3)
    return {"ok": res.get("ok"), "detail": f"{len(res.get('dms', []))} DMs drafted"}
```

**Step 4: Register in skill_library** (auto-learns on first run)

**Step 5: Test**
```bash
# Test 1: Happy path
python << 'EOF'
import asyncio
from app.agents.linkedin_outreach import draft_linkedin_dms

result = asyncio.run(draft_linkedin_dms("solar"))
print(f"✅ {len(result['dms'])} DMs" if result["ok"] else f"❌ {result['detail']}")
EOF

# Test 2: Zero prospects
# Test 3: LLM down
# Test 4: Timeout
# Test 5: Rate-limit
```

**Step 6: Enable & Monitor**
```bash
# No special env flag needed (draft-only)
# Monitor:
python scripts/automation_health_audit.py --weekly-audit | grep linkedin_dm_draft
```
