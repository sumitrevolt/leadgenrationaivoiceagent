---
name: self-improve-loop
description: Self-improving CONTINUOUS agent loop (task→task, no cron timing) — architecture + 12 actions + skill_library auto-learn + eval_gate signal + social channels. Use when extending/building the loop, adding actions, debugging heartbeat/revive/requeue, or tuning guards. (Operate/audit/pause = self-improve-control.)
---

# Self-Improve Continuous Loop

## Architecture (free-stack, ban-safe)
- `app/agents/self_improve.py` — pick task (queue → auto: weakest funnel stage + skill_library epsilon-greedy, +diversity guard: last-6 dedup + 20-min per-action cooldown) → execute (existing engines reuse) → learn (record_use; har 8 runs LLM reflection→lesson) → Celery self-requeue (countdown=gap). **Koi cron timing nahi** — task complete → agla task. **17 ACTIONS**: scrape_leads, harvest_leads, channel_experiments, content_pack, seo_pages, sales_deepdive, social_drafts, revenue_sweep, optimizer, campaign_optimize, reflection, study_skills, code_scan, rescore_pipeline, cadence_sweep + **VOICE**: `voice_eval` (persona smoke, gated VOICE_EVAL_AUTO) · `voice_learn` (REAL recent call transcripts → `live_eval.eval_recent_calls` analyze → weakest call ka Hinglish lesson `skill_library` `voice_{niche}` me, jise `telecaller_brain` `lessons_snippet('voice_{niche}')` se consume karta = **voice-agent COMPOUNDING from real calls**; dedupe `data/voice_learn_state.json` last_call_id, draft-only, never-raise). Voice actions `_STAGE_ACTIONS["conversion"]` me biased.
- **eval_gate close-the-loop (F.3)**: har iteration `eval_gate.score_and_gate("self_improve", action, current_score=1.0|0.0)` se rolling-baseline ke against scored. Action ka success drop (e.g. 0.9→0.3) = `regression` flag (REJECT). INERT jab `EVAL_GATE` unset; `EVAL_GATE_HARD` set = detail me visible mark. Auto-rollback NAHI (drift flag, kaam block nahi).
- `app/platform/skill_library.py` — shared auto-learn ledger: per-tactic Laplace success-rate + lessons. `pick_action()` (epsilon-greedy 0.3 explore), `lessons_snippet()` (prompt inject). Stores `skill_uses.jsonl` + `skill_lessons.jsonl`.
- `app/marketing/social_channels.py` — 8 naye approach channels (instagram_comment, youtube_shorts, gbp_qna, whatsapp_status, micro_influencer, local_pr, event_outreach, listing_optimizer) — sab DRAFTS, channel_experiments bandit me wired.
- Celery: `staff_jobs.self_improve_tick` (self-requeue chain) + `self_improve_revive` (beat */20min dead-man) + watchdog-job `ensure_alive()`.

## Guards (prod-down + Groq-TPD lessons)
- GATED `SELF_IMPROVE_LOOP=1` (default OFF, par live VPS pe ON). Web process me KABHI inline run nahi — sirf Celery worker.
- `SELF_IMPROVE_GAP_S` (default 180s min gap) · `SELF_IMPROVE_MAX_PER_DAY` (default **120**, cap hit = requeue) · per-iteration 240s hard timeout · LLM degraded (`llm_metrics` ok-rate) → sirf light no-LLM actions (scrape/revenue_sweep).
- **Cost + approval gates** (Phase 6/7): `SELFIMPROVE_COST_CAP` (default $50/day, CostTracker) · deterministic gates (budget / expensive_risky cost>$5+success<60% / low_roi) · `SELF_IMPROVE_APPROVAL=1` = LLM-heavy actions human-approve (ApprovalQueue, `data/self_improve_approvals.jsonl`).

## API (admin, /api/growth)
`GET /selfimprove/status` · `POST /selfimprove/run` (enqueue tick) · `POST /selfimprove/task` {task,action} · `GET /selfimprove/actions` · `GET /selfimprove/cost-status` · `GET /selfimprove/approvals-pending` · `PATCH /selfimprove/approval/{id}/approve|reject` · `GET /skills/library` · `POST /skills/lesson` · `GET /social/channels` · `POST /social/draft` · `POST /social/batch`
(Koi `/selfimprove/hint` route nahi — guidance ke liye `/selfimprove/task` use karo.)

## Naya action add karne ka pattern
1. `self_improve.ACTIONS` me entry `(llm_heavy, desc)` + `_STAGE_ACTIONS` me relevant stage.
2. `_execute()` me elif — lazy import, EXISTING engine reuse, bounded (timeout), `{"ok": bool, "detail": str}` return.
3. Side-effect actions (send/call/post) KABHI nahi — sirf gated/draft-only engines.

## Stores
`data/self_improve_state.json` (heartbeat) · `self_improve_queue.jsonl` · `self_improve_runs.jsonl` (cost+outcome_value per run) · `self_improve_approvals.jsonl` · `skill_uses.jsonl` · `skill_lessons.jsonl`

## Enterprise gate

- **Operating loop**: Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). Naya action wiring = `teach-agent-loop`; operate/pause/audit = `self-improve-control`.
- **Risk-tier: High** (always-on loop, runs unattended on live VPS). Locks: `SELF_IMPROVE_LOOP` flag default-OFF, cost-cap + approval gates, eval_gate drift signal, dead-man (revive */20min + watchdog `ensure_alive()` + `automation_health` entry).
- **Side-effect safety (non-negotiable)**: naya action sirf gated/draft-only engine invoke kare — direct send/call/post/bill KABHI nahi (ban-safe ethos). `voice_learn`/social = draft-only by design.
- **Reliability**: per-iteration 240s hard timeout · every `_execute()` branch never-raise `{"ok": bool, "detail": str}` · Celery failure → `dlq:failed_tasks` · LLM-degraded (`llm_metrics` ok-rate / breaker open) → sirf light no-LLM actions (Groq TPD din-bhar khatam ho sakta).
- **Idempotency**: action-level dedupe (e.g. `voice_learn` `data/voice_learn_state.json` last_call_id) + loop diversity guard (last-6 dedup + 20-min cooldown) so requeue duplicate na kare.
- **Cost/quota**: `SELFIMPROVE_COST_CAP` (default $50/day NOTIONAL throttle, free-stack — real paisa nahi) + deterministic gates (budget / expensive_risky / low_roi). `SELF_IMPROVE_APPROVAL=1` = LLM-heavy actions human-gate.
- **Rollback (NAMED)**: `SELF_IMPROVE_LOOP=0` in `.env` + `docker compose -f docker-compose.vps.yml up -d --no-deps worker scheduler` (running task finishes, no new pick). Bad action = remove from `ACTIONS`/`_STAGE_ACTIONS` + recreate.
- **Evidence (done)**: `.venv\Scripts\python.exe scripts\prod_check.py` PASS + `pytest tests\test_self_improve*.py -q` (action happy + 1 failure-branch + dedupe) + `GET /selfimprove/status` heartbeat fresh + `data/self_improve_runs.jsonl` real outcome row.
