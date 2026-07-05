---
name: dr-restore-drill
description: Disaster-recovery backup + RESTORE drill for leadsgenai.in — Postgres pg_backup, rclone offsite (Drive/R2/B2), data/ dir backup, freshness checks, quarterly restore rehearsal, RTO/RPO targets. Use jab backup verify karna ho, restore test karna ho, "kya hum data-loss se bachenge" poochha jaye, ya VPS rebuild/migration plan bane.
---

# DR Restore Drill (backup jo restore-tested nahi = backup NAHI hai)

> Enterprise audit skill. Backup EXIST karna kaafi nahi — enterprise bar = **restore PROVEN**. Pehle `context-first`.

## Repo truth
- **DB backup**: `scripts/pg_backup.sh` (host cron `30 2 * * *`, 30d retention) — Postgres `leadgen_db` dump.
- **data/ backup**: `scripts/data_backup_rclone.sh` (cron `45 2 * * *`, 7d retention, full `data/` dir — email 18MB cap bypass).
- **Offsite**: rclone → `RCLONE_REMOTE` (gdrive:leadgen-backups / R2 / B2, zero code diff). Config: `deploy/offsite/rclone.conf.example`. Email-backup cron (Hostinger mail) = secondary.
- **Freshness alert**: `scripts/backup_offsite_check.py` (generic, remote-agnostic).
- **Rollback assets**: SQLite `/opt/leadgen/leadgen.db` (DB rollback-backup only) · systemd `leadgen` installed-but-disabled (container rollback) · `requirements.lock.txt` + baked image (rebuild deterministic).
- **Kya backup NAHI hota (audit karo)**: Redis (transient by design — celery queue regenerable), Qdrant `kb_main` (kb-refresh Sun 05:00 se rebuild hota — RPO = 1 week, document karo), `.env` (offsite copy MANUAL — sabse bada single-point!), Grafana dashboards (provisioning me hai = git-safe).

## RTO/RPO targets (single-VPS reality)
- RPO: DB ≤24h (daily dump) · data/ ≤24h · Qdrant ≤7d (rebuildable) · .env = jab last manual copy hui (FIX: encrypted offsite copy per rotation).
- RTO: fresh VPS + Docker + git pull + image build + pg_restore + .env = target **≤4h**. Drill me MEASURE karo, guess mat karo.

## Quarterly restore drill (evidence mandatory)
1. Latest offsite dump fetch: `rclone ls $RCLONE_REMOTE` → newest `pg_*.sql.gz` + `data_*.tar.gz` download.
2. Scratch restore (PROD ko touch mat karo): `docker run -d --name dr_test postgres:16` → `gunzip -c dump | psql`.
3. Verify queries: clients count, subscriptions count, consent_ledger rows, latest lead timestamp vs RPO.
4. data/ tar extract → spot-check `voice_gemini_keys.json`, `job_heartbeats.json`, `ai_images/` present.
5. Evidence log → `docs/SESSION_LOG.md` (date, dump age, row counts, restore minutes = measured RTO).
6. Cleanup scratch container. Fail mile → blocker ticket, backup script fix SHIP karo (decide-and-ship).

## Full-VPS rebuild runbook (worst case)
Fresh Ubuntu 24.04 → Docker install → git clone (main) → `.env` restore (encrypted copy se) → `docker compose -f docker-compose.vps.yml build app` → db up → pg_restore → data/ untar → `up -d` full stack → Caddy/DNS point → `/health` = `environment:production` → self-heal cron + backup crons re-install (`vps_selfheal.sh`, pg_backup, data_backup_rclone, obsidian_host_push).

## Output
Backup coverage matrix (store × frequency × retention × offsite × restore-tested Y/N) · measured RTO/RPO vs target · gaps + fixes shipped · drill evidence in SESSION_LOG.

## Related repo skills
`leadgen-infra-doctor` (prod diagnose) · `hostinger-deploy` (VPS gotchas) · `prod-incident-triage` (live incident) · `secrets-rotation` (.env offsite handling).
