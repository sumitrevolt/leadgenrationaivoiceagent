# Incident Runbooks — LeadGen AI

Project-specific incident runbooks for the live VPS (`leadsgenai.in`, `72.61.245.204`,
Docker, `/opt/leadgen`). These satisfy the Enterprise Playbook's `docs/runbooks/`
requirement with **real** project commands, containers, and scripts — not generic
templates.

## Standing facts (every runbook assumes these)
- **App** = Docker container `leadgen_app` :8000 (`docker compose -f docker-compose.vps.yml`).
- **Workers** = `leadgen_worker` + `leadgen_worker_heavy` (Celery) + `leadgen_scheduler` (beat) — `--profile celery`. Sahayak: `leadgen_postiz` (social) + `leadgen_waha` (WhatsApp). (2026-07-05)
- **Data** = Postgres `leadgen_db` via PgBouncer `pgbouncer:6432` + Redis `leadgen_redis` :6379 + Qdrant :6333.
- **SSH** (from Windows): `C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204`
- **Health gate:** `GET /health` must return `environment:production`. `GET /health/ready` checks DB+Redis pool.
- **Rollback (scheduler):** `.env` `RUN_IN_PROCESS_SCHEDULER=1` + `WEB_CONCURRENCY=1`, stop worker/scheduler, recreate app.
- **Self-heal:** `scripts/vps_selfheal.sh` runs */10 via cron. **Alerts:** `ops_alerts` → ntfy (`ntfy.leadsgenai.in`) + email.

## Runbook index
| # | Runbook | Trigger |
|---|---------|---------|
| 1 | [Queue Backlog](RUNBOOK_QUEUE_BACKLOG.md) | Celery queue depth grows, jobs delayed |
| 2 | [Scheduler Failure](RUNBOOK_SCHEDULER_FAILURE.md) | beat dead, jobs not firing, dead-man overdue |
| 3 | [Provider Outage](RUNBOOK_PROVIDER_OUTAGE.md) | LLM/STT/TTS provider 429/down |
| 4 | [Billing Incident](RUNBOOK_BILLING_INCIDENT.md) | payment/invoice/UPI dispute or duplicate |
| 5 | [Duplicate Outreach](RUNBOOK_DUPLICATE_OUTREACH.md) | lead contacted twice / opted-out contacted |
| 6 | [Security Incident](RUNBOOK_SECURITY_INCIDENT.md) | leaked secret, intrusion, DSAR, abuse |
| 7 | [Production Deploy Failure](RUNBOOK_PRODUCTION_DEPLOY_FAILURE.md) | deploy breaks health / 404 / 502 |

> Naye operator ke liye entry-point: [docs/HANDOFF.md](../HANDOFF.md)

## Incident process (all runbooks)
1. **Detect** (alert / probe / report).  2. **Declare** if customer impact — assign one owner.
3. **Stop the bleed** (pause the offending loop via its flag — OFF = inert).  4. **Diagnose** (logs + evidence).
5. **Recover** (rollback or targeted fix → smoke test → gradual re-enable).  6. **Post-incident** (RCA + regression test + update this runbook).

> **Golden rule (operating-manual):** measure before you mutate; root-cause once before
> symptom-fixing; never disable a compliance gate (DLT/DND/AI-disclosure/calling-window).
