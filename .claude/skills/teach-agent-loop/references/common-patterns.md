> Verbatim reusable code patterns for new actions (LLM-heavy / data-read / gated). See SKILL.md.

## Common Patterns

### Pattern: LLM-Heavy Action (Drafting)

```python
async def draft_something(niche: str) -> dict[str, Any]:
    try:
        from app.voice_agent import free_ai
        
        # Prepare input
        context = f"niche={niche}"
        
        # Call LLM (with fallback)
        try:
            result = await free_ai.chat(context, system="you are copywriter")
        except Exception:
            result = "Static fallback template"  # fail-open
        
        # Return outcome
        return {
            "ok": True,
            "detail": f"drafted for {niche}",
            "output": result,
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}
```

### Pattern: Data-Read Action (No Side Effects)

```python
async def analyze_something(niche: str) -> dict[str, Any]:
    try:
        from app.platform.prospector_store import by_niche
        
        data = await by_niche(niche)
        
        analysis = {
            "count": len(data),
            "avg_score": sum(d["score"] for d in data) / len(data) if data else 0,
        }
        
        return {
            "ok": bool(data),
            "detail": f"analyzed {len(data)} records",
            "analysis": analysis,
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}
```

### Pattern: Gated Action (Requires Flag)

```python
async def send_email_bulk(niche: str) -> dict[str, Any]:
    # Check gate
    if not os.environ.get("AUTO_EMAIL_OUTREACH", "").lower() in ("1", "true"):
        return {"ok": False, "detail": "AUTO_EMAIL_OUTREACH not enabled"}
    
    # Check cost
    cost_est = 0.1  # $ per email
    today_budget = float(os.environ.get("SELFIMPROVE_COST_CAP", "50"))
    if cost_est > today_budget * 0.2:  # Don't spend >20% on one action
        return {"ok": False, "detail": "cost would exceed daily allocation"}
    
    # Proceed
    try:
        # email sending code
        return {"ok": True, "detail": "sent X emails"}
    except Exception as e:
        return {"ok": False, "detail": str(e)}
```

