# UNITY VIRTUAL OFFICE — DEPLOYMENT & ROLLOUT (2026-07-12)

## 0. Current blockers (honest state)

| Blocker | Detail | Owner |
|---|---|---|
| Unity Editor not installed | Start-menu app scan 2026-07-12: no Unity Hub/Editor. Install Unity Hub + **2022.3 LTS** + WebGL module. | USER |
| Repo dirty (Loop 27/28) | Working tree on `recovery/loop27-loop28-20260711` @ `1c7441b3` with uncommitted dashboard work. Master rule: commit/stabilize BEFORE Unity deploy. | USER (+agent on go) |
| Verify gates blocked in sandbox | FUSE mount truncates large reads (main.py 2099→2067) — run gates on Windows venv: see §2. | USER runs, agent interprets |
| No SSH key in session | VPS deploy commands must be run by user (existing runbook `memory/playbooks.md`). | USER |

## 1. What ships in which commit (Phase 32 — small, reviewable, on `feat/unity-blueprint-virtual-office`)

```
docs(office): inventory existing blueprint command center and map assets
  → docs/EXISTING_BLUEPRINT_ASSET_INVENTORY.md, UNITY_BLUEPRINT_STYLE_GUIDE.md,
    COMMAND_CENTER_UNITY_MAPPING.md, OFFICE_MAP_UNITY_MAPPING.md
docs(office): architecture, API contract, security, deployment, UAT
  → docs/UNITY_VIRTUAL_OFFICE_{ARCHITECTURE,SECURITY,DEPLOYMENT,UAT}.md, UNITY_OFFICE_API_CONTRACT.md
feat(office-shell): blueprint office shell + INERT mode routing + guarded unity mount
  → frontend/office_blueprint.html; app/main.py (mode param on /app/office + guarded
    /static/office-unity mount); app/api/automation_flags.py (+UNITY_* flags)
test(office): INERT-flag + bridge-allowlist + secret/geometry drift locks
  → tests/test_office_blueprint_shell.py
chore(unity-office): Unity WebGL project scaffold (scripts, jslib bridge, build script)
  → unity/LeadGenVirtualOffice/**
```
NEVER in these commits: Loop 27/28 dashboard files, `.env`, customer data, Unity `Library/`.
Branch creation (user, Windows PowerShell — repo is currently ON the recovery branch):
```powershell
cd C:\Users\Ratanshila\Documents\leadgenrationaiagent
git status --short            # review: Unity/office files vs pre-existing Loop 27/28 files
git checkout -b feat/unity-blueprint-virtual-office
git add docs/EXISTING_BLUEPRINT_ASSET_INVENTORY.md docs/UNITY_*.md docs/COMMAND_CENTER_UNITY_MAPPING.md docs/OFFICE_MAP_UNITY_MAPPING.md docs/UNITY_OFFICE_API_CONTRACT.md
git commit -m "docs(office): blueprint asset inventory + unity office architecture pack"
git add frontend/office_blueprint.html app/main.py app/api/automation_flags.py
git commit -m "feat(office-shell): blueprint office shell, INERT mode routing, guarded unity mount"
git add tests/test_office_blueprint_shell.py && git commit -m "test(office): shell INERT + allowlist + drift locks"
git add unity/ && git commit -m "chore(unity-office): unity webgl project scaffold"
```
(`git add -A` FORBIDDEN — CLAUDE.md §8. main.py/automation_flags.py carry ONLY additive
office hunks from this program; diff them first: `git diff app/main.py`.)

## 2. Verification gate (run on Windows venv BEFORE any commit)

```powershell
.venv\Scripts\python.exe -m pytest tests/test_office_blueprint_shell.py -q
.venv\Scripts\python.exe scripts\prod_check.py
.venv\Scripts\python.exe scripts\check_secrets.py
.venv\Scripts\python.exe -m ruff check app/main.py app/api/automation_flags.py
```
Expected: shell suite green (S8 may skip if build dir exists); prod_check ALL PASS with
route count +0 (mode param reuses existing route); secrets clean.

## 3. Unity build → static assets

1. Build per `unity/LeadGenVirtualOffice/README.md` → `Build/LeadGenVirtualOffice.{loader.js,data.br,framework.js.br,wasm.br}`.
2. Copy to `frontend/office_unity/Build/` (versioned: keep `office_unity/` per-release; rollback = restore previous dir).
3. `app/main.py` mounts `/static/office-unity` automatically when the dir exists.
4. Caddy (VPS host) already proxies everything to :8000; Brotli files are served pre-compressed —
   verify `Content-Type: application/wasm` for `.wasm.br` + `Content-Encoding: br` handling.
   If Caddy strips/mangles, add explicit header matcher for `/static/office-unity/*` (host-side, user).
5. Record in this doc after first build: build size, compressed size, load time, memory, request count.
   (Budget: ≤12 MB compressed, ≤20s load on office wifi.)

## 4. Flags & rollout order (Phase 24)

```
UNITY_VIRTUAL_OFFICE_ENABLED   (default unset = OFF → /app/office?mode=3d serves 2D map, fully INERT)
UNITY_CUSTOMER_OFFICE_ENABLED  (default unset = OFF; Milestone E)
```
1. Local dev: set flag in dev env, open http://localhost:8000/app/office?mode=3d — shell with live
   panel; "Unity build: NOT DEPLOYED" state until a build exists (honest state, not blank).
2. VPS admin preview: set `UNITY_VIRTUAL_OFFICE_ENABLED=1` in `.env` (user), recreate app container;
   admin-only exposure is inherent (snapshot API = require_admin; shell without admin session shows
   login-required).
3. Selected customers: ONLY after Milestone E + tenant-SSE/polling isolation tests; per-tenant
   rollout via existing Redis feature-flag service.
4. Rollback: unset flag (INERT immediately); static build dir can stay (unreachable state).

## 5. Deploy checklist (Phase 33 — deltas over standard runbook `memory/playbooks.md`)

- Current repo committed + gates green (§2) BEFORE build/deploy.
- Standard deploy: git push → SSH → `git pull && docker compose -f docker-compose.vps.yml build app && up -d --no-deps app`.
- Post-deploy: 2× `/health` = `environment:production`; `curl -I /app/office` 200;
  `curl -I "/app/office?mode=3d"` 200 (serves 2D map while flag off); no new 5xx in logs;
  worker/scheduler untouched (no code paths shared).
- **Do not** replace the default `/app/office` experience until preview proven (default stays 2D map).
