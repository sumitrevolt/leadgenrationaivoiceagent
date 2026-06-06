---
name: hostinger-deploy
description: Deploy / fix / manage the LeadGen AI platform on the Hostinger KVM VPS. Use when the user mentions VPS, Hostinger, deploy, server, leadsgenai.in, SSH, Caddy, "site is down", SSL, 502, 404, or wants to update the live server. Captures the exact gotchas hit during first deploy so they are never repeated.
---

# Hostinger VPS Deploy & Ops (LeadGen AI)

Live server facts (memorize):
- VPS IP: **72.61.245.204** , hostname `srv1736379`, Ubuntu 24.04, Hostinger **Docker** template.
- Domain: **leadsgenai.in** (+ www) -> A record points to the VPS IP.
- App dir on VPS: **/opt/leadgen** , runs as systemd service **leadgen** (uvicorn :8000, 0.0.0.0).
- Reverse proxy: **Caddy** (auto-HTTPS via Let's Encrypt), config `/etc/caddy/Caddyfile`.
- DB: SQLite at `/opt/leadgen/leadgen.db` (seeded). Public repo: github.com/sumitrevolt/leadgenrationaivoiceagent

## ⚠️ CRITICAL gotchas (these broke the first deploy — avoid!)

1. **Windows OpenSSH is broken on this PC** (`ssh.exe`/`ssh-keygen.exe` exit 255 instantly, no output). **ALWAYS use Git's ssh**: `C:\PROGRA~1\Git\usr\bin\ssh.exe`. Run remote commands via a `.bat` (DC mangles inline quotes). Key: `C:\Users\Ratanshila\.ssh\id_rsa` (passphrase-free, already in VPS authorized_keys).
   - Connect: `C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes root@72.61.245.204 "<cmd>"`

2. **Hostinger Docker template runs Traefik on ports 80 + 443** (`traefik-traefik-1`, compose in `/docker/traefik`). Caddy can't bind -> `bind: address already in use` -> Caddy fails -> site returns Caddy default `404 page not found` (Server: None). FIX:
   `docker stop traefik-traefik-1 && docker update --restart=no traefik-traefik-1 && systemctl restart caddy`

3. **.env from .env.example has inline comments** (`KEY=value  # note`). pydantic-settings does NOT strip them -> `ValidationError ... bool_parsing input_value='false  # Set to true'` -> app crashes on every start (systemd shows "active" but port 8000 NOT listening). FIX:
   `sed -i 's/[[:space:]]\+#.*$//' /opt/leadgen/.env && systemctl restart leadgen`

4. **Port 8000 is firewalled externally** on Hostinger (only 22/80/443 open). Never tell the user to use `:8000` from outside — always go through Caddy (80/443) / the domain.

5. **Gemini model name**: `DEFAULT_LLM` must be a real model like `gemini-2.5-flash-lite`, NOT just `gemini` (invalid model id -> LLM calls fail -> agent falls back to rule-based).

6. **Free-tier daily quotas are PER MODEL and tiny** (e.g. gemini-2.5-flash = 20 req/day). When the bot suddenly answers with "[echo / test-mode] ... No live LLM configured", check `journalctl -u leadgen | grep -i ResourceExhausted` — if 429 quota, switch `DEFAULT_LLM` in `/opt/leadgen/.env` to a model with quota left (`gemini-2.5-flash-lite` has the largest free allowance) and `systemctl restart leadgen`. Quick per-model probe: `env PYTHONPATH=/opt/leadgen DEFAULT_LLM=<model> .venv/bin/python scripts/llm_probe.py`.

## Common ops (run via Git ssh in a .bat)

- Health: `curl -s http://127.0.0.1:8000/health` (on VPS) or test `https://leadsgenai.in/health` from anywhere.
- App logs: `journalctl -u leadgen -n 40 --no-pager`
- Restart app after code/.env change: `cd /opt/leadgen && git pull && systemctl restart leadgen`
- Caddy logs: `journalctl -u caddy -n 30 --no-pager`
- Re-deploy everything (idempotent): `curl -fsSL https://raw.githubusercontent.com/sumitrevolt/leadgenrationaivoiceagent/main/deploy_vps.sh | bash`
- Add a secret (e.g. Sarvam): `sed -i 's/^SARVAM_API_KEY=.*/SARVAM_API_KEY=xxx/' /opt/leadgen/.env && systemctl restart leadgen`

## Add a key/secret safely
Edit `/opt/leadgen/.env` (no inline comments!), then `systemctl restart leadgen`. Verify with `journalctl -u leadgen -n 10` for "Application startup complete".

## To enable background jobs (scraping/calling automation)
App logs "Redis disabled". For Celery workers, install + start Redis (`apt install -y redis-server && systemctl enable --now redis-server`), set `REDIS_URL=redis://localhost:6379/0` in .env, and run a celery worker service. Not needed just to serve the web app.
