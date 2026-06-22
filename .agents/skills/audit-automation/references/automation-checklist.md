# Daily/Weekly/Monthly Checklist — Automation Loop Health

Quick reference for keeping automation loops healthy without deep debugging.

---

## DAILY (5 min — Every Morning)

**Goal**: Catch dealbreakers before standup.

```
[ ] 1. Loop alive check
      Command: python scripts/automation_health_audit.py --daily-check
      ✅ = heartbeat <10 min old
      ⚠️ = heartbeat 10-30 min old (investigate cost/LLM)
      🔴 = heartbeat >30 min old (restart service immediately)

[ ] 2. Budget check
      Same output, look for "Budget Status" section
      ✅ = <40% spent today
      ⚠️ = 40-80% spent (monitor, may hit cap by EOD)
      🔴 = >80% spent (loop throttled or paused)

[ ] 3. Error check
      Same output, look for "Anomalies" section
      ✅ = no anomalies, DLQ depth 0
      ⚠️ = 1-2 actions with low success rate (acceptable)
      🔴 = DLQ >10 or task error rate >30% (debug)

[ ] 4. Queue check
      Same output, "Next Action" section
      ✅ = queue <3 items, current task progressing
      ⚠️ = queue 3-5 items (admin added goals)
      🔴 = current task stuck >240s, or queue >10
```

**If anything is red**: Stop, run full audit before continuing with day's work.

---

## WEEKLY (15 min — Monday Morning Review)

**Goal**: Identify trends, prevent drift, fix accumulating small issues.

```
[ ] 1. Success rate stability
      Command: python scripts/automation_health_audit.py --weekly-audit
      Look for "Skill Success Rates" section
      — Did any action drop <50%? Investigate 1–2 tasks
      — Did any action jump >95%? Great! Consider increasing weight

[ ] 2. Cost trends
      Same output, "Weekly Cost Summary"
      — Total spend: trending up/flat/down?
      — Most expensive action: still justified?
      — Outlier days: was there a spike? Why?

[ ] 3. Approval cycle time (if enabled)
      Same output, "Approval Metrics"
      — Average time pending: <30 min (good), 30-60 min (ok), >60 min (slow)
      — Oldest pending: >2h? Triage immediately
      — Approval rate: how many get rejected? Too high = gate too strict

[ ] 4. Lesson quality spot-check
      Command: tail -20 data/skill_lessons.jsonl
      — Read last 5 lessons from LLM reflection
      — Do they make sense? Or are they generic/wrong?
      — Example BAD lesson: "Cost is fake, spend unlimited"
      — If >1 bad lesson found: disable reflection temporarily + review

[ ] 5. Compliance checklist
      — [ ] DLT enabled? (check ENABLE_DLT env)
      — [ ] Opt-out list recent? (check /api/growth/compliance/optout-sync)
      — [ ] Call recordings being deleted per retention? (cron active)
      — [ ] High-risk actions gated? (voice calls need approval if sensitive)

[ ] 6. Deadletter queue
      Command: python scripts/automation_health_audit.py --dlq-status
      — How many failed tasks? >5 = investigate
      — Age of oldest failure? >24h = likely won't recover
      — Can auto-retry help, or should we remove permanently?
```

**Follow-up actions**:
- If success rates drop: disable action or add to low-priority rotation
- If cost trends up: identify which action spiked, tune parameters
- If lessons are bad: turn off reflection (SELF_IMPROVE_LEARN=0) + manual review
- If DLQ > 5: retry (`POST /api/growth/infra/dlq/retry`) or delete (are they safe to lose?)

---

## MONTHLY (1 hour — End-of-Month Deep Dive)

**Goal**: Comprehensive audit + long-term trend analysis + strategic adjustments.

### Step 1: Full Audit Report (10 min)
```bash
python scripts/automation_health_audit.py --monthly-report
# Outputs to: reports/automation_202606.txt
```

**Read**:
- Sections: Vital Signs, Action Performance, Cost Analysis, Lessons Learned, Risk Assessment
- Key metrics: % uptime, avg cost/task, success rate by action, top lessons, compliance gaps

### Step 2: Historical Comparison (10 min)
```bash
# Compare this month vs. last month
diff reports/automation_202605.txt reports/automation_202606.txt | head -50
# Or read both side-by-side, look for trends
```

