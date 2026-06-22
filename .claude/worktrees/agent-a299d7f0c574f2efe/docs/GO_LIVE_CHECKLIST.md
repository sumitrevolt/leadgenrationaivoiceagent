# ✅ GO-LIVE CHECKLIST — Production Deployment

**Status**: READY TO LAUNCH | **Last Updated**: 2026-06-14  
**Operator**: Sumit | **Launch Date**: [YOUR DATE]

---

## 🟢 PRE-DEPLOYMENT (Do 1-2 Days Before)

- [ ] **Team Communication**
  - [ ] Notify stakeholders: "Deploying on [DATE] [TIME] IST"
  - [ ] Plan maintenance window (off-peak): 02:00-03:00 AM IST recommended
  - [ ] Have rollback plan ready
  
- [ ] **Code Readiness**
  - [ ] All PRs merged to main
  - [ ] Commit message clear: `Production: Agent prompts + operational runbooks`
  - [ ] Latest git tag created: `git tag prod-2026-06-14`
  - [ ] Push: `git push origin main --tags`
  
- [ ] **Tests Passing**
  - [ ] Run: `pytest tests/test_loop_*.py -v`
  - [ ] Expected: `14/14 PASSED`
  - [ ] Coverage: `pytest --cov=app` >80%
  - [ ] E2E: `pytest tests/test_e2e_loop_24h.py -v -s` PASS
  
- [ ] **Configuration Ready**
  - [ ] `.env` has all 4 P0 credentials (or user acknowledges missing):
    - [ ] `RAZORPAY_KEY_ID` = [filled]
    - [ ] `RAZORPAY_KEY_SECRET` = [filled]
    - [ ] `RAZORPAY_WEBHOOK_SECRET` = [filled]
    - [ ] ⚠️ Remaining 3 blockers (DLT/Exotel/UPI) OK to skip now
  - [ ] `.env` backup created: `cp .env .env.backup_pre_deploy`
  
- [ ] **Documentation Ready**
  - [ ] 4 markdown files checked:
    - [ ] `AGENT_SYSTEM_PROMPTS.md` reviewed (12 agents defined)
    - [ ] `FEEDBACK_LOOPS_AND_REFLEXION.md` understood (13 loops mapped)
    - [ ] `TEST_SCENARIOS_LOOP_CLOSURE.md` tests passing
    - [ ] `AGENT_LOOP_PROMPT_MASTER.md` bookmarked
  - [ ] `OPERATIONAL_RUNBOOKS.md` printed & available
  - [ ] `DEPLOYMENT_AUTOMATION.sh` tested (dry-run): `./deploy_production.sh prod --dry-run`

---

## 🔴 DURING DEPLOYMENT (30 min window)

### PRE-DEPLOYMENT WINDOW (5 min)

- [ ] **Stop Traffic (Optional - for safety)**
  - [ ] Post message: "Maintenance: 02:00-02:30 IST"
  - [ ] Or: Continue serving (app has no downtime)
  
- [ ] **Final Verification**
  - [ ] Health check: `curl https://leadsgenai.in/health` → 200 OK
  - [ ] Get current state: `git log --oneline -1` (note: ABC1234)
  - [ ] Note agents active: `curl https://leadsgenai.in/api/platform/team | jq '.roster | length'`
  
- [ ] **SSH Ready**
  - [ ] Open terminal: `ssh -i ~/.ssh/id_rsa root@72.61.245.204`
  - [ ] Verify access (should see VPS prompt)
  - [ ] Have rollback branch ready: `git log --oneline -5` visible

### DEPLOYMENT (15 min)

- [ ] **Run Deployment Script**
  ```bash
  ./scripts/deploy_production.sh prod
  ```
  - [ ] Pre-flight checks PASS
  - [ ] Backup created (check VPS `/opt/leadgen/backups/`)
  - [ ] Health check BEFORE shows: healthy or acceptable
  - [ ] Tests passed (14/14) - if any fail, **STOP and fix**
  - [ ] Git pulled successfully
  - [ ] Containers restarted
  - [ ] Smoke tests ran

