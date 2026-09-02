# 🚀 OPERATIONAL RUNBOOKS — Production Incident & Operations Playbooks

**Platform**: LeadGenAI | **Date**: 2026-06-14  
**Audience**: Sumit (operator), on-call engineer  
**Purpose**: Step-by-step playbooks for every common scenario

---

## 📋 QUICK REFERENCE

| Scenario | Severity | Time to Fix | Runbook |
|----------|----------|-------------|---------|
| App unhealthy (500 errors) | P0 | 5 min | RB-001 |
| Database slow/stuck | P0 | 10 min | RB-002 |
| Payment webhook failing | P0 | 5 min | RB-003 |
| Queue backlog (>500 jobs) | P1 | 10 min | RB-004 |
| Memory leak / OOM | P1 | 15 min | RB-005 |
| Agent not running (missing heartbeat) | P1 | 10 min | RB-006 |
| Call stream dropout | P1 | 5 min | RB-007 |
| Email delivery failing | P2 | 10 min | RB-008 |
| Need to scale (traffic spike) | P2 | 20 min | RB-009 |
| Backup failed | P2 | 15 min | RB-010 |
| Need to deploy code change | P2 | 15 min | RB-011 |
| Suspected data corruption | P0 | 30 min | RB-012 |
| Production go-live / launch verification | P2 | 30 min | RB-013 |

---

## RB-001: App Unhealthy / 500 Errors

**Indicators**: `/health` returns 500 or error, users report "site down"  
**Time-to-fix**: 5 minutes

### STEP 1: Diagnose (1 min)
```bash
# SSH to VPS
ssh -i ~/.ssh/id_rsa root@72.61.245.204

# Check health
curl http://127.0.0.1:8000/health
# Expected: 200 OK, environment=production

# Check logs
docker logs leadgen_app -f --tail 50
# Look for: ERROR, exception, traceback

# Check container status
docker compose -f /opt/leadgen/docker-compose.vps.yml ps
# Expected: all containers "Up"
```

### STEP 2: Triage (2 min)
**If error is "connection refused"**:
→ Database crashed (RB-002)

**If error is "out of memory"**:
→ Memory leak (RB-005)

**If error is "timeout"**:
→ Database slow (RB-002)

**If error is "module not found"**:
→ Code deployment issue (RB-011)

### STEP 3: Restart (2 min)
```bash
# Least invasive: restart app only (keep DB alive)
docker compose -f /opt/leadgen/docker-compose.vps.yml restart app

# Check health (wait 10s)
sleep 10
curl http://127.0.0.1:8000/health

# If still down: restart all
docker compose -f /opt/leadgen/docker-compose.vps.yml restart

# Wait 15s, recheck
sleep 15
curl http://127.0.0.1:8000/health
```

### STEP 4: Escalate (if still down)
```bash
# Check disk space
df -h /opt/leadgen
# If <10% free: emergency cleanup (RB-010)

# Check DB connection
docker exec leadgen_app python -c "from app.main import get_db; db=next(get_db()); print('DB OK')"

# If DB fails: RB-002

# Rollback last deploy if recent
docker compose -f /opt/leadgen/docker-compose.vps.yml stop app
git -C /opt/leadgen reset --hard HEAD~1
docker compose -f /opt/leadgen/docker-compose.vps.yml up -d app
```

---

## RB-002: Database Slow / Stuck

**Indicators**: Queries take >5s, connections frozen, app timeout  
**Time-to-fix**: 10 minutes

### STEP 1: Check DB Status (2 min)
```bash
# Connect to Postgres
docker exec -it leadgen_db psql -U leadgen -d leadgen

# Inside psql:
-- Check active queries
SELECT pid, usename, state, query FROM pg_stat_activity WHERE state != 'idle' LIMIT 10;

-- Check connections
SELECT count(*) FROM pg_stat_activity;
-- Expected: <8 (pool size 8)

-- Check locks
SELECT * FROM pg_locks WHERE NOT granted;
-- If >0 locks: transaction deadlock

-- Check table sizes
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) 
FROM pg_tables WHERE schemaname = 'public' ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 5;
```

