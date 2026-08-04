# CURRENT_STATE - LeadGen AI (operational truth)

Evidence labels: PRODUCTION-PROVEN | CODE-PRESENT | TEST-PROVEN | LOCAL-ONLY | PARTIAL | STALE | UNKNOWN | DIRECT_HOST_VERIFIED | GIT_VERIFIED | ASSUMED
(`DIRECT_HOST_VERIFIED` = probed from the live host at a stated time; `GIT_VERIFIED` = re-derivable from this repo; `ASSUMED` = carried forward, not re-checked.)

## Last verified timestamp
2026-08-03 — Buzz Admin Plane completion pass + prior `/health`=`303b061f`. See `docs/context/SESSION_HANDOFF.md`.

## Sprint goal (LOCKED)
**GTM 0→1** — pehle paid customers on Marketing product; mid-funnel bottleneck (Hot Queue `/app/inbox` + dialer sprint); 2nd paying customer target.

## Production SHA
`303b061f` — merge commit of PR #225 (revenue automation: refill / pay-truth / inquiry Hot Queue / Owner OS calling badge). Live-probed 2026-08-03 over direct HTTPS: `{"version":"303b061f","environment":"production","status":"healthy"}`.
5 app-image services pinned equal to this SHA (no per-container skew); queues + DLQ = 0.
Rollback reference: `fa9f47c7` (prior) / `303b061f` current.
Label: DIRECT_HOST_VERIFIED (2026-08-03) + GIT_VERIFIED.

## Origin/main
`303b061` — **EQUAL to production** (`git fetch origin && git rev-parse origin/main`). Prod holds zero commits main lacks. Open PRs = 0.
Label: GIT_VERIFIED (2026-08-03)

## Production health
`status: healthy`, `environment: production` at `303b061f` (2026-08-03, direct HTTPS).
Label: DIRECT_HOST_VERIFIED (2026-08-03)

## Sales Autopilot (live, REAL email — owner 2026-08-03 refill arm)
- `SALES_AUTOPILOT_ENABLED=1` · `DRY_RUN=0` · `EMAIL_ENABLED=1` · `WHATSAPP_ENABLED=0` · `REFILL=1` · `REFILL_CAP=25` · `REFILL_MIN_SCORE=0`.
- Manual refill 2026-08-03: upserted 25 `new` prospects (store was idle on Estique-only).
- **Cold** autopilot WhatsApp stays OFF (`SALES_AUTOPILOT_WHATSAPP_ENABLED=0`).
Label: DIRECT_HOST_VERIFIED (2026-08-03)

## Cold email outreach
`AUTO_EMAIL_OUTREACH=1` — LIVE. 2026-08-02 counts: 19 sent + 20 follow-ups.
Label: DIRECT_HOST_VERIFIED (2026-08-02)

## WAHA / WhatsApp — Swara interested follow-up ARMED
WAHA `default` = **WORKING** (`918261030181`, `leadsgenai.in`). Owner 2026-08-03: post-call WA ON for Swara-interested — `WHATSAPP_AUTO_SEND=1` · `POST_CALL_WHATSAPP=1` · `VOICE_CLOSE_WHATSAPP=1` · allowlist `*`. Cold prospect WA remains OFF. Backup `.env.bak-postcall-wa-20260803115342`.
Label: DIRECT_HOST_VERIFIED (2026-08-03 recreate + in-container env)

## Staging provenance
`docker-compose.staging.yml` ab **fail-CLOSED**: `APP_VERSION` mandatory (`${APP_VERSION:?...}`) — `:latest` refused (ADR-097, ISSUE-04). `check_skew.sh` watches `leadgen_app_staging`.
Label: CODE-PRESENT (2026-08-02)

## Calling / flag posture — read this before quoting any flag from this file
`platform_dial` = **FULL CAMPAIGN LIVE** (owner go-ahead 2026-08-02). **Naming trap:** `PLATFORM_DIAL_DAILY` = **boolean on/off** (prod `=1`); per-run cap = `PLATFORM_DIAL_LIMIT` (prod `=100`). Also: `VOICE_LAUNCH_KILL=0` · `DIAL_TEST_MODE=0` · `VOICE_DAILY_CALL_CAP=100`. LIVE proof: 3 real Vobiz calls 2026-08-02 (session `S20260802-a280d841`). Daily 11:30 IST auto-dial uses `PLATFORM_DIAL_LIMIT` (niche=all). Compliance spine UNTOUCHED. Rollback = `.env.bak-fullcampaign-20260802075851`. Docs previously mis-wrote `PLATFORM_DIAL_DAILY=100` — that was wrong wording, not a prod miss-set (re-proved 2026-08-03).
Label: DIRECT_HOST_VERIFIED (2026-08-03 in-container env + 2026-08-02 live call proof).

