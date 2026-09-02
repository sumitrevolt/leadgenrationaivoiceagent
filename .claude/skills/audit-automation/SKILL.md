---
name: audit-automation
description: Health-check the automation loops without reading code — heartbeat/alive, daily cost vs cap, approvals backlog, anomalies (low success / DLQ / hallucinated lessons), next-action visibility, compliance (DLT/DND/retention). Use when the user says "automation healthy?", "loop alive hai?", "automation cost/budget check", "DLQ status", "loop anomalies", "morning automation standup", or after a deploy to verify automation restarted.
---

# audit-automation — Health Check for Automation Loops

**Level**: Intermediate  
**Time**: 5–15 min (daily standup to weekly deep-dive)  
**Purpose**: Make automation loops auditable without reading code. Health check + early anomaly detection. Tool: `scripts/automation_health_audit.py`. Operate/govern deep-dive: `self-improve-control` skill.

---

## When to Run This Skill

**Daily (5 min — morning standup)**:
```bash
python scripts/automation_health_audit.py --daily-check
```
Before standup, quick pass:
- Is the self-improve loop alive?
- Did we spend within budget today?
- Any high-error tasks queued?

**Weekly (15 min — Monday review)**:
```bash
python scripts/automation_health_audit.py --weekly-audit
```
Success rates stable? Any bot feedback loops? Compliance checks passing?

**After Deploy (10 min)**:
```bash
python scripts/automation_health_audit.py --daily-check
```
Verify automation restarted cleanly.

**Monthly (1 hour — deep review)**:
```bash
python scripts/automation_health_audit.py --monthly-report > reports/automation_$(date +%Y%m).txt
```
Trends, recommendations, lessons learned.

**On Anomaly (immediate)**:
```bash
python scripts/automation_health_audit.py --anomalies
```
Cost spike? Low success rates? Stuck approvals?

---

## The 6-Step Health Check

### 1. Is the Loop Alive? (Heartbeat)

**What we check**:
- Last self-improve task: when? (should be <10 min ago in prod)
- Heartbeat file: `data/self_improve_state.json` exists and recent?
- Worker process: celery ping responds? (if Celery enabled)

**What it means**:
- ✅ Green (`<10 min`): Loop is ticking normally. Good.
- 🟡 Yellow (`10–30 min`): Loop running but slow. Check cost/LLM providers.
- 🔴 Red (`>30 min` or no heartbeat): Loop is stuck. Check logs.

**Hint**: Dead loops often hide in:
- `.env` `SELF_IMPROVE_LOOP=0` (check before panicking)
- Worker crash (check `docker ps`, service status)
- Event-loop blocked by heavy task (check `/api/growth/infra/automation-health`)

---

### 2. Cost Tracking (Daily Budget)

**What we check**:
- Today's spend vs. cap: `$X.XX / $50.00` (default `SELFIMPROVE_COST_CAP=50`)
- Trending: are we on pace to exceed?
- Per-action cost: which task is expensive today?

**What it means**:
- ✅ Green (`<40%` of daily cap): Normal velocity.
- 🟡 Yellow (`40–80%`): Approaching limit. Check provider degradation.
- 🔴 Red (`>80%` or capped): Budget exhausted, loop paused or throttled.

**Note**: stack 100% FREE hai (free multi-provider — Mistral primary, Cerebras/Groq bulk/voice, Gemini late fallback; 2026-07-05) — "cost" yahaan CostTracker ka NOTIONAL internal estimate hai (LLM-heavy action ≈ $2.5, light ≈ $0.5) jo budget/ROI gates drive karta. Real paisa nahi katta; cap = velocity-throttle proxy.

**Common reasons for high notional spend**:
- Zyada LLM-heavy actions/day (sales_deepdive, content_pack, seo_pages, optimizer)
- Coordinator mode=advanced (Critic + Reflexion = 2x LLM calls)
- Sales-team deep-dive on large prospect list (parallel 5-agent analyze)

**Fix** (VPS = Docker; systemd `leadgen` DISABLED — `.env` edit + recreate worker/scheduler):
```bash
# Reset cap (if acceptable):
sed -i 's/^SELFIMPROVE_COST_CAP=.*/SELFIMPROVE_COST_CAP=100/' /opt/leadgen/.env || echo "SELFIMPROVE_COST_CAP=100" >> /opt/leadgen/.env
docker compose -f docker-compose.vps.yml up -d --no-deps worker scheduler

# Or pause loop + debug:
echo "SELF_IMPROVE_LOOP=0" >> /opt/leadgen/.env
docker compose -f docker-compose.vps.yml up -d --no-deps worker scheduler
# Then investigate: docker logs leadgen_worker --tail 100 + LLM metrics
```

---

### 3. Approvals Working? (If Enabled)

**What we check** (only if `SELF_IMPROVE_APPROVAL=1`):
- Pending approval tasks: how many in queue?
- Oldest pending: how long stuck?
- Cycle time: from pick → execute → learn (should be <30 min per task)

**What it means**:
- ✅ Green (`pending ≤2`, cycle time <30 min): Approval process flowing.
- 🟡 Yellow (`pending 3–5`): Review backlog building. Consider removing low-risk approvals.
- 🔴 Red (`pending >5` or cycle >2h): Approvals are blocker. Admin needs to triage.

