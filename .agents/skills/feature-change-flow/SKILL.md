---
name: feature-change-flow
description: Kisi bhi EXISTING feature me change karne ka production-safe flow — kahan code hai, kya gate lagana, kaise verify/ship karna. Use jab "feature change karo", "X me ye add karo", "behaviour badlo", "ye endpoint modify karo", ya kisi live module ko touch karne se pehle.
---

# Feature-change flow (production-safe, is repo ka proven loop)

## 1. LOCATE (rebuild mat karo — ~1030 routes already hain)
- `grep '@router' app/api/<area>.py` + CLAUDE.md section padho — feature PEHLE se ho sakta hai (festivals-duplicate lesson). FastAPI first-route-wins = duplicate prod ko silently shadow karta.
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
SESSION_LOG me milestone + CLAUDE.md me 1-2 line. Naya gotcha mila → relevant skill me append.

## Enterprise gate
Yeh 5-step loop = operating loop ka concrete roop — Discover(LOCATE) → Contract(DESIGN) → Execute → Self-review → Evidence(VERIFY+SHIP) (full loop `fable-operating-manual`).

**Change-risk tier = jis cheez ko chhoo rahe ho uska tier** (fable §0.6 table). LOCATE step me hi classify karo, phir gates lock:
- **Trivial** (copy/comment/single non-hot-path fn) → Read-before-Edit + 1 targeted test.
- **Standard** (existing endpoint/UI behaviour, non-billing) → DESIGN ke flag-gate + dup-route grep + changed-file test + `prod_check`.
- **High-risk** (billing · public route · telephony · secrets/auth · automation loop · DB migration) → per-domain gate + `self-code-review` + `security-review` + named rollback.

**Per-domain gate (jo file chhoo rahe ho uska):**
- **Billing/pricing** → change SIRF `app/marketing/packages.py` (voice = `voice_packages.py`) me; `tests/test_billing_truth_2026.py` SAATH green; GST sirf `GST_GSTIN` set pe.
- **Public route** → SSRF/auth/rate-limit; KB/ML = `asyncio.to_thread` + hard timeout (widget-chat prod-down); deploy pe **HARD RELOAD** (container recreate, warna stale .pyc 404).
- **Telephony/outbound** → TRAI 9am–7pm + DND fail-CLOSED (lookup-fail = block) + AI-disclosure-at-start + consent-ledger — bypass KABHI nahi.
- **Automation loop** → idempotency/dedupe + never-raise + DLQ `dlq:failed_tasks` + `automation_health` parity + flag default-OFF.
- **Secrets** → sirf `.env`; `scripts\check_secrets.py` gate. **Schema** → Alembic forward + rollback dono.
- **Auth level** → `require_admin` (module-limited pass) vs `require_super_admin` (critical) — `backend-rbac` skill.

**Rollback (named):** flag OFF (behaviour revert) · prev-image container recreate · Alembic downgrade · data-repair script — change ke type ke hisaab se VERIFY se pehle likho. Fail pe prod KABHI red nahi.

**Evidence (done):** §3-§4 ka `.venv\Scripts\python.exe scripts\prod_check.py` + targeted `pytest` (`pytest_run.log` Read) + `sleep 16`+2x `/health`=`environment:production` + changed-route smoke. Billing-touch = `test_billing_truth_2026`; cross-path side-effect (qualify/call/bill hooks) = `scripts\cross_path_audit.py`.
