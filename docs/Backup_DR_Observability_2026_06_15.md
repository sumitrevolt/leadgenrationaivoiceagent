# Backup/DR Observability — Silent-Failure Alerting

**Date:** 2026-06-15 · **Scope:** Deep backup/DR analysis; close the one real micro-gap (no alerting on backup/drill failure).
**Outcome:** Backup + restore-drill emit Prometheus textfile metrics → 4 alerts. Builds on the exporter suite (same session). bash + YAML validated.

---

## 1. Deep analysis — backup/DR pehle se MATURE (no big gap)

Scripts dekhe — backup story genuinely solid hai:
- **`pg_backup.sh`** — nightly `pg_dump -F c | gzip -9`, 30-day local retention, optional rclone offsite (R2/B2, gated). Cron 02:30.
- **`pg_restore_drill.sh`** — monthly THROWAWAY-container restore + table/row verification, PASS/FAIL. Cron monthly. ("untested backup = no backup" — already implemented!)
- **PITR** (`pg_pitr_enable.sh` + walarchive volume) · **offsite_email_backup.py** · **vps_backup.sh**.

Yeh mature hai — **bada gap nahi**. (Isliye check kiya — duplicate nahi banaya.)

## 2. The real micro-gap

`pg_backup.sh` + `pg_restore_drill.sh` cron pe chalte hain par PASS/FAIL sirf **log-file** me jaata (`/var/log/leadgen_backup.log`, `/var/log/leadgen_drill.log`). **Agar backup ya drill FAIL ho to koi ALERT nahi** — "silent backup failure" = #1 DR trap (teams ko corruption disaster ke time pe pata chalta hai). Single-VPS pe (no HA) backup hi recovery hai → uska silent-fail unacceptable hai.

## 3. Fix — textfile metrics → alerting (leverages new node_exporter)

- **`pg_backup.sh`** — success pe `leadgen_pg_backup_last_success_timestamp_seconds` + `_size_bytes` likhta (atomic, best-effort `|| true` — backup ko kabhi fail nahi karta). Fail = timestamp stale = alert.
- **`pg_restore_drill.sh`** — exit-trap se `leadgen_pg_restore_drill_success` (1=pass/0=fail) + timestamp (saare exit-paths covered).
- **node_exporter** — `--collector.textfile.directory=/textfile` + `/opt/leadgen/backups/metrics:/textfile:ro` mount → ye `.prom` files scrape karta.
- **alert_rules.yml** (`infrastructure` group):
  - **BackupStale** — koi successful backup >26h se nahi (critical).
  - **BackupMetricMissing** — backup metric kabhi nahi (cron/mount check, warning).
  - **RestoreDrillFailed** — `drill_success==0` (critical, backup suspect).
  - **RestoreDrillStale** — koi drill >40 din se nahi (warning).

## 4. Discipline
Backup khud SOLID tha — naya backup tool (pgBackRest/Barman) NAHI add kiya (over-engineering; existing pg_dump+drill+PITR single-VPS ke liye kaafi). Sirf **observability+alerting** wala thin layer add kiya jo existing scripts + naye exporters ko join karta. No new container, no new dep.

## 5. Verification + deploy
- `bash -n` dono scripts OK · YAML OK · infrastructure group ab 11 alerts (7 USE + 4 backup).
- **Deploy = obs-compose only (no app rebuild)** — exporters wale step ke saath: `git pull` → `docker compose -f docker-compose.observability.yml up -d` (node_exporter recreate w/ textfile mount) → `curl -X POST 127.0.0.1:9090/-/reload`. Metrics next cron-run pe (ya manual `bash scripts/pg_backup.sh`) populate. `mkdir -p /opt/leadgen/backups/metrics` (scripts khud bhi karte).

### Files
- `scripts/pg_backup.sh` · `scripts/pg_restore_drill.sh` · `docker-compose.observability.yml` (node_exporter textfile) · `monitoring/alert_rules.yml` (4 backup alerts)

## Sources
- "Untested backup = no backup" / restore-testing levels — https://oneuptime.com/blog/post/2026-01-21-postgresql-backup-testing/view · https://dev.to/piteradyson/postgresql-backup-verification-how-to-test-and-validate-your-postgresql-backups-2al8
- node_exporter textfile collector — https://github.com/prometheus/node_exporter#textfile-collector
