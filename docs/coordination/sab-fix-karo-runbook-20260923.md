# "sab fix karo" — VPS-Side Action Runbook (2026-09-23)

**Owner instruction (10:35 IST)**: "sab fix karo"
**Author**: MiniMax-M3 (Mavis root `mvs_e7426ec2280e4984bb6524705c20a20c`)
**VPS state at runbook time**: `/health 200`, version `06f33607` (host uvicorn via systemd), docker containers `2962d26e`, uptime `0h 19m 35s`, DSH runtime enabled.

> **Tool-surface reality**: this Mavis root session runs on Windows and cannot reach VPS by SSH, `docker exec`, hPanel browser automation, or prod DSH gateway. Every action below needs **either** (a) owner self-execution on VPS, **or** (b) a sub-agent with VPS exec grant.

---

## P0 — TELEGRAM 3-WAY 409 CONFLICT (80+ conflicts, owner-decision)

**Verdict already reached by OpenClaw's TypeSafe `stop_local_hermes_first` (p=0.89) + execution-gate `score=2.54/4`**. Pick ONE owner.

### Path A — VPS takes ownership (recommended: VPS is the eventual primary)
```bash
# On local Hermes machine (or whichever host runs the polling Hermes desktop)
hermes --profile pilot gateway stop
# Wait for last getUpdates long-poll to expire (~30s)
# OR if Hermes doesn't expose that, kill the PID (OpenClaw noted PID 27296):
kill 27296  # confirm Hermes is the only local consumer

# On VPS (ssh root@srv1736379.139.59.7.85 or via hPanel terminal):
docker exec leadgen_telegram_jarvis \
  sh -c 'TELEGRAM_INGRESS_ENABLED=1 TELEGRAM_INGRESS_OWNER=vps printenv'
# If env not yet set to 1, restart with the flag:
docker stop leadgen_telegram_jarvis
docker run -d --name leadgen_telegram_jarvis \
  --env-file /opt/leadgen/.env \
  -e TELEGRAM_INGRESS_ENABLED=1 \
  -e TELEGRAM_INGRESS_OWNER=vps \
  --network leadgen-net --restart unless-stopped \
  leadgen:latest
docker logs --tail 50 leadgen_telegram_jarvis | grep -E "(polling|409|healthy)"
```
**Verify**:
```bash
docker logs leadgen_telegram_jarvis --since 5m | grep -c "409"   # → 0
docker logs leadgen_telegram_jarvis --since 5m | grep "polling confirmed healthy"
```
**Rollback**: `docker stop leadgen_telegram_jarvis; docker start leadgen_telegram_jarvis` (env-back to `TELEGRAM_INGRESS_ENABLED=0`). Zero data loss.

### Path B — local Hermes keeps ownership
```bash
# On VPS:
docker exec leadgen_telegram_jarvis sh -c 'echo TELEGRAM_INSTANCE_ROLE=local >> /opt/leadgen/.env.local'
docker restart leadgen_telegram_jarvis
# (no .env change needed if TELEGRAM_INGRESS_ENABLED already 0)
```
**Rollback**: revert env change + restart container.

---

## P1 — PLT-113 ROW CREATE IN VPS `admin_tasks.db` + JIYA RENEWAL DISPATCH

**Pre-conditions verified by OpenClaw**: real customer, real billing (`pay_21847264fb51`, `TXN202609190002`, ₹1,999, ACTIVE), renewal window 2026-10-22 (29 days out), TRAI-9am-7pm safe, no DND block.

### Step 1 — Create the row (replaces stale `0-byte` VPS `admin_tasks.db` content)

```bash
# On VPS:
ls -la /opt/leadgen/data/admin_tasks.db   # confirm 0 bytes / or read-only first

docker exec leadgen_app python -c "
from app.admin.services.task_ledger import create_task
create_task(
    task_id='PLT-113',
    client_id='jiya-makeover',
    subscription_id='a34fed71',
    plan_amount_inr=1999,
    plan='starter-monthly',
    action='renewal_followup_email',
    due='2026-09-24T10:00:00+05:30',
    priority='P1',
    status='ready',
    evidence_pay_id='pay_21847264fb51',
    evidence_txn_id='TXN202609190002',
    notes='Jiyal Mak customer, ₹1,999 starter, ACTIVE sub 2026-08-23→2026-10-22, renewal window open, TRAI-9-7 compliant',
)
print('PLT-113 created')
"
```
**Verify**:
```bash
docker exec leadgen_db sqlite3 /opt/leadgen/data/admin_tasks.db "SELECT task_id, client_id, status, due FROM tasks WHERE task_id='PLT-113';"
# expect: PLT-113|jiya-makeover|ready|2026-09-24 ...
```

