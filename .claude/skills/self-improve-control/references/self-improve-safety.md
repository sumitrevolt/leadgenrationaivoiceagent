# Self-Improve Loop: Safety Risk Matrix

Which tasks are **auto-safe** (run unsupervised) vs. **approval-required** (wait for human OK)?

## Risk Dimensions

| Dimension | Risk Level | Examples | Mitigation |
|-----------|-----------|----------|-----------|
| **External Action** | High | Cold email, WhatsApp auto-send, phone calls | Requires flag gate + approval |
| **Cost** | Medium | LLM-heavy (sales_team analysis = $5) | Cost cap + budget tracking |
| **Data Write** | Medium | Dunning case creation, invoice gen, lead scoring | Logged + reversible |
| **Compliance** | Critical | Any call/SMS without opt-in | DLT check + TRAI disclosure |
| **Irreversible** | High | Deleting leads, closing deals | Approval-gated, soft delete only |

---

## Task Safety Classification

### ✅ AUTO-SAFE (Run Immediately, No Approval)

**These tasks are read-only, deterministic, and low-cost.** Loop can run them unsupervised.

| Task | Cost | Risk | Notes |
|------|------|------|-------|
| `prospector.scrape` | $1-3 | Low | Read OSM/Places, no external post |
| `lead_harvester.run` | $1-2 | Low | Harvest from public data |
| `growth_optimizer.analyze` | $0.5-1 | Low | Analyze existing data, no action |
| `skill_library.refresh` | $0 | Low | Scan disk, update success rates |
| `content.digest_generate` | $1-2 | Medium | Generates email draft (not sent) |

**Approval**: None. Run on schedule.

---

### ⚠️ MODERATE RISK (Approval Recommended)

**These tasks have external reach but are gated / low-volume.** Recommend approval on first 3 runs, then auto-trust.

| Task | Cost | Risk | Gate | Notes |
|------|------|------|------|-------|
| `cadence.run_due` | $0.5-1 | Medium | Flag: CADENCE_ENGINE | Sends enqueued emails/WA (pre-approved by human) |
| `email_outreach.auto_send` | $2-5 | Medium | Flag: AUTO_EMAIL_OUTREACH; daily cap 25 | Cold emails, MX-verified, paced |
| `reply_agent.triage` | $0.5 | Low | Flag: REPLY_AGENT | Reads inbound, drafts reply (no send) |
| `process_engine.advance` | $1-3 | Medium | Deterministic (no LLM) | Moves deal stage (audit-logged) |
| `client_health.alerts` | $0.5 | Low | Flag: CLIENT_HEALTH_ALERTS | Emails admin only (not customer) |

**Approval**: First 3 runs = review audit log. After: auto-trust, but monitor cost.

---

### 🔴 APPROVAL-REQUIRED (Always Ask Before Running)

**These tasks have high risk, cost, or compliance implications.** Loop must wait for `SELF_IMPROVE_APPROVAL=1` + human click.

| Task | Cost | Risk | Why | Mitigation |
|------|------|------|-----|-----------|
| `call_manager.make_callback` | $0.50-2 | Critical | TRAI DLT required; opt-in tracking | Verify DLT approval first |
| `whatsapp_campaign.send_auto` | $1-3 | High | Number ban if too aggressive | Manual approval per campaign |
| `sales_team.deep_dive` | $3-8 | Medium | LLM-heavy, highest cost | Budget cap + approval UI |
| `dunning.run_sweep` | $1-2 | Medium | Writes case records, sends email | Review dunning cases first |
| `billing.auto_invoice` | $0.1 | Medium | Tax/legal doc, must audit | Verify invoice count |
| `lead_scoring.rescore_db` | $2-5 | Medium | Bulk DB writes (reversible) | Approval before running |

**Approval**: Require `SELF_IMPROVE_APPROVAL=1` + `/app/automation` UI button "Approve" per task.

---

## Cost Allocation Strategy

Default daily budget: **$50/day** (tunable via `SELFIMPROVE_COST_CAP`).

Suggested allocation (by priority):

| Tier | Budget | Tasks | Example |
|------|--------|-------|---------|
| **Tier 1 (Lead Loop)** | $20 | prospector + cadence | Niche rotation + MX verify |
| **Tier 2 (Sales Loop)** | $15 | sales_team + process_engine | Deep dives on hot leads |
| **Tier 3 (Growth Loop)** | $10 | growth_optimizer + skill_refresh | Analyze + learn |
| **Tier 4 (Reserve)** | $5 | Unexpected high-value task | One-off expensive analysis |

When daily spend hits cap → loop stops; waits for reset at 00:00 UTC.

---

## Approval UI Behavior

