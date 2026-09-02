---
name: automate
description: Set up recurring automation for LeadGen — Celery beat jobs, cron on VPS, or Cursor Automations when in Cursor IDE. Use when user asks to automate deploy checks, outreach, or scheduled agent tasks.
---
# Automate (LeadGen)

**Disambiguation:** "automate" ≠ always Cursor Automations.

| Surface | Use when |
|---------|----------|
| **LeadGen Celery** | Production jobs — `app/worker.py` beat, `team_scheduler` |
| **VPS cron** | Backups, pg_restore, self-heal |
| **Cursor Automations** | User explicitly says "Cursor Automation" — only in Cursor Agents Window |

## LeadGen path (default)

1. Identify job: existing `team_scheduler._run_job` / `worker.py` entry?
2. New job → `scheduler-job` skill: wire 6-layer (beat + `_run_job` + flag + health gap).
3. Flag in `AUTOMATION_FLAGS` — default OFF.
4. Verify: `scripts/automation_health_audit.py --daily-check`

## Cursor Automations path

Only if `cursor-app-control.open_automation` available — see Cursor `automate` skill in IDE. Repo me Celery = source of truth for leadsgenai.in.

## Ban-safe

Auto-send email/WA/calls = gated + capped. Coordinator never auto-executes side effects.
