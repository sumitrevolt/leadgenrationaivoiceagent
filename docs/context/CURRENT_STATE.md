# CURRENT_STATE - LeadGen AI (operational truth)

Evidence labels: PRODUCTION-PROVEN | CODE-PRESENT | TEST-PROVEN | LOCAL-ONLY | PARTIAL | STALE | UNKNOWN | DIRECT_HOST_VERIFIED | GIT_VERIFIED | ASSUMED
(`DIRECT_HOST_VERIFIED` = probed from the live host at a stated time; `GIT_VERIFIED` = re-derivable from this repo; `ASSUMED` = carried forward, not re-checked.)

## Last verified timestamp
2026-08-04 — direct `/health` probe = `e06687c7`. See `docs/context/SESSION_HANDOFF.md`.

## DEPLOYED 2026-08-09 — `d1b106b2` (PR #294 merged + shipped)
Prod `/health` = `{"version":"d1b106b2","environment":"production","status":"healthy"}`. All 5 app-image services on `:d1b106b2`, **zero skew**. Queues identical to the pre-deploy baseline (`celery` 0 · `dlq:failed_tasks` 0 · `dlq:dead` **8** — the 8 were already there BEFORE this deploy, do not attribute them to it). Public smoke: `/health` 200 · new `/api/clientops/video-production/daily-status` **401** (mounted + guarded) · unknown sibling route 404.
Kill-fence procedure executed as documented: backup `.env.bak-dailyvideo-20260809` → `VOICE_LAUNCH_KILL=1` → `scripts/deploy_vps.sh` → reverted to `0` → recreate → proven `0` in all 5 containers. `.env` is byte-identical to the pre-deploy backup (md5 `ec9db158d99269cc463e97923970b50f`).
**Every new flag stayed unset** (`DAILY_VIDEO_ENABLED`, `DAILY_VIDEO_CLIENTS`, `DAILY_VIDEO_ENGINE`, `CELERY_VIDEO_QUEUE`, `CREATIVE_PROVIDER_HYPERFRAMES_ENABLED`) — the producer is INERT in prod. Calling flags unchanged (`PLATFORM_DIAL_DAILY=1`, `PLATFORM_DIAL_LIMIT=100`, `DIAL_TEST_MODE=0`, `VIDEO_AD_CYCLE=1`).
Rollback ref = `3cd95ba2` (prior prod).
⚠️ **Operator error during this deploy, recorded so it is not repeated:** the fence-closing recreate was run as a bare `docker compose up -d` **without `APP_VERSION`**, so compose fell back to `${APP_VERSION:-latest}` and prod ran the `:latest` image (`266d772a…`) for ~55s before it was caught by the `/health.version` check and corrected with `APP_VERSION=d1b106b2 docker compose … up -d`. This is exactly the ADR-097 landmine. **Any manual recreate — including the one that closes the kill fence — MUST carry `APP_VERSION=<sha>`.** `deploy_vps.sh` itself was never the problem; it pinned correctly.
Label: DIRECT_HOST_VERIFIED (2026-08-09 post-deploy probes)