### STEP 2: Clear Stale Connections (3 min)
```bash
# If connections stuck
docker exec leadgen_db psql -U leadgen -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < NOW() - INTERVAL '10 minutes';"

# Force pool reset
docker compose -f /opt/leadgen/docker-compose.vps.yml stop leadgen_pgbouncer
sleep 2
docker compose -f /opt/leadgen/docker-compose.vps.yml up -d leadgen_pgbouncer
```

### STEP 3: Rebuild Indexes (5 min)
```bash
# If table bloated
docker exec leadgen_db psql -U leadgen -d leadgen -c "VACUUM FULL ANALYZE leads;"

# Rebuild biggest index
docker exec leadgen_db psql -U leadgen -d leadgen -c "REINDEX TABLE prospects;"
```

### STEP 4: Restart DB (if severe)
```bash
# Last resort: restart DB container
docker compose -f /opt/leadgen/docker-compose.vps.yml stop leadgen_db

# Wait for clean shutdown
sleep 5

# Restart
docker compose -f /opt/leadgen/docker-compose.vps.yml up -d leadgen_db

# Wait for DB ready
sleep 10

# Restart app
docker compose -f /opt/leadgen/docker-compose.vps.yml up -d app
```

---

## RB-003: Payment Webhook Failing

**Indicators**: Dunning emails not sent, subscriptions stuck "pending_payment"  
**Time-to-fix**: 5 minutes

### STEP 1: Check Webhook Status (2 min)
```bash
# SSH to VPS
ssh root@72.61.245.204

# Check recent webhook errors
docker logs leadgen_app | grep -i "webhook\|razorpay" | tail -20

# Check Postgres webhook table
docker exec leadgen_db psql -U leadgen -d leadgen << 'EOF'
SELECT id, event_type, status, created_at FROM webhook_events 
WHERE event_type LIKE '%razorpay%' 
ORDER BY created_at DESC LIMIT 10;
EOF
```

### STEP 2: Verify Razorpay Credentials (1 min)
```bash
# Check .env has credentials
docker exec leadgen_app grep "RAZORPAY" /app/.env | grep -v "SECRET"

# If missing or wrong: update .env
nano /opt/leadgen/.env
# Add: RAZORPAY_KEY_ID=<key>
#      RAZORPAY_KEY_SECRET=<secret>
#      RAZORPAY_WEBHOOK_SECRET=<secret>

# Restart app
docker compose -f /opt/leadgen/docker-compose.vps.yml restart app
```

### STEP 3: Re-register Webhook (1 min)
```bash
# Razorpay Dashboard → Settings → Webhooks
# Verify URL: https://leadsgenai.in/api/billing/webhooks/razorpay
# Verify secret is set in .env

# Test webhook manually
docker exec leadgen_app python << 'EOF'
from app.api.webhooks import webhook_razorpay
import json

test_payload = {
    "event": "payment.captured",
    "payload": {
        "payment": {
            "id": "pay_test",
            "amount": 299900,
            "status": "captured",
            "email": "test@test.com"
        }
    }
}

result = asyncio.run(webhook_razorpay(json.dumps(test_payload)))
print(f"Test webhook: {result}")
EOF
```

### STEP 4: Recover Failed Payments (1 min)
```bash
# Find stuck subscriptions
docker exec leadgen_db psql -U leadgen -d leadgen << 'EOF'
SELECT id, client_id, status, updated_at FROM subscriptions 
WHERE status = 'pending_payment' 
AND updated_at < NOW() - INTERVAL '24 hours';
EOF

# Mark as recovered (if payment now confirmed in Razorpay)
docker exec leadgen_db psql -U leadgen -d leadgen << 'EOF'
UPDATE subscriptions SET status = 'active' 
WHERE status = 'pending_payment' 
AND id = <subscription_id>;

-- Or trigger dunning recovery manually
INSERT INTO dunning_cases (subscription_id, reason, status) 
VALUES (<sub_id>, 'payment_webhook_recovery', 'open');
EOF
```

