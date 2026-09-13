# DEPLOY READINESS HANDOFF - 2026-09-13

**Purpose:** one-page, owner-run deploy so the pending 24x7 / enterprise work ships.
**Nothing has been committed or deployed by the agent.** All items below are LOCAL-ONLY.

## 1. What this deploy ships
| Area | Effect |
|---|---|
| `app/workers/cli_worker.py` (+ `__init__.py`) | first headless CLI worker runtime (register/heartbeat/claim, no-op safe) |
| `app/main.py` | `/telegram/setup` router becomes live (writes still fail-closed) |
| `scripts/vps_migrate.sh` + `scripts/deploy_vps.sh` guard | deploys now run `alembic upgrade head` before verify (schema drift closed) |
| `app/config.py`, `app/platform/owner_admin.py` | CORS allowlist (no wildcard) + trusted_hosts fail-safe |
| `admin-dashboard/` | dashboard now type-checks + builds |
| `docs/`, profiles, records | FINAL DECISION, CLI worker roster, profile bindings |

Migrations 026/027 were already applied to the prod DB on 2026-09-12 (with a 61 MB backup).

## 2. Commit (per-file - never `git add -A`)
```
git add app/workers app/api/telegram_setup.py app/main.py app/config.py app/platform/owner_admin.py app/platform/telegram_ingress.py app/platform/omniroute_aliases.py config/telegram scripts/telegram_setup.py scripts/vps_migrate.sh scripts/deploy_vps.sh admin-dashboard/tsconfig.json admin-dashboard/src/lib admin-dashboard/src/pages/TelegramSetup.tsx admin-dashboard/package.json admin-dashboard/package-lock.json admin-dashboard/src/App.tsx admin-dashboard/src/api/client.ts admin-dashboard/src/types.ts admin-dashboard/src/components docs/architecture docs/hermes docs/TELEGRAM_ENTERPRISE_SETUP.md docs/context/PHASE0_RECONCILIATION_2026-09-12.md docs/reports tests/test_cli_worker.py tests/test_cors_hardening.py tests/test_telegram_setup.py .gitignore HERMES_AGENT_ROSTER.yaml
git commit -m "feat(24x7): CLI worker runtime + telegram wiring + deploy migration guard + dashboard build fix"
```

## 3. Push + deploy (canonical, MANUAL)
```
git.exe push origin HEAD
ssh.exe -i %USERPROFILE%/.ssh/id_rsa root@72.61.245.204
cd /opt/leadgen && setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &
tail -f /tmp/dep.log
```

## 4. Verify after deploy
```
curl -s https://leadsgenai.in/health                                   # environment:production, version == new sha
curl -s -o /dev/null -w 'http_code_status' https://leadsgenai.in/telegram/setup   # expect 200 (was 404)
cd /opt/leadgen && .venv/bin/alembic current                           # expect 027_add_dev_workers
```

## 5. Start the first CLI worker (after deploy)
```
PER=$(docker inspect --format '{{.Config.Image}}' leadgen_app | sed 's/.*://')
docker compose -f docker-compose.vps.yml --profile celery up -d worker-cli-operations
docker exec leadgen_db sh -lc 'psql -U $POSTGRES_USER -d $POSTGRES_DB -tAc "select worker_id,kind,supervisor_bot,health from dev_workers"'
# expect: cli_operations | cli | operations | healthy  (heartbeat < 60s)
```

## 6. Rollback
- Code: `git revert <sha>` or redeploy the previous APP_VERSION.
- Migrations: additive only; `alembic downgrade 025` drops only the 2 new tables/columns.
- Worker: `docker compose ... stop worker-cli-operations` (row -> dead in 600 s; reap_stale clears it).
- WAHA (prior fix): restore `/opt/leadgen/.env.bak-waha-fix-*` + recreate `app`.

## 7. Current change set (67 files)
```
M .gitignore
 M HERMES_AGENT_ROSTER.yaml
 M admin-dashboard/package-lock.json
 M admin-dashboard/package.json
 M admin-dashboard/src/App.tsx
 M admin-dashboard/src/api/client.ts
 M admin-dashboard/src/components/layout/Sidebar.tsx
 M admin-dashboard/src/components/orchestration/OrchestrationView.tsx
 M admin-dashboard/src/components/ui/ErrorBoundary.tsx
 M admin-dashboard/src/types.ts
 M app/api/dev_tasks.py
 M app/config.py
 M app/main.py
 M app/platform/coordination_hub_auth.py
 M app/platform/owner_admin.py
 M config/desktop_apps/combo_distribution.yaml
 M data/leadgen_dev.db
 M data/prospect_export.csv
 M data/prospects.jsonl
 M docs/context/SESSION_HANDOFF.md
 M docs/hermes/profiles/board/profile.yaml
 M docs/hermes/profiles/claude/profile.yaml
 M docs/hermes/profiles/engineering/profile.yaml
 M docs/hermes/profiles/guardian/profile.yaml
 M docs/hermes/profiles/hunter/profile.yaml
 M docs/hermes/profiles/openclaw/profile.yaml
 M docs/hermes/profiles/operations/profile.yaml
 M docs/hermes/profiles/pilot/profile.yaml
 M docs/hermes/profiles/platform/profile.yaml
 M docs/hermes/profiles/sales/profile.yaml
 M docs/hermes/profiles/success/profile.yaml
 M docs/hermes/profiles/verdant/profile.yaml
 M docs/hermes/profiles/workbuddy/profile.yaml
 M memory/incidents.md
 M progress.md
 M scripts/deploy_vps.sh
?? admin-dashboard/src/lib/
?? admin-dashboard/src/pages/TelegramSetup.tsx
?? admin-dashboard/tsconfig.json
?? app/api/telegram_setup.py
?? app/platform/omniroute_aliases.py
?? app/platform/telegram_ingress.py
?? app/workers/
?? config/telegram/
?? docs/TELEGRAM_ENTERPRISE_SETUP.md
?? docs/architecture/24X7_FINAL_DECISION_2026-09-12.md
?? docs/context/PHASE0_RECONCILIATION_2026-09-12.md
?? docs/hermes/CLI_WORKER_ROSTER.md
?? docs/philosophy/
?? docs/reports/REVENUE_RECONCILIATION_20260912.md
?? docs/reports/SMARTFLO_ESCALATION_20260912.md
?? gen_0913.py
?? "last10ï€º, last10(raw))ï€Šprint()ï€Šraw_comp = +918ï€ªï€ªï€ªï€ª0181,+918ï€ªï€ªï€ªï€ª2607,+919ï€ªï€ªï€ªï€ª4977ï€Šfor raw in raw_comp.split(,)ï€ºï€Š    print("
?? "last10ï€º, last10(raw))ï€Šï€¢ï€Š"
?? new-clone/
?? scripts/ops_rev_recon.py
?? scripts/ops_rev_recon2.py
?? scripts/ops_rev_recon3.py
?? scripts/ops_rev_recon4.py
?? scripts/prospect_stats.py
?? scripts/telegram_setup.py
?? scripts/vps_migrate.sh
?? tests/test_cli_worker.py
?? tests/test_cors_hardening.py
?? tests/test_dev_task_audit.py
?? tests/test_telegram_setup.py
?? tmp/
```