## Daily video — diagnosis + new producer (2026-08-09)
Prod `/health` re-probed 2026-08-09 = **`3cd95ba2`**, equal to `origin/main` (the `33651cfc` / `084cd990` values elsewhere in these docs are stale).
Owner report "daily videos not set up, advanced not running, old not running" — probed, all three had different causes:
- **Old (classic) path DOES run** but at `VIDEO_AD_INTERVAL_DAYS` unset → **5 days**, and generation landed 2026-07-22 then not again until 2026-08-06 (**15-day gap**). **Cause of the gap = a dead gate, NOT budget starvation** (an earlier draft of this entry claimed starvation — corrected per CAUSAL-CLAIM DISCIPLINE): `git log -S` shows `1664811e` (2026-08-05) taught `video_ad_cycle.enabled()` to honour the `VIDEO_DAILY_SCHEDULER_ENABLED` alias — prod had the cell flag ON while `VIDEO_AD_CYCLE` was OFF, leaving `run_cycle` fully inert. Generation resumed the next run (08-06). Corroboration: prod `delivery_ledger` holds exactly 6 `video_*` events, **all 2026-08-06** — no render was attempted or failed during 08-02..05.
- **SEPARATE live hazard (real, but not this gap's cause):** `content` exceeded its 420s `CONTENT_TIME_BUDGET_S` on **15 consecutive daily runs** (2026-07-18 → 2026-08-01, 452–530s); `_run_content_engine` drops every engine behind the overrun **silently** (no exception, no log naming it). Runs are 32–262s since 08-02 so the window is closed — but nothing recorded it, and nothing prevented a recurrence. Now instrumented (below).
- **Advanced (Creative OS / HyperFrames) never ran**, three independent reasons: `CREATIVE_PROVIDER_HYPERFRAMES_ENABLED` **unset in prod**; the Node/Chrome toolchain exists only in the opt-in `Dockerfile.video` while `docker-compose.vps.yml` builds **all** services (incl. `worker-video`) from `Dockerfile.lock`; and Creative OS had **no scheduler producer at all** (API-enqueue-only). `CELERY_VIDEO_QUEUE` also unset → render tasks use the default queue, `worker-video` idle.
- **Review pile-up:** 32/39 video records stuck `pending`, only 4 ever published — generation had no backpressure.
Shipped (ADR-166): `app/marketing/daily_video.py` — own beat job `staff-daily-video-daily` 09:45 IST (never on the `content` chain), **enqueue-only**, engine `auto|advanced|classic`, fail-closed `DAILY_VIDEO_CLIENTS` allowlist, per-client open-review backpressure, day-level idempotency, and `run_cycle` cadence-ownership deferral so the 5-day loop cannot double-generate. Missing flags (`CREATIVE_PROVIDER_HYPERFRAMES_ENABLED`, `CREATIVE_HYPERFRAMES_CANARY_TENANTS`, `CELERY_VIDEO_QUEUE`, `VIDEO_AD_INTERVAL_DAYS`) added to `AUTOMATION_FLAGS`. Admin: `GET/POST /api/clientops/video-production/daily-status|daily-run`.
**Companion fix — silent engine-skips are now observable** (this was the systemic hole behind the whole class): `automation_health.record_engine_skip()` logs *before* persisting and records every engine a mega-job drops, via the `runtime_data_authority` resolver (a hardcoded `data/...` path would land in the LEGACY location — `data/job_heartbeats.json` is a stale leftover; live automation state is under `/var/lib/leadgen/runtime/automation/`). Surfaced as `health().engine_skips`, folded into `ok`/`status` (un-run work ≠ healthy), and rendered in the "Aaj" tab in Hinglish with a fix hint. 8 dedicated tests.
⚠️ **Rollout note:** the `run_cycle` deferral is per-client, so Stage 1 (one client) leaves inline ffmpeg running for the other ~16 clients inside the budgeted chain. `DAILY_VIDEO_CLIENTS=*` (Stage 2) is what actually retires the starvation hazard — not optional polish.
**Companion fix 2 — the CUSTOMER approval backlog is now owner-visible.** `_pending_decisions()` (the `needs_decision` number on the Aaj tab) reads `approvals_bridge`, which has **zero** reference to `content_approval` — so the queue that decides whether a generated video ever reaches a customer was counted by nothing. That is how 32/39 sat `pending` (only 4 ever published) while the page said sab theek. `today_overview` now reports count + oldest-age + per-type, kept SEPARATE from `needs_decision` (owner-decides vs customer-decides). Threshold 3 items OR 3 days. 6 tests.
Enable steps (owner, staged) = `docs/runbooks/RUNBOOK_DAILY_VIDEO.md`. All flags default OFF.
**PR #294** open (branch `freebuff/daily-posting-videos-...`), 5 commits, CI green except pre-existing non-required Gate A (ruff-format vs black conflict that already fails on untouched `main` files — proof + rationale in a PR comment; owned by WS-PRF1/#248).
Label: CODE-PRESENT | TEST-PROVEN (122 targeted tests + `prod_check` PASS) | LOCAL-ONLY (not committed/deployed); diagnosis = DIRECT_HOST_VERIFIED (2026-08-09)

## Sprint goal (LOCKED)
**GTM 0→1** — pehle paid customers on Marketing product; mid-funnel bottleneck (Hot Queue `/app/inbox` + dialer sprint); 2nd paying customer target.

## Production SHA
`33651cfc` — merge of PR #236 (interested-reply offer footer: canonical UPI resolver + NPCI deep-link, no amount prefill). Deployed 2026-08-04 via `scripts/deploy_vps.sh` under the `VOICE_LAUNCH_KILL=1` fence; `/health` = `{"version":"33651cfc","environment":"production","status":"healthy"}`.
5/5 app-image services equal (`app`/`worker`/`scheduler`/`worker-heavy`/`worker-video`), all healthy; celery + `dlq:failed_tasks` + `dlq:dead` = 0; `.env` restored byte-identical to pre-deploy backup (md5 `1bb0dac0f6d522d130f9843cfa8e2625`, backup `.env.bak-upifooter-20260804`); `VOICE_LAUNCH_KILL=0` restored in all 5 containers.
Rollback reference: `e06687c7` (prior) / `33651cfc` current.
Label: DIRECT_HOST_VERIFIED (2026-08-04) + GIT_VERIFIED.

## ⚠️ UPI auto-activate — documentation drift found 2026-08-04
Docs (this file, CLAUDE.md, AGENTS.md) recorded `UPI_AUTO_ACTIVATE=0` as the 2026-07-18 containment state. **Prod `.env` actually has `UPI_AUTO_ACTIVATE=1`.**
Containment is still effective — the master flag alone is never enough (`upi_payments.auto_activate_clients_allowed`): `UPI_AUTO_ACTIVATE_CLIENTS` holds exactly **one** client id, and both a random client and an empty client id are refused (probed). So this is ARMED-but-scoped, not open auto-activation.
Not changed by this session — flipping it is an owner money decision. Recorded so the next agent does not quote `=0` from docs.
Label: DIRECT_HOST_VERIFIED (2026-08-04 in-container probe)

## Origin/main
`33651cf` — **EQUAL to production** (`git fetch origin && git rev-parse origin/main`). Prod holds zero commits main lacks.
Open PRs: **#238** (this docs-only truth refresh). Open issues: **#237** (`tests` workflow red on main — pydantic-core drift).
Label: GIT_VERIFIED (2026-08-04)

## Production health
`status: healthy`, `environment: production` at `e06687c7` (2026-08-04, direct HTTPS).
Label: DIRECT_HOST_VERIFIED (2026-08-04)

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
ADR-164 adds a complete per-agent enterprise profile: agent+tenant-isolated memory/KB namespaces, eight common SaaS controls, role competencies and existing runtime governance. ADR-165 derives Boss → 7 domain teams → 30 workers from the canonical Office map, giving **31/31 coordination coverage** and visible mission assignments, handoffs and Boss verdicts in Owner OS/Coordination Hub. Coordination-ready remains setup truth: runtime is still **12 canary-ready / 17 rollout-hold / 2 intentionally disabled**; `AGENT_MATURITY_CONTEXT` and Coordination Hub flags default OFF.
Label: CODE-PRESENT | TEST-PROVEN | LOCAL-ONLY (not committed/deployed)

## Paying customers
1 - Jiya Makeover (`jiya-makeover`). MRR ₹1,999. Estique autopilot prospect `converted` (see WS-2 in ACTIVE_WORK).

## Admin manual customer call
`/app/admin` now has a prominent owner-only single-call form (phone + `ai_marketing` pitch + explicit transactional/promotional relation + confirmation). It reuses canonical `POST /api/telephony/vobiz/stream-call`; no second dialer route, no automatic retry, 60s same-number UI cooldown. Compliance remains backend fail-closed. Local evidence: 22 manual-call/Vobiz tests + 19 admin-nav tests green, `prod_check.py` PASS.
Label: CODE-PRESENT | TEST-PROVEN | LOCAL-ONLY (not committed/deployed)

## Top next actions
1. Review/commit/deploy admin manual-call slice only when owner asks; then admin-login canary.
2. GTM Hot Queue `/app/inbox` → 2nd paying Marketing customer.
3. Feed sales_autopilot new non-converted prospects (or accept idle until new leads).