---

## RB-004: Queue Backlog (>500 Jobs)

**Indicators**: Celery queue depth alert, jobs slow to process  
**Time-to-fix**: 10 minutes

### STEP 1: Check Queue Size (1 min)
```bash
# SSH to VPS
ssh root@72.61.245.204

# Check Redis queue depth
redis-cli LLEN celery
# Expected: <100 (normal)

# If >500: backlog exists
redis-cli LLEN dlq:failed_tasks
# Expected: <20 (failed jobs)
```

### STEP 2: Identify Long-Running Jobs (2 min)
```bash
# Check Celery workers
docker exec leadgen_worker celery -A app.worker inspect active

# Check slow tasks
docker exec leadgen_worker celery -A app.worker inspect stats | grep time_limit

# If tasks >3 minutes: kill them
docker exec leadgen_worker celery -A app.worker control shutdown
sleep 5
docker compose -f /opt/leadgen/docker-compose.vps.yml up -d worker
```

### STEP 3: Scale Workers (3 min)
```bash
# Check current worker concurrency
docker inspect leadgen_worker | grep CONCURRENCY

# Increase concurrency (if backlog >500)
docker exec leadgen_worker celery -A app.worker control pool_grow 4

# Or restart with higher concurrency
CELERY_WORKER_CONCURRENCY=8 \
docker compose -f /opt/leadgen/docker-compose.vps.yml up -d worker
```

### STEP 4: Clean DLQ (2 min)
```bash
# If many failed jobs
redis-cli LLEN dlq:failed_tasks

# View sample failures
redis-cli LRANGE dlq:failed_tasks 0 10

# Purge old failed jobs (>7 days)
# (manual: via Redis cleanup script)

# Retry failed jobs
docker exec leadgen_app python << 'EOF'
from app.tasks.dlq import retry_failed_tasks
result = retry_failed_tasks(max_age_days=1)
print(f"Retried {result['count']} jobs")
EOF
```

### STEP 5: Monitor Drain (5 min)
```bash
# Watch queue shrink
watch -n 2 'redis-cli LLEN celery'

# Should decrease 50-100/min
# If stuck: check worker logs for errors
docker logs leadgen_worker -f --tail 100
```

---

## RB-005: Memory Leak / OOM

**Indicators**: Container restarts, "killed" in logs, OOMKilled event  
**Time-to-fix**: 15 minutes

### STEP 1: Verify OOM (2 min)
```bash
# Check recent restarts
docker inspect leadgen_app | grep -A5 State

# Check memory usage
docker stats leadgen_app --no-stream
# Expected: <500MB (limit 1GB)

# Check dmesg for OOM killer
docker exec leadgen_app dmesg | grep -i oom | tail -5
```

### STEP 2: Identify Memory Hog (5 min)
```bash
# Get memory breakdown
docker exec leadgen_app python << 'EOF'
import tracemalloc
import psutil

# Top memory consumers
p = psutil.Process()
print(f"Total: {p.memory_info().rss / 1e9:.2f} GB")

# Check for loaded modules
import sys
modules = sorted(sys.modules.items(), key=lambda x: x[1].__sizeof__() if hasattr(x[1], '__sizeof__') else 0, reverse=True)[:10]
for name, mod in modules:
    try:
        size = mod.__sizeof__() / 1e6
        if size > 10:
            print(f"  {name}: {size:.1f} MB")
    except:
        pass
EOF

# Common culprits:
# - Cache not cleared (Redis or in-memory)
# - Large dataset not paginated
# - Open file handles
```

### STEP 3: Fix & Restart (8 min)

**If cache issue**:
```bash
# Clear Redis cache
redis-cli FLUSHDB

# Clear app in-memory cache
docker exec leadgen_app python -c "from app.cache import clear_all; clear_all()"

# Restart app
docker compose -f /opt/leadgen/docker-compose.vps.yml restart app
```

**If not fixed**:
```bash
# Deploy fix (code change to prevent leak)
git -C /opt/leadgen pull origin main
docker compose -f /opt/leadgen/docker-compose.vps.yml up -d --build app

# Monitor
watch -n 5 'docker stats leadgen_app --no-stream'
```

