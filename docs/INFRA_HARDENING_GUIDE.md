# Infra Hardening Guide — Top 5 Advancements (2026)
**Status key:** ✅ DONE (live) · 🟡 READY (config done, tum activate karo) · 📋 GUIDE (account chahiye)

Yeh guide tumhare single-VPS Docker stack (leadsgenai.in) ke liye. Solo-scale ke hisaab se — over-engineer nahi.

---

## 1. Cloudflare front pe (CDN + WAF + DDoS + Tunnel) — 📋 GUIDE (tumhara CF account)
**Kyun:** VPS abhi internet pe direct-exposed (IP visible, no WAF/DDoS). #1 security+perf gap.

**Steps:**
1. cloudflare.com pe free account → "Add site" `leadsgenai.in`.
2. CF tumhe 2 nameservers dega → Hostinger DNS me nameservers CF wale set karo (Hostinger panel → Domains → DNS/Nameservers). ~Few hrs propagate.
3. CF dashboard: SSL/TLS mode = **Full (strict)** (Caddy already valid cert deta).
4. **WAF**: Security → WAF → Managed rules ON. Rate-limiting rule: `/api/*` pe 100 req/min/IP.
5. **DDoS**: automatic (free plan me on).
6. **Cache**: Caching → static assets (`/site/*`, posters, blog) cache; `/api/*` bypass.
7. **Cloudflare Tunnel (IP chhupao + ports band)** — best security:
   ```bash
   # VPS pe:
   curl -L https://pkg.cloudflare.com/install.sh | bash   # ya cloudflared install
   cloudflared tunnel login
   cloudflared tunnel create leadgen
   # config: ingress leadsgenai.in -> http://127.0.0.1:8000 (Caddy/app)
   cloudflared tunnel route dns leadgen leadsgenai.in
   systemctl enable --now cloudflared
   # fir VPS firewall: 80/443 inbound BAND karo (sirf tunnel se traffic)
   ufw allow 22/tcp && ufw default deny incoming && ufw enable
   ```
   Iske baad VPS IP public nahi, attack surface ~0.

---

## 2. PgBouncer connection pooling — ✅/🟡 (container compose me, switch verify pe)
**Kyun:** FastAPI(async)+Celery+scheduler sab direct Postgres connect karte → load pe connection-exhaustion risk.

- `docker-compose.vps.yml` me `pgbouncer` service add ho gaya (session mode, asyncpg-safe).
- Switch: app ka `DATABASE_URL` ko `@pgbouncer:6432` pe point (deploy script ya .env).
- **Verify pehle staging pe** (`deploy/compose/docker-compose.staging.yml`), fir prod.
- Session mode = asyncpg ke prepared statements safe. Transaction mode mat use karo (asyncpg break karta) jab tak `statement_cache_size=0` na ho.

---

## 3. Zero-downtime deploy + STAGING — ✅ staging file ready
**Kyun:** Abhi `--force-recreate` = ~3-5s downtime; **koi staging nahi** (changes seedhe prod).

- **Staging**: `deploy/compose/docker-compose.staging.yml` bana (prod mirror, alag DB+Redis+port 8001, automation OFF). Use:
  ```bash
  cp .env .env.staging   # test values
  docker compose -f deploy/compose/docker-compose.staging.yml --profile staging --env-file .env.staging up -d
  # Caddy: staging.leadsgenai.in -> 127.0.0.1:8001 (basic-auth)
  ```
  ⚠️ Saare staging services `profiles: ["staging"]` pe hain (2026-08-08) — bina
  `--profile staging` ke `up -d` staging start KABHI nahi karta. Staging pe prod jaisi
  `mem_limit`/`pids_limit`/`oom_score_adj` caps hain (OOM containment) — `down` = `--profile staging down`.
- **Zero-downtime** (2 options):
  - **CI already health-gated + auto-rollback** (`deploy-vps.yml`) — recreate downtime ~3-5s, acceptable.
  - **True blue-green** (optional): naya container `:8002` pe → health-check → Caddy upstream `:8002` pe swap (Caddy admin API `/load`) → old stop. OR **Coolify** (self-hosted PaaS) jo yeh sab auto karta — bada migration, abhi zaroori nahi.

---

## 4. SPOF khatam — offsite backups + DR — ✅ cron / 🟡 offsite (R2/B2 creds)
**Kyun:** Single VPS gir gaya = sab down + data-loss.

- ✅ **restore-drill monthly cron** set (`0 3 1 * *` → `pg_restore_drill.sh`, throwaway-container restore-verify). "Untested backup = no backup" fix.
- ✅ **fail2ban + unattended-upgrades** active.
- 🟡 **Offsite (R2/B2)** — `pg_backup.sh` me rclone hook hai, bas creds chahiye:
  ```bash
  # Cloudflare R2 (free 10GB) ya Backblaze B2:
  rclone config   # remote naam 'r2', S3-compatible, R2 keys daalo
  # fir cron/env: RCLONE_REMOTE=r2:leadgen-backups
  ```
  Iske baad nightly dump auto-offsite (VPS mare to bhi backup safe).
- 📋 **Warm standby (next level)**: ek sasta 2nd node (Hetzner ~₹400/mo) pe Postgres streaming replica → failover. Solo ke liye optional; offsite+restore-drill abhi kaafi.

---

## 5. Secrets management + server hardening — ✅ fail2ban/auto-updates / 📋 SOPS
**Kyun:** Secrets plain `.env`; brute-force/patch exposure.

- ✅ **fail2ban** (SSH brute-force block) + **unattended-upgrades** (auto security patches) — LIVE.
- 📋 **SSH key-only + 2FA**: `/etc/ssh/sshd_config` → `PasswordAuthentication no` (key already use ho raha — confirm karke).
- 📋 **Secrets encrypt (SOPS+age)**:
  ```bash
  apt install age && age-keygen -o ~/.age/key.txt
  sops --encrypt --age <pubkey> .env > .env.enc   # .env.enc commit-safe; .env gitignored rahe
  ```
  Ya **Infisical** (self-host/cloud free) — team-scale.

---

## Priority order (mera suggestion)
1. **Cloudflare Tunnel + WAF** (#1) — biggest security win, free. (Tumhara CF account.)
2. **Offsite backups activate** (#4) — R2 creds daalo, data safe. (Tumhara R2/B2.)
3. **PgBouncer switch** (#2) — staging pe verify → prod.
4. Staging use karna shuru (#3) — har change pehle staging pe.
5. SOPS + SSH-hardening (#5) — jab time mile.

Account-wale steps (Cloudflare, R2) ke liye creds do to main configs/commands ready kar dunga.
