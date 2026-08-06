# Production Cutover Runbook — Lean (SQLite + systemd) → Docker stack (Postgres + Redis)

> **Goal:** Live `leadsgenai.in` ko lean `systemd + SQLite + single uvicorn` se ek
> reproducible, auto-healing **Docker stack** (app + Postgres + Redis) pe le jaana —
> **usi VPS pe, fully free, host Caddy TLS untouched**.
>
> **Safety model:** Hum SQLite se sirf **READ** karke Postgres me data COPY karte hain
> (source untouched). Isliye rollback = instant: `docker compose down` + `systemctl start leadgen`.
>
> **Status of the code (already done + verified):**
> - `docker-compose.vps.yml` — canonical VPS stack (app+db+redis; worker/beat opt-in)
> - `scripts/migrate_sqlite_to_postgres.py` — safe, verified, idempotent copy (tested)
> - `scripts/pg_backup.sh` — nightly pg_dump + 30d retention + optional offsite
> - `.github/workflows/deploy-vps.yml` — push→build(GHCR)→SSH deploy (Cloud Run workflows disabled)
> - `app/cache` rate-limiter bug fixed (real Redis-backed limiting), Redis re-enabled in `main.py`
> - `RUN_IN_PROCESS_SCHEDULER` gate added (default ON = aaj jaisa behaviour)

---

## 0) Pre-requisites (one-time)

**On the VPS** (`ssh root@72.61.245.204`):

```bash
docker --version && docker compose version    # Docker pehle se hai (Qdrant chal raha)
cd /opt/leadgen && git pull --ff-only         # naya compose + scripts laao
```

**Add to `/opt/leadgen/.env`** (secrets — sirf .env me, commit mat karo):

```ini
# --- Postgres (self-host in stack) ---
POSTGRES_USER=leadgen
POSTGRES_PASSWORD=<STRONG_RANDOM>          # openssl rand -hex 24
POSTGRES_DB=leadgen
# App ko Postgres + Redis pe point karo (cutover ke waqt switch — Phase 3):
# DATABASE_URL=postgresql+asyncpg://leadgen:<STRONG_RANDOM>@db:5432/leadgen
# REDIS_URL=redis://redis:6379/0
WEB_CONCURRENCY=1                            # aaj jaisa (web + in-process scheduler)
RUN_IN_PROCESS_SCHEDULER=1
```

> Abhi `DATABASE_URL` ko SQLite hi rehne do — Phase 3 me switch karenge.

**GitHub repo secrets** (for auto-deploy, Settings → Secrets → Actions):
`VPS_HOST=72.61.245.204`, `VPS_USER=root`, `VPS_SSH_KEY=<private key>`, `GHCR_PAT=<PAT read:packages>`.

---

## 1) Phase 0 — Full backup (NEVER skip)

```bash
cd /opt/leadgen
TS=$(date +%Y%m%d_%H%M)
cp leadgen.db   leadgen.db.bak_$TS
cp .env         .env.bak_$TS
sqlite3 leadgen.db ".backup leadgen_snapshot_$TS.db"   # consistent snapshot
ls -lh leadgen*.db* .env.bak_*
```

---

## 2) Phase 1 — Bring up Postgres + Redis ONLY (app abhi nahi)

```bash
docker compose -f docker-compose.vps.yml up -d db redis
docker compose -f docker-compose.vps.yml ps          # db+redis = healthy hone tak ruko
docker exec leadgen_db pg_isready -U leadgen          # "accepting connections"
docker exec leadgen_redis redis-cli ping              # PONG
```

---

## 3) Phase 2 — Build schema + copy data into Postgres

```bash
# Build the app image once (or let CI push to GHCR and `pull`)
docker compose -f docker-compose.vps.yml build app

# 3a) Schema on Postgres (alembic = source of truth; create_all bhi safe net)
docker compose -f docker-compose.vps.yml run --rm \
  -e DATABASE_URL=postgresql+asyncpg://leadgen:<PW>@db:5432/leadgen \
  app alembic upgrade head

# 3b) Copy SQLite -> Postgres (READ-only on SQLite, verified + idempotent)
docker compose -f docker-compose.vps.yml run --rm \
  -e DATABASE_URL=postgresql+psycopg2://leadgen:<PW>@db:5432/leadgen \
  app python scripts/migrate_sqlite_to_postgres.py \
     --sqlite sqlite:////app/leadgen.db \
     --postgres postgresql+psycopg2://leadgen:<PW>@db:5432/leadgen
```