---

## RB-006: Agent Not Running (Missing Heartbeat)

**Indicators**: Arjun hasn't run QA in 3+ hours, scheduler log shows skip  
**Time-to-fix**: 10 minutes

### STEP 1: Check Scheduler (2 min)
```bash
# SSH to VPS
ssh root@72.61.245.204

# Check if scheduler is running
docker ps | grep leadgen_scheduler

# Check scheduler logs
docker logs leadgen_scheduler -f --tail 20

# Check heartbeat file
docker exec leadgen_app ls -lh /opt/leadgen/data/job_heartbeats.json
```

### STEP 2: Check Agent Heartbeat (2 min)
```bash
# Check if agent ran recently
docker exec leadgen_app python << 'EOF'
import json
from datetime import datetime, timedelta

with open('/opt/leadgen/data/job_heartbeats.json') as f:
    hb = json.load(f)

now = datetime.utcnow()
for agent, last_ts in hb.items():
    last = datetime.fromisoformat(last_ts)
    delta = (now - last).total_seconds() / 60
    status = "✓" if delta < 30 else "✗ OVERDUE"
    print(f"{agent}: {delta:.0f} min ago {status}")
EOF
```

### STEP 3: Restart Agent (3 min)
```bash
# If scheduler not running
docker compose -f /opt/leadgen/docker-compose.vps.yml up -d scheduler

# If agent-specific job stuck
docker exec leadgen_app python << 'EOF'
from app.platform.team import team_scheduler

# Force run job
result = team_scheduler._run_job("arjun_qa", force=True)
print(f"Job result: {result}")
EOF

# Check heartbeat again
docker exec leadgen_app python -c "import json; print(json.load(open('/opt/leadgen/data/job_heartbeats.json')))"
```

### STEP 4: Full Restart (3 min)
```bash
# If still not running
docker compose -f /opt/leadgen/docker-compose.vps.yml restart scheduler app

# Verify all jobs scheduled
docker logs leadgen_scheduler | grep "scheduled" | tail -10
```

---

## RB-007: Call Stream Dropout

**Indicators**: Calls disconnect mid-stream, transcription cuts off  
**Time-to-fix**: 5 minutes

### STEP 1: Check Exotel Status (2 min)
```bash
# Check Exotel API health
docker exec leadgen_app python << 'EOF'
import requests

resp = requests.get("https://api.exotel.com/v1/Accounts/leadsgenai1/Balance.json",
    auth=("leadsgenai1", "EXOTEL_API_TOKEN"))
print(f"Exotel API: {resp.status_code}")
print(f"Balance: {resp.json()['account']['balance']}")
EOF

# Check credentials
docker exec leadgen_app grep "EXOTEL" /app/.env | grep -v HIDDEN
```

### STEP 2: Check WebSocket Connection (2 min)
```bash
# Monitor WebSocket logs
docker logs leadgen_app | grep -i "websocket\|ws\|exotel" | tail -20

# Check connection count
netstat -an | grep -i established | wc -l

# If <5 connections: issue with app or network
```

### STEP 3: Reconnect (1 min)
```bash
# Restart Exotel stream handler
docker compose -f /opt/leadgen/docker-compose.vps.yml restart app

# Force reconnect
docker exec leadgen_app python << 'EOF'
from app.voice_agent.exotel_stream import ExotelVoicebotSession

# Reconnect (kills stale connections)
session = ExotelVoicebotSession()
result = await session.reconnect()
print(f"Reconnected: {result}")
EOF
```

---

## RB-008: Email Delivery Failing

**Indicators**: Emails not arriving, bounce rate >5%, SPF/DKIM warnings  
**Time-to-fix**: 10 minutes

### STEP 1: Check SMTP Status (2 min)
```bash
# Test Hostinger SMTP
docker exec leadgen_app python << 'EOF'
import smtplib

try:
    smtp = smtplib.SMTP_SSL("smtp.hostinger.com", 465, timeout=5)
    smtp.login("admin@leadsgenai.in", "PASSWORD")
    print("✓ SMTP connection OK")
    smtp.quit()
except Exception as e:
    print(f"✗ SMTP error: {e}")
EOF
```

