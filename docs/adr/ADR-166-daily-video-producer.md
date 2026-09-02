# ADR-166 — Daily video producer (dedicated job, enqueue-only, engine-selecting)

- **Date:** 2026-08-09
- **Status:** Accepted (code CODE-PRESENT / TEST-PROVEN / LOCAL-ONLY — flags default OFF, not deployed)
- **Supersedes nothing.** Extends ADR-143 (Creative Automation OS) and the Video Production Cell.

## Context — what was actually broken (measured, not assumed)

Owner report: "daily posting videos are not a proper setup; the advanced videos we set up are not
running and the old setup is not running either."

Probed on the live host 2026-08-09 (prod `/health` = `3cd95ba2`, equal to `origin/main`):

| Claim | Reality found |
|---|---|
| Old setup not running | It *does* run now — `VIDEO_AD_CYCLE=1` and `VIDEO_DAILY_SCHEDULER_ENABLED=1`; real renders exist (`data/reels/*.mp4`, 39 records). But cadence is `VIDEO_AD_INTERVAL_DAYS` **unset → 5 days**, and generation landed 2026-07-22 then not again until 2026-08-06 — a **15-day gap**. Cause established below. |
| Advanced videos not running | Correct, for three independent reasons: (1) `CREATIVE_PROVIDER_HYPERFRAMES_ENABLED` is **not set in prod** → the provider is off; (2) the HyperFrames Node/Chrome toolchain only exists in the opt-in `Dockerfile.video` image, and `docker-compose.vps.yml` builds **every** service — `worker-video` included — from `Dockerfile.lock`; (3) Creative OS has **no scheduler producer at all** — it is API-enqueue-only, so nothing ever created a daily creative. |
| Not a proper setup | 32 of 39 video records sit at `pending` customer review; only 4 were ever published. Generation had **no backpressure** against that pile. |

### Cause of the 15-day gap — two separate findings, deliberately not conflated

An earlier draft of this ADR blamed budget starvation for the gap. That was an unproven causal
leap of the same shape as the retracted ADR-097 claim (CLAUDE.md §7 CAUSAL-CLAIM DISCIPLINE), and
the evidence does not support it. Corrected:

**(a) The gap itself — the `enabled()` gate, not the budget.** `git log -S` shows commit
`1664811e` (2026-08-05) changed `video_ad_cycle.enabled()` to honour the
`VIDEO_DAILY_SCHEDULER_ENABLED` alias: prod had the Video Production Cell flag ON while
`VIDEO_AD_CYCLE` was OFF, which left `run_cycle` **fully inert**. Generation resumed on the very
next daily run, **2026-08-06**. Corroborating evidence: the `delivery_ledger` on prod holds
exactly **6** `video_*` events, **all dated 2026-08-06** — no `video_render_started` and no
`video_render_failed` anywhere in the 2026-08-02..05 window, so the renderer was never entered.
The gap was a dead gate, not a starved or failing renderer.

**(b) A separate, still-invisible hazard — budget starvation is real and unrecorded.**
`video_ad_cycle.run_cycle()` is the **second** engine in the `content` mega-job, behind
`auto_content.run_daily_content()`, under a shared `CONTENT_TIME_BUDGET_S` (default 420s).
`team_scheduler._run_content_engine` closes the coroutine and returns `False` on exhaustion —
**no exception, no log naming the engine**. Prod `job_runs` proves the mechanism trips in practice:
`content` exceeded 420s on **15 consecutive daily runs**, 2026-07-18 → 2026-08-01 (452–530s each).
It has run 32–262s since 2026-08-02, so the window is currently closed — but nothing prevents it
reopening, and nothing would record it if it did. This is what ADR-166's companion change makes
observable (`automation_health.record_engine_skip`).

Both findings independently justify moving video generation out of the `content` chain: (a) says
the video path needs its own gate and cadence, (b) says anything doing inline ffmpeg inside a
budgeted chain is both a starvation victim and a starvation *cause* for the ~10 engines behind it.

`CELERY_VIDEO_QUEUE` is also unset in prod, so video render tasks land on the default `celery`
queue and the dedicated `worker-video` container sits idle.

## Decision

