---
name: windows-dev-gotchas
description: Windows dev environment gotchas for LeadGen — stale sandbox, Git ssh, curl.exe, VPS deploy quoting, bat logs, venv truth. Use on any terminal/git/SSH/deploy task on Windows.
---
# Windows Dev Gotchas

## Source of truth

- **File edits:** Cursor/Windows file tools — sandbox mount STALE ho sakta hai
- **Verify:** `.venv\Scripts\python.exe` on Windows, not sandbox bash alone
- **Tests:** `scripts\run_tests.bat` → Read **`pytest_run.log`**

## curl on Windows

PowerShell `curl` = `Invoke-WebRequest` alias — **`-fsS` fail**.

Use:
```powershell
curl.exe -fsS https://leadsgenai.in/health
curl.exe -fsS https://leadsgenai.in/api/activation/summary
```

## Git / SSH

- OpenSSH broken → **Git ka ssh:**
  `C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204`
- Git: `C:\PROGRA~1\Git\cmd\git.exe`
- Git index unreadable in sandbox → Windows git only

## SSH quoting (CRITICAL)

PowerShell `&`, `<`, `{{}}` todta → complex VPS smoke = **`scripts/x.py` file** + ssh run python

Deploy one-liner OK:
```powershell
& "C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 "cd /opt/leadgen && git reset --hard origin/main -q && docker compose -f docker-compose.vps.yml build app && docker compose -f docker-compose.vps.yml up -d --no-deps app"
```

## .bat rules

- `call npm.cmd` / `call git.cmd`
- `timeout /t` fail → `ping -n N 127.0.0.1`
- Long commands → `.bat` file, output log, Read log

## Parallel edits

Same file pe parallel agent edit = **truncate** — sequential only

## Memory files

`CLAUDE.md` / SESSION_LOG — **bash append MAT** (corruption) — Edit tool only

## VPS quick smoke

```powershell
curl.exe -fsS https://leadsgenai.in/health
curl.exe -fsS https://leadsgenai.in/api/voice/agents
curl.exe -fsS https://leadsgenai.in/api/activation/summary
```

## Claude tip

Har code task pe parallel Grep/Read — `context-first` skill.

## Enterprise gate (LIGHT — reference skill)

Operating loop chalao — Discover → Contract → Execute → Self-review → Evidence (full loop `fable-operating-manual`).

**Change-risk tier:** Yeh pure environment-reference hai (Trivial), par iske gotchas **High-risk gates enable** karte: Windows=truth (warna stale-mount ghost-bug), `.venv` python verify (warna jhootha "syntax error"), SSH-quoting (warna deploy abort), `git push --force`/`reset` = `careful` skill. Deploy/billing/telephony actual change pe is skill se hatkar uska domain-skill ka FULL gate lock karo.
