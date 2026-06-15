> Verbatim 6-step guide: add a new self-improve ACTION. See SKILL.md for when/risk/testing/safety.

## 6 Steps to Add New Action (Fastest Path)

### Step 1: Define the Action

**Decide**:
- **Name** (snake_case, <30 chars): e.g., `linkedin_outreach`, `sms_campaign`, `gchat_followup`
- **Cost** (LLM-heavy or light?): Does it call free_ai.chat? Costs money?
- **Risk level** (auto-safe, draft-only, approval-required?):
  - **auto-safe**: `scrape_leads`, `seo_pages` (no send/post)
  - **draft-only**: `sales_deepdive`, `social_drafts` (humans click to send)
  - **approval-required**: `email_campaign`, `voice_calls` (sensitive, needs review)

**Example**:
```
Name: sms_campaign_draft
Cost: Light (free-LLM to draft SMS content)
Risk: Draft-only (humans click send via UI)
Description: Draft bulk SMS campaigns for opted-in leads per niche
```

### Step 2: Write Code (or Reuse Existing)

**Option A: New code** (if feature doesn't exist)

Create `app/agents/sms_agent.py`:
```python
"""SMS campaign drafting for self-improve + coordinator."""

async def draft_sms_campaigns(niche: str = None, limit: int = 5) -> dict[str, Any]:
    """Draft SMS campaigns for opted-in leads.
    
    Returns: {ok: bool, detail: str, campaigns: [{content, audience_size, cta}]}
    """
    try:
        from app.integrations.sms_dlt import list_approved_templates
        from app.platform.prospector_store import by_niche
        from app.voice_agent.free_ai import chat
        
        # Get leads
        niche = niche or random.choice(list(NICHES.keys()))
        leads = await by_niche(niche, limit=limit)
        
        # Draft campaign
        lesson = "SMS + email combo works better (32% open vs. 18% email alone)"
        prompt = f"""Niche: {niche}
Leads: {len(leads)} opted-in prospects
Known: {lesson}

Draft 2 SMS variants (max 160 chars) for this niche. Use emojis, CTA link."""
        
        msgs = await chat(prompt, system="You are SMS copywriter.")
        
        return {
            "ok": True,
            "detail": f"{len(leads)} leads in {niche}",
            "campaigns": [{"content": m, "audience": len(leads)} for m in msgs.split("\n\n")],
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}
```

**Option B: Reuse existing** (if feature already exists)

Find the function in existing code:
```python
from app.marketing import whatsapp_campaign
# whatsapp_campaign.draft_bulk_campaign(niche) already exists ✓
```

Then wrap it:
```python
async def draft_whatsapp_campaign(niche: str = None) -> dict[str, Any]:
    """Reuse existing whatsapp drafting for self-improve."""
    try:
        result = await whatsapp_campaign.draft_bulk_campaign(niche)
        return {"ok": result.get("ok"), "detail": result.get("summary", "")}
    except Exception as e:
        return {"ok": False, "detail": str(e)}
```

### Step 3: Register in Action Dispatch

**Edit**: `app/agents/self_improve.py`

Add to `ACTIONS` dict (line ~168):
```python
ACTIONS: dict[str, tuple[bool, str]] = {
    # ... existing ...
    "sms_campaign_draft": (False, "draft bulk SMS for opted-in leads (light LLM)"),
}
```

Add execution logic in `async def _execute()` (line ~283):
```python
if action == "sms_campaign_draft":
    from app.agents.sms_agent import draft_sms_campaigns
    
    res = await draft_sms_campaigns(limit=3)
    return {
        "ok": res.get("ok"),
        "detail": f"{res.get('detail', '')} → {len(res.get('campaigns', []))} variants drafted"
    }
```

Add to stage bias in `_STAGE_ACTIONS` (line ~190):
```python
_STAGE_ACTIONS = {
    "lead_supply": ["harvest_leads", "scrape_leads", "seo_pages", ...],
    "outreach_quality": ["sms_campaign_draft", "sales_deepdive", ...],  # ← Add here
    ...
}
```

### Step 4: Register in Skill Library

**Edit**: `app/platform/skill_library.py`

Initial entry (auto-learns on first run):
```python
# self-improve will call skill_library.record_use() after task completes
# No manual registration needed — learns from runs
```

**Optional**: Pre-populate success expectation:
```bash
# Manual lesson (if you know it'll be ~80% successful):
python -c "
from app.platform import skill_library
skill_library.record_lesson(
    'sms_campaign_draft',
    'SMS drafting works well (fast, low-cost), humans decide on send',
    source='manual'
)
"
```

### Step 5: Test (5 Runs)

**Local test** (no Docker):
```bash
cd C:\Users\Ratanshila\Documents\leadgenrationaiagent

# Set env (if new integration):
export SMS_DLT_ENABLED=1
export SMS_PROVIDER_URL=https://...

# Test the action directly:
python << 'EOF'
import asyncio
from app.agents.sms_agent import draft_sms_campaigns

result = asyncio.run(draft_sms_campaigns(niche="plumbing", limit=3))
print("✅ PASS" if result["ok"] else f"❌ FAIL: {result['detail']}")
EOF
```

**Test via self-improve** (if enabled):
```bash
# Trigger via API:
curl -X POST http://localhost:8000/api/growth/selfimprove/run-action \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"action": "sms_campaign_draft", "task": "test"}'

# Monitor:
tail -f logs/automation.log | grep sms_campaign_draft
```

**Test scenarios** (5 required):

1. ✅ **Happy path**: Valid niche, >1 leads, SMS drafted
2. ✅ **Empty niche**: No leads found, returns ok=False gracefully
3. ✅ **LLM down**: free_ai.chat fails, fallback returns static template (if exists)
4. ✅ **Timeout**: Task runs >240s, watchdog cancels, logged in DLQ
5. ✅ **Rate-limit**: API quota hit, task paused, retried next cycle

**Example test output**:
```
Test 1 (happy path): ✅ PASS
  Input: niche=plumbing, limit=3
  Output: ok=True, detail="3 leads in plumbing", campaigns=[2 variants]
  
Test 2 (empty niche): ✅ PASS
  Input: niche=nonexistent
  Output: ok=False, detail="no leads found" (graceful)
  
Test 3 (LLM down): ✅ PASS
  Input: free_ai.chat mocked to fail
  Output: ok=True, detail="fallback template", campaigns=[1 static]
  
Test 4 (timeout): ✅ PASS
  Input: task takes 300s
  Behavior: Watchdog cancels after 240s, logged in DLQ
  
Test 5 (rate-limit): ✅ PASS
  Input: API quota 429
  Behavior: Task paused, re-queued, retried next cycle (watchdog.ensure_alive)
```

### Step 6: Enable & Monitor (2 weeks)

**Enable in prod**:
```bash
# For most actions, no env flag needed — it auto-runs if SELF_IMPROVE_LOOP=1
# But if your action has an integration flag:

export SMS_DLT_ENABLED=1
systemctl restart leadgen
```

**Monitor first 2 weeks**:
```bash
# Daily:
python scripts/automation_health_audit.py --daily-check | grep sms_campaign_draft

# Weekly:
python scripts/automation_health_audit.py --weekly-audit
# Check: success rate (should stabilize >70%), cost (should be <$1/run), no DLQ failures

# Sample command (run weekly):
grep '"action":"sms_campaign_draft"' data/self_improve_runs.jsonl | tail -10
```

**Expected growth curve**:
- Week 1: Success rate 50–80% (learning phase)
- Week 2: Success rate stabilizes 75–90%
- Week 3+: Rate stays stable, self-improve learns best use cases

**If success rate <60% after 2 weeks**:
- Check error logs: `grep sms_campaign_draft logs/*.log`
- Inspect failed runs: `grep -A 2 '"ok":false' data/self_improve_runs.jsonl | grep sms`
- Fix bug or adjust parameters
- Or disable action temporarily: remove from `_STAGE_ACTIONS`
