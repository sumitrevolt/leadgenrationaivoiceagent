---
name: teach-agent-loop
description: Extend the self-improve loop safely — naya AI agent (staff member) ya naya action/task add karo, risk-assessed + tested + gated. Use when the user says "naya agent banao", "loop me action add karo", "self-improve ko X sikhao", "add a new automation task", "new staff member to team", or wiring a new integration into the agent loop.
---

# teach-agent-loop — Add New Agents & Actions to Self-Improve

**Level**: Advanced  
**Time**: 30–90 min (new agent) to 15 min (new action)  
**Purpose**: Extend the self-improve loop safely: add new AI agents or automate new tasks. Companion: `self-improve-loop` (architecture) · `agent-loop-design` (generalized loop pattern) · `self-improve-control` (operate/audit).

---

## When to Add a New Agent or Action

**New agent** (staff member on the team):
- You need a dedicated person (e.g., "Outreach Manager")
- The agent has 2–5 recurring responsibilities
- You want team.py roster to reflect them

**New action** (task for self-improve to pick):
- Automatable work that fits in 30–180 sec
- Measurable outcome (success rate trackable)
- Low risk (gated, draft-only, or already-safe)
- Complements existing actions (revenue, lead gen, growth, compliance)

**New integration** (e.g., LinkedIn DM sender):
- Entire feature (not just one action)
- Start with new action in self-improve, not separate agent
- Wrap integration in gated flag + fail-open defensive code

---

## Risk Assessment Matrix

**Before enabling, categorize risk level**:

| Action | Risk | Why | Mitigation |
|--------|------|-----|-----------|
| scrape_leads | 🟢 Low | Read-only, legal sources | OSM+Places API only, no crawling |
| draft_social | 🟢 Low | Draft-only, humans send | Template + free_ai, no auto-post |
| sales_deepdive | 🟡 Medium | LLM-heavy, costly | Per-action cost cap, monitors |
| sms_campaign | 🟡 Medium | High-volume send | DLT-gated, opt-in verified, daily cap |
| voice_calls | 🔴 High | Costly, regulatory | DLT-required, approval gate, compliance audit |
| social_auto_post | 🔴 High | Public, can fail | NEVER enable, banned by platforms |
| cold_email_bulk | 🔴 High | Reputation risk | Email-warming ramp, low volume start |

**For 🔴 High-risk**:
- [ ] Require `SELF_IMPROVE_APPROVAL=1`
- [ ] Add compliance audit (DLT, opt-in, recording retention)
- [ ] Set low initial cap (5/day instead of 50)
- [ ] Monitor DND/opt-out lists closely
- [ ] Test in staging first, not prod

---

## How to actually do it (step-by-step guides)

The full prescriptive walkthroughs and code live in `references/` to keep this guide lean:

- See `references/add-new-action.md` for the **6 steps to add a new action** (fastest path, ~15 min): define → write/reuse code → register in dispatch → register in skill library → test (5 runs) → enable & monitor.
- See `references/add-new-agent.md` for the **6 steps to add a new agent** (longer path, 30–90 min): define → agent code → team roster → coordinator → self-improve actions → test & document.
- See `references/worked-example-linkedin-dm.md` for a complete worked example ("Add LinkedIn DM Outreach") end to end.
- See `references/common-patterns.md` for copy-paste code patterns (LLM-heavy drafting / data-read / gated action).
- See `references/agent-extension-guide.md` for the deep-dive architecture reference (agent template, integration points, bandit mechanism, coordinator modes).

---

## Testing Checklist (5 Test Scenarios)

### Generic Tests (for any new action)

```
[ ] Test 1: Happy Path
    Input: Valid parameters (e.g., valid niche)
    Expected: ok=True, meaningful detail + output
    Command: python -c "asyncio.run(action(...)); assert result['ok']"

[ ] Test 2: Edge Case (Empty)
    Input: No data found (e.g., niche with 0 leads)
    Expected: ok=False (graceful error), no crash
    Command: (same, mock by_niche to return [])

[ ] Test 3: LLM Provider Down
    Input: free_ai.chat fails (429, 500, timeout)
    Expected: Fallback or static template, ok=True or ok=False (no crash)
    Command: Mock free_ai.chat to raise, check error handling

[ ] Test 4: Timeout (>240s)
    Input: Slow operation (e.g., network hang)
    Expected: Task cancelled, logged to DLQ, not blocking loop
    Command: Mock to time.sleep(300), watchdog should cancel after 240s

[ ] Test 5: Concurrent Calls (Multi-Worker)
    Input: 2 workers call same action simultaneously
    Expected: No race condition, both complete or one skipped, no data corruption
    Command: pytest with asyncio, 2 tasks, verify data/skill_uses.jsonl intact
```

### Action-Specific Tests

For **email/SMS actions**:
```
[ ] Verify recipients are opt-in (check consent_ledger)
[ ] Verify email is on warmup ramp (not full blast)
[ ] Verify templates match DLT (if SMS)
```

