---
name: agent-loop-design
description: Naya ALWAYS-ON / recurring agent loop design karne ka generalized pattern — self_improve/growth-pulse/process_tick se distilled. Use when building a new continuous loop, converting a cron job to task-chain, or debugging loop death/restart-storms.
---

# Agent Loop Design — naya loop banane ka pattern

> Yeh GENERALIZED pattern hai. Specific engines: `self-improve-loop` (self_improve), `scheduler-job` (cron-style jobs), `automation-pipeline` (funnel ops). Naya loop = yeh teeno pehle padho, DUPLICATE engine mat banao.

## Loop anatomy (pick → execute → learn → requeue)
1. **Pick**: explicit queue (jsonl) → warna auto-heuristic (weakest funnel stage / least-recent / bandit via `skill_library.pick_action`).
2. **Execute**: EXISTING engine reuse (lazy import), bounded — `asyncio.wait_for` / hard timeout per iteration. Naya side-effect KABHI loop se direct nahi (send/call/post = gated engines hi karte hain, loop sirf unhe invoke karta hai).
3. **Learn**: run record (jsonl, auto-trim ~10k) + optional reflection (har N runs LLM lesson → `skill_library`).
4. **Requeue**: Celery `apply_async(countdown=gap)` self-chain — task→task, cron timing nahi. Gap env-tunable (min 180s pattern).

## Kahan chalega (NON-NEGOTIABLE — 3 prod-downs ka lesson)
- **SIRF Celery worker** (`app/tasks/staff_jobs.py` me task) — web process me KABHI inline nahi.
- In-process scheduler path me ho to **boot-grace** respect karo (restart pe heavy job fire = HTTP starve, commit 50749b6 lesson).
- Loop ke andar ML/KB/embedder = `model-asset-bake` rule: image-bake + off-loop load + deadline + disable-switch.

## Dead-man trio (loop chup-chaap mar jata hai — hamesha teeno lagao)
1. **Heartbeat**: har tick state-file me timestamp (`data/<loop>_state.json`, `.lock` ke saath).
2. **Revive beat**: Celery beat entry (*/20min pattern) — heartbeat stale to naya tick enqueue.
3. **Watchdog hook**: hourly ops-watchdog me `ensure_alive()` + `automation_health` EXPECTED_GAP_MIN registry me entry (overdue alert gated `AUTOMATION_HEALTH_ALERTS`).

## Guards checklist (har naye loop pe)
- [ ] GATED env flag, default **OFF** (`AUTOMATION_FLAGS` registry growth.py me add — flags endpoint pe dikhe)
- [ ] Daily cap (`<LOOP>_MAX_PER_DAY`, hit = lambi requeue) + min gap env
- [ ] Per-iteration hard timeout (240s pattern)
- [ ] **LLM-degraded mode**: `llm_metrics` fallback-rate high / circuit-breaker open → sirf light (no-LLM) actions; Groq TPD din-bhar khatam ho sakta hai
- [ ] NEVER raises — har execute branch try/except, `{"ok": bool, "detail": str}` return
- [ ] Win/op event → `team.log_event` (staff member assign karo — /app/team + Schedule tab me dikhe)
- [ ] Store jsonl + auto-trim; PII minimal

## Determinism chahiye? → process engine, loop nahi
Multi-step workflow jisme **order + gates + human approval** chahiye = `agents/process_engine.py` (event-sourced journal, crash-safe resume, breakpoints) — naya loop mat banao. Loop = open-ended continuous improvement; process = finite workflow.

## Existing loops inventory (naya banane se pehle dekho — overlap?)
- `self_improve_tick` (180s chain, 9 actions, bandit) · `growth_engine` 15-min pulse (quantity heal) · `growth_optimizer` daily (strategy) · `process_tick` (10s, running processes) · hourly: reply-triage / ops-watchdog / auto-onboard / Hermes infra / telephony-readiness · daily staff jobs (blog/content/digest/prospect/outreach/qa/trainer).

## Debug: loop mar gaya / restart-storm
1. `GET /api/growth/infra/automation-health` — heartbeats table (ya /app/automation Schedule tab).
2. Worker logs: `docker logs leadgen_worker --tail 100` · DLQ: `GET /infra/dlq`.
3. Restart-storm = selfheal cron + unhealthy healthcheck combo dekho (compose healthcheck cmd image me exist karta hai? — scheduler pgrep lesson).
4. Boot pe block = boot-grace skip list me job add karo (team_scheduler).