When `SELF_IMPROVE_APPROVAL=1` is set:

1. **Loop picks a task** (bandit + Reflexion)
2. **Task queued in** `data/automation_audit.jsonl` with status `pending`
3. **Admin sees** `/app/automation` → "Pending Approvals" section:
   ```
   [Task: sales_team.deep_dive | Cost: $5.20 | Reason: "18 hot leads ready for analysis"]
   [✅ Approve] [❌ Reject] [📋 History]
   ```
4. **Admin decides**:
   - ✅ **Approve** → task executes immediately, logged as `approval: admin:sumit`
   - ❌ **Reject** → task skipped, bandit learns not to pick it again
   - **Timeout** (24h) → task auto-cancels (prevents stale approvals)

---

## Compliance Checklist

If your loop ever interacts with **regulated channels** (calls, SMS):

- [ ] **DLT approval**: All SMS/voice tasks require DLT exemption or opt-in list
- [ ] **Opt-in tracking**: `consent_ledger` recorded before any auto-call/SMS
- [ ] **TRAI disclosure**: "This is an AI call" greeting played at start
- [ ] **DND check**: Before cold calls, `dnd_checker.verify()` runs
- [ ] **Recording retention**: Calls retained 90 days max (see `RECORDING_RETENTION` flag)
- [ ] **Audit log**: Every outbound interaction logged with timestamp + consent status

**If loop ever picks a cold-call or bulk-SMS task**:
1. **Stop**: Set `SELF_IMPROVE_LOOP=0`
2. **Verify**: Check DLT status (provider dashboard / Vobiz)
3. **Clear**: Ensure opt-in list is current
4. **Resume**: Set flag back to 1

---

## Tuning the Loop

### Lower Cost

- Increase `SELFIMPROVE_COST_CAP` threshold (less often paused)
- Or: deprioritize expensive tasks in `skill_library.jsonl` (reduce weight)
- Or: split large task into smaller ones (e.g., "analyze all hot leads" → "analyze top-5 hot leads")

### Better Outcomes

- Check reflection quality: `python scripts/selfimprove_audit.py --memory-audit`
- If lessons are hallucinating, reduce task complexity (see Step 4 in SKILL.md)
- Manually inject hints when you spot an opportunity (Step 4)

### Stricter Safety

- Set `SELF_IMPROVE_APPROVAL=1` (all tasks need click)
- Set `SELFIMPROVE_COST_CAP=10` (low daily budget, forces prioritization)
- Reduce task roster: `data/skill_library.jsonl` — remove high-risk tasks temporarily

---

## Decision Tree: Should I Approve This Task?

```
Task pending approval. Ask yourself:

1. Do I recognize the task?
   NO → Reject. Loop may have hallucinated or found a new action.
   
2. Is the cost reasonable for the potential outcome?
   NO → Reject. Check skill_library success_rate first.
   
3. Is this the right time (given current leads/prospects)?
   NO → Reject, or Hint the loop toward a better task.
   
4. Do I have budget left today?
   NO → Reject for now. It'll queue for tomorrow.
   
5. Have I verified compliance (if external action)?
   NO → Reject. Check DLT/opt-in/TRAI first.
   
6. ✅ All above → Approve.
```

---

## Examples

### Scenario 1: "Sales team deep-dive is expensive. Should I approve?"

```
Task: sales_team.deep_dive
Cost estimate: $5.20
Reason picked: "18 hot leads ready (avg score 0.68)"
Success rate: 0.78 (7/9 runs, avg 4.2 qualified leads per run)

Decision:
- Cost/outcome: $5.20 / 4.2 = $1.24 per lead = reasonable
- Budget: $50 cap, current spend $18 = $32 left = OK
- Time: Yes, 18 leads queued = right time
→ APPROVE
```

### Scenario 2: "Loop keeps picking an expensive task with mediocre outcomes. What do I do?"

```
Task: growth_optimizer.brainstorm
Cost: $8/run (Cerebras LLM-heavy)
Success rate: 0.45 (2/5 runs, most ideas unused)
Picked 5 days in a row

Decision:
→ REJECT this task
→ Check skill_library: manually reduce success_rate for this task to 0.3
→ Loop will deprioritize it (bandit learns)
→ Hint loop toward prospector instead (higher success)
```

### Scenario 3: "Loop wants to cold-call unsolicited. What do I do?"

```
Task: call_manager.make_callback
Compliance note: "DLT status = notstarted"
Cost: $1.50/min

Decision:
→ REJECT
→ Action: Verify Vobiz DID + DLT approval (dashboard)
→ Until DLT approved, add call tasks to "APPROVAL_REQUIRED" list in code
→ Document in AUTOMATION.md under "Voice DLT workflow"
```