Output me har table ka `SRC == DST` aur **`[OK] all tables migrated and verified`** dekho.
Mismatch ho → STOP, rollback safe hai (Postgres alag hai, SQLite chhua nahi).

> Re-run karna ho (failed attempt ke baad): same command `--wipe` ke saath.

---

## 4) Phase 3 — Cutover (downtime ~30–60 sec)

```bash
# 4a) .env me app ko Postgres+Redis pe point karo
sed -i 's#^DATABASE_URL=.*#DATABASE_URL=postgresql+asyncpg://leadgen:<PW>@db:5432/leadgen#' /opt/leadgen/.env
grep -q '^REDIS_URL=' /opt/leadgen/.env || echo 'REDIS_URL=redis://redis:6379/0' >> /opt/leadgen/.env

# 4b) Purana systemd uvicorn band karo (yeh :8000 chhodta hai). ROLLBACK ANCHOR — uninstall mat karo.
systemctl stop leadgen

# 4c) Naya stack uthao (app ab 127.0.0.1:8000 pe — host Caddy isi ko proxy karta hai)
docker compose -f docker-compose.vps.yml up -d
docker compose -f docker-compose.vps.yml ps

# 4d) Verify
curl -fsS http://127.0.0.1:8000/health && echo
curl -fsS http://127.0.0.1:8000/health/ready | python3 -m json.tool   # database+redis = healthy
curl -fsS https://leadsgenai.in/health && echo                        # Caddy → container OK
```

`/health/ready` me `database` aur `redis` dono `healthy` → cutover successful.

---

## 5) Phase 4 — Smoke test (5 min)

```bash
curl -fsS https://leadsgenai.in/ | head -c 200          # landing
curl -fsS https://leadsgenai.in/audit | head -c 200     # #1 lead magnet
curl -fsS https://leadsgenai.in/api/data/niches?tier=S  # API + DB read
docker compose -f docker-compose.vps.yml logs -f app     # errors? scheduler started?
```

Dashboards (`/app/admin`, `/app/customer`), ek test inquiry (`/audit`), aur ek FREE web-call (`/app/test-call`) bhi check karo.

---

## 6) ROLLBACK (kuch bhi galat → 60 sec me wapas)

```bash
docker compose -f docker-compose.vps.yml down
# .env me DATABASE_URL wapas SQLite (ya .env.bak_$TS restore karo)
cp /opt/leadgen/.env.bak_<TS> /opt/leadgen/.env
systemctl start leadgen
curl -fsS http://127.0.0.1:8000/health && echo   # back on SQLite
```
SQLite ko hum ne sirf padha tha → **zero data loss**.

---

## 7) Post-cutover (production hardening — same din)

**Nightly backups (cron):**
```bash
chmod +x /opt/leadgen/scripts/pg_backup.sh
( crontab -l 2>/dev/null; echo "30 2 * * * /opt/leadgen/scripts/pg_backup.sh >> /var/log/leadgen_backup.log 2>&1" ) | crontab -
/opt/leadgen/scripts/pg_backup.sh        # test once now
# Offsite (free): rclone config (Cloudflare R2 / Backblaze B2) → set RCLONE_REMOTE in env
```

**Auto-deploy ON:** GitHub secrets set kar do → ab `git push origin main` = auto build→deploy.
Manual SSH + "stale .pyc / hard reload" drama KHATAM (har deploy fresh immutable image).

**Monitoring (optional, free):**
```bash
docker compose -f deploy/compose/docker-compose.observability.yml up -d   # Prometheus+Grafana+Uptime Kuma
```
Uptime Kuma me `https://leadsgenai.in/health` ka monitor + email/Telegram alert lagao.

---

## 8) Scaling later (jab traffic badhe — abhi zarurat nahi)

Multi-worker safe hai ab (Postgres). Double-scheduler se bachne ke liye:

```ini
# .env
WEB_CONCURRENCY=4
RUN_IN_PROCESS_SCHEDULER=0     # web replicas jobs nahi chalayenge
```
```bash
# ek dedicated scheduler/worker (Celery) container:
docker compose -f docker-compose.vps.yml --profile celery up -d worker scheduler
```
Tab in-process scheduler band, jobs Celery beat/worker pe — horizontally scalable.

---

### Quick reference

| Cheez | Command |
|---|---|
| Stack up | `docker compose -f docker-compose.vps.yml up -d` |
| Logs | `docker compose -f docker-compose.vps.yml logs -f app` |
| Migrate DB | `... up head` (Phase 2) |
| Backup | `scripts/pg_backup.sh` |
| Rollback | `... down` + `systemctl start leadgen` |
| Health | `curl https://leadsgenai.in/health/ready` |
