# Production Checklist — LeadGenAI

> **Purpose:** ONE lean, actionable pre-ship + launch checklist. **Single source of operational truth** for "is it safe to deploy / is it production-ready."
> **This is an INDEX, not a re-derivation.** Deep narrative audits live in `PRODUCTION_READINESS_2026.md`, `PRODUCTION_READINESS_AUDIT_2026_06_24.md`, and `Production_Readiness_Analysis_2026-06-24.md`. Don't duplicate — point here, run the real gates.
> **Last verified:** 2026-06-27 (see `DIAGNOSTIC_ROOT_CAUSE_2026_06_27.md`).

---

## A. Pre-Ship Gate (run on Windows BEFORE every deploy)

Each row = a REAL script. Green-or-block.

| # | Gate | Command | Blocking? |
|---|---|---|---|
| 1 | Import + routes + wiring | `python scripts/prod_check.py` | ✅ YES |
| 2 | Test suite (~220 files) | `scripts\run_tests.bat` → **read `pytest_run.log`** | ✅ YES (targeted suites if full hangs) |
| 3 | Secrets not committed | `python scripts/check_secrets.py` | ✅ YES |
| 4 | Cross-path parity (voice billing/qualify) | `python scripts/cross_path_audit.py` | ✅ YES |
| 5 | Frontend↔API wiring | `python scripts/deep_wiring_audit.py` | ✅ YES |
| 6 | Automation flags + jobs | `python scripts/automation_wiring_audit.py` | ✅ YES |
| 7 | Full integration check | `python scripts/final_integration_check.py` | ✅ YES |
| 8 | Billing truth (pricing↔packages.py) | `pytest tests/test_billing_truth_2026.py -q` | ✅ YES (CI-blocking) |

> Shortcut: `/verify` slash-command bundles prod_check + tests + secrets.

---

## B. Deploy (MANUAL SSH — CI is gate-only, does NOT auto-deploy)

```bash
# Windows git push first (scripts\run_tests.bat does this), then:
SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204"
$SSH 'cd /opt/leadgen && git pull \
  && docker compose -f docker-compose.vps.yml build app \
  && docker compose -f docker-compose.vps.yml up -d --no-deps app \
  && sleep 16 && curl -s localhost:8000/health'
```

- **New `@app.get` page-route?** → hard reload (stale `.pyc` 404): recreate container, OR `pkill -9 -f uvicorn; find app -name __pycache__ -prune -exec rm -rf {} +`.
- **Automation/loop code change?** → also recreate `worker` + `scheduler` (not just `app`).
- Verify `/health` shows `environment: production`. Keep `sleep 16` + 2× health-check.
- Full deploy SOP + gotchas: `ship-checklist` / `hostinger-deploy` skills, `PROJECT_SOP.md`.

---

## C. Post-Deploy Runtime Liveness (verify automation actually restarted)

```bash
$SSH 'cd /opt/leadgen \
  && docker compose -f docker-compose.vps.yml ps \
  && docker exec leadgen_redis redis-cli llen celery \
  && stat -c "%y" data/job_heartbeats.json'
```

| Check | Healthy value |
|---|---|
| `leadgen_worker` / `leadgen_scheduler` | Up (healthy) |
| `redis-cli llen celery` | < 500 (>800 auto-trims; >500 after recreate → `del celery`) |
| `job_heartbeats.json` mtime | < 10 min old |
| `python scripts/automation_health_audit.py --daily-check` | loop alive, cost < cap |

---

## D. Launch / First-Paid-Customer Readiness

| Item | State |
|---|---|
| `GET /api/activation/readiness` → `ready_for_first_paid_customer` | ✅ true |
| UPI payments (`UPI_VPA`, `/api/public/pay-info`, `is_armed()`) | ✅ LIVE |
| GST gated on `GST_GSTIN` (unregistered = no tax) | ✅ correct |
| Marketing tiers sellable (Product 1) | ✅ |
| Voice cold-calling (Product 2) | ⛔ DLT + Vobiz recharge+DID (user paperwork — NOT a code blocker) |

---

## E. Compliance Gates (NEVER disable — code must stay intact)

- TRAI: 140-series · DLT · DND scrub (**fail-CLOSED**) · 9am–7pm calling-window · AI-disclosure greeting.
- Consent ledger: opt-out → instant cross-channel suppression + 90-day recording retention.
- WhatsApp bulk auto-send = OFF (ban-safe, 1-click human send only).
- Detail: `PROJECT_HANDOFF.md` §12, `SWARA_HANDOFF_SOP.md` Part E.

---

## F. Rollback

`.env`: `RUN_IN_PROCESS_SCHEDULER=1` + `WEB_CONCURRENCY=1`, stop worker/scheduler, recreate app. SQLite `/opt/leadgen/leadgen.db` = read-only backup (live DB = Postgres).

---

**Related:** `E2E_TEST_PLAN.md` (test→pipeline map) · `PRODUCTION_READINESS_2026.md` (narrative) · `DIAGNOSTIC_ROOT_CAUSE_2026_06_27.md` (last health snapshot).