### STEP 2: Check SPF/DKIM (3 min)
```bash
# Verify DNS records
docker exec leadgen_app python << 'EOF'
import dns.resolver

# Check SPF
try:
    spf = dns.resolver.query("leadsgenai.in", "TXT")
    spf_record = [r for r in spf if "v=spf1" in str(r)][0]
    print(f"✓ SPF: {spf_record}")
except:
    print("✗ No SPF record")

# Check DKIM
try:
    dkim = dns.resolver.query("default._domainkey.leadsgenai.in", "TXT")
    print(f"✓ DKIM: {dkim[0]}")
except:
    print("✗ No DKIM record")

# Check DMARC
try:
    dmarc = dns.resolver.query("_dmarc.leadsgenai.in", "TXT")
    print(f"✓ DMARC: {dmarc[0]}")
except:
    print("✗ No DMARC record")
EOF

# If missing: Update DNS via Hostinger API or dashboard
```

### STEP 3: Check Email Queue (2 min)
```bash
# Find stuck emails
docker exec leadgen_db psql -U leadgen -d leadgen << 'EOF'
SELECT COUNT(*) FROM emails WHERE status = 'pending' AND created_at < NOW() - INTERVAL '1 hour';
EOF

# Retry stuck emails
docker exec leadgen_app python << 'EOF'
from app.platform.email_sender import retry_failed_emails
result = retry_failed_emails(hours=1)
print(f"Retried {result['count']} emails")
EOF
```

### STEP 4: Check Bounce Rate (3 min)
```bash
# Check bounced emails
docker exec leadgen_db psql -U leadgen -d leadgen << 'EOF'
SELECT COUNT(*) as bounced FROM emails 
WHERE status = 'bounced' 
AND created_at > NOW() - INTERVAL '1 day';
EOF

# If >20 bounces today: check Hostinger mail logs
# Login: Hostinger Dashboard → Email → Logs
```

---

## RB-009: Scale for Traffic Spike

**Indicators**: CPU >80%, response time >2s, queue backlog growing  
**Time-to-fix**: 20 minutes

### STEP 1: Add Web Workers (10 min)
```bash
# Increase app concurrency
WEB_CONCURRENCY=4 docker compose -f /opt/leadgen/docker-compose.vps.yml up -d app

# Verify
curl https://leadsgenai.in/health | jq '.version'

# Monitor
watch -n 2 'docker stats leadgen_app --no-stream'
```

### STEP 2: Add Celery Workers (5 min)
```bash
# Scale worker concurrency
CELERY_WORKER_CONCURRENCY=8 docker compose -f /opt/leadgen/docker-compose.vps.yml up -d worker

# Or add 2nd worker
cp docker-compose.vps.yml docker-compose.vps.scale.yml
# Edit: change service name to "worker2", different port

docker compose -f docker-compose.vps.scale.yml up -d worker2
```

### STEP 3: Monitor Response Time (5 min)
```bash
# Watch latency drop
for i in {1..10}; do
    time curl -s https://leadsgenai.in/api/platform/team | jq . > /dev/null
done

# Should see latency decrease as load spreads
```

---

## RB-010: Backup Failed

**Indicators**: `/var/log/leadgen_offsite_mail.log` shows error, no backup uploaded  
**Time-to-fix**: 15 minutes

### STEP 1: Check Backup Cron (2 min)
```bash
# SSH to VPS
ssh root@72.61.245.204

# Check cron jobs
crontab -l | grep leadgen

# Expected: 0 23 * * * /opt/leadgen/scripts/pg_backup.sh

# Check recent backups
ls -lh /opt/leadgen/backups/ | tail -10
```