- [ ] **Monitor Deployment**
  ```bash
  docker logs leadgen_app -f --tail 50
  ```
  - [ ] Watch for `ERROR`, `FATAL`, `CRITICAL` messages
  - [ ] Should see `INFO` messages about startup
  - [ ] Should NOT see database connection errors
  - [ ] After ~10s, should see "Application started" or similar

- [ ] **Verify Health (Immediately After)**
  ```bash
  curl https://leadsgenai.in/health | jq .
  ```
  - [ ] Response time: <1 second
  - [ ] Status: 200 OK
  - [ ] `environment`: `production`
  - [ ] All services: `healthy`

### POST-DEPLOYMENT CHECKS (10 min)

- [ ] **API Routes Live**
  ```bash
  curl https://leadsgenai.in/openapi.json | jq '.paths | length'
  ```
  - [ ] Should be >330 routes (check vs before: ABC1234)
  - [ ] If lower: **ALERT** - missing routes, investigate logs

- [ ] **Agent Roster**
  ```bash
  curl https://leadsgenai.in/api/platform/team | jq '.roster'
  ```
  - [ ] Shows 12 agents: Boss, Swara, Dev, Rohan, Arjun, Meera, Kavya, Isha, Nikhil, Tara, Vikram, Guru
  - [ ] All status: `active` or `idle` (not `error`)

- [ ] **Database Healthy**
  ```bash
  curl https://leadsgenai.in/health/ready | jq '.'
  ```
  - [ ] `db`: `healthy`
  - [ ] `redis`: `healthy`
  - [ ] Response time: <1 second

- [ ] **Infra Readiness**
  ```bash
  curl https://leadsgenai.in/api/growth/infra/hermes | jq '.readiness_score'
  ```
  - [ ] Score: ≥90 (excellent)
  - [ ] If <50: check alert details, may need investigation

---

## 🟡 FIRST 24 HOURS (Monitor Actively)

### Hour 1-4

- [ ] **Tail Logs Continuously**
  ```bash
  docker logs leadgen_app -f --tail 100 | grep -E "ERROR|CRITICAL|WARN" &
  ```
  - [ ] Watch for errors
  - [ ] No authentication failures
  - [ ] No database timeouts
  - [ ] No memory issues

- [ ] **Check Queue**
  ```bash
  redis-cli LLEN celery
  ```
  - [ ] Should be <50 (normal operations)
  - [ ] If >200: alert, likely jobs piling up (RB-004)

- [ ] **Sample Transactions**
  - [ ] Manually test: New prospect → outreach → call (simulate)
  - [ ] Check logs: No errors during flow
  - [ ] Verify: Prospect appears in DB + cadence scheduled

### Hour 4-24

- [ ] **Daily Monitoring Checklist** (run every 4 hours)
  - [ ] Health: `curl https://leadsgenai.in/health` → 200
  - [ ] Agents: 12 active
  - [ ] Queue: <100 jobs
  - [ ] Memory: <60% via `docker stats`
  - [ ] Error rate: <1% (check logs)
  
- [ ] **Agent Loop Verification** (at scheduled times)
  - [ ] 09:30 IST: DEV ran research? (check `/var/log/leadgen_scheduler.log`)
  - [ ] 10:30 IST: ROHAN sent emails? (check `cadence_runs.jsonl`)
  - [ ] 02:30 IST: ARJUN QA ran? (check `agent_events` table)
  
- [ ] **Revenue/Compliance**
  - [ ] Payment webhook received? (check `webhook_events` table)
  - [ ] Invoice auto-created? (check if `invoices` table has new rows)
  - [ ] Dunning case created? (if needed, check `dunning_cases`)

---

## 🟢 GO-LIVE SUCCESS CRITERIA

**System is production-ready when:**

- [ ] ✅ All 14 tests passing (pre-deploy)
- [ ] ✅ Health check responds 200 (post-deploy)
- [ ] ✅ 12 agents active (roster verified)
- [ ] ✅ No ERROR in logs (first 4 hours)
- [ ] ✅ Queue depth normal (Celery <50)
- [ ] ✅ Database responsive (<1s queries)
- [ ] ✅ Payment webhook fired (at least 1)
- [ ] ✅ Lead loop completed (harvest→qualify→enroll→CRM)
- [ ] ✅ Email sent successfully (SMTP OK)
- [ ] ✅ Infra score ≥90 (monitoring healthy)

