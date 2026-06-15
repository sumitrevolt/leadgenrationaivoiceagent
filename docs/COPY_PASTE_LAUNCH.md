# 🚀 COPY-PASTE LAUNCH GUIDE

**Status**: Ready to execute  
**Time**: 30 minutes  
**Action**: Copy each section, run in order  

---

## DESKTOP (Your Local Machine)

### 1️⃣ Copy Agent Prompts to Code

```bash
cp app_platform_agent_system_prompts.py app/platform/agent_system_prompts.py
```

**Expected**: No error, file appears at `app/platform/agent_system_prompts.py`

---

### 2️⃣ Update free_ai.py (Add Import)

Open `app/voice_agent/free_ai.py` and add this at the TOP:

```python
from app.platform.agent_system_prompts import get_system_prompt
```

Then find the main `chat()` function and update it to use:

```python
# Before: async def chat(system: str = None, messages: list, **kwargs):
# After:
async def chat(system: str = None, messages: list, agent_name: str = None, **kwargs):
    if agent_name and not system:
        system = get_system_prompt(agent_name)
    # ... rest of function
```

**Expected**: File saved, no syntax errors

---

### 3️⃣ Run Tests

```bash
pytest tests/test_loop_*.py -v --tb=short
```

**Expected Output**:
```
test_dev_research_creates_prospect_db PASSED
test_score_prospect_hot_lead_flag PASSED
... (14 total)
================== 14 passed in 8.23s ==================
```

**If any fail**: STOP. Fix it before proceeding.

---

### 4️⃣ Commit & Push

```bash
git add app/platform/agent_system_prompts.py
git add AGENT_SYSTEM_PROMPTS.md FEEDBACK_LOOPS_AND_REFLEXION.md TEST_SCENARIOS_LOOP_CLOSURE.md AGENT_LOOP_PROMPT_MASTER.md
git add DEPLOYMENT_AUTOMATION.sh OPERATIONAL_RUNBOOKS.md GO_LIVE_CHECKLIST.md DEPLOY_VERIFICATION_CHECKLIST.md

git commit -m "Production launch: Agent system prompts + operational runbooks (14 tests PASS)"

git tag prod-2026-06-14-launch

git push origin main --tags
```

**Expected**: All files pushed, tag created

---

## VPS (Your Server: 72.61.245.204)

### 5️⃣ SSH to VPS

```bash
ssh -i ~/.ssh/id_rsa root@72.61.245.204
```

**Expected**: You're now on VPS (terminal shows `root@...`)

---

### 6️⃣ Pull Latest Code

```bash
cd /opt/leadgen
git pull origin main
```

**Expected**:
```
Updating ABC1234..DEF5678
Fast-forward
 app/platform/agent_system_prompts.py | 350 +++++++++++++
 AGENT_SYSTEM_PROMPTS.md              | 1200 +++++
 ... (more files)
```

---

### 7️⃣ Restart Containers

```bash
docker compose -f docker-compose.vps.yml restart app worker scheduler
```

**Expected**:
```
[+] Restarting 3/3
  ✔ leadgen_app Restarted
  ✔ leadgen_worker Restarted  
  ✔ leadgen_scheduler Restarted
```

---

### 8️⃣ Wait 15 seconds for startup

```bash
sleep 15
```

---

### 9️⃣ Check Health

```bash
curl http://127.0.0.1:8000/health
```

**Expected**:
```json
{
  "status": "healthy",
  "environment": "production",
  "version": "latest"
}
```

---

## BACK TO DESKTOP

### 🔟 Verify Externally

```bash
# Health check (external)
curl https://leadsgenai.in/health | jq .

# Agent roster (should be 12)
curl https://leadsgenai.in/api/platform/team | jq '.roster | length'

# Routes count (should be >330)
curl https://leadsgenai.in/openapi.json | jq '.paths | length'

# Infra readiness (should be ≥90)
curl https://leadsgenai.in/api/growth/infra/hermes | jq '.readiness_score'
```

**Expected**:
```
200 OK
12
>330
≥90
```

---

## ✅ SUCCESS CHECKLIST

If ALL of these are ✅:

- [ ] Tests: 14/14 PASS
- [ ] Health: 200 OK, environment=production
- [ ] Agents: 12 active
- [ ] Routes: >330
- [ ] Infra: ≥90
- [ ] Logs: No ERROR (check `docker logs leadgen_app`)

**Then you're LIVE!** 🚀

---

## 🚨 TROUBLESHOOTING

| Problem | Fix |
|---------|-----|
| Test fails | Run `pytest tests/test_loop_*.py -v` alone, debug, commit fix, push, re-pull on VPS |
| Health 500 | Check logs: `docker logs leadgen_app --tail 50` |
| Agents not 12 | Verify agent_system_prompts.py copied correctly |
| Routes <330 | Run `git status` on VPS, might not have pulled latest |
| Container won't start | Check errors: `docker compose logs app` |

---

## 📞 SUPPORT

If stuck, check these in order:

1. **OPERATIONAL_RUNBOOKS.md** — Find your issue (RB-001 to RB-012)
2. **DEPLOY_VERIFICATION_CHECKLIST.md** — Full verification steps
3. **LAUNCH_SUMMARY.txt** — TL;DR reference

---

## 🎉 YOU DID IT!

Once all ✅: Production is LIVE with 12 agents + 13 loops + full operations.

**Aashchal! 🚀**
