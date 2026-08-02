# CURRENT_STATE - LeadGen AI (operational truth)

Evidence labels: PRODUCTION-PROVEN | CODE-PRESENT | TEST-PROVEN | LOCAL-ONLY | PARTIAL | STALE | UNKNOWN | DIRECT_HOST_VERIFIED | GIT_VERIFIED | ASSUMED
(`DIRECT_HOST_VERIFIED` = probed from the live host at a stated time; `GIT_VERIFIED` = re-derivable from this repo; `ASSUMED` = carried forward, not re-checked.)

## Last verified timestamp
2026-08-02 — `/health` re-probed from the live host (live launch-check session, no browser). See `docs/context/SESSION_HANDOFF.md`.

## Sprint goal (LOCKED)
**GTM 0→1** — pehle paid customers on Marketing product; mid-funnel bottleneck (Hot Queue `/app/inbox` + dialer sprint); 2nd paying customer target.

## Production SHA
`15613b35` — merge commit of PR #211 (`voice-session-limiter-2026-08-02`). Live-probed 2026-08-02 over direct HTTPS: `{"version":"15613b35","environment":"production","status":"healthy"}`.
5 app-image services pinned equal to this SHA (no per-container skew); queues + DLQ = 0.
Rollback reference: `15613b35` until the next deploy.
Label: DIRECT_HOST_VERIFIED (2026-08-02, live session) + GIT_VERIFIED (this file's git ref matches).

## Origin/main
`15613b35` — **EQUAL to production** (`git fetch origin && git rev-parse origin/main`). Prod holds zero commits main lacks.
Label: GIT_VERIFIED (2026-08-02)

## Production health
`status: healthy`, `environment: production` at `15613b35` (2026-08-02, direct HTTPS).
Label: DIRECT_HOST_VERIFIED (2026-08-02)

## Sales Autopilot (live, REAL sends — owner mandate 2026-08-01)
- `SALES_AUTOPILOT_ENABLED=1` · `SALES_AUTOPILOT_DRY_RUN=0` · `SALES_AUTOPILOT_EMAIL_ENABLED=1` · `SALES_AUTOPILOT_WHATSAPP_ENABLED=0`.
- Scheduler routes to email channel when WhatsApp off (PR #207 `_primary_channel`).
- Last tick `dry_run:false` processed 0 — only prospect Estique is `converted`. Empty queue = expected idle, NOT failure (idle_reason now explicit in `last_tick.json` + Mission Control Schedule tab, ISSUE-03).
- WhatsApp stays 1-click human (`WHATSAPP_AUTO_SEND=0`), dial test-mode cap 10 (both legal/ban gates — do NOT flip).
Label: DIRECT_HOST_VERIFIED (2026-08-02) — re-probe container env before acting.

## Cold email outreach
`AUTO_EMAIL_OUTREACH=1` — LIVE. 2026-08-02 counts: 19 sent + 20 follow-ups.
Label: DIRECT_HOST_VERIFIED (2026-08-02)

## WAHA / WhatsApp self-host
WAHA `default` session status **FAILED** (QR timeout — not scanned) as of 2026-08-02. Owner must re-start session + scan QR. Backend endpoints `/api/wa/selfhost/{status,start,qr}` exist; frontend now surfaces FAILED/SCAN_QR_CODE/WORKING states + QR auto-refresh (ISSUE-01).
Label: DIRECT_HOST_VERIFIED (2026-08-02)

## Staging provenance
`docker-compose.staging.yml` ab **fail-CLOSED**: `APP_VERSION` mandatory (`${APP_VERSION:?...}`) — `:latest` refused (ADR-097, ISSUE-04). `check_skew.sh` watches `leadgen_app_staging`.
Label: CODE-PRESENT (2026-08-02)

## Calling / flag posture — read this before quoting any flag from this file
`platform_dial` = **TEST-MODE** (owner re-enabled 2026-07-31): `PLATFORM_DIAL_DAILY=10`, `data/platform_dial.json enabled:true limit:10` + allowlist + bot/IVR detection. Calling window + DND gates still ACTIVE on the call path. No live call fired (no_call_log). `OPENCLAW_REQUIRE_APPROVAL_FOR_AMBER=0` but prod still GREEN-only structural. Self-improve loop ALIVE (120/day cap). Revenue snapshot: MRR ₹1,999 / 1 active / 0 churn.
Label: DIRECT_HOST_VERIFIED (2026-08-02 live session probes) — re-probe container env before acting.

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