For **LLM-heavy actions** (free_ai chain = Mistral primary → Groq → Cerebras → … → Gemini, circuit-breaker + fallback):
```
[ ] Cost tracking: record_use() called (skill_uses.jsonl)
[ ] Provider fallback: if Mistral down, chain tries Groq→Cerebras→... (then static template)
[ ] Latency: should complete <30s for draft tasks
[ ] eval_gate: ok/fail feeds score_and_gate baseline (if EVAL_GATE on)
```

For **data-write actions** (e.g., enroll_in_cadence):
```
[ ] Idempotency: running 2x should not double-enroll
[ ] Rollback: if 2nd part fails, 1st part still ok (best-effort)
[ ] Audit trail: action logged to agent_events
```

---

## Safety Gates (Before Prod)

**For any new action**:

```
[ ] 1. Import-safe: Can it be imported without side effects?
      → No `if __name__ == "__main__"` that runs on import
      → Lazy imports inside function (not module-level)
      → No module-init code that talks to DB
      
[ ] 2. Fail-open: If something breaks, does it crash the loop?
      → Wrap in try/except, return {"ok": False}
      → No bare `raise` statements
      → Graceful degradation (fallback data if API down)
      
[ ] 3. Gated: Is the action behind a flag if sensitive?
      → DLT, SMS, calls: env flag required
      → Auto-send: SELF_IMPROVE_APPROVAL=1 required
      → Write operations: test-safe (staging only)
      
[ ] 4. Bounded: Can it run away in cost/time?
      → Cost cap per run? (e.g., LLM-heavy = <$5/run)
      → Timeout watchdog? (hard 240s limit)
      → Concurrency limit? (e.g., max 3 parallel)
      
[ ] 5. Logged: Can we audit what happened?
      → Outcome recorded: skill_library.record_use()
      → Details logged: result["detail"] is human-readable
      → Errors captured: DLQ if task fails
      
[ ] 6. Tested: Did it pass 5 test scenarios?
      → Happy path ✓
      → Empty data ✓
      → LLM down ✓
      → Timeout ✓
      → Concurrent ✓
```

## Enterprise gate (wiring into the live loop)

Run the operating loop — Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). Naya agent/action = automation loop change → **High-risk tier** (locks: §9 ten-point bar + named rollback + self+security review). 🔴-row actions (calls/SMS/bulk email/social-post) = **always High-risk, fail-CLOSED**.

- **Safety:** har action gated env-flag default OFF + inert-without-creds; 🔴 actions need `SELF_IMPROVE_APPROVAL=1`. Auto-post / auto-send KABHI hardcode-enable nahi — `social_auto_post` row = NEVER. New flag ko `AUTOMATION_FLAGS` registry (growth.py) me add karo so it shows at `/api/growth/infra/flags`. Tenant/client boundary respect; secrets sirf `.env`.
- **Idempotency/dedupe:** agar action send/call/bill/post/CRM-write karti hai → idempotency key + daily/period dedupe (state-file, success pe hi mark → fail pe next-tick retry). Running 2× = no double-enroll/double-send (Test 5 + data-write checklist).
- **Reliability:** timeout (hard 240s watchdog) + bounded retry + never-raise wrapper (`return {"ok": False}`, no bare raise) + fail → DLQ Redis `dlq:failed_tasks`. Loop ko KABHI crash na kare.
- **Durable parity:** persistent job → `team_scheduler._run_job` + mirror `worker.py` beat + register in `automation_health.EXPECTED_GAP_MIN` (dead-man switch). Heartbeat/event recorded (`agent_events`, `skill_library.record_use()`).
- **Compliance (fail-CLOSED):** SMS/voice/email actions → DLT-gated · DND scrub (lookup-fail = block) · TRAI 9am–7pm window · AI-disclosure-at-start · consent_ledger opt-in/retention · email warmup ramp. Bypass = legal risk.
- **Rollback (NAMED):** flag OFF (instant inert) · revert dispatch registration · `data/skill_uses.jsonl` benign (no repair needed) · container REBUILD + recreate (`docker compose -f docker-compose.vps.yml build app` phir `docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps worker scheduler`) if beat changed — code image me BAKED, sirf up -d purani image chalayega (2026-07-05).
- **Cost/quota:** LLM-heavy action → per-run cap + free_ai chain fallback (Mistral→Groq→…→static template), `SELFIMPROVE_COST_CAP` honored.
- **Evidence (done):** 5 test scenarios green + `.venv\Scripts\python.exe scripts\prod_check.py` + `.venv\Scripts\python.exe -m pytest tests\test_teach_agent_loop.py tests\test_parity_*.py -q` + `scripts\check_secrets.py`. Live-VPS enable = explicit user-auth, infer mat karo.

## See Also

- `audit-automation/SKILL.md` — Monitor action health
- `docs/AUTOMATION.md` — Architecture (3 loops)
- `app/agents/self_improve.py` — Task picking (source code)
- `app/platform/skill_library.py` — Learning mechanism (source code)
- `app/platform/team.py` — Staff roster (source code)
- `.claude/skills/orchestrate-goal/SKILL.md` — Using coordinator with actions