### STEP 2: Run Backup Manually (5 min)
```bash
# Run backup script
/opt/leadgen/scripts/pg_backup.sh

# Check logs
tail -50 /var/log/leadgen_offsite_mail.log

# If R2/B2 error: check rclone credentials
rclone config show

# If missing: add R2 config
rclone config create r2 s3 provider=Cloudflare access_key_id=<KEY> secret_access_key=<SECRET> endpoint=https://r2-<account>.s3.amazonaws.com
```

### STEP 3: Verify Backup Uploaded (3 min)
```bash
# List uploaded backups
rclone ls r2:leadgen-backups/

# Should see recent .gz files

# Test restore (dry-run)
rclone copy -v --dry-run r2:leadgen-backups/db_*.sql ./

# If works: add to cron
echo "0 23 * * * /opt/leadgen/scripts/pg_backup.sh >> /var/log/leadgen_backup.log 2>&1" | crontab -
```

---

## RB-011: Deploy Code Change

**Indicators**: New feature ready, bug fix tested, system prompt updated  
**Time-to-time**: 15 minutes

### STEP 1: Test Locally (5 min)
```bash
# On your machine
pytest tests/test_loop_*.py -v
# Expected: 14/14 PASS

# Check git
git status
git log --oneline -5
```

### STEP 2: Push to Main (2 min)
```bash
git add .
git commit -m "Feature: Agent system prompts + test suite"
git push origin main
```

### STEP 3: Deploy via Automation (5 min)
```bash
# Run deployment script
./scripts/deploy_production.sh prod

# Script does:
#  - Pre-flight checks (git, SSH, tests)
#  - Backup current state
#  - git pull on VPS
#  - docker compose up
#  - smoke tests
#  - health checks

# Monitor: docker logs leadgen_app -f
```

### STEP 4: Verify (3 min)
```bash
# Check health
curl https://leadsgenai.in/health | jq .

# Check routes count (should increase)
curl https://leadsgenai.in/openapi.json | jq '.paths | length'

# Check agent list
curl https://leadsgenai.in/api/platform/team | jq '.roster | length'

# Expected: all green
```

---

## RB-012: Suspected Data Corruption

**Indicators**: Duplicate prospects, missing leads, inconsistent counts  
**Time-to-fix**: 30 minutes

### STEP 1: Backup Before Repair (5 min)
```bash
# Create emergency backup
docker exec leadgen_db pg_dump -U leadgen leadgen > /tmp/db_backup_emergency.sql

# Upload to safety
scp /tmp/db_backup_emergency.sql ~/backups/
```

### STEP 2: Run Integrity Checks (10 min)
```bash
# SSH to VPS
ssh root@72.61.245.204

# Run diagnostic
docker exec leadgen_app python << 'EOF'
from app.models import Prospect, Lead, Call

# Check duplicates
dupes = db.query(Prospect).group_by(Prospect.phone).having(func.count() > 1).all()
print(f"Duplicate prospects by phone: {len(dupes)}")

# Check orphans (calls without prospects)
orphans = db.query(Call).filter(~Call.prospect_id.in_(
    db.query(Prospect.id)
)).count()
print(f"Orphaned calls: {orphans}")

# Check integrity
leads_total = db.query(Lead).count()
prospects_total = db.query(Prospect).count()
print(f"Leads: {leads_total}, Prospects: {prospects_total}")
EOF
```

### STEP 3: Repair (15 min)

**If duplicates**:
```bash
docker exec leadgen_db psql -U leadgen -d leadgen << 'EOF'
-- Mark older duplicate as archived
UPDATE prospects SET status = 'archived'
WHERE id NOT IN (
    SELECT MAX(id) FROM prospects GROUP BY phone
) AND status != 'archived';
EOF
```

**If orphans**:
```bash
docker exec leadgen_db psql -U leadgen -d leadgen << 'EOF'
-- Delete orphaned calls (or mark as unlinked)
DELETE FROM calls WHERE prospect_id NOT IN (SELECT id FROM prospects);

-- Or move to lost-and-found
UPDATE calls SET prospect_id = NULL WHERE prospect_id NOT IN (SELECT id FROM prospects);
EOF
```

