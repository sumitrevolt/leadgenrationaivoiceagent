# RUNBOOK — Daily video for marketing customers

Companion to `docs/adr/ADR-166-daily-video-producer.md`. Owner-applied; nothing here is
auto-deployed. All flags default OFF, so an un-run runbook changes nothing.

---

## 0. Where it stands before you start (measured 2026-08-09, prod `3cd95ba2`)

| Thing | State |
|---|---|
| `VIDEO_AD_CYCLE` / `VIDEO_DAILY_SCHEDULER_ENABLED` | `1` / `1` — the classic loop is ON |
| Cadence | `VIDEO_AD_INTERVAL_DAYS` unset → **5 days**, and it was silently skipped for 15 days |
| `CREATIVE_OS_ENABLED` | `1` |
| `CREATIVE_PROVIDER_HYPERFRAMES_ENABLED` | **unset → advanced provider OFF** |
| HyperFrames toolchain (Node + Chrome) | **not in the running image** — lives only in the opt-in `Dockerfile.video` |
| `CELERY_VIDEO_QUEUE` | unset → video tasks use the default queue; `worker-video` is idle |
| Review backlog | 32 of 39 records stuck at `pending` |
| `DAILY_VIDEO_ENABLED` | unset → new producer inert |

---

## Stage 1 — Turn on daily video, classic engine, ONE customer (do this first)

Classic = the proven deterministic ffmpeg path. It needs **no new image and no new infra**.

1. Backup: `cp /opt/leadgen/.env /opt/leadgen/.env.bak-dailyvideo-$(date +%Y%m%d%H%M%S)`
2. Add to `/opt/leadgen/.env` (no inline comments — pydantic does not strip them):

   ```
   DAILY_VIDEO_ENABLED=1
   DAILY_VIDEO_CLIENTS=jiya-makeover
   DAILY_VIDEO_ENGINE=classic
   DAILY_VIDEO_MAX_PENDING=2
   DAILY_VIDEO_MAX_PER_RUN=10
   ```

3. Recreate the containers that read it (`restart` does NOT reload env).
   **`APP_VERSION` is mandatory** — a bare `docker compose up -d` falls back to
   `${APP_VERSION:-latest}` and silently moves prod onto the `:latest` image. That happened
   during the 2026-08-09 deploy (~55s on an unknown build before `/health.version` caught it),
   so it is written here rather than left to memory:

   ```
   cd /opt/leadgen
   APP_VERSION=$(curl -fsS http://127.0.0.1:8000/health | sed 's/.*"version":"\([^"]*\)".*/\1/') \
     docker compose -f docker-compose.vps.yml --profile celery \
     up -d --no-deps app worker scheduler
   ```

   Then re-check `/health.version` is unchanged. If it moved, you just deployed something else.

4. Verify the flag actually landed: `docker exec leadgen_scheduler printenv DAILY_VIDEO_ENABLED`
5. Verify the producer's own view (admin token required):

   ```
   GET /api/clientops/video-production/daily-status
   ```

   Expect `enabled: true`, `allowlist: ["jiya-makeover"]`, and for that client
   `engine: "classic"` with `engine_reason` naming why advanced is unavailable.
6. Fire one pass without waiting for 09:45: `POST /api/clientops/video-production/daily-run`
7. Confirm a new record appears: `GET /api/clientops/video-ads?client_id=jiya-makeover`

**Backpressure note:** with `DAILY_VIDEO_MAX_PENDING=2`, a client already sitting on 2+ unapproved
videos is skipped with `reason: pending_review_backlog`. That is intended. Clear the backlog through
the normal approve / request-changes surfaces first, or the daily producer will correctly refuse.

**Rollback:** `DAILY_VIDEO_ENABLED=0` + the same recreate. The module goes inert and
`video_ad_cycle.run_cycle()` resumes its own cadence for that client with no further action.

---

## Stage 2 — Widen to every marketing customer (NOT optional polish)

Only after Stage 1 has delivered for a few days and the review loop is keeping up:

```
DAILY_VIDEO_CLIENTS=*
```

`*` means every **active marketing/combo** client (voice-only clients are excluded by
`video_ad_cycle._eligible_clients`). Keep `DAILY_VIDEO_MAX_PER_RUN` sane — each enqueue is a real
ffmpeg render on the worker.

**Why this stage actually matters.** The `run_cycle` deferral is **per-client**: it only stops the
old 5-day loop for clients in `DAILY_VIDEO_CLIENTS`. At Stage 1 that is one client, so `run_cycle`
still does inline ffmpeg for the other ~16 eligible clients **inside** the budgeted `content`
chain — i.e. the starvation mechanism that put `content` over its 420s budget on 15 consecutive
days (2026-07-18 → 2026-08-01) is still live. Stage 2 is the step that finally moves heavy renders
out of that chain and onto the video queue. Treat it as part of the fix, not a nice-to-have.

