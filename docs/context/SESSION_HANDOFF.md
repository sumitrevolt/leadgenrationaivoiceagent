# SESSION_HANDOFF — 2026-08-07 Option A containment (REPLY_AUTO_SEND_HARD_OFF)

## OWNER DECISION (LOCKED — do not re-litigate)

**Verdict: Option A containment — restore kill switch to declared SAFETY_INVARIANT default.**

1. Set `REPLY_AUTO_SEND_HARD_OFF=1` on prod (manifest default already `"1"`; prod drifted to `0`).
2. Do **NOT** flip `REPLY_AUTO_SEND` itself.
3. Do **NOT** choose Option B (docs saying "owner-armed forever") — that would leave SAFETY_INVARIANT contradictory to §5.
4. `REPLY_AGENT` stays ON (draft/triage only — fine).
5. After HARD_OFF proven (`_reply_auto_send_enabled()` → False), then merge+deploy PR #276 Master Blueprint admin nav (`8b36b795`, branch `fix/admin-master-blueprint-nav`).
6. WI-CP2 interaction-log = follow-up when auto-send is re-armed later — **not** a blocker for containment tonight.
7. No side-effect run-now. No secrets in chat. Never print token/DATABASE_URL/settings values.

## Coordination status (Cloud Cursor)

| Plane | Status |
|---|---|
| Cloud VPS/SSH | **NO** — `root@72.61.245.204` Permission denied (publickey). Local Cursor owns the flip. |
| Prod `/health` (Cloud probe 2026-08-07) | `version=a08dd5e9` · `environment=production` · `status=healthy` |
| PR #276 | OPEN · MERGEABLE · 1 commit `8b36b795` · **DO NOT deploy until HARD_OFF evidence posted** |
| main tip | `34836739` (#275 safe_settings) — ahead of prod `a08dd5e9`; deploy rides this too |
| Option B | **REJECTED** |

## Exact VPS commands for Local Cursor (HARD_OFF flip ONLY)

Pin recreate to current prod SHA. Do **not** deploy #276 in this step.

```bash
# on VPS as root, from /opt/leadgen
TS=$(date -u +%Y%m%d%H%M%S)
cp -a .env ".env.bak-hardoff-${TS}"

# surgical: set HARD_OFF=1 only — do NOT touch REPLY_AUTO_SEND / REPLY_AGENT
# Prefer a known sed/awk pattern; verify with grep -E '^REPLY_AUTO_SEND' .env
# (print names only — never dump full .env)

grep -E '^REPLY_AUTO_SEND(_HARD_OFF)?=' .env | sed 's/=.*/=<redacted-len-check>/'
# expect to see HARD_OFF line present; after edit it must be =1

# If line exists:
sed -i 's/^REPLY_AUTO_SEND_HARD_OFF=.*/REPLY_AUTO_SEND_HARD_OFF=1/' .env
# If missing, append:
# echo 'REPLY_AUTO_SEND_HARD_OFF=1' >> .env

# Recreate app+worker ONLY at pinned prod SHA (no code deploy):
export APP_VERSION=a08dd5e9
docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps --force-recreate app worker

# Prove kill works (names/bool only — no settings dump):
docker compose -f docker-compose.vps.yml exec -T app \
  python -c "import asyncio; from app.platform.reply_agent import _reply_auto_send_enabled; print('enabled=', asyncio.run(_reply_auto_send_enabled()))"
# ACCEPTANCE: enabled= False

# Container env name check (value presence only):
docker compose -f docker-compose.vps.yml exec -T app \
  python -c "import os; v=os.getenv('REPLY_AUTO_SEND_HARD_OFF'); print('HARD_OFF_set=', v is not None, 'HARD_OFF_is_one=', v=='1')"
```

### After HARD_OFF evidence posted → PR #276 deploy (separate step)

```bash
# ONLY after enabled=False proven and posted in handoff
# VOICE_LAUNCH_KILL=1 dance + deploy_vps.sh with APP_VERSION pin
# Acceptance: curl -s https://leadsgenai.in/app/admin | grep -c -i "master blueprint"  ≥ 1
# Canonical: scripts/deploy_vps.sh (never hand-rolled compose without APP_VERSION)
```

## Evidence already proven (local session — carried)

- Prod `/health` = `a08dd5e9` (cache-bust curl, uptime advancing) — **Cloud re-confirmed**
- Auth pass: 43 jobs, 0 disabled, 0 unhealthy, 60 runs 0 failures; 5 families ran today
- HARD_OFF=0 + REPLY_AUTO_SEND=ON → sends live; content scan is only remaining guard
- Env `REPLY_AUTO_SEND=0` alone insufficient (falls through to Redis `reply_auto_send`)
- PR #276 OPEN MERGEABLE, 2 files only

## [CURSOR Cloud] HANDOFF → Local Cursor

- **Goal:** Option A — `REPLY_AUTO_SEND_HARD_OFF=1` on prod; prove `_reply_auto_send_enabled()` False; then (only then) merge+deploy #276
- **Done:** Decision locked in SESSION_HANDOFF + progress Loop Run; Cloud confirmed no VPS key; prod health `a08dd5e9` re-probed; #276 deploy gated
- **Evidence:** Cloud `/health` JSON version=`a08dd5e9` environment=production; SSH to VPS = Permission denied; PR #276 mergeable=MERGEABLE oid=`8b36b795`; manifest HARD_OFF default=`1`
- **Left:** Local Cursor executes HARD_OFF=.env backup + recreate app+worker @ `APP_VERSION=a08dd5e9` + prove enabled=False; post Evidence; then #276 kill-fence deploy via `deploy_vps.sh`
- **Touched:** `docs/context/SESSION_HANDOFF.md`, `docs/context/ACTIVE_WORK.md`, `progress.md` (docs-only; no prod mutation from Cloud)

## Out of scope tonight
- Option B docs rewrite
- Flipping `REPLY_AUTO_SEND`
- WI-CP2 interaction-log
- Side-effect run-now / scheduler fire
- Swara/voice edits (FROZEN)