### STEP 4: Verify Repair (2 min)
```bash
# Rerun checks
docker exec leadgen_app python << 'EOF'
# Same checks as STEP 2 - should show 0 dupes/orphans
EOF

# Restart services
docker compose -f /opt/leadgen/docker-compose.vps.yml restart app
```

---

## ESCALATION PROCEDURES

**If incident can't be resolved in 15 min**:
1. Document exact steps taken + errors
2. Check `#leadgen-incident` Slack channel
3. Contact platform team (if available)
4. Consider rollback (RB-011 reverse)

**Post-Incident**:
- Update runbook with new learnings
- Add test case to prevent recurrence
- Document root cause

---

## RB-013: Go-Live / Production Launch Verification

**When**: Major release, first-paid-customer cutover, or post-recovery re-launch.
**Time-to-fix**: 30 min. **Consolidates** the former `GO_LIVE_CHECKLIST.md` + `DEPLOY_VERIFICATION_CHECKLIST.md` (de-staled — payments are UPI, not Razorpay; roster is 15+ staff; ~840 routes).

### STEP 1: Pre-deploy gates (Windows = source of truth)
```bash
python scripts/prod_check.py        # must end: [OK] ALL CHECKS PASSED
scripts\run_tests.bat               # targeted suites green (Read pytest_run.log)
python scripts/check_secrets.py     # 0 secrets (false positive → `nosecret`)
```
- [ ] prod_check PASS (routes + 0 automation gaps + graph 73/73)
- [ ] targeted pytest green · `git status` clean before push

### STEP 2: Deploy (see RB-011 for the full build+recreate)
```bash
# VPS: pull → build app → recreate (data-only changes skip rebuild)
docker compose -f docker-compose.vps.yml build app && \
docker compose -f docker-compose.vps.yml up -d --no-deps app
```
- [ ] New `@app.get` page-route added? → hard-reload (clear `__pycache__`) or full recreate

### STEP 3: Post-deploy health verify
```bash
curl -s https://leadsgenai.in/health        | jq .environment   # "production"
curl -s https://leadsgenai.in/health/ready  | jq '{db,redis}'   # both healthy
curl -s https://leadsgenai.in/openapi.json  | jq '.paths|length'# ~840
curl -s https://leadsgenai.in/api/activation/summary            # ready_for_first_paid_customer
```
- [ ] `environment=production` · db+redis healthy · routes not regressed

### STEP 4: First 24h monitor
```bash
redis-cli LLEN celery            # <100 (>500 → del celery, beat re-schedules)
docker stats leadgen_app --no-stream   # memory <60%
docker logs leadgen_app --since 1h | grep -ic ERROR   # ~0
curl -s https://leadsgenai.in/api/growth/infra/automation-health | jq '.overdue_jobs'  # []
```

### STEP 5: Rollback criteria + procedure
Trigger if (first hour): `/health` 500 >2 min · >50% ERROR logs · queue >500 · memory >80% · DB timeouts.
```bash
# Fast: revert in-process scheduler if worker/beat unstable
#   .env: RUN_IN_PROCESS_SCHEDULER=1 + WEB_CONCURRENCY=1, stop worker/scheduler, recreate app
# Code rollback:
git -C /opt/leadgen reset --hard HEAD~1
docker compose -f /opt/leadgen/docker-compose.vps.yml up -d --no-deps app
curl -s https://leadsgenai.in/health   # confirm recovered
```

---

## MONITORING CHECKLIST (Daily)

- [ ] `/health` responds 200 with `environment=production`
- [ ] 12 agents in roster (check `/api/platform/team`)
- [ ] Queue depth <100 (check `redis-cli LLEN celery`)
- [ ] Memory usage <60% (check `docker stats`)
- [ ] No ERROR in logs (check `docker logs leadgen_app`)
- [ ] Last backup <24h old (check `/opt/leadgen/backups/`)
- [ ] Infra score ≥90 (check `/api/growth/infra/hermes`)
- [ ] Email deliverability OK (check bounce alerts)
- [ ] Payment webhooks firing (check recent subscriptions)

---

**Keep this open during operations. Laminate & post on wall!**