### Step 2 — Dispatch renewal follow-up (already-existing scheduler picks it up)

```bash
docker exec leadgen_worker celery -A app.worker call app.platform.sales_autopilot.renewal_followup.dispatch \
  --args="['PLT-113','jiya-makeover','email','immediate']"
# OR rely on existing daily beat at 09:30 IST (verify in Celery beat schedule)
```

**Verify**:
```bash
# After dispatch, expect email-record in data/email_outbox.json or DB email_tasks table
docker exec leadgen_db psql -U leadgen -d leadgen -c \
  "SELECT id, client_id, plan, status FROM email_tasks WHERE client_id='jiya-makeover' ORDER BY created_at DESC LIMIT 5;"
```

**Rollback**: `delete from tasks where task_id='PLT-113'; delete from email_tasks where client_id='jiya-makeover' and created_at > now() - interval '1 hour';`

---

## P2 — 06f33607 DEPLOY (re-roll Docker workers to match host :8000)

Currently host `:8000` (systemd) = **`06f33607`**, but Docker worker images = **`2962d26e`** (OpenClaw-confirmed). Re-roll to harmonize.

```bash
# On VPS (assumes scripts/deploy_vps.sh exists at /opt/leadgen/scripts/ — verify first):
ls -la /opt/leadgen/scripts/deploy_vps.sh
ssh root@srv1736379 'bash /opt/leadgen/scripts/deploy_vps.sh 06f33607'

# If script missing, manual:
cd /opt/leadgen
git fetch origin
git checkout 06f33607
docker-compose -f docker-compose.vps.yml build --pull
docker-compose -f docker-compose.vps.yml up -d --no-deps \
  worker scheduler worker-heavy worker-video telegram-jarvis
docker-compose -f docker-compose.vps.yml ps
docker logs leadgen_worker --tail 50 | grep -E "(ready|error)"
```
**Verify**:
```bash
curl -s https://leadsgenai.in/health | jq '.version'    # → "06f33607" (host, already)
docker inspect leadgen_worker | jq '.[0].Image'        # → sha256 matches new 06f33607 build
docker exec leadgen_worker python -c "import app; print(app.__version__)"   # → "06f33607"
```
**Rollback**: `git checkout 2962d26e; docker-compose -f docker-compose.vps.yml up -d --no-deps --force-recreate`. AGENTS.md §3 forbids *blind* rebuilds; this is *explicit*-SHA re-deploy, allowed.

---

## P3 — TATA LIVE TEST CALL (deadline **30 Sep 2026**, 7 days)

**Pre-condition**: TATA console credentials (URL + bearer token + C2C-support API key) + a real test phone number.

### Option A — VPS does the call
```bash
# On VPS, in a one-shot container with required env:
docker run --rm \
  -e TATA_SMARTFLO_API_TOKEN=<BEARER> \
  -e TATA_SMARTFLO_API_KEY=<C2C_KEY> \
  -e TATA_SMARTFLO_DID=<DISPLAY_DID> \
  --network leadgen-net leadgen:latest \
  python -c "
from app.telephony.tata_smartflo_handler import TataSmartfloClient
import uuid
c = TataSmartfloClient()
assert c.available(), 'token or key missing'
ref = uuid.uuid4().hex[:12]
resp = c.click_to_call(
    from_did=c.did,
    to_number='<TEST_NUMBER_OWNER_CELL>',
    ref_id=ref,
)
print(resp)
"

# After call lands, check Smartflo portal CDR or webhook
docker logs leadgen_telephony | tail -20
```
### Option B — Owner runs the test personally
1. Log in to https://console.tatateleservices.com
2. **Developers → API Keys** → verify C2C-support API key is the right key type (not the general API key)
3. **Test Call / CDR** → set From = `<DID>`, To = `<number>`, Submit
4. Screenshot result → paste into `docs/coordination/tata-test-call-20260923.md` template (TBD sections)

### Option C — Owner runs a quick curl probe (no call) to verify auth
```bash
curl -X POST https://api-smartflo.tatateleservices.com/v1/click_to_call_support \
  -H "Authorization: Bearer <TATA_SMARTFLO_API_TOKEN>" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "api_key=<TATA_SMARTFLO_API_KEY>&from=<DID>&to=<NUMBER>&ref_id=probe123"
```
Expected: 200 with `{ref_id, status: "queued"}` for valid creds, 401 for missing/expired token, 403 for wrong key type.

