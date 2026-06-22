---
name: investigate
description: Root-cause-first debugging — symptom fix se pehle "kyun" pakdo. Use jab error/stack-trace mile, "ye kaam kyun nahi kar raha", "production down hai", "kal tak theek tha", regression dhoondna ho, ya koi bhi root-cause analysis chahiye. Project gotchas (event-loop sync call, stale .pyc, fastembed cache, Windows os.kill) built-in.
---

# Skill: investigate
**Adapted from gstack by Garry Tan (YC). MIT License.**

## When to invoke
- Error / stack trace mili
- "Yeh kaam kyun nahi kar raha?"
- "Production down hai"
- "Kal tak theek tha"
- Root cause analysis chahiye

## ⚠️ IRON LAW
**ROOT CAUSE BINA KOI FIX NAHI.**
Symptom fix = whack-a-mole. Pehle cause, phir code.

**3 FIX RULE:** Agar 3 alag hypotheses try karne ke baad bhi fix nahi mila — STOP karo aur user ko bolo: "Root cause unclear, tumhe yeh context dena hoga: [specific info needed]."

---

## Phase 1: Evidence Gather karo

1. **Error exact copy karo** — stack trace, log line, exact message. User se maango agar nahi diya.

2. **Code path trace karo:**
```bash
grep -rn "ERROR_KEYWORD" app/ --include="*.py" | head -20
```

3. **Recent changes dekho:**
```bash
git log --oneline -20 -- <affected-file>
git diff HEAD~3..HEAD -- <affected-file>
```
Regression = cause is diff mein hai.

4. **Live container logs (VPS pe):**
```
docker logs leadgen_app --tail=100 2>&1 | grep -i error
docker logs leadgen_worker --tail=50
```

5. **Reproduce karo:** Deterministic reproduction ke bina fix mat karo.

---

## Phase 2: Pattern Analysis

1. **Pehle hua hai?** — AGENTS.md / SESSION_LOG mein search karo: `grep -i "PROD-DOWN\|incident\|fixed" AGENTS.md | head -20`

2. **Architectural smell check:**
   - Event loop pe sync/blocking call? (humara #1 cause — KB/ML/fastembed)
   - Import time pe heavy instantiation?
   - Race condition ya shared state?
   - Thread safety issue?

3. **Common project gotchas (PEHLE check karo):**
   - `asyncio.to_thread` missing? (ML/KB sync call in async context)
   - `--break-system-packages` missing in pip?
   - `.pyc` stale? (`find app/ -name __pycache__ -exec rm -rf {} +`)
   - Windows `os.kill(pid, 0)` bug?
   - fastembed cache wiped? (image rebuild ke baad)
   - silero-vad cuda vs cpu?

---

## Phase 3: Hypothesis Testing

List karo (confidence ke order mein):
```
H1: [Most likely cause] — Evidence: [kya dekha]
H2: [Second likely] — Evidence: [kya dekha]  
H3: [Long shot] — Evidence: [kya dekha]
```

Pehle H1 verify karo. Agar wrong — H2. H3 ke baad bhi nahi = STOP (3-fix rule).

**Verify before fix:** `git stash` ya test script se hypothesis confirm karo pehle.

---

## Phase 4: Fix + Guard

Fix karte waqt:
1. Additive fix karo — existing behavior ZERO change jab bug nahi ho
2. Fail-open pattern: error pe block nahi karo unless safety-critical
3. **Zaroor add karo:**
   - Timeout/deadline (ML loads ke liye `asyncio.wait_for`)
   - Disable switch env var (`FEATURE_DISABLED=1`)
   - Test coverage for the exact bug

```bash
# Quick smoke ke baad:
python scripts/prod_check.py
scripts\run_tests.bat  # ya targeted: pytest tests/test_<area>.py -v
```

---

## Phase 5: Report + SESSION_LOG

Fix ke baad:
```
📍 ROOT CAUSE: [1 sentence]
🔧 FIX: [kya badla]
🧪 VERIFIED: [kaise check kiya]
📚 LESSON: [dobara na ho iske liye kya rule add karna chahiye]
```

Important lesson hai to `docs/SESSION_LOG.md` mein append karo + AGENTS.md update karo (agar project-wide rule hai).