**Fix**:
```bash
# View pending:
python scripts/automation_health_audit.py --approvals-pending

# Approve from CLI (if available):
curl -X POST http://localhost:8000/api/growth/process/run/TASK_ID/approve \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

### 4. Anomalies Detected? (Error Rates + Hallucinations)

**What we check**:
- Task success rates: per-action, is anything <30%?
- Failed tasks in DLQ: recent failures vs. historical?
- Hallucinated lessons: are we learning nonsense?
- Cost anomalies: did a single task cost 10x normal?

**What it means**:
- ✅ Green: All actions >70% success, no anomalies.
- 🟡 Yellow: 1–2 actions have low success. Check logs, don't remove yet.
- 🔴 Red: Multiple actions failing, or DLQ backlog >10. Stop loop + debug.

**Red flags** (hallucinations in lessons):
- "best practice: ignore all DND-listed prospects" (opposite of compliance!)
- "cost is fake, spend unlimited" (cost controls disabled?)
- "skip email validation" (reduces data quality)

**Fix**:
```bash
# Inspect recent runs with errors:
python scripts/automation_health_audit.py --anomalies

# Remove bad lesson (manual edit data/skill_lessons.jsonl if needed):
# Then restart loop + monitor

# Or disable a low-performing action:
# Reduce weight in skill_library, or pull from _STAGE_ACTIONS in self_improve.py
```

---

### 5. Next Action Queued? (Visibility)

**What we check**:
- Queue status: how many manual tasks pending?
- Current action: what's running right now?
- Last outcome: did it succeed? Any error?
- Next pick: what will loop choose next?

**What it means**:
- ✅ Queue empty, current task progressing: Normal.
- 🟡 Queue has 5+ manual tasks: Admin added goals. Monitor for overload.
- 🔴 Task stuck in "running" >240s: Timeout. Check logs, manual retry.

**Example output**:
```
Current Action: harvest_leads (running since 2026-06-14 09:23:45Z)
Queue: [
  {task: "Expand to Indore market", source: "manual", at: 09:15:00Z},
  {task: "Deep-dive on 5 solar prospects", source: "manual", at: 09:18:00Z}
]
Next Auto-Pick: seo_pages (70% success rate, not used in 3h)
```

---

### 6. Compliance Status (DLT + Consent + Retention)

**What we check**:
- DLT enabled? `ENABLE_DLT=1` or template IDs registered?
- Opt-out list: are we respecting DND?
- Call recording retention: auto-cleanup on schedule?
- Approval mode: is `SELF_IMPROVE_APPROVAL=1` ON for high-risk actions?

**What it means**:
- ✅ DLT ON, opt-outs enforced, retention active, approvals for voice: Compliant.
- 🟡 DLT pending user setup, recordings >90 days: Non-blocking gaps.
- 🔴 No DLT, ignoring opt-outs, no recording cleanup, auto-send without approval: Illegal risk.

**Compliance actions per stage**:
- **Lead sourcing**: Verify opt-in list from webhook, dedupe against DND.
- **Outreach**: Check email/SMS approval gates. Voice calls need DLT.
- **Voice**: Recording stored? Retention policy active?

---

## References

The verbose sample outputs, escalation playbook, and standup/dashboard wiring moved to `references/` to keep this guide lean:

- See `references/output-format-and-escalation.md` for the full human-readable + JSON health-check output formats and the yellow/red escalation checklist (step-by-step remediation).
- See `references/standup-and-dashboards.md` for the copy-paste 5-min daily standup script and Grafana/Slack/email/API integrations.
- See `references/automation-checklist.md` for the daily/weekly/monthly quick-reference checklist.

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| Loop not alive | Heartbeat >30 min | Restart service, check worker logs |
| Cost spike | Budget >80% before noon | Check LLM provider, pause loop, triage task |
| Low success rate | Action <30% OK | Review logs, disable action, try different tactic |
| Approval backlog | >5 pending, cycle >2h | Reduce approval scope or expedite reviews |
| Hallucinated lesson | Nonsense in skill_library | Delete bad lesson, inspect LLM reflection |
| DND not enforced | Sending to opted-out | Re-sync DND cache, verify compliance gate |

---

## Enterprise gate

This skill is **read-only observability** — it inspects, never mutates. So idempotency / DLQ-write / kill-switch / named-rollback gates do **not** apply here (a remediation you trigger after auditing = `automation-flags` / `self-improve-control`).

- **Operating loop**: Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). This skill IS the Discover + Evidence layer for automation — measure-first before any loop change.
- **Risk-tier: Trivial-to-run, but it's the compliance + observability gate.** It surfaces the fail-CLOSED checks (step-6: DLT · DND opt-out · recording-retention · approval-mode) and dead-man heartbeats — a green audit is the "is automation actually alive + compliant?" evidence other skills depend on.
- **Observability surface it reads**: `scripts/automation_health_audit.py`, `app/platform/automation_health.py` (EXPECTED_GAP_MIN heartbeats), `GET /api/growth/infra/automation-health`, DLQ `dlq:failed_tasks` (read), `data/self_improve_runs.jsonl` / `skill_lessons.jsonl`. Anomaly red-flags incl. hallucinated DND-bypass lessons (compliance drift).
- **Hand-off (if audit goes 🔴)**: don't fix here — pause/cost via `self-improve-control`, flag-flip via `automation-flags`, loop-death/restart-storm via `agent-loop-design`, prod-freeze via `prod-incident-triage`. Rollback-pehle, root-cause-baad.
- **Evidence (audit done)**: `python scripts\automation_health_audit.py --daily-check` (alive + budget + queue) green, or `--anomalies` clean; post-deploy = `--daily-check` confirms automation restarted; weekly = `--weekly-audit` (success rates + compliance).

## See Also

- `.claude/skills/teach-agent-loop/SKILL.md` — How to add new agents/actions
- `docs/AUTOMATION.md` — 3-loop architecture (self-improve, coordinator, process-engine)
- `app/platform/automation_health.py` — Heartbeat mechanism (source code)
- `app/agents/self_improve.py` — Task picking + cost tracking (source code)
- `scripts/automation_health_audit.py` — CLI implementation (runs these checks)