**If ANY of above fail: DO NOT DECLARE SUCCESS. Debug 1st.**

---

## 🔴 ROLLBACK CRITERIA (Auto-Trigger If)

If ANY of these happen in first hour:
- [ ] `/health` returns 500 for >2 minutes
- [ ] >50% ERROR in logs
- [ ] Queue backlog >500
- [ ] Memory >80%
- [ ] Database timeout errors
- [ ] Payment processing broken

**Rollback procedure:**
```bash
# Option 1: Revert code
git -C /opt/leadgen reset --hard HEAD~1
docker compose -f /opt/leadgen/docker-compose.vps.yml restart app

# Option 2: Restore from backup
docker compose -f /opt/leadgen/docker-compose.vps.yml stop app
# (restore .env + DB from backup)
docker compose -f /opt/leadgen/docker-compose.vps.yml up -d app

# Verify health
curl https://leadsgenai.in/health
```

---

## 📋 SIGN-OFF CHECKLIST

- [ ] **Go-live Approved By**: _________________ (Sumit)
- [ ] **Date/Time**: _________________________ (2026-06-14 02:00 IST)
- [ ] **Environment**: production
- [ ] **Git Commit**: _________________________ (ABC1234)
- [ ] **Tests Passing**: 14/14 ✅
- [ ] **Health Check**: 200 OK ✅
- [ ] **Agents Active**: 12/12 ✅
- [ ] **No Critical Errors**: ✅
- [ ] **Rollback Ready**: ✅

### Post-Launch Sign-Off (24 hours later)
- [ ] **Uptime**: ___% (target >99.9%)
- [ ] **Transactions Processed**: _____ (prospects → leads)
- [ ] **Payment Success Rate**: ___% (target >95%)
- [ ] **Agent Errors**: _____ (target 0)
- [ ] **System Status**: 🟢 STABLE

---

## 🚀 LAUNCH DAY COMMUNICATION

**Pre-Launch (1 hour before)**:
```
🚀 Production Deployment Starting
Time: [TIME] IST
Window: 30 minutes
Status: Will update in #leadgen-updates Slack channel
```

**During Launch (every 10 min)**:
```
⏳ Deployment in progress...
- Pre-flight: ✅
- Building: ✅
- Deploying: [IN PROGRESS]
- Testing: [PENDING]
```

**Post-Launch**:
```
✅ Production Deployment Complete!
- Health: 🟢 OK
- Agents: 12/12 active
- Tests: 14/14 passed
- Next check: [TIME] IST
Monitoring actively. Will alert if issues.
```

**If Rollback**:
```
🚨 Production Issue Detected
- Issue: [BRIEF DESCRIPTION]
- Action: Initiating rollback to [PREVIOUS COMMIT]
- ETA: 5 minutes
- Will update when stable
```

---

## QUICK REFERENCE (Laminate This!)

| Check | Command | Expected |
|-------|---------|----------|
| Health | `curl https://leadsgenai.in/health \| jq .environment` | `production` |
| Agents | `curl https://leadsgenai.in/api/platform/team \| jq '.roster \| length'` | `12` |
| Routes | `curl https://leadsgenai.in/openapi.json \| jq '.paths \| length'` | `>330` |
| Queue | `redis-cli LLEN celery` | `<100` |
| Memory | `docker stats --no-stream` | `<60%` |
| Logs | `docker logs leadgen_app \| grep ERROR` | `(no output)` |
| DB | `curl https://leadsgenai.in/health/ready \| jq '.db'` | `healthy` |
| Tests | `pytest tests/test_loop_*.py -v` | `14 passed` |

---

## SUCCESS! 🎉

Once all checks pass and system stable for 24 hours:

1. ✅ **Production launch successful**
2. ✅ **Handoff to operations team** (or Sumit solo)
3. ✅ **Update docs with lessons learned**
4. ✅ **Schedule next review**: 2026-07-14 (monthly health check)

**Celebrate! You shipped! 🚀**

---

**Print this page. Keep it handy. Follow it exactly.**
