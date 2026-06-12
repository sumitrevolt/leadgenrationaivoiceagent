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
- DB changes se pehle: `docker exec leadgen_db pg_dump -U postgres leadgendb > /tmp/backup.sql`

### Hostinger SSH:
- `git push --force` = `main` branch ka history rewrite = CI/deploy broken
- `pkill -9 uvicorn` = 30s downtime (HTTP blip normal hai, service restart karta hai)

### Data files:
- `data/*.jsonl` = production data. Delete = leads/invoices gone forever.
- `data/content_schedule.jsonl` = client content queue
- `data/deals.jsonl` = sales pipeline
