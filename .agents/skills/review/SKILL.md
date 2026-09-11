---
name: review
description: PR/diff code review for the LeadGen AI platform — 5-lens critical pass (bugs · prod-killers · security · tests · perf) + FastAPI project-specific checks (route-shadow, hard-reload, flags, boot-grace) → classified AUTO-FIX/ASK/INFO report. Use before `/ship`, "review this code", PR merge se pehle, ya naya feature complete hone ke baad.
---

# Skill: review
**Adapted from gstack by Garry Tan (YC). MIT License.**

## When to invoke
- `/ship` se pehle
- "Is code ko review karo"
- PR merge se pehle
- Naya feature complete hone ke baad

---

## Step 0: Diff lo

```bash
git diff main..HEAD --stat
git diff main..HEAD -- '*.py' | head -500
```

Agar main pe ho:
```bash
git diff HEAD~5..HEAD --stat
```

Scope check: 500 lines se zyada diff? Large change — per-file review karo.

---

## Step 1: Critical Pass (5 lenses)

Har changed file ke liye inhe dhundo:

### 1. 🐛 Bugs that pass CI
- Off-by-one errors
- None/null unchecked
- Wrong async/await pattern
- Dict key missing (`get()` vs `[]`)
- Exception silently swallowed

### 2. 🔥 Production Killers (project-specific)
- **Event loop blocking**: sync ML/DB call in async function bina `asyncio.to_thread`
- **Startup heavy init**: import pe instantiate nahi karna chahiye heavy objects
- **`os.kill(pid, 0)` on Windows** — KABHI mat karo (signal 0 = CTRL_C)
- **Hardcoded URLs/IDs** — env variable hona chahiye
- **`.env` values committed** — secrets kabhi code mein nahi

### 3. 🔒 Security
- User input sanitized hai?
- Admin endpoint pe auth check hai? (`require_admin`); billing/customer mutation `_authed_client_id` scope (IDOR-closed)?
- Public/LLM endpoint rate-limited hai? (`rate_limit("name",N,sec)`; LLM = `require_admin`+`tier_rate_limit`)
- SQL injection possible? (raw string nahi, ORM/params use karo)
- SSRF possible? (user-provided URLs = private-IP block, `website_auditor.py` pattern)
- Webhook signature verify FIRST + prod fail-CLOSED 503? Secrets sirf `.env` (`check_secrets.py`)?

### 4. 🧪 Test Coverage
- Naya code test covered hai?
- Edge case: empty list, None, empty string
- Error path test hai?

### 5. 📊 Performance
- N+1 DB query?
- `asyncio.gather` possible hai jahan sequential hai?
- Large file/response without streaming?
- Cache possible hai (repeat expensive ops)?

---

## Step 2: FastAPI/Python Project-Specific Checks

```bash
# Route conflicts check
python scripts/prod_check.py 2>&1 | tail -5

# Import check
python -c "import app.main; print('OK')"

# Circular import?
python -c "from app.api.<new_module> import router"
```

- Naya route add kiya? → `grep '@router' app/api/<file>.py` se shadow check (FastAPI first-route-wins, ~1030 routes already). Page-route `@app.get` = **HARD RELOAD zaroori** (stale .pyc 404).
- New env flag? → `app/api/growth.py` ke `AUTOMATION_FLAGS` list mein add kiya?
- New scheduler job? → boot-grace skip logic + Celery worker me chale (web process nahi).
- Price/plan change? → `app/marketing/packages.py`(ya `voice_packages.py`) + `tests/test_billing_truth_2026.py` SAATH?
- Marketing feature? → `frontend/marketing.html` (28 tabs) me UI tab bhi add hua?

---

## Step 3: Classify Findings

**[AUTO-FIX]** — Low risk, clear fix, karo do
**[ASK]** — Risk ya tradeoff hai, user se poocho
**[INFO]** — Note rakho, immediately fix zaroori nahi

---

## Step 4: Report

```
## Code Review Summary

### AUTO-FIX (kiya):
- file.py:42 — [description]

### ASK (user decision needed):
- file.py:88 — Race condition in X. Option A: Y. Option B: Z.

### INFO (FYI):
- Technical debt noted: ...

### ✅ Looks Good:
- Auth, rate limits, error handling sahi hai
```

Har AUTO-FIX atomic commit mein karo: `git commit -m "fix: [description]"`

> Cross-link (2026-07-05): project security/billing lens checklists ka authoritative source = `self-code-review` (5 passes) — drift se bachne ke liye wahan update karo, yahan copy nahi.
