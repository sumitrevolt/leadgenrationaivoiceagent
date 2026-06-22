---
name: feature-change-flow
description: Kisi bhi EXISTING feature me change karne ka production-safe flow — kahan code hai, kya gate lagana, kaise verify/ship karna. Use jab "feature change karo", "X me ye add karo", "behaviour badlo", "ye endpoint modify karo", ya kisi live module ko touch karne se pehle.
---

# Feature-change flow (production-safe, is repo ka proven loop)

## 1. LOCATE (rebuild mat karo — ~761 route decorators already hain)
- `grep '@router' app/api/<area>.py` + AGENTS.md section padho — feature PEHLE se ho sakta hai (festivals-duplicate lesson). FastAPI first-route-wins = duplicate prod ko silently shadow karta.
- Module map: marketing=`app/marketing/*`+`api/marketing.py` · growth/infra=`api/growth.py` · agents=`app/agents/*` · billing=`app/billing/*` (`app/marketing/packages.py` = marketing-pricing TRUTH, `app/marketing/voice_packages.py` = voice-pricing TRUTH) · voice=`app/voice_agent/*` · scheduler (Celery LIVE)=`worker.py`+beat, rollback APScheduler=`platform/team_scheduler.py`.

## 2. DESIGN the change
- **Additive + gated default**: naya behaviour env-flag ke peeche (default OFF = zero change), flag `growth.py AUTOMATION_FLAGS` me register.
- Side-effect (send/call/post) = ban-safe drafts unless explicit gate; public endpoint me KB/ML = `asyncio.to_thread` + hard timeout (widget-chat prod-down lesson).
- Pricing change = `app/marketing/packages.py` (ya voice = `voice_packages.py`) + `tests/test_billing_truth_2026.py` SAATH badlo. Marketing feature add = `frontend/marketing.html` (28 tabs) me UI tab bhi SAATH (API-only = adhoora). Schema change = Alembic revision (DB stamped 005+).
- Access level: `require_admin` (module-limited members pass) vs `require_super_admin` (critical) — backend-rbac skill.

## 3. VERIFY (Windows = truth)
`python scripts/prod_check.py` → targeted pytest (`pytest_run.log` Read karo) → naya flag/route ho to test add. Frontend JS = `node --check`.

## 4. SHIP (health-gated)
Commit (simple msg, no secrets) → push → VPS: pull + `docker compose -f docker-compose.vps.yml build app` + `--profile celery up -d app worker scheduler` → `sleep 16` + 2x health 200 → smoke the changed route. Naye page-routes = HARD RELOAD. Build pipe me `set -o pipefail` (exit-mask lesson). Fail → prev-image rollback, prod kabhi red nahi.

## 5. RECORD
SESSION_LOG me milestone + AGENTS.md me 1-2 line. Naya gotcha mila → relevant skill me append.
