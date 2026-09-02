# Phase 6 Deployment Guide
## Safety Gates for Self-Improve Loop

**Delivery Date**: 2026-06-14  
**Estimated effort**: 4 hours implementation, 30 min deployment

---

## What's New

Phase 6 adds **human-in-the-loop safety gates** to the self-improving loop:

1. **Cost tracking** — tracks daily LLM spending, blocks tasks exceeding budget
2. **Approval queue** — pauses LLM-heavy actions for admin approval before executing

Both are **gated** — cost tracking always on, approval gates optional (`SELF_IMPROVE_APPROVAL=0/1`).

---

## Deployment Steps

### Step 1: Pull changes
```bash
cd /opt/leadgen
git pull origin main
```

Expected changes:
```
✅ Modified: app/agents/self_improve.py (+150 lines)
✅ Modified: app/api/growth.py (+80 lines)
✅ Modified: frontend/automation.html (+180 lines)
✅ Modified: .env (+2 lines)
✅ Added: scripts/test_phase6_safety_gates.py
✅ Added: .claude/skills/self-improve-control/PHASE6_IMPLEMENTATION.md
✅ Added: docs/PHASE6_DEPLOYMENT_GUIDE.md
```

### Step 2: Verify syntax
```bash
# Python syntax check
python3 -m py_compile app/agents/self_improve.py app/api/growth.py
echo "✅ Python syntax OK"

# Run Phase 6 unit tests
python3 scripts/test_phase6_safety_gates.py
# Expected output: "✅ ALL PHASE 6 TESTS PASSED"
```

### Step 3: Update environment
```bash
# .env already updated, verify these lines exist:
grep "SELF_IMPROVE_APPROVAL" .env
grep "SELFIMPROVE_COST_CAP" .env

# Output should be:
# SELF_IMPROVE_APPROVAL=0
# SELFIMPROVE_COST_CAP=50

# If missing, add to .env:
echo -e "\n# Self-Improve Safety (Phase 6)" >> .env
echo "SELF_IMPROVE_APPROVAL=0" >> .env
echo "SELFIMPROVE_COST_CAP=50" >> .env
```

### Step 4: Rebuild and restart
```bash
# Docker rebuild (app image)
docker compose -f docker-compose.vps.yml build app

# Restart services
docker compose -f docker-compose.vps.yml up -d app worker scheduler

# Verify health
sleep 5
curl -s https://leadsgenai.in/health/ready | jq '.environment'
# Should show: "production"
```

### Step 5: Verify UI
```bash
# Check if automation.html loads (hard reload may be needed in browser)
curl -s -I https://leadsgenai.in/app/automation | grep "200"
# Should show: "HTTP/2 200"

# Manual browser check:
# 1. Go to https://leadsgenai.in/app/admin-login
# 2. Login with admin credentials
# 3. Click "🤖 Automation Mission Control"
# 4. Click "📥 Approvals" tab
# 5. Verify 3 sections visible:
#    - 💰 Self-Improve Cost Tracking
#    - ✋ Self-Improve Approval Queue
#    - 📥 Process Breakpoints + Code Patches
```

### Step 6: Test API endpoints
```bash
# Get admin token (from login or env)
TOKEN="your-admin-token"

# Test cost status endpoint
curl -s -H "Authorization: Bearer $TOKEN" \
  https://leadsgenai.in/api/growth/selfimprove/cost-status | jq .

# Expected output:
# {
#   "date": "2026-06-14",
#   "cap": 50.0,
#   "spent": 0.0,
#   "remaining": 50.0,
#   "pct_used": 0.0,
#   "tasks": []
# }

# Test approval queue endpoint
curl -s -H "Authorization: Bearer $TOKEN" \
  https://leadsgenai.in/api/growth/selfimprove/approvals-pending | jq .

# Expected output:
# {
#   "approval_required": false,
#   "pending_count": 0,
#   "pending": [],
#   "approved_count": 0
# }
```

---

## Configuration

### Enable approval gates (optional)
```bash
# Edit .env on VPS
echo "SELF_IMPROVE_APPROVAL=1" >> /opt/leadgen/.env

# Restart app
docker compose -f docker-compose.vps.yml restart app

# Now LLM-heavy actions will queue for approval
```

### Adjust budget cap
```bash
# Default $50/day, change to $100
echo "SELFIMPROVE_COST_CAP=100" >> /opt/leadgen/.env
docker compose -f docker-compose.vps.yml restart app
```