**Questions to ask**:
- Did uptime improve? (should be >99%)
- Did average cost/task go up or down?
- Which actions improved? Which regressed?
- How many lessons did we learn? (should be >3/month)
- Did we hit compliance checks? (must be 100%)

### Step 3: Lesson Review (10 min)
```bash
# All lessons from this month
grep -E '"at".*202606' data/skill_lessons.jsonl | head -20
```

**Check for**:
- Are lessons actionable? (not generic like "more data is better")
- Any conflicting lessons? (lesson A says X, lesson B says not-X)
- Any hallucinations? (nonsensical advice)
- Are we actually applying top lessons? (link to actions taken)

**Red flags**:
- 0 lessons learned (reflection not working or disabled)
- >50% of lessons are generic ("success depends on multiple factors")
- Contradictory lessons from different agents

### Step 4: Cost Breakdown (10 min)
```bash
python scripts/automation_health_audit.py --monthly-report | grep -A 30 "Cost Analysis"
```

**Analyze**:
- Most expensive action: is it worth it? (ROI > 3x spend?)
- Least expensive action: can we increase frequency?
- Daily budget vs. actual: over- or under-spending?
- Cost per lead/outcome: trending better or worse?

### Step 5: Risk & Compliance (10 min)
```bash
python scripts/automation_health_audit.py --monthly-report | grep -A 20 "Risk Assessment"
```

**Check**:
- DLT coverage: are we calling compliant numbers only?
- Opt-out enforcement: how many leads were correctly skipped?
- Recording retention: auto-delete scheduled and active?
- Approval gates: are risky actions being reviewed?
- Data freshness: opt-out lists, DND cache, skill library all recent?

**Document**:
- [ ] All compliance checks passed? (must be yes)
- [ ] Any gaps or workarounds? (log for resolution)
- [ ] Any external blockers? (e.g., Vobiz DID/recharge pending)

### Step 6: Action Items & Recommendations (10 min)

**What changed this month**:
```
Changes:
 - Enabled CADENCE_ENGINE (new omnichannel sequence)
 - Added 3 new social drafting actions
 - Reduced sales_deepdive frequency (cost spike last week)
 
Results:
 - Overall success rate: 82% → 85% ✅
 - Cost efficiency improved 12% ✅
 - DLQ depth increased 1→5 (monitor) ⚠️
```

**Next month priorities**:
```
[ ] Investigate DLQ growth (is a task consistently failing?)
[ ] Test new action: [new_thing] (plan 2-3 runs)
[ ] Optimize [expensive action] (reduce frequency or improve success rate)
[ ] Update skill_library weights (reflect real success rates)
[ ] Review & apply top lesson: "[lesson]" (document where applied)
```

---

## COMPLIANCE WEEKLY (Dedicated Check)

**Run separately if compliance-heavy**:

```bash
python scripts/automation_health_audit.py --compliance-check
```

**Verify**:
1. **DLT setup**
   - [ ] Template IDs registered with provider (Vobiz/Twilio)
   - [ ] Outgoing calls use DLT-approved sender ID
   - [ ] Content matches approved template (no ad-lib)

2. **Opt-Out Enforcement**
   - [ ] DND list synced in last 24h? (check timestamp)
   - [ ] Outreach engine respects DND gate?
   - [ ] Calls blocked for opted-out? (verify in logs)

3. **Recording & Retention**
   - [ ] Calls being recorded? (check for files in data/recordings/)
   - [ ] Retention policy active? (delete after 90 days)
   - [ ] Cron job running? (check crontab for nightly cleanup)

4. **Consent Management**
   - [ ] Lead source tracks opt-in? (inquiry form, booking, etc.)
   - [ ] Consent recorded in database? (consent_ledger table)
   - [ ] Can users withdraw consent? (API endpoint working)

5. **Data Privacy**
   - [ ] PII not logged to stdout? (check logs for phone/email)
   - [ ] Data retention: old records deleted? (90-day archive)
   - [ ] Backup encrypted? (if offsite backup enabled)

---

## Approval Cycle Audit (If `SELF_IMPROVE_APPROVAL=1`)

**Weekly check**:
```bash
python scripts/automation_health_audit.py --approvals-pending
```

