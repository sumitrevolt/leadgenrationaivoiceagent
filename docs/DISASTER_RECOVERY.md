# Disaster Recovery Plan — LeadGenAI

> **Scope:** Single VPS Mumbai (SPOF) · **Deep detail:** [`Backup_DR_Observability_2026_06_15.md`](Backup_DR_Observability_2026_06_15.md) · [`PRODUCTION_CUTOVER.md`](PRODUCTION_CUTOVER.md)
> **Updated:** 2026-06-20

---

## 1. Objectives

| Metric | Target | Notes |
|--------|--------|-------|
| **RPO** (max data loss) | ≤24h | Nightly pg_dump 02:30 IST; `./data` bind-mount |
| **RTO** (restore to serving) | 1–4h | Manual VPS rebuild + restore |
| **HA** | None (by design) | Second server = future spend |

---

## 2. What is backed up

| Asset | Method | Location | Retention |
|-------|--------|----------|-----------|
| Postgres | `scripts/pg_backup.sh` | `/opt/leadgen/backups/` | 30 days |
| Restore drill | `scripts/pg_restore_drill.sh` | Monthly verify | PASS/FAIL metrics |
| `.env` | `vps_backup.sh` / email cron | Offsite email | Operator mailbox |
| `data/` jsonl | Bind-mount in compose | Host `/opt/leadgen/data` | With VPS disk |
| SQLite rollback | `leadgen.db` | Legacy read-only | Emergency only |
| Qdrant | Docker volume / manual | `127.0.0.1:6333` | Re-seed from KB if lost |
| Git code | GitHub `main` | Remote | Full history |

**Optional (not active):** R2/B2 rclone — needs creds (`INFRA_HARDENING_GUIDE.md`).

---

## 3. Failure scenarios & procedures

### 3.1 App container crash

```
docker compose -f docker-compose.vps.yml logs app --tail=100
docker compose -f docker-compose.vps.yml up -d --no-deps app
curl http://127.0.0.1:8000/health
```

Self-heal: `scripts/vps_selfheal.sh` (cron */10).

### 3.2 Postgres corruption / data loss

1. Stop app: `docker compose stop app worker scheduler`
2. Restore latest dump: see `pg_restore_drill.sh` pattern (throwaway container test first)
3. Start stack: `docker compose up -d`
4. Verify: `/health/ready` db=healthy

### 3.3 Redis / Celery flood

```
redis-cli llen celery   # if >500:
redis-cli del celery
docker compose --profile celery up -d worker scheduler
```

### 3.4 Full VPS loss

1. Provision new Hostinger VPS (Ubuntu 24.04, Mumbai)
2. Clone repo, restore `.env` from secure backup
3. `docker compose -f docker-compose.vps.yml up -d` + celery profile
4. Restore Postgres from latest pg_dump
5. Point DNS A record to new IP · Caddy TLS
6. Smoke: `/health`, `/pricing`, `/api/public/pay-info`

**Ansible rebuild:** `INFRA_HARDENING_GUIDE.md` (optional).

### 3.5 Telephony provider failure

- Vobiz down → queue calls fail gracefully; no Twilio for India-domestic
- Run Tara readiness: `/api/telephony/` health · `telephony_readiness.py`
- Runbook: `OPERATIONAL_RUNBOOKS.md` RB-005 (telephony)

### 3.6 Voice agent / LLM outage

- Circuit breaker in `free_ai.py` — auto-fallback chain
- Manual: check provider status; reduce `WEB_CONCURRENCY` if OOM
- Web-call tuning continues on alternate providers

---

## 4. Rollback levels

| Level | Trigger | Action |
|-------|---------|--------|
| **L1** | Bad deploy | Previous Docker image tag + `up -d` |
| **L2** | Scheduler broken | `RUN_IN_PROCESS_SCHEDULER=1`, stop celery |
| **L3** | Postgres bad | Restore dump |
| **L4** | Total failure | New VPS + backup restore |

systemd `leadgen` service installed but **disabled** — emergency rollback path.

---

## 5. Monitoring & alerts

| Signal | Tool |
|--------|------|
| Backup stale >26h | Prometheus `BackupStale` alert |
| Restore drill fail | `RestoreDrillFailed` |
| App health | Gatus `/health/ready` body assert |
| Dead-man jobs | `ops_watchdog` + ntfy |

Activate obs stack: `docker compose -f deploy/compose/docker-compose.observability.yml up -d`

---

## 6. Failover

**No hot failover today.** DNS cutover to new VPS = manual failover. Cloudflare Tunnel can hide origin IP when enabled.

---

## 7. DR test schedule

| Test | Frequency | Script |
|------|-----------|--------|
| pg restore drill | Monthly cron | `pg_restore_drill.sh` |
| Manual smoke post-deploy | Every deploy | `prod_check.py` + `/health` 2× |
| Offsite `.env` verify | Quarterly | Operator |

---

## 8. Contacts

| Role | Contact |
|------|---------|
| Platform owner | Sumit |
| VPS | Hostinger panel + SSH root@72.61.245.204 |
| Domain/DNS | Hostinger DNS API (`scripts/hostinger_dns.py`) |
