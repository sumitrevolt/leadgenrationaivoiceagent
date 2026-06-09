@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set GIT="C:\PROGRA~1\Git\cmd\git.exe"
%GIT% add .github/workflows/ci-cd.yml .github/workflows/deploy.yml .github/workflows/deploy-vps.yml CLAUDE.md app/cache/__init__.py app/main.py docs/SESSION_LOG.md docs/PRODUCTION_CUTOVER.md docker-compose.vps.yml docker-compose.observability.yml monitoring/prometheus.yml scripts/migrate_sqlite_to_postgres.py scripts/pg_backup.sh scripts/_dc_infra_push.bat
%GIT% commit -m "feat(infra): production Docker stack (Postgres+Redis) + auto-deploy CI (GHCR->VPS) + safe SQLite-to-PG migration + rate-limiter fix; Cloud Run workflows manual-only"
echo --- PUSH ---
%GIT% push origin HEAD:main
echo DONE_EXIT=%ERRORLEVEL%
