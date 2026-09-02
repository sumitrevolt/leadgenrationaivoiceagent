# ADR-001: Repo organize + unnecessary files cleanup

**Status:** Accepted
**Date:** 2026-06-10
**Deciders:** Sumit

## Context
Repo me ~10 mahine ka accretion: root pe ~200 untracked one-off `.log` files, `scripts/` me ~290 files jisme ~170 one-off session bats (`launch_*`, `cowork_*`, `*_deploy.bat`, `*_push.bat`), legacy Cloud-Run/Railway/Render deploy configs (ab Docker-on-VPS canonical hai), aur 10+ loose top-level MD guides. Production LIVE hai (leadsgenai.in, Docker stack) — koi bhi cleanup runtime ko touch nahi kar sakta.

**Constraints:** zero behaviour change; `prod_check` + full pytest green rahe; VPS crons ke scripts (vps_selfheal.sh, pg_backup.sh, offsite_email_backup.py) untouched; CI test.yml push pe `Dockerfile.production` build karta hai.

## Decision
**Option B (non-runtime cleanup)** — sirf generated artifacts, one-off scripts aur dead deploy-configs hatao; Python code/module layout BILKUL nahi chhedna.

## Options Considered

### Option A: Aggressive restructure (app/ modules reorganize + legacy code delete)
| Dimension | Assessment |
|-----------|------------|
| Complexity | High |
| Risk | **Very high** — app.ml/lead_scraper/automation startup pe IMPORT hote hain (prod_check proof); FastAPI route-shadow + import-path breakage ka history |
| Benefit | Cosmetic |

**Rejected** — pichhli baar duplicate-module galti se prod `/festivals` shadow hua tha; module moves = sab imports + Dockerfile + tests risk.

### Option B: Non-runtime cleanup (CHOSEN)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Risk | Low — sab `git rm` history se recoverable; runtime files untouched |
| Benefit | Root ~230 → ~60 entries; scripts/ ~290 → ~120; naya contributor/agent confuse nahi hota |

### Option C: Status quo
Free, par har session me junk badhta hai; agents galat one-off script utha sakte hain.

## What was done
1. **Local purge (untracked, gitignored):** root `*.log` (~200), `.coverage`, `demo.db`, `test.db-journal`, one-off untracked bats.
2. **`git rm` (history me recoverable):** `scripts/launch_*.bat`, `scripts/cowork_*.bat`, `scripts/*_deploy.bat`, `scripts/*_push.bat`, `scripts/push_*.bat` + explicit one-off bats (call/brain/cb/conv/vobiz/p12/nps probe-bats); root legacy: `cloudbuild*.yaml`, `cloud-run-patch.yaml`, `railway.json`, `render.yaml`, `Procfile`, `Dockerfile.backup`, `.gcloudignore`, `deploy.ps1`, `deploy_vps.sh`, `start_local.*`, `quickstart.py`, `verify_maya_conversation.py`, `_dc_commit_push.bat`, `source.tar.gz`, `demo.db-journal`.
3. **`git mv` → `docs/legacy/`:** ORIGINAL_REQUEST, PRODUCTION_READY, production_readiness_report, AUTOMATION_SETUP, DEPLOYMENT, DEPLOY_GUIDE, LAUNCH_GUIDE, PRODUCTION_CHECKLIST, QUICKSTART, env.template.
4. **`.gitignore` harden:** `*.log`, `*.db-journal`, `.coverage`, `*.tar.gz`.

## Explicitly KEPT (wired/referenced — delete mat karna)
- **Sab `app/` code** (legacy-looking app/ml, lead_scraper, automation bhi startup-imported hain).
- `Dockerfile.lock` (canonical VPS build) · `Dockerfile.production` + `docker-compose.yml`/`docker-compose.prod.yml` (CI test.yml push-pe build + Makefile refs) · `docker-compose.{vps,staging,observability}.yml` · `Dockerfile`.
- Scripts referenced by skills/crons: `prod_check.py`, `run_tests.bat`, `fix_push_redeploy.bat`, `vps_agents_test.py`, `ws_test.py`, `llm_probe.py`, `agent_tester.py`, `setup_status.py`, `env_set.py`, sab `vps_*.sh`, `pg_*.sh`, `offsite_email_backup.py`, `hostinger_dns.py`, `exotel_setup_audit.py`, sab `check_*.py`/`smoke_*.py`, `migrate_sqlite_to_postgres.py`, `scripts/ops/`.
- Root: README, CLAUDE.md, AGENTS.md, CHANGELOG, CONTRIBUTING, SECURITY, LICENSE, dono `.xlsx`, `leadgen.db` (rollback-backup), `alembic/`, `monitoring/`, `infrastructure/`, `models/`, `data/` (Business_Playbook ab `docs/playbooks/` me).

## Consequences
- **Easier:** repo navigate, agent context, naya one-off = turant dikhega (gitignore se log clutter wapas nahi aayega).
- **Harder:** purana one-off chahiye to `git log --diff-filter=D` se nikalna padega.
- **Revisit:** (a) legacy CI workflows (ci-cd/deploy/test.yml) + Dockerfile.production/compose-legacy ka retire — alag ADR jab GHCR deploy-vps.yml full-canonical ho; (b) top-level Hinglish playbook/xlsx ka docs/ move — user call.

## Rollback
`git revert <cleanup-commit>` ya individual: `git checkout <commit>~1 -- <path>`.

## Action Items
1. [x] Cleanup execute (scripts/cleanup_repo.bat)
2. [x] prod_check + tests green
3. [x] Push + VPS pull (tree clean)