After Stage 2, watch `GET /api/growth/infra/automation-health` → `engine_skips`. It should stay at
`total: 0`. Any non-zero value names the exact engines a mega-job dropped.

---

## Stage 3 — Enable the ADVANCED (HyperFrames) engine

This is the part that is **not** a flag flip. The Node + pinned Chrome toolchain is not in the
running image; it is only in `Dockerfile.video`, which `docker-compose.vps.yml` does not use.

1. Build the video image **at the deployed SHA** (the tag must match `APP_VERSION` or the deploy
   skew check fails):

   ```
   docker build -f Dockerfile.video \
     --build-arg APP_IMAGE=ghcr.io/sumitrevolt/leadgenrationaivoiceagent:$SHA \
     -t ghcr.io/sumitrevolt/leadgenrationaivoiceagent-video:$SHA .
   ```

2. Apply the overlay so `worker-video` uses it:

   ```
   docker compose -f docker-compose.vps.yml -f deploy/compose/docker-compose.video.yml \
     --profile celery up -d --no-deps worker-video
   ```

3. Route render tasks to that worker — **without this the tasks go to the default queue and the
   video worker stays idle**:

   ```
   CELERY_VIDEO_QUEUE=1
   ```

4. Turn the provider on, canary-scoped:

   ```
   CREATIVE_PROVIDER_HYPERFRAMES_ENABLED=1
   CREATIVE_HYPERFRAMES_CANARY_TENANTS=jiya-makeover
   DAILY_VIDEO_ENGINE=auto
   ```

5. Recreate `app worker scheduler worker-video`, then re-check
   `GET /api/clientops/video-production/daily-status` — the canary tenant should now read
   `engine: "advanced"`, `advanced_gate_ok: true`.

**Why `auto` and not `advanced`:** `hyperframes` is in `providers.NO_SILENT_FALLBACK` — if the
toolchain is missing or the render fails, the creative **fails**, it does not quietly downgrade.
Under `auto`, after `DAILY_VIDEO_ADVANCED_FAIL_WINDOW` (default 2) consecutive advanced failures
the producer downgrades that tenant to classic and says so in `engine_reason`, so the customer keeps
receiving a video instead of nothing. `DAILY_VIDEO_ENGINE=advanced` is the strict mode: it refuses
rather than shipping a lower tier — use it only once the toolchain is proven.

---

## Diagnosing "no video came today"

Work down this list; each step distinguishes a different cause.

1. `GET /api/clientops/video-production/daily-status` — `enabled`, `allowlist_configured`, and the
   per-client `engine_reason` / `open_reviews` / `generated_today`. This answers most cases.
2. `GET /api/growth/infra/automation-health` — is the `daily_video` job heartbeating? Overdue means
   the beat is not firing, not that video generation failed.
3. `docker exec leadgen_scheduler printenv | grep ^DAILY_VIDEO` — did the env actually reload?
   (`restart` does not; `up -d` does.)
4. `docker logs leadgen_worker --tail 200 | grep -i daily_video`
5. If `CELERY_VIDEO_QUEUE=1`: `docker logs leadgen_worker_video --tail 200`. If that container is
   quiet while renders are expected, the flag or the overlay is missing.
6. Advanced failing: `GET /api/clientops/video-production/ops` plus the Creative OS records — a
   `failed` streak with no `fallback_from` is the NO_SILENT_FALLBACK behaviour, i.e. toolchain.
7. `advanced_block` non-null in `daily-status` = the customer's **brief** is incomplete (missing
   offer / unverified brand facts), not an infra fault. Complete it in the customer record, then
   `POST /api/clientops/video-production/daily-clear-block?client_id=<id>`. Blocks also auto-expire
   after `DAILY_VIDEO_ADVANCED_BLOCK_DAYS` (default 7). Under `auto` the client keeps receiving
   classic videos meanwhile; under `advanced` they receive nothing until the brief is fixed.

---

## Things this runbook deliberately does NOT do

- **No auto-publish.** Videos still go through customer approval; social publish stays behind
  `VIDEO_SOCIAL_PUBLISH_ENABLED` and the publish gate.
- **No daily WhatsApp blast.** `VIDEO_WHATSAPP_REVIEW_ENABLED=1` combined with daily generation
  means a WA message to the same number every day. Ban-safety: leave review on the 1-click human
  path unless the customer has explicitly asked for a daily WA preview.
- **No pricing-copy change.** `app/marketing/packages.py` still promises "AI video ads
  (Reels/Shorts)" with no cadence. Upgrade that copy to "daily" only after the flag is on and a
  week of delivery is evidenced — and change `tests/test_billing_truth_2026.py` in the same commit.
