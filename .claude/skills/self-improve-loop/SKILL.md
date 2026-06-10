---
name: self-improve-loop
description: Self-improving CONTINUOUS agent loop (task→task, no cron timing) + skill_library auto-learn + naye social channels. Use when extending the loop, adding actions, debugging heartbeat/revive, or tuning guards.
---

# Self-Improve Continuous Loop

## Architecture (free-stack, ban-safe)
- `app/agents/self_improve.py` — pick task (queue → auto: weakest funnel stage + skill_library epsilon-greedy) → execute (existing engines reuse) → learn (record_use; har 8 runs LLM reflection→lesson) → Celery self-requeue (countdown=gap). **Koi cron timing nahi** — task complete → agla task.
- `app/platform/skill_library.py` — shared auto-learn ledger: per-tactic Laplace success-rate + lessons. `pick_action()` (bandit), `lessons_snippet()` (prompt inject).
- `app/marketing/social_channels.py` — 8 naye approach channels (instagram_comment, youtube_shorts, gbp_qna, whatsapp_status, micro_influencer, local_pr, event_outreach, listing_optimizer) — sab DRAFTS, channel_experiments bandit me wired.
- Celery: `staff_jobs.self_improve_tick` (self-requeue chain) + `self_improve_revive` (beat */20min dead-man) + watchdog-job `ensure_alive()`.

## Guards (prod-down + Groq-TPD lessons)
- GATED `SELF_IMPROVE_LOOP=1` (default OFF). Web process me KABHI inline run nahi — sirf Celery worker.
- `SELF_IMPROVE_GAP_S` (default 180s min gap) · `SELF_IMPROVE_MAX_PER_DAY` (default 60, cap hit = 1hr requeue) · per-iteration 240s hard timeout · LLM degraded → sirf light actions (scrape/revenue_sweep).

## API (admin, /api/growth)
`GET /selfimprove/status` · `POST /selfimprove/run` (enqueue tick) · `POST /selfimprove/task` {task,action} · `GET /selfimprove/actions` · `GET /skills/library` · `POST /skills/lesson` · `GET /social/channels` · `POST /social/draft` · `POST /social/batch`

## Naya action add karne ka pattern
1. `self_improve.ACTIONS` me entry `(llm_heavy, desc)` + `_STAGE_ACTIONS` me relevant stage.
2. `_execute()` me elif — lazy import, EXISTING engine reuse, bounded (timeout), `{"ok": bool, "detail": str}` return.
3. Side-effect actions (send/call/post) KABHI nahi — sirf gated/draft-only engines.

## Stores
`data/self_improve_state.json` (heartbeat) · `self_improve_queue.jsonl` · `self_improve_runs.jsonl` · `skill_uses.jsonl` · `skill_lessons.jsonl`