1. **A dedicated daily producer with its own beat entry** — `app/marketing/daily_video.py`,
   staff job `daily_video`, beat `staff-daily-video-daily` at **09:45 IST**. It is NOT another
   engine on the `content` chain; that is precisely the failure mode being fixed.
2. **The producer never renders.** It only enqueues (`daily_video_client_task` → video queue, or
   `creative_os.service.enqueue_generate` → video queue). A light producer cannot be budget-starved
   and cannot block the beat.
3. **Engine selection (`DAILY_VIDEO_ENGINE`, default `auto`).** `advanced` = Creative OS +
   HyperFrames; `classic` = the proven deterministic ffmpeg path. `auto` picks advanced when the
   gate allows *and* the tenant's recent advanced attempts are not all failing, otherwise classic.
   Rationale: `hyperframes` is in `providers.NO_SILENT_FALLBACK`, so a missing render toolchain
   produces **zero** videos rather than a downgraded one. `auto` is the safety net that keeps the
   customer supplied while the toolchain image is not deployed.
4. **Fail-closed tenant allowlist.** `DAILY_VIDEO_CLIENTS` empty = **no client**. An unset allowlist
   meaning "everyone" is how a canary becomes a fleet-wide daily render storm (same rule as
   `hyperframes_provider.tenant_allowed`). `*` = all eligible.
5. **Review backpressure.** `DAILY_VIDEO_MAX_PENDING` (default 2) counts open reviews across BOTH
   pipelines (`video_ad_cycle` pending + Creative OS `queued|generating|approval_pending|qa_failed`)
   and stops generating for that client. Daily cadence must not grow the stuck-review pile faster.
6. **Cadence ownership.** When the daily producer owns a client, `video_ad_cycle.run_cycle()` skips
   *generation* for it (`deferred_to_daily_video` in the result) while still running regen, publish
   and stuck-row repair for everyone. Without this a client gets two videos every 5th day.
   **Consequence for rollout:** the deferral is per-client, so at Stage 1
   (`DAILY_VIDEO_CLIENTS=jiya-makeover`) `run_cycle` still performs inline ffmpeg for the other
   ~16 eligible clients inside the budgeted chain. Moving to `DAILY_VIDEO_CLIENTS=*` is therefore
   **not** cosmetic widening — it is the step that actually removes heavy renders from the
   `content` budget and retires hazard (b). The runbook says this explicitly.
7. **Budget skips become observable (companion change).** `automation_health.record_engine_skip`
   logs (before persisting, so a storage failure cannot re-swallow the signal) and records every
   engine a mega-job drops, resolved through `runtime_data_authority` like its `job_runs` siblings —
   a hardcoded `data/...` path would write to the legacy location and be invisible in prod, the
   exact trap a stale `data/job_heartbeats.json` set during this audit. Surfaced as
   `health().engine_skips`, counted into `ok`/`status` (un-run work is not "healthy"), and rendered
   in the owner-facing "Aaj" tab in Hinglish with an actionable fix.
8. **The CUSTOMER approval backlog becomes an owner-facing problem.** Generation is only half the
   delivery: a video the customer never approves is never delivered. Nothing on the owner's "Aaj"
   page counted that queue — `_pending_decisions()` reads `approvals_bridge`, which contains **no
   reference to `content_approval` at all** — which is how 32 of 39 records sat `pending` with only
   4 ever published while the page reported no problem. `today_overview` now reports count, oldest
   age and per-type breakdown, with the two queues kept deliberately separate
   (`needs_decision` = what the OWNER must decide; `customer_approvals_pending` = what the CUSTOMER
   has not). Threshold is 3 items **or** 3 days, so normal same-day review stays quiet while a
   single item ignored for days still surfaces — that is the shape the 32-pile started as. This
   also prevents the backpressure in decision 5 from *looking* like "the daily video stopped
   working" when it is in fact correctly refusing a backlogged client.
9. **Every new store resolves through `runtime_data_authority`, none are born as legacy debt.**
   The producer's day-state and advanced-block files, and the budget-skip ledger, are all
   *resolvers* called at I/O time — not module constants frozen to `data/...` at import. The repo's
   runtime-data ratchet (`scripts/runtime_data_path_scan.py ratchet`, MUST-PASS in CI) caught the
   first draft of this module doing exactly that and failed the build, which is the correct
   outcome: `data/` is the LEGACY root, live automation state lives under the runtime root, and a
   store written to the wrong one is invisible in prod — the same trap a stale
   `data/job_heartbeats.json` set during this audit.
