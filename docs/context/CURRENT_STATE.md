# CURRENT_STATE - LeadGen AI (operational truth)

Evidence labels: PRODUCTION-PROVEN | CODE-PRESENT | TEST-PROVEN | LOCAL-ONLY | PARTIAL | STALE | UNKNOWN | DIRECT_HOST_VERIFIED | GIT_VERIFIED | ASSUMED
(`DIRECT_HOST_VERIFIED` = probed from the live host at a stated time; `GIT_VERIFIED` = re-derivable from this repo; `ASSUMED` = carried forward, not re-checked.)

## Last verified timestamp
2026-08-14 — prod `/health` = `150bf898` (PR #356 AUTH-DEPLOY). ADR-180 INERT (`HARNESS_SESSION_EVENTS` UNSET). Kill fence closed (VLK=FALSE_TOKEN in all 5). Revenue GO unchanged (`ready_for_first_paid_customer=true`, `blocker_count=0`).

## DEPLOYED 2026-08-14 — `150bf898` (PR #356 hygiene + ADR-180)
**Prod `/health` = `150bf898`** twice after kill-restore (DIRECT_HOST_VERIFIED 2026-08-14 04:16Z / 04:17Z): `healthy` · `environment:production`. Merge tip is `150bf898` from feature head `e5feaa6e` (UP045); old wait SHA `8fa39c84` is ancestor only. Ships hygiene archive + ADR-180 SessionEvent (INERT) + prior undeployed main (#353/#352/#327 ancestry).
Kill-fence: backup `.env.bak-killfence-20260814035416` → VLK TRUE for `deploy_vps.sh` → `DEPLOYED 150bf898 OK` (BUILD_RC=0 UP_RC=0 5/5 skew-zero smoke 200) → VLK=0 + recreate with `APP_VERSION=150bf898` → 5/5 VLK=FALSE_TOKEN · HSE=UNSET · APP_VERSION_MATCH=1. Rollback = `2326c931`.
Label: DIRECT_HOST_VERIFIED (2026-08-14)
**#307:** stays OPEN; dunning stays OFF. **#304:** guest bind CODE-LIVE (PR #320 `a3fbc8bb`).

## SUPERSEDED — DEPLOYED 2026-08-13/14 — `2326c931` (PR #327 mypy land)
> Historical. Replaced by `150bf898` above. Keep as rollback tag.
**Prod `/health` was `2326c931`** (DIRECT_HOST_VERIFIED 2026-08-14 pre-deploy). Includes PR #327 and ancestry of `9c47647c`.
Label: DIRECT_HOST_VERIFIED (2026-08-14) — SUPERSEDED by `150bf898`

## SUPERSEDED — DEPLOYED 2026-08-12 (estimated) — `9c47647c` (PR #332 ADR-177 batch)
> Historical. Replaced by `2326c931` above.
`origin/main` tip = `23ea2d46` (includes #333 staff-bus, #334/#335 docs). **Prod `/health` = `9c47647c`** (DIRECT_HOST_VERIFIED 2026-08-12 07:39 UTC). Deploy timestamp estimated ~2026-08-11 22:05 UTC (uptime 9h 33m backtrack). Includes: PR #332 (ADR-177 GSC + funnel + referral + triage), PR #330 (Boss governance), PR #329 (rollback retention).
Label: DIRECT_HOST_VERIFIED (2026-08-12) — SUPERSEDED by `2326c931`

## SUPERSEDED — DEPLOYED 2026-08-11 — `9b09a808` (PR #321)
> Historical. Replaced by `9c47647c` above.
Prod `/health` = `{"version":"9b09a808","environment":"production","status":"healthy"}` (DIRECT_HOST_VERIFIED 2026-08-11; two probes with unique `cb=` — timestamp/uptime advanced). Exact SHA = `9b09a80825389983829b1c0b4de6caf3789d16bf`.
**#304 / #306:** still WAIT live proofs. **#307:** dunning OFF.
Label: DIRECT_HOST_VERIFIED (2026-08-11)

## SUPERSEDED — DEPLOYED 2026-08-10 — `a3fbc8bb`
> Historical. Replaced as prod tip by later deploys; do not quote as current without re-probe.
Rollback ref chain includes `76348926`.
Label: STALE vs 2026-08-11 prod

## SUPERSEDED — DEPLOYED 2026-08-09 — `d1b106b2` (PR #294)
> Historical only. Do not quote as current. Replaced by `a3fbc8bb` above.

Prod `/health` was `{"version":"d1b106b2","environment":"production","status":"healthy"}`. All 5 app-image services on `:d1b106b2`, **zero skew**. Queues identical to the pre-deploy baseline (`celery` 0 · `dlq:failed_tasks` 0 · `dlq:dead` **8** — the 8 were already there BEFORE this deploy, do not attribute them to it). Public smoke: `/health` 200 · new `/api/clientops/video-production/daily-status` **401** (mounted + guarded) · unknown sibling route 404.
Kill-fence procedure executed as documented: backup `.env.bak-dailyvideo-20260809` → `VOICE_LAUNCH_KILL=1` → `scripts/deploy_vps.sh` → reverted to `0` → recreate → proven `0` in all 5 containers. `.env` is byte-identical to the pre-deploy backup (md5 `ec9db158d99269cc463e97923970b50f`).
**Every new flag stayed unset** (`DAILY_VIDEO_ENABLED`, `DAILY_VIDEO_CLIENTS`, `DAILY_VIDEO_ENGINE`, `CELERY_VIDEO_QUEUE`, `CREATIVE_PROVIDER_HYPERFRAMES_ENABLED`) — the producer is INERT in prod. Calling flags unchanged (`PLATFORM_DIAL_DAILY=1`, `PLATFORM_DIAL_LIMIT=100`, `DIAL_TEST_MODE=0`, `VIDEO_AD_CYCLE=1`).
Rollback ref = `3cd95ba2` (prior prod).
⚠️ **Operator error during this deploy, recorded so it is not repeated:** the fence-closing recreate was run as a bare `docker compose up -d` **without `APP_VERSION`**, so compose fell back to `${APP_VERSION:-latest}` and prod ran the `:latest` image (`266d772a…`) for ~55s before it was caught by the `/health.version` check and corrected with `APP_VERSION=d1b106b2 docker compose … up -d`. This is exactly the ADR-097 landmine. **Any manual recreate — including the one that closes the kill fence — MUST carry `APP_VERSION=<sha>`.** `deploy_vps.sh` itself was never the problem; it pinned correctly.
Label: DIRECT_HOST_VERIFIED (2026-08-09 post-deploy probes) — STALE vs current tip

## Approval backlog — real numbers + retirement tool (2026-08-09, PR #297)
"32 stuck approvals" was only the `video_ad` slice. Real queue = **422** `content_approval` pendings: **321** belong to client ids ABSENT from `clients_store` (8 dead ids — un-actionable forever), **101** belong to the 3 live clients (`leadgenai-self` 53 · `0511a69b900e` 28 · `jiya-makeover` 20).
**The 101 are NOT technically stuck.** `token_is_expired` is consulted in exactly ONE place (`approval_principal.from_approval_token` = the public emailed link); the authenticated dashboard resolves by id and never checks it, and the customer video path is fully wired (`customer_dashboard.py` → `from_customer_session` → `approval_saga`, UI supplies `expected_content_sha256`). Customers can complete them today.
**Why they don't:** the mail is announced once per item (`idempotency_key`) and says "You have content awaiting your approval" — singular, no count, no age. Prod `approval_notifications`: **36 mails sent to jiya-makeover 2026-07-14→08-09, all `sent`, zero failures**, 20 still open. Delivery was never the problem.
Shipped: `content_approval.retire_orphaned_pending()` (orphans only · append-only terminal `expired` · `dry_run=True` default · fail-CLOSED if the live-client set can't resolve · retiring ≠ approving) + queue-aware reminder wording (no extra sends). **Sweep NOT yet run against prod** — dry-run reported scanned 422 / would-retire 321 / skipped-live 101, nothing written.
⚠️ Backpressure check: `daily_video.open_review_count` counts `video_ad_cycle`, NOT `content_approval` — measured on prod jiya=1, Kamal dar=1, leadgenai-self=4 against `DAILY_VIDEO_MAX_PENDING=2`. So the paying customer is **not** blocked by this backlog; only own-brand would be.
Label: DIRECT_HOST_VERIFIED (2026-08-09) | CODE-PRESENT (PR #297, not deployed)

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

## Production SHA — SUPERSEDED (historical, 2026-08-06)
> Current prod SHA lives in the `DEPLOYED 2026-08-09 — d1b106b2` section above. Everything in this
> section is the 2026-08-06 reading, kept only because the probe-discipline note below was learned
> here. Do **not** quote `b5fc2dea` as current.

`b5fc2dea` — was exact parity with `origin/main` as fetched on 2026-08-06.
`/health` = `{"status":"healthy","version":"b5fc2dea","environment":"production"}` (direct HTTPS, 2026-08-06 10:56 UTC, uptime 2h 35m).

**Prod and `origin/main` were in exact SHA parity ON 2026-08-06.** The `31169c78..b5fc2dea` delta was deployed by another authorized operator/session; this checkout did not perform that deployment.

**It was NOT deployed "since" the earlier report — it was already live when that report was written.** Uptime arithmetic: at 11:03:02 UTC uptime was `2h 42m 38s`, so the `b5fc2dea` container started ≈ **08:20 UTC**. The session that claimed "prod is 10 commits behind" did its work from ≈10:10 UTC — about **1.8 hours after** `b5fc2dea` was already serving. That claim was **false when asserted**, not overtaken by events. Root cause in the note below.
Previous deployed rollback reference: `31169c78` (confirm the canonical deploy rollback state on-host before using it).
Label: DIRECT_HOST_VERIFIED (2026-08-06) + GIT_VERIFIED (2026-08-06).

> **Correction chain:** this file has recorded prod as `33651cfc` → `31169c78` → `b5fc2dea` (2026-08-06) → `3cd95ba2` → `d1b106b2` (2026-08-09, current). Every one of those was "fresh truth" when written. Re-probe `/health` before quoting any SHA.

> 🚨 **HOW TO PROBE `/health` — the 2026-08-06 cached-probe trap.**
> An agent probed `/health` once via a fetch tool, got `31169c78`, and propagated "prod is 10 commits behind" into three context docs. The payload was **~6.5 hours stale**: it carried `timestamp` `03:37:42Z` and `uptime 1h 6m 28s` (a container started 02:31Z) while the wall clock was ≈10:10Z and the real container had been up since 08:20Z. A later identical fetch returned the **byte-identical** body — same timestamp, same uptime — which is the tell.
> **The origin is ruled out.** It correctly serves `cache-control: no-store, no-cache, must-revalidate, max-age=0` (header-verified 2026-08-06), and `curl` against the same origin returned live, advancing values. The stale copy therefore entered somewhere in the **fetch path** used by that probe. **Which component cached was never instrumented**, so no specific implementation is named here — asserting one would repeat the same unevidenced-cause mistake this note exists to prevent.
> **Rule:** probe with `curl` and a unique cache-buster —
> `curl -sS -H 'Cache-Control: no-cache' "https://leadsgenai.in/health?cb=$(date +%s)"`
> — and **sanity-check `timestamp`/`uptime` against the wall clock before believing `version`**. Two probes returning an identical `timestamp` means you are reading a cache, not production. One probe is never evidence.

## ⚠️ UPI auto-activate — documentation drift corrected 2026-08-12
Docs (CURRENT_STATE, CLAUDE.md, AGENTS.md) recorded `UPI_AUTO_ACTIVATE=0` as the 2026-07-18 containment state. **Prod `.env` actually has `UPI_AUTO_ACTIVATE=1`.** (Re-verified 2026-08-12 revenue audit.)
Containment is still effective — the master flag alone is never enough (`upi_payments.auto_activate_clients_allowed`): `UPI_AUTO_ACTIVATE_CLIENTS` holds exactly **one** client id, and both a random client and an empty client id are refused (probed). So this is ARMED-but-scoped, not open auto-activation.
Not changed by this session — flipping it is an owner money decision. Recorded so the next agent does not quote `=0` from docs.
Label: DIRECT_HOST_VERIFIED (2026-08-04 in-container probe + 2026-08-12 revenue audit)

## Origin/main — SUPERSEDED (historical, 2026-08-06)
`b5fc2dea` — was exact parity with production (`git fetch origin`, `git rev-parse origin/main`, and direct HTTPS `/health`, 2026-08-06). `origin/main` has since advanced well past this; re-derive it, do not quote this line.
Open issues: **#237** (`tests` workflow red on main — pydantic-core drift; `07bafd40` added a non-failing diagnostic, root cause still open).
Label: GIT_VERIFIED (2026-08-06, STALE)

## Production health — SUPERSEDED (historical, 2026-08-06)
`status: healthy`, `environment: production` at `b5fc2dea` (2026-08-06 10:56 UTC, direct HTTPS).
Public funnel smoke **re-run on deployed `b5fc2dea`** (2026-08-06 11:04 UTC, cache-busted `curl`): `/` `/pricing` `/start` `/audit` `/site-audit` `/demo` `/privacy` `/health/ready` — all **200**, with `/health` re-confirming `b5fc2dea` immediately after the sweep. (An earlier identical 8/8 sweep was recorded against `31169c78`; that reading is now superseded, see the cached-probe note above.)
Label: DIRECT_HOST_VERIFIED (2026-08-06)

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
