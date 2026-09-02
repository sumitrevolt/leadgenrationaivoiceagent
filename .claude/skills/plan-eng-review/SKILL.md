---
name: plan-eng-review
description: Naya feature build se pehle ka engineering review — duplicate-route grep, ASCII architecture, state-machine, edge-case + test matrix, phased plan, fail-open/flag-gated checklist. Use when user bole "eng review karo", "architecture decide karo", "ye feature ka design", ya `/plan-ceo-review` ke baad implementation plan se pehle.
---

# Skill: plan-eng-review
**Adapted from gstack by Garry Tan (YC). MIT License.**

## When to invoke
- Naya feature build karne se pehle
- `/plan-ceo-review` ke baad
- Architecture decision chahiye
- "Eng review karo"

---

## Step 0: Existing Code Read

```bash
# Related existing code dhundo
grep -rn "FEATURE_KEYWORD" app/ --include="*.py" | head -20

# Route conflicts check
grep -n "@router\." app/api/marketing.py app/api/growth.py | grep -i "KEYWORD"

# Current prod_check state
python scripts/prod_check.py 2>&1 | tail -3
```

**STOP agar duplicate route milti** — existing route extend karo, naya mat banao.

---

## Step 1: Architecture Diagram (ASCII)

Feature ke liye data flow diagram banao:

```
User Request
     │
     ▼
FastAPI Router (app/api/xxx.py)
     │ rate_limit + require_admin
     ▼
Service Layer (app/platform/ ya app/marketing/)
     │ business logic
     ├──► Postgres (via SQLAlchemy async)
     ├──► Redis (cache, 60s TTL)
     ├──► data/*.jsonl (lightweight store)
     └──► External API (gated, never-raise)
```

Har box ke liye: kaunsi existing class/function reuse karein.

---

## Step 2: State Machine (agar applicable)

```
NEW → PROCESSING → DONE
         │
         └── FAILED → RETRY (max 3) → DEAD_LETTER
```

Har state: trigger kya hai, side effects kya hain.

---

## Step 3: Edge Cases Matrix

| Scenario | Expected Behavior |
|----------|-------------------|
| Empty input | Return `{ok: False, error: "input required"}` |
| External API down | Fail-open, log, return cached/default |
| DB connection lost | `try/except`, best-effort, never crash |
| Duplicate request | Idempotent (check existing before insert) |
| Large payload | Streaming ya pagination |
| Concurrent calls | Thread-safe (asyncio.Lock ya DB-level) |
| Flag OFF | Inert return, zero side effect |

---

## Step 4: Test Matrix

| Test | Type | What to verify |
|------|------|----------------|
| Happy path | unit | Normal input → expected output |
| Empty input | unit | Graceful error |
| Flag disabled | unit | Returns early, no side effect |
| Auth missing | integration | 401/403 returned |
| Rate limit | integration | 429 after N requests |
| DB error | unit | Never raises, logs error |
| Idempotency (agar send/call/bill/post/CRM) | unit | Dedupe key → duplicate side-effect NAHI |
| Provider/network down (background work) | unit | Timeout + bounded retry → DLQ `dlq:failed_tasks`, never-raise |
| Billing-touch | unit | `test_billing_truth_2026` green (`packages.py` single source) |
| Compliance fail-CLOSED (telephony/outbound) | unit | DND lookup-fail = BLOCK · 9am–7pm window · AI-disclosure present |

---

## Step 5: Implementation Plan

**Phased approach (koi bhi ek phase mein sab mat karo):**

### Phase 1 (core logic, no scheduler):
- `app/[module]/feature.py` — core function
- `app/api/[router].py` — endpoints
- `tests/test_feature.py` — basic tests

### Phase 2 (agar needed):
- Scheduler integration (`team_scheduler`)
- Boot-grace skip logic add karo
- Dead-man heartbeat

### Phase 3 (agar needed):
- UI tab in relevant HTML page
- Admin dashboard integration

---

## Step 6: Eng Review Checklist

Yeh review = operating loop ka **Contract** phase ka eng-gate; review me hi feature ka **change-risk tier** (Trivial/Standard/**High-risk** — fable §0.6) assign karo aur uske gates lock karo (`fable-operating-manual`).

- [ ] Existing code read kiya (no duplicates)?
- [ ] **Change-risk tier assigned** (billing/public-route/telephony/secrets/auth/automation-loop/DB-migration = High-risk → security-review bhi plan me)?
- [ ] Fail-open pattern?
- [ ] Env flag gated (default OFF) + inert-without-creds?
- [ ] **Idempotency/dedupe** (agar send/call/bill/post/CRM-write)?
- [ ] **Background/provider work** = timeout + bounded retry + DLQ `dlq:failed_tasks` + never-raise?
- [ ] **Compliance fail-CLOSED** (telephony/outbound: DND lookup-fail=block · 9am–7pm · AI-disclosure)?
- [ ] **Billing-touch** = `packages.py` single source + `test_billing_truth_2026`?
- [ ] **Rollback path NAMED** (flag OFF · container recreate · Alembic downgrade · data-repair)?
- [ ] Atomic commits planned?
- [ ] Hard reload needed documented?
- [ ] `AUTOMATION_FLAGS` list update?
- [ ] `prod_check.py` route count expected?
- [ ] Boot-grace agar scheduler-heavy?
- [ ] Secrets sirf `.env` (`scripts\check_secrets.py` clean)?

---

## Output

```
## Engineering Review

Architecture: [diagram above]
Reusing: [existing classes/functions]
New files: [list]
New routes: [count] (total will be ~N)
Flag: `FEATURE=1` (default OFF)
Tests planned: [count]
Deploy notes: [hard reload? flag enable?]

Approved to build: [YES / NEEDS CHANGES]
```
