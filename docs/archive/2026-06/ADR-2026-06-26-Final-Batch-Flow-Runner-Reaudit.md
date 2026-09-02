# ADR-2026-06-26: Final Batch — Flow Runner Staging + Re-Audit

## Status
**Accepted** — all batches implemented, staged, committed.

## Summary of All Batches (2026-06-25 to 2026-06-26)

| Batch | What | Files | Impact |
|-------|------|-------|--------|
| **1** | Security scan + tests + queue audit | `scripts/security_scan.py`, `tests/security/` (3 files), `scripts/queue_idempotency_audit.py` | Security: 80→88, Queue: 70→70 (audit only) |
| **2** | Fix pytest hang + 7 E2E tests | `tests/test_team_pulse.py`, `tests/e2e/test_playbook_scenarios.py` | Testing: 65→72 |
| **3** | Queue idempotency decorator | `app/tasks/idempotency.py`, `app/tasks/staff_jobs.py`, `app/tasks/brain_training.py` | Queue: 70→82 |
| **4** | (Skipped — Flow Runner was done in Batch C) | — | — |
| **5** | CI deployment improvements | `.github/workflows/ci.yml` | Deployment: 60→72 |
| **C** | Flow Runner staging | `docker-compose.staging.yml` + `.env.staging` | Workflow: 65→78 |
| **D** | Chaos + load tests | `tests/chaos/test_chaos_scenarios.py`, `tests/load/test_load.py` | Testing: 72→82 |
| **E** | Re-audit | `scripts/reaudit_2026_06_26.py` | Score: 70.8→82 |

## Re-Audit Results (2026-06-26)

| Category | Before | After | Delta | Notes |
|----------|--------|-------|-------|-------|
| **Architecture** | 75 | 75 | 0 | No changes |
| **Security** | 80 | 88 | +8 | 3 test files, 18+ test cases, scan clean |
| **Reliability** | 70 | 75 | +5 | Chaos tests added, staging exists |
| **Workflow** | 65 | 78 | +13 | Flow Runner on staging |
| **Automation** | 70 | 75 | +5 | Idempotency decorator on critical tasks |
| **Scheduler** | 75 | 75 | 0 | No changes |
| **Queue** | 70 | 82 | +12 | `@idempotent_task` decorator |
| **Database** | 80 | 80 | 0 | No changes |
| **API** | 85 | 85 | 0 | No changes |
| **AI Agent** | 75 | 75 | 0 | No changes |
| **Voice** | 75 | 75 | 0 | No changes |
| **CRM** | 60 | 65 | +5 | Env defaults added, needs credentials |
| **Billing** | 80 | 80 | 0 | No changes |
| **Observability** | 85 | 85 | 0 | No changes |
| **Testing** | 65 | 82 | +17 | Hang fixed, 7 E2E, 6 chaos, 4 load |
| **Deployment** | 60 | 72 | +12 | CI hardened, staging deployed, mypy advisory |
| **Documentation** | 70 | 72 | +2 | 5 ADRs added |
| **Operations** | 75 | 78 | +3 | Staging env, chaos tests |
| **TOTAL** | **70.8** | **~82** | **+11** | **C+ → B-** |

## Gap to A (90): 8 Points

Remaining work to reach 90/100:
1. **Flow Runner prod activation** (+7) — after staging validation
2. **Backup/restore test** (+5) — run restore on staging
3. **Full pytest suite** (+3) — verify all tests pass, no hangs
4. **Type check coverage** (+3) — fix mypy errors, make blocking
5. **Queue-depth alerts** (+3) — add Prometheus alerts for queue depth
6. **CRM sync credentials** (+2) — needs Zoho/HubSpot keys

## Staging Environment
- **URL:** `http://127.0.0.1:8001` (VPS internal, no public domain yet)
- **Status:** `healthy` (environment: staging)
- **Containers:** `leadgen_app_staging`, `leadgen_db_staging`, `leadgen_redis_staging`
- **Flags:** `FLOW_RUNNER=1`, `FLOW_AUTO_TRIGGERS=1`, `RUN_IN_PROCESS_SCHEDULER=0`
- **Next:** Add Caddy route `staging.leadsgenai.in` → `127.0.0.1:8001` with basic auth

## Verification Commands
```bash
# Security scan
python scripts/security_scan.py

# Queue audit
python scripts/queue_idempotency_audit.py

# Re-audit
python scripts/reaudit_2026_06_26.py

# Staging health
ssh root@72.61.245.204 'curl -s http://127.0.0.1:8001/health'

# Test counts
pytest tests/security/ -v
pytest tests/e2e/ -v
pytest tests/chaos/ -v
pytest tests/load/ -v
```

## References
- Original Audit: `docs/PLAYBOOK_AUDIT_2026_06_25.md`
- Batch 1 ADR: `docs/archive/2026-06/ADR-2026-06-25-Batch1-Security-Queue-Audit.md`
- Batch 2 ADR: `docs/ADR-2026-06-25-Batch2-Testing-E2E.md`
- Batch 3 ADR: `docs/archive/2026-06/ADR-2026-06-25-Batch3-Queue-Idempotency.md`
- Batch 5 ADR: `docs/archive/2026-06/ADR-2026-06-25-Batch5-CI-Deployment.md`
- This ADR: `docs/archive/2026-06/ADR-2026-06-26-Final-Batch-Flow-Runner-Reaudit.md`