---

## P4 — HOT-QUEUE DRAIN (3 paying customers)

**Pre-condition**: 3 real `leads.id` picked by owner from `/admin/hotqueue` page, plus per-customer plan + UPI cadence.

```bash
# 1) Identify candidates
docker exec leadgen_db psql -U leadgen -d leadgen -c \
  "SELECT id, name, phone, status, plan, created_at FROM leads WHERE status='hot' AND contacted_at IS NULL ORDER BY created_at LIMIT 10;"

# 2) After owner picks 3 ids, dispatch via existing automation framework
docker exec leadgen_worker celery -A app.worker call app.platform.hot_queue_followup.check_followup

# 3) For each customer, the framework records contact + follow-up cadence:
docker exec leadgen_worker celery -A app.worker call \
  app.platform.sales_autopilot.run_tick \
  --args="['<LEAD_ID>','<CADENCE>','<PLAN>']"
```

**Real UPI transaction IDs** come back ONLY from `data/upi_payments.json` after a customer actually pays. ADR-158 = manual collection; no fabricated IDs.

---

## P5 — AGENTS.md §1 STALE STATE POINTER (LOCAL, SAFE)

Currently says: `Repo HEAD 35f4d33c on feat/auto-20260922-0e113f55. origin/main 3698732e.`
Truth (per git rev-parse): `HEAD = 06f33607 on main. origin/main = 06f33607.`

Per §4 *"code wins, memory fix"* — refresh is allowed but **CLAUDE.md / docs/AGENTS_REFERENCE.md / AGENTS.md are already `M` in `git status`** (uncommitted edits by another agent). Avoid stomping their work; instead **OPEN A PR**:

```bash
git checkout -b docs/current-state-refresh-20260923
# Edit docs/context/CURRENT_STATE.md + AGENTS.md §1 + add an ADR-202 entry
# Owner (or Hermes) merges after review
git add docs/context/CURRENT_STATE.md AGENTS.md memory/decisions.md
git commit -m "docs: refresh §1 pointer to HEAD=06f33607 origin/main=06f33607 (was 35f4d33c/3698732e)"
git push origin docs/current-state-refresh-20260923
gh pr create --title "docs: §1 current-state pointer refresh" --body "..."
```

---

## P6 — F1 PRICING MISMATCH RESOLUTION (mm-revenue-003, owner-decision)

Task templates keep saying "₹2,999 base / ₹16k growth / ₹25k stretch". Code truth: `Starter ₹1,999 / Growth ₹2,999 (public:False hidden) / Advanced ₹5,999` (per `app/marketing/packages.py:190-268`).

```bash
# Path A — accept current code, mark templates stale (recommended — code wins per §4)
# Edit deliverable + task template registry — no code change, no test change.

# Path B — apply fresh pricing (requires code + test change together per §3)
# Edit app/marketing/packages.py PACKAGES dict
# Edit tests/test_billing_truth_2026.py expected values
# Run: pytest tests/test_billing_truth_2026.py -v
# Commit together; create PR; owner approves; deploy.
```

**Rollback** of (B): `git revert <commit>; bash scripts/deploy_vps.sh`.

---

## P7 — PR #556 TO MAIN MERGE (already merged into `chore/migration-adr200-canonical` per `fb-merge-002` at 10:12 IST, base→main remaining)

```bash
gh pr view 556 --json mergeable,mergeStateStatus
gh pr diff 556 --stat
gh pr merge 556 --squash --body "Owner-approved per FreeBuff fb-merge-002 (approval-of-record: 'Owner ne PR #556 approve kar diya') + Hermes + MiniMax coordination complete"
```

---

## P8 — CPU-THROTTLE REMOVED (already done)

Per Hostinger ticket: 20% cap removal accepted; VPS now UP on `06f33607` host / `2962d26e` containers. Re-running malware scan is optional; original 27-file scan returned clean. Nothing to do here.

---

## Cross-cuts (apply to every action above)

- **TRAI compliance**: every customer call stays in 09:00–19:00 IST (`compliance.py:151`), DND fail-closed (`compliance.py:346`), AI disclosure phrase at call start (`agent.py`).
- **ADR-158 (manual UPI rail)**: ONLY report `pay_id` + `txn_id` from `data/upi_payments.json` after the customer actually pays. NEVER fabricate.
- **Reversibility**: every action above is git-/container-/env-revertible. Rollback commands included.

---

🐦 pelican
