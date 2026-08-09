# SESSION_HANDOFF

## Last session — 2026-08-09: daily video producer (ADR-166)

**Prod probed live:** `/health` = `3cd95ba2`, equal to `origin/main`. Any `33651cfc` / `084cd990`
still quoted in other context docs is stale — re-probe before asserting a SHA.

**What the owner reported:** "daily posting videos not a proper setup; advanced videos not running;
old setup not running either." All three had *different* causes — verified on the host, not assumed:

1. Classic path was running, but on a **5-day** interval (`VIDEO_AD_INTERVAL_DAYS` unset) **and**
   silently budget-skipped inside the `content` mega-job → real 15-day generation gap (2026-07-22
   → 2026-08-06). `_run_content_engine` swallows budget exhaustion with no log naming the engine.
2. Advanced path never ran: `CREATIVE_PROVIDER_HYPERFRAMES_ENABLED` unset, Node/Chrome toolchain
   only in the un-applied `Dockerfile.video` image, and **no scheduler producer existed at all**.
3. 32/39 records stuck at `pending` review with no backpressure on generation.

**Shipped (local only, flags OFF):** `app/marketing/daily_video.py` + own beat job
`staff-daily-video-daily` (09:45 IST) + `daily_video_client_task` on the video queue + admin
`daily-status`/`daily-run` + `run_cycle` cadence-ownership deferral + 4 missing flags registered.
122 targeted tests green, `prod_check.py` PASS, `check_secrets.py` clean, ruff clean on changed files.

**Next agent, start here:**
- Owner action = Stage 1 of `docs/runbooks/RUNBOOK_DAILY_VIDEO.md`. Nothing is deployed.
- The advanced engine needs an **image build + compose overlay + `CELERY_VIDEO_QUEUE=1`**, not a
  flag flip. Do not promise "advanced is on" from a flag alone.
- Clearing the 32 pending reviews is a prerequisite — `DAILY_VIDEO_MAX_PENDING=2` will correctly
  refuse to generate for a backlogged client.
- Do **not** change `packages.py` to say "daily" until a week of delivery is evidenced; if you do,
  `tests/test_billing_truth_2026.py` moves in the same commit.
- Housekeeping: `POSTIZ_API_KEY` was visible in a plain `printenv` grep during this session's
  read-only prod probe. Value not recorded anywhere in the repo, but consider rotating it and
  filtering secrets out of future env probes.
