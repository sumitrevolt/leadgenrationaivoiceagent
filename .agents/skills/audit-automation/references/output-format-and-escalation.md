> Verbatim: full health-check output formats (human-readable + JSON) and the yellow/red escalation checklist. See SKILL.md for the 6-step check.

## Health Check Output Format

**Human-readable output** (default):
```
╔════════════════════════════════════════════════════════╗
║ AUTOMATION HEALTH CHECK — 2026-06-14 10:15:00Z        ║
╚════════════════════════════════════════════════════════╝

1. LOOP ALIVE
   Status: ✅ HEALTHY (last tick 8 min ago)
   Heartbeat: data/self_improve_state.json (last_tick: 2026-06-14T10:07:32Z)
   Worker: ✅ celery@worker.1 responding (ping: 87ms)

2. BUDGET
   Today Spend: $12.34 / $50.00 (24% of cap)
   Trend: On pace for $38.50 end-of-day (normal)
   Actions by Cost:
     • sales_deepdive: $8.50 (69% of spend)
     • harvest_leads: $2.10
     • seo_pages: $1.74

3. APPROVALS
   Status: ✅ Not enabled (SELF_IMPROVE_APPROVAL=0)
   (Skipped for this check)

4. ANOMALIES
   Status: ✅ NONE DETECTED
   Task Success Rates:
     • scrape_leads: 95% (20 uses)
     • harvest_leads: 88% (10 uses)
     • sales_deepdive: 92% (12 uses)
   DLQ Depth: 0 (clean)

5. NEXT ACTION
   Current: harvest_leads (running 4 min, ETA 6 min remaining)
   Queue Pending: 2 manual tasks
   Auto-Pick Next: channel_experiments (74% rate, cooldown OK)

6. COMPLIANCE
   DLT Status: ✅ ENABLED (template 1234567890)
   Opt-Out Enforced: ✅ (synced 2h ago)
   Recording Retention: ✅ Cleanup scheduled daily 03:00Z
   High-Risk Approval: ✅ ON for voice/calls

═══════════════════════════════════════════════════════════
VERDICT: ✅ ALL GREEN — Loop healthy, no action needed.
```

**JSON output** (for dashboards/monitoring):
```json
{
  "timestamp": "2026-06-14T10:15:00Z",
  "checks": {
    "alive": {"status": "green", "last_tick_min": 8, "worker_ping_ms": 87},
    "budget": {"status": "green", "spent": 12.34, "cap": 50.0, "percent": 24},
    "approvals": {"status": "disabled"},
    "anomalies": {"status": "green", "dlq_depth": 0, "low_success_count": 0},
    "next_action": {"current": "harvest_leads", "queue_pending": 2},
    "compliance": {"dlt_enabled": true, "optout_enforced": true, "retention_active": true}
  },
  "verdict": "green",
  "actions": []
}
```

---

## Escalation Checklist

**If status is 🟡 Yellow**: Investigate but don't panic.

- [ ] Check `/api/growth/infra/automation-health` dashboard
- [ ] Look at last 10 runs in `data/self_improve_runs.jsonl`
- [ ] If cost spike: check `llm_metrics` for provider degradation
- [ ] If low success: pull skill_library stats + see which action is failing
- [ ] Log entry point: `tail -f logs/automation.log`

**If status is 🔴 Red**: Immediate action required.

1. **Loop not alive** (>30 min heartbeat):
   - [ ] `systemctl status leadgen` or `docker ps` (is service running?)
   - [ ] Check error logs: `tail logs/app.log` (any crash?)
   - [ ] Try restart: `systemctl restart leadgen` or `docker restart leadgen_app`
   - [ ] If worker: `celery -A app.worker inspect ping` (is worker responding?)
   - [ ] If still stuck: page on-call engineer

2. **Budget exceeded** (>80%):
   - [ ] Pause: `export SELF_IMPROVE_LOOP=0; systemctl restart leadgen`
   - [ ] Check LLM provider: `python scripts/automation_health_audit.py --llm-status`
   - [ ] If quota exhausted: increase `SELFIMPROVE_COST_CAP` or wait for quota reset
   - [ ] Review spiked task: was it cost-aware? Remove if wasteful.
   - [ ] Re-enable when safe

3. **Approvals stuck** (>5 pending):
   - [ ] Review pending via API or dashboard
   - [ ] Approve safe ones, reject others
   - [ ] Consider disabling approvals for low-risk actions if cycle time hurts velocity

4. **Anomalies detected** (errors, hallucinations):
   - [ ] Pause loop: `export SELF_IMPROVE_LOOP=0`
   - [ ] Inspect error logs + skill_library lessons
   - [ ] Remove malformed lessons from `data/skill_lessons.jsonl` (if safe)
   - [ ] Disable failing action from `_STAGE_ACTIONS` in `self_improve.py`
   - [ ] Restart and monitor

5. **Compliance alert**:
   - [ ] DLT not enabled? Set up via Vobiz + `ENABLE_DLT=1`
   - [ ] Opt-outs ignored? There is NO `scripts/dnd_sync.py` — do not look for it.
         The DND cache is IN-MEMORY (`app/utils/dnd_checker.py`, `DNDChecker._cache`,
         7-day expiry) and clears on process restart; there is nothing to rebuild.
         Correct checks, in order:
           1. `DND_FAIL_OPEN` MUST be unset/0. If set to 1 in production it is
              refused and logged CRITICAL (`app/telephony/compliance.py:173`),
              but unset it anyway — there is no legitimate prod use.
           2. Opt-outs are authoritative from the local consent ledger, NOT the
              registry API (`dnd_checker.py:36-38`). Verify the ledger, not the cache.
           3. An un-cached number returns UNVERIFIED and the gate fails CLOSED
              (`compliance.py:266-278`). "No result" is safe, not a bug.
           4. Restart the worker to drop the in-memory cache if you suspect staleness.
   - [ ] Recording retention? Verify `RECORDING_RETENTION_DAYS` set + cron active
