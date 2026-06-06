---
name: leadgen-ops
description: LeadGen AI ka proven ops loop — verify, test, push, deploy + production triage. Use when the user says "deploy", "redeploy", "tests chalao", "VPS issue", "production error", "verify karo", "push karo", or anything about shipping code to leadsgenai.in / debugging the live server.
---

# LeadGen Ops Loop (verify → test → push → deploy)

Yeh exact 4-step cycle har deploy pe follow karo — isi se ab tak ke sab deploys green gaye hain.

## The proven loop

1. **Pre-flight**: `python scripts/prod_check.py` — parse/pycache/import/route/config checks. Koi fail = pehle fix karo, aage mat badho.
2. **Tests**: `scripts\run_tests.bat` chalao, phir **pytest_run.log Read karo** (console output truncate hota hai — log file hi source of truth). 80/80 expected.
3. **Git push**: Windows git hi — `C:\PROGRA~1\Git\cmd\git.exe` — aur hamesha ek `.bat` ke andar (DC one-liner quoting mangle karta hai; sandbox git index nahi padh sakta). Reference pattern: `scripts/fix_push_redeploy.bat`.
4. **VPS pull+restart** (Git ka ssh.exe — Windows OpenSSH is PC pe broken hai):
   ```
   C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen"
   ```
   Phir verify: `https://leadsgenai.in/health` → `environment:production` aana chahiye.

## Production triage table

| Symptom | Root cause | Fix |
|---|---|---|
| Bot echo-reply ("[echo / test-mode]") | Gemini free quota khatam (quota PER MODEL hoti hai) | VPS pe `journalctl -u leadgen \| grep -i ResourceExhausted` → `/opt/leadgen/.env` me `DEFAULT_LLM` switch karo (`gemini-2.5-flash-lite` = max free quota) → `systemctl restart leadgen` |
| Startup MINUTES tak hang | cloud-logging bina GCP creds har logger pe retry karta tha | Fix already main me (logger.py attempted-flag + creds check) — VPS latest commit pe hai? Warna pull+restart |
| Random 500s (e.g. /api/data/niches) | Stale `__pycache__` purana bytecode serve kar raha | `find /opt/leadgen -name __pycache__ -type d -exec rm -rf {} +` → restart (prod_check.py locally yehi pakadta hai) |
| Naye features VPS pe import-fail | deploy_vps.sh ka pip fallback naye deps skip kar deta hai | Explicit install: `.venv/bin/pip install langgraph langgraph-checkpoint-sqlite langchain-core fastapi-mcp qdrant-client fastembed` → restart |

## Long-running commands (DC ~60s pe process kill kar deta hai)

Launcher-bat pattern: `.bat` me `start /min cmd /c "<long command> > C:\path\to\log.txt 2>&1"` likho — turant return hota hai — phir log file ko poll-Read karo jab tak done-marker na dikhe. pip installs, npm builds, full pytest sab isi se chalao. (`.bat` me npm/git ko `call` se invoke karo; `timeout /t` ki jagah `ping -n N 127.0.0.1`.)

## Smoke tests

- **Local**: `scripts\smoke_test.bat` — app port 8923 pe boot karke key endpoints hit karta hai.
- **VPS agents** (LangGraph/Qdrant/MCP): `cd /opt/leadgen && PYTHONPATH=/opt/leadgen .venv/bin/python scripts/vps_agents_test.py`
- **VPS live websocket** (web-call bot): `.venv/bin/python scripts/ws_test.py` (VPS pe)
- **LLM per-model probe**: `env PYTHONPATH=/opt/leadgen DEFAULT_LLM=<model> .venv/bin/python scripts/llm_probe.py`

VPS-level gotchas (Caddy vs Traefik, .env inline comments, firewalled ports) ke liye sibling skill padho: `.claude/skills/hostinger-deploy/SKILL.md`.