**Metrics**:
- Pending count: how many tasks waiting?
- Oldest pending: how long stuck?
- Approval rate: % approved vs. rejected
- Cycle time: from pick → execute (should be <30 min)

**Healthy baseline**:
- Pending: 0–2 tasks
- Oldest: <30 min old
- Approval rate: >80% (most are approved)
- Cycle time: avg 15–20 min

**If unhealthy**:
- Too much pending (>5)? Reduce approval scope or assign approvals to team
- Cycle too slow (>1h)? Reduce batch size or enable auto-approve for low-risk
- Rejection rate >20%? Gate is too strict; discuss with admin

---

## Template: Monthly Report Summary

```
═══════════════════════════════════════════════════════════
AUTOMATION LOOP MONTHLY REVIEW — JUNE 2026
═══════════════════════════════════════════════════════════

VITAL SIGNS:
  Uptime: 99.8% (1 restart on 2026-06-10)
  Heartbeat Misses: 0 (loop stable)
  Restarts: 1 (scheduled) ✅

COST:
  Total Spend: $287.50 (Budget: $1500)
  Daily Avg: $9.58 (trend: ↓ 3% vs May)
  Most Expensive: sales_deepdive ($145, 50% of spend)
  ROI: $287.50 spend → 156 leads → 3 customers → $18,000 revenue ✅

ACTIONS (Top 5):
  1. harvest_leads: 28 runs, 92% success, $0.45/run
  2. scrape_leads: 25 runs, 87% success, $0.02/run ⭐ (cheap!)
  3. seo_pages: 12 runs, 78% success, $1.50/run
  4. sales_deepdive: 8 runs, 88% success, $18.12/run (expensive, high-value)
  5. channel_experiments: 15 runs, 81% success, $0.87/run

LESSONS LEARNED:
  "High-volume cities (Mumbai, Delhi) > mid-size (Indore, Surat) by 3x"
  → Applied: Rebalanced niche frequency
  
  "Email + SMS combo > email alone (32% reply rate vs. 18%)"
  → Applied: Enabled CADENCE_ENGINE for omnichannel
  
  "Prospect freshness matters: <7 days old doubles conversion"
  → Applied: Increased scraping frequency for high-value niches

COMPLIANCE:
  DLT: ✅ Enabled (template 98765432)
  Opt-Out: ✅ Enforced (256 contacts skipped)
  Recording Retention: ✅ Auto-cleanup active (90-day policy)
  Data Privacy: ✅ PII logging clean

RISKS:
  DLQ Depth: 2 (healthy, <5)
  Low-Success Actions: None (<50%)
  Budget Overage: None (well under cap)
  Compliance Gaps: None

NEXT MONTH PRIORITIES:
  1. Test new action: "micro_influencer_outreach" (need 50 runs for learning)
  2. Optimize: sales_deepdive (cost up 8%, try sampling instead of full analysis)
  3. Compliance: Vobiz DID/recharge + DLT (unblocks cold calls)
  4. Lesson quality: Review reflection (3 generic lessons, reduce noise)

APPROVAL METRICS (if enabled):
  Pending Tasks: 0
  Avg Cycle Time: 22 min
  Approval Rate: 95%
  SLA Met: ✅ Yes

═══════════════════════════════════════════════════════════
```

---

## Quick Reference: When to Escalate

| Condition | Severity | Action |
|-----------|----------|--------|
| Heartbeat >30 min | 🔴 Critical | Restart service immediately |
| Budget >80% | 🔴 Critical | Pause loop, investigate cost spike |
| DLQ >10 | 🟡 High | Inspect errors, retry or remove tasks |
| Success rate <50% | 🟡 High | Disable action, review logs |
| Compliance gap | 🔴 Critical | Block automation, fix immediately |
| Approval backlog >5 | 🟡 High | Assign approvers or reduce scope |
| Lessons nonsensical | 🟡 High | Turn off reflection, manual review |
| Cost trend up >20% | 🟡 High | Audit expensive actions |

---

## See Also

- `audit-automation/SKILL.md` — Full health check guide (this skill)
- `automation_health_audit.py` — CLI script that runs these checks
- `docs/AUTOMATION.md` — Architecture reference
- `app/platform/automation_health.py` — Heartbeat mechanism
- `app/agents/self_improve.py` — Task picking + cost logic
