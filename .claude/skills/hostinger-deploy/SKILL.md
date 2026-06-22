---
name: hostinger-deploy
description: Deploy / fix / manage the LeadGen AI platform on the Hostinger KVM VPS (Docker). Use when the user mentions VPS, Hostinger, deploy, server, leadsgenai.in, SSH, Caddy, "site is down", SSL, 502, 404, Docker, or wants to update the live server. Captures the exact gotchas hit during deploys so they are never repeated.
---

# Hostinger VPS Deploy & Ops (LeadGen AI)

Live server facts (memorize):
- VPS IP: **72.61.245.204**, hostname `srv1736379`, Ubuntu 24.04, Hostinger **Docker** template.
- Domain: **leadsgenai.in** (+ www) → A record points to the VPS IP.
- App dir on VPS: **/opt/leadgen**. **App = Docker container `leadgen_app` :8000** (`docker compose -f docker-compose.vps.yml`, restart:unless-stopped). systemd service `leadgen` is **DISABLED** (installed for rollback only — do NOT `systemctl restart leadgen` as the deploy step anymore).
- Reverse proxy: **Caddy** (host-level, auto-HTTPS via Let's Encrypt) → proxies to 127.0.0.1:8000. Config `/etc/caddy/Caddyfile`.
- DB: **Postgres `leadgen_db` via PgBouncer (`pgbouncer:6432`) + Redis `leadgen_redis`** (containers). SQLite `/opt/leadgen/leadgen.db` = rollback-backup only. Repo: github.com/sumitrevolt/leadgenrationaivoiceagent (main).
- Scheduler = **Celery durable (LIVE)**: `leadgen_worker` + `leadgen_scheduler` containers (`--profile celery`). ~13+ containers total (app+db+redis+pgbouncer+worker+scheduler+freeswitch+6 obs).

## ⚠️ CRITICAL gotchas (these broke deploys — avoid!)

1. **Windows OpenSSH is broken on this PC** (`ssh.exe`/`ssh-keygen.exe` exit 255 instantly, no output). **ALWAYS use Git's ssh**: `C:\PROGRA~1\Git\usr\bin\ssh.exe`. Run non-trivial remote commands via a `.bat` (DC mangles inline quotes; `&`/`<`/`{{}}` break over PS→ssh → base64-encode + `base64 -d | bash`). Key: `C:\Users\Ratanshila\.ssh\id_rsa` (passphrase-free, already in VPS authorized_keys).
   - Connect: `C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes root@72.61.245.204 "<cmd>"`

2. **Hostinger Docker template runs Traefik on ports 80 + 443** (`traefik-traefik-1`, compose in `/docker/traefik`). Caddy can't bind → `bind: address already in use` → site returns Caddy default `404 page not found`. FIX:
   `docker stop traefik-traefik-1 && docker update --restart=no traefik-traefik-1 && systemctl restart caddy`

3. **.env from .env.example has inline comments** (`KEY=value  # note`). pydantic-settings does NOT strip them → `ValidationError ... bool_parsing input_value='false  # ...'` → app crashes on every start. FIX:
   `sed -i 's/[[:space:]]\+#.*$//' /opt/leadgen/.env` then recreate the app container.

4. **Port 8000 is firewalled externally** on Hostinger (only 22/80/443 open). Never tell the user `:8000` from outside — always go through Caddy (the domain).

5. **App is in the Docker image** — `app/` + `frontend/` + `.claude/skills/` are BAKED into `Dockerfile.lock`. Code/skill change = **`docker compose build app` + `up -d --no-deps app`** (NOT git-pull-only restart). Only `./data` + `./logs` are bind-mounts (data-only change = no rebuild).

6. **New `@app.get` page-route** = fresh image picks it up on rebuild (old systemd stale-`.pyc` issue is moot under Docker), but ALWAYS curl-verify the new route post-deploy (200 + real content).

## Common ops (run via Git ssh in a .bat)

- Health: `curl -s http://127.0.0.1:8000/health` (on VPS) or `https://leadsgenai.in/health` (anywhere) → `environment:production`.
- App logs: `docker logs leadgen_app -n 60` (NOT journalctl — app is a container now).
- **Deploy / restart after code change**:
  ```
  cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && \
  docker compose -f docker-compose.vps.yml build app && \
  docker compose -f docker-compose.vps.yml up -d --no-deps app
  ```
  Then `sleep 16` + 2x health-check.
- Caddy logs: `journalctl -u caddy -n 30 --no-pager` (Caddy IS still host-level systemd).
- Worker/scheduler restart: `docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps worker scheduler`. **After worker recreate**: `redis-cli llen celery` — if >500, `del celery` (tasks transient, beat re-schedules).
- Self-heal cron `scripts/vps_selfheal.sh` runs */10 (restarts unhealthy containers).

## Add a key/secret safely
Edit `/opt/leadgen/.env` (NO inline comments!), then recreate the app: `docker compose -f docker-compose.vps.yml up -d --no-deps app`. Verify `docker logs leadgen_app -n 10` for "Application startup complete".

## LLM quota note
LLM chain is FREE multi-provider (`app/voice_agent/free_ai.py`): **Mistral `mistral-small-latest` PRIMARY** → Groq `llama-3.1-8b-instant` → Cerebras `gpt-oss-120b` (429-prone, NOT primary) → Ollama floor → Gemini → SambaNova → OpenRouter. Escalating circuit-breaker handles 429s. If bot suddenly rule-based / "[echo / test-mode]", check `docker logs leadgen_app | grep -iE "429|quota|ResourceExhausted"` — usually a provider cooldown that self-recovers; Gemini is only a late fallback, not the default.

## Rollback path (if a deploy goes red)
`.env`: set `RUN_IN_PROCESS_SCHEDULER=1` + `WEB_CONCURRENCY=1`, stop worker/scheduler, recreate app. Last resort: `docker compose -f docker-compose.vps.yml down` + `systemctl start leadgen` (old SQLite service still installed). See `ship-checklist` for health-gate + rollback discipline.