10. **Day-level idempotency, twice.** Producer day-state store plus a Celery
   `task_id = daily_video:{client_id}:{YYYY-MM-DD}` behind `@idempotent_task` (20h TTL). A failed
   enqueue does **not** mark the day — it stays retryable on the next tick.
11. **Operator visibility.** `GET /api/clientops/video-production/daily-status` answers "why is the
   daily video not running" in one call (flags, allowlist, per-client engine + reason + open-review
   count + last generated). `POST .../daily-run` fires one pass manually (safe from the web process
   precisely because the producer does not render). `daily_video` is registered in `STAFF_JOBS`,
   `JOB_META`, `_last_ran`, `JOB_INFO` and `automation_health.EXPECTED_GAP_MIN` (dead-man).
12. **Permanent advanced refusals are parked, not retried.** `enqueue_generate` calls
   `record_attempt()` *before* dispatch, so a brief that fails `resolve_brief`
   (`needs_customer_input` / `blocked` — e.g. missing offer or unverified brand fact) would be
   retried every single day, burning `CREATIVE_TENANT_DAILY_BUDGET` on records that never render,
   while the operator saw `engine: "advanced"` and simply no video. The producer now classifies the
   refusal: permanent ones park the tenant in `data/.daily_video_advanced_block.json` (surfaced in
   `advanced_gate` and `status().clients[].advanced_block`), and under `auto` it immediately ships
   today's video via classic so the customer is not left empty-handed. Transient refusals
   (`tenant_budget_exceeded`, `enqueue_failed`) deliberately do NOT park. Blocks auto-expire after
   `DAILY_VIDEO_ADVANCED_BLOCK_DAYS` (default 7) and can be cleared via
   `POST /api/clientops/video-production/daily-clear-block`. Under `DAILY_VIDEO_ENGINE=advanced`
   the block is still recorded but there is **no** classic fallback — strict mode means advanced
   or nothing.
13. **Flag registry gap closed.** `CREATIVE_PROVIDER_HYPERFRAMES_ENABLED`,
   `CREATIVE_HYPERFRAMES_CANARY_TENANTS`, `CREATIVE_HYPERFRAMES_DEFAULT_TEMPLATE`,
   `CELERY_VIDEO_QUEUE` and `VIDEO_AD_INTERVAL_DAYS` were **missing** from `AUTOMATION_FLAGS`, so
   `/api/growth/infra/flags` reported Creative OS healthy while its only enterprise-grade provider
   was unset. All are registered now.

## Consequences

- Every flag defaults OFF; with no flags set nothing changes. Rollback = `DAILY_VIDEO_ENABLED=0`
  + recreate → the module is inert and `run_cycle` resumes its own cadence automatically.
- **The advanced path still needs infrastructure the code cannot supply**: the `Dockerfile.video`
  image must be built at the deployed SHA and `deploy/compose/docker-compose.video.yml` applied,
  plus `CELERY_VIDEO_QUEUE=1`. Until then `auto` intentionally serves classic videos. See
  `docs/runbooks/RUNBOOK_DAILY_VIDEO.md`.
- **Product promise not changed here.** `app/marketing/packages.py` still says "AI video ads
  (Reels/Shorts)" without a cadence. Copy should be upgraded to "daily" only after the flag is on
  and a week of delivery is evidenced — promising daily before delivering it is worse than the gap.
- The 32 already-pending reviews are not auto-resolved. Backpressure stops the pile growing; the
  owner still has to clear it (existing approve/request-changes surfaces).

## Alternatives rejected

- **`VIDEO_AD_INTERVAL_DAYS=1` alone.** One env flip, but keeps the producer inside the starvable
  `content` chain, adds no backpressure, and does nothing for the advanced path. It would have
  produced a daily *intent* with the same silent gaps.
- **Appending another engine to the `content` chain.** Recreates the exact defect.
- **Forcing deterministic fallback when HyperFrames fails.** Would violate
  `NO_SILENT_FALLBACK`, which exists so an enterprise deliverable cannot silently degrade. The
  `auto` streak-based downgrade is explicit, bounded and reported instead.
