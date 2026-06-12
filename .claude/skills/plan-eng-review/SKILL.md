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

- [ ] Existing code read kiya (no duplicates)?
- [ ] Fail-open pattern?
- [ ] Env flag gated (default OFF)?
- [ ] Atomic commits planned?
- [ ] Hard reload needed documented?
- [ ] `AUTOMATION_FLAGS` list update?
- [ ] `prod_check.py` route count expected?
- [ ] Boot-grace agar scheduler-heavy?

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
