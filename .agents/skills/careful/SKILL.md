---
name: careful
description: Destructive/irreversible command se pehle RUKO aur confirm karo. Use jab koi rm -rf, DROP/TRUNCATE/DELETE-without-WHERE, git push --force, git reset --hard, docker prune, VPS .env overwrite, ya prod container stop hone wala ho — ya jab user "careful mode" / "production data ko haath laga rahe" bole.
---

# Skill: careful
**Adapted from gstack by Garry Tan (YC). MIT License.**

## When to invoke
- Destructive operations se pehle
- "Careful mode mein kaam karo"
- Production data se related changes

## What this does
Before koi bhi destructive command run karo, **RUKO** aur user se confirm karo.

---

## Protected Operations (confirm karo pehle)

| Operation | Example | Risk |
|-----------|---------|------|
| `rm -rf` (important dirs) | `rm -rf /opt/leadgen/data` | Data loss |
| `DROP TABLE` / `TRUNCATE` | `DROP TABLE leads;` | Irreversible DB loss |
| `git push --force` | `git push -f origin main` | History rewrite |
| `git reset --hard` | `git reset --hard HEAD~5` | Uncommitted work loss |
| `docker system prune` | `docker system prune -a` | All images deleted |
| VPS `.env` overwrite | `echo "" > /opt/leadgen/.env` | All secrets wiped |
| `docker stop leadgen_app` | without health check | Prod down |
| Postgres `DELETE FROM` without `WHERE` | `DELETE FROM leads` | All leads gone |
| `alembic downgrade` | reverting migrations | Schema loss |

## Safe (no confirmation needed)

- `rm -rf __pycache__` / `.pyc` / `node_modules` / `dist` / `build`
- `docker restart leadgen_app` (normal restart)
- `git stash` (can be recovered)
- `pytest` runs

---

## How to use

Kisi bhi command se pehle jo protected list mein match kare:

**RUKO. Confirm karo:**
```
⚠️ CAREFUL: Main [operation] karne wala hoon.
- Kya: [exact command]
- Risk: [kya ho sakta hai agar galat]
- Rollback: [kaise undo karein]

Proceed karna hai? (haan/nahi)
```

User "haan" bole tab hi proceed karo.

---

## Project-Specific Extra Care

### VPS pe kaam karte waqt:
- `.env` ka backup PEHLE: `cp .env .env.bak_$(date +%Y%m%d_%H%M%S)`
- Docker recreate se pehle: health check URL note karo
- DB changes se pehle: `docker exec leadgen_db pg_dump -U leadgen leadgen > /tmp/backup.sql` (user+db dono default `leadgen`)

### Hostinger SSH:
- `git push --force` = `main` branch ka history rewrite = CI/deploy broken
- `pkill -9 uvicorn` = leadgen_app container process down — systemd DISABLED hai, KOI service auto-restart nahi karega; recover = `docker compose -f docker-compose.vps.yml up -d --no-deps app` (2026-07-05)

### Data files:
- `data/*.jsonl` = production data. Delete = leads/invoices gone forever.
- `data/content_schedule.jsonl` = client content queue
- `data/deals.jsonl` = sales pipeline

---

## Enterprise gate — yeh skill KHUD ek fail-CLOSED safety gate hai

Operating loop chalao — Discover → Contract → Execute → Self-review → Evidence (full loop `fable-operating-manual`). Destructive command iska sabse risky "Execute" phase hai; yeh skill us phase pe **fail-CLOSED brake** lagata hai.

**Change-risk tier: ALWAYS High-risk + irreversible.** Default = **REFUSE/PAUSE** jab tak teeno na ho: (1) exact command, (2) named rollback/recovery, (3) explicit user "haan". Ambiguity = block, proceed nahi. Yeh gate bypass mat karo "jaldi hai" me — prod-down/data-loss inhi me se aata hai.

**Hard pre-conditions (sab teen, warna RUKO):**
1. **Backup PEHLE (rollback proof):** DB → `docker exec leadgen_db pg_dump -U leadgen leadgen > /tmp/backup_$(date +%s).sql`; `.env` → `cp .env .env.bak_$(date +%Y%m%d_%H%M%S)`; data file → copy before delete. Backup confirm hone TAK destructive run mat karo.
2. **Scope-narrow:** `DELETE`/`UPDATE` me `WHERE` mandatory; `rm -rf` me exact path (kabhi `/` ya bare var); `git push --force` → `--force-with-lease` prefer; migration → `alembic downgrade` ka forward-path bhi confirmed.
3. **Confirm template (upar wala) + user "haan".** Sirf tab proceed.

**Live-prod fail-CLOSED (non-negotiable):**
- **Telephony/outbound se chhedchhad** (DND/calling-window/AI-disclosure guard disable, consent-ledger purge) = REFUSE — TRAI/legal risk, "careful" se bhi nahi (illegal, user-haan se bhi nahi).
- **Secrets:** VPS `.env` overwrite = saare secrets wipe → backup + line-diff dikhao pehle; secret kabhi log/commit me echo mat karo.
- **Billing data** (`data/*.jsonl` invoices, DB leads/deals) delete = irreversible revenue/PII loss → backup + WHERE + haan.
- **Prod container stop/recreate:** health-check URL note + recreate ke baad `/health` = `environment:production` verify; `leadgen_app` blind stop mat.

**Evidence (done):** destructive ke baad — backup file exists (path bolo) + intended state verify (`/health` 200 / row-count / `git log`) + 1-line SESSION_LOG (kya delete/reset, backup kahan). Bina rollback-artifact "ho gaya" KABHI mat bolo. Galti hui → backup se restore + `prod-incident-triage`.