## Secret hygiene (owner action)
`GEMINI_API_KEY` historically leaked in bash_history (scrubbed 2026-08-03). **Owner chose not to rotate** — voice primary moved off Gemini onto free stack (`VOICE_GEMINI_PRIMARY=0`, runtime `voice_primary=false`, `GEMINI_TTS=0`). Live smoke: `free_ai.chat` → **mistral**. Optional: still revoke burned Gemini key in Google console when convenient.
Label: DIRECT_HOST_VERIFIED (2026-08-03 free-AI switch + chat smoke).

## Migration
No pending migration on the deployed release path. `008` is NOT the head — it is one revision in the 008..022 chain.
Label: PRODUCTION-PROVEN (no migration introduced by the current release lineage)

## Routes
0 route collisions on deployed release path (prod_check gate green; current session shipped additive frontend/middleware changes only — no new routes).
Label: PRODUCTION-PROVEN

## Deployment architecture (hardened path - PRODUCTION-PROVEN)
The proven canonical deployment path is:

```
GitHub Actions
  -> leadgen-deploy (dedicated SSH user, VPS_DEPLOY_USER; NOT root, no docker group)
  -> VPS_SSH_KEY_DEPLOY (dedicated ed25519 key)
  -> root-owned /usr/local/sbin/leadgen-deploy-release wrapper (scoped NOPASSWD sudo, strict 40-hex SHA validation, flock)
  -> immutable exact-SHA anonymous GHCR pull (no docker login, no registry secret)
  -> docker compose (celery profile) up
  -> alembic upgrade head (hard-gated)
  -> /health/ready gate
  -> automatic rollback to the previously-running immutable image on migration or health failure
```

- The old root-based GitHub deploy path is retired. `GHCR_PAT` is retired; the registry package is public and pulled anonymously by exact SHA.
- The emergency root key is retained OUTSIDE GitHub (operator machine / VPS recovery) for break-glass only.
- `DEPLOY_ENABLED` defaults unset (off); a push to `main` runs the gate job only. Deploy requires operator-set `DEPLOY_ENABLED=true` + `workflow_dispatch`.
- Emergency/canonical VPS path also includes `scripts/deploy_vps.sh` with mandatory `APP_VERSION=<sha>`.
Label: PRODUCTION-PROVEN

## Secret state (GitHub Actions)
Retained: `VPS_HOST`, `VPS_DEPLOY_USER`, `VPS_SSH_KEY_DEPLOY`.
Retired (deleted from GitHub Actions after the proven hardened run): `GHCR_PAT`, `VPS_USER`, `VPS_SSH_KEY`.
Emergency root key remains outside GitHub for operator recovery. (Names/state only; no values recorded.)
Label: PRODUCTION-PROVEN

## Skill architecture (canonical registry - CODE-PRESENT on main via PR #106 / ADR-131)
`.claude/skills` is the single canonical tracked skill root; `.agents/skills` is removed.
- Decision record: ADR-131 (`docs/adr/ADR-131-canonical-skill-registry.md`).
- Duplicate-regression CI guard: `tests/test_skill_tree_canonical_guard.py`.
Label: CODE-PRESENT

## OpenClaw
Stage A ON (`OPENCLAW_ENABLED=1`). Admin Dashboard `#openclawAdminCard` LIVE. GREEN-only allowlist; AMBER rejected in Stage A; RED refuse intact; `OPENCLAW_ALLOW_RED_ACTIONS=0`; Owner OS sole authority. Workforce stays **31 agents**.
Label: PRODUCTION-PROVEN (Stage A shipped PR #105) — re-probe env before acting on flags.

## Agent workforce
Canonical workforce remains **31 agents**. OpenClaw/Boss is Owner OS Copilot surface — **not** a 32nd agent.
Label: CODE-PRESENT (registry) | PRODUCTION-PROVEN

## Paying customers
1 - Jiya Makeover (`jiya-makeover`). MRR ₹1,999. Estique autopilot prospect `converted` (see WS-2 in ACTIVE_WORK).

## Top next actions
1. OpenCode issue batch (this session): WAHA status UI ✅ · CSP PostHog allowlist ✅ · autopilot idle_reason ✅ · staging `:latest` fail-closed ✅ · context-docs refresh ✅ — remaining issues continue.
2. Owner: restart WAHA session + scan QR → reply `WAHA CONNECTED`; then agent verify + canary.
3. Feed sales_autopilot new non-converted prospects (or accept idle until new leads).
4. GTM Hot Queue `/app/inbox` → 2nd paying Marketing customer. Keep WhatsApp auto-send / dial / bulk WA OFF.