---

## Testing Guide

### Unit tests
```bash
python3 /opt/leadgen/scripts/test_phase6_safety_gates.py
```

### Integration test
```bash
# Manually trigger one loop tick with approval gate enabled
SELF_IMPROVE_APPROVAL=1 SELFIMPROVE_COST_CAP=5 python3 -c "
from app.agents import self_improve
import asyncio
result = asyncio.run(self_improve.run_once())
print('Loop result:', result)
"
```

### Manual UI test (5 min)
1. Set `SELF_IMPROVE_APPROVAL=1` + low cap ($5)
2. Click "🗓️ Schedule" → "▶️ Ek tick abhi"
3. Click "📥 Approvals" → "✋ Self-Improve Approval Queue" → "Load"
4. Verify: pending task card appears with cost + reason
5. Click "✅ Approve" → "✅ Approved" toast
6. Loop resumes on next tick

---

## Monitoring

### Daily checks
```bash
# Check cost tracking
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://leadsgenai.in/api/growth/selfimprove/cost-status

# Watch for approaching budget
# If pct_used > 80%, consider increasing SELFIMPROVE_COST_CAP
```

### Audit log
```bash
# Review approval decisions
tail -20 /opt/leadgen/data/self_improve_approvals.jsonl | jq .

# Review costs
tail -20 /opt/leadgen/data/self_improve_runs.jsonl | jq '.[] | {action, cost, ok}'
```

### Logs
```bash
# Check for errors
docker logs leadgen_app 2>&1 | grep -i "self_improve\|cost\|approval"

# Should see normal lines like:
# "[self-improve] approval_pending: sales_deepdive"
# "[self-improve] budget cap: spent $15.0, need $2.5"
```

---

## Rollback

If Phase 6 causes issues:

### Option 1: Disable gates (keep feature, disable safety)
```bash
echo "SELF_IMPROVE_APPROVAL=0" >> /opt/leadgen/.env
echo "SELFIMPROVE_COST_CAP=999999" >> /opt/leadgen/.env
docker compose -f docker-compose.vps.yml restart app
```

### Option 2: Full rollback (revert commits)
```bash
cd /opt/leadgen
git log --oneline | head -10
# Find Phase 6 commit hash (likely has "Phase 6" in message)
git revert <hash>
docker compose -f docker-compose.vps.yml build app
docker compose -f docker-compose.vps.yml up -d app
```

---

## Success criteria

Phase 6 is successfully deployed when:

- [ ] ✅ `scripts/test_phase6_safety_gates.py` runs without errors
- [ ] ✅ `/app/automation` → "📥 Approvals" tab visible + loads
- [ ] ✅ `/api/growth/selfimprove/cost-status` returns valid JSON
- [ ] ✅ `/api/growth/selfimprove/approvals-pending` returns valid JSON
- [ ] ✅ Manual test: approve/reject buttons work
- [ ] ✅ Cost logged to `/data/self_improve_runs.jsonl` (check `cost` field)
- [ ] ✅ Approvals logged to `/data/self_improve_approvals.jsonl`
- [ ] ✅ No errors in `docker logs leadgen_app`

---

## Troubleshooting

| Issue | Diagnosis | Fix |
|---|---|---|
| Approvals tab shows "Load ho raha..." | API not responding | Check `/health/ready`, ensure admin token in localStorage |
| "Cost tracking not available" | cost_status() returns None | Restart app, check env vars loaded |
| Approve button disappears after click | JS error or fetch fail | Check browser console (F12), admin token valid? |
| Pending approvals don't appear even with SELF_IMPROVE_APPROVAL=1 | No LLM-heavy tasks queued yet | Trigger manual loop tick via Schedule tab |
| "token chakiye" error on API call | Missing authorization header | Ensure `accessToken` saved in localStorage after login |

---

## Support

Questions or issues?

1. Check `/app/automation` → "🏠 Aaj" tab for active problems
2. Review logs: `docker logs leadgen_app | tail -50`
3. Check audit trail: `tail -20 /opt/leadgen/data/self_improve_approvals.jsonl`
4. Reference: `docs/PHASE6_DEPLOYMENT_GUIDE.md` (this file)

---

## Next phases

- **Phase 7** (future): Cost-aware action selection (pick cheaper tasks when budget low)
- **Phase 8** (future): Weekly budgets + rolling window costs
- **Phase 9** (future): Predictive cost warnings ("budget might exceed next week")
