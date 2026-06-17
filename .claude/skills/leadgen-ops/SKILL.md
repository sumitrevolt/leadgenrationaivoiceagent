---
name: leadgen-ops
description: LeadGen AI ka proven ops loop — verify, test, push, deploy + production triage. Use when the user says "deploy", "redeploy", "tests chalao", "VPS issue", "production error", "verify karo", "push karo", or anything about shipping code to leadsgenai.in / debugging the live Docker server.
---

# LeadGen Ops Loop (verify → test → push → deploy)

Yeh exact 4-step cycle har deploy pe follow karo. Live stack = Hostinger VPS Docker (`leadgen_app` container :8000), NOT systemd. Windows = source of truth (sandbox mount stale ho jata hai).

## The proven loop

1. **Pre-flight**: `python scripts/prod_check.py` — parse/pycache/import/route/config checks. Koi fail = pehle fix karo, aage mat badho.
2. **Tests**: `scripts\run_tests.bat` chalao, phir **pytest_run.log Read karo** (console output truncate hota hai — log file hi source of truth). ~80+ green expected (full pytest team_pulse area pe hang ho sakta — targeted suites).
3. **Git push**: Windows git hi — `C:\PROGRA~1\Git\cmd\git.exe` — aur hamesha ek `.bat` ke andar (DC one-liner quoting mangle karta hai; sandbox git index nahi padh sakta). Reference pattern: `scripts/fix_push_redeploy.bat`.
4. **VPS pull + rebuild + recreate** (Git ka ssh.exe — Windows OpenSSH is PC pe broken hai). App image me baked hai → **rebuild zaroori** (git-pull-restart kaafi nahi):
   ```
   C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 \
     "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && \
      docker compose -f docker-compose.vps.yml build app && \
      docker compose -f docker-compose.vps.yml up -d --no-deps app"
   ```
   Phir verify: `https://leadsgenai.in/health` → `environment:production`. `sleep 16` + 2x health-check.
   - Data-only change (`./data`/`./logs` bind-mount) = rebuild ki zaroorat NAHI.

## Production triage table

| Symptom | Root cause | Fix |
|---|---|---|
| App unhealthy + CPU ~0%, WS/endpoint hang | Sync ML/KB init event-loop par freeze (classic prod-down) | `docker logs leadgen_app`; HOST se `py-spy dump --pid $(pgrep -f uvicorn\|head -1)`; `docker restart leadgen_app`. Root: `asyncio.to_thread`+hard-timeout (model-asset-bake + prod-incident-triage skills) |
| First WS hit after rebuild hangs (~250MB HF download) | ML asset runtime-download instead of baked | Model BAKE in `Dockerfile.lock` + disable-switch (model-asset-bake skill) |
| Bot rule-based / "[echo / test-mode]" | Free LLM provider cooldown (Cerebras/groq 429) | `docker logs leadgen_app \| grep -iE "429\|quota"`; circuit-breaker usually self-recovers (escalating 60s→30min). Gemini = late fallback, not default |
| Random 500s (e.g. /api/data/niches) | Stale `__pycache__` — but fresh Docker image has none | Rebuild app (`build app` + recreate). prod_check.py locally yehi class pakadta |
| Naye deps import-fail in container | image lock out of date | `requirements.lock.txt` refresh (`scripts/vps_freeze.sh`) → commit → rebuild |
| celery queue blow-up after worker recreate | transient tasks pile up | `redis-cli llen celery`; >500 = `del celery` (beat re-schedules) |

## Long-running commands (DC ~60s pe process kill kar deta hai)

Launcher-bat pattern: `.bat` me `start /min cmd /c "<long command> > C:\path\to\log.txt 2>&1"` likho — turant return — phir log file poll-Read karo jab tak done-marker na dikhe. pip installs, npm builds, full pytest sab isi se. (`.bat` me npm/git ko `call` se; `timeout /t` ki jagah `ping -n N 127.0.0.1`.)

## Smoke tests

- **Local**: `scripts\smoke_test.bat` — app boot karke key endpoints hit karta hai.
- **VPS agents** (LangGraph/Qdrant/MCP): `cd /opt/leadgen && docker exec leadgen_app python scripts/vps_agents_test.py`
- **VPS live websocket** (web-call bot): `docker exec leadgen_app python scripts/ws_test.py`
- **LLM probe**: `docker exec leadgen_app python scripts/llm_probe.py`

VPS-level gotchas (Caddy vs Traefik, .env inline comments, firewalled ports, Docker rebuild, rollback) ke liye sibling skills: `hostinger-deploy`, `ship-checklist`, `prod-incident-triage`.
