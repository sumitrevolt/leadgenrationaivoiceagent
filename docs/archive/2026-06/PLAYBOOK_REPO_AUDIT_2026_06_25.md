# LeadGen AI Playbook Repository Audit - 2026-06-25

Source: `docs/LeadGen-AI-Enterprise-Playbook-v1.0`.

Scope read: playbook, governance, architecture, automation, workflows, agents, security, testing, operations, deployment, checklists, templates. The merged playbook file is a combined copy; the split source docs were treated as the normative source.

## 1. Current Architecture Map

- Edge/UI: FastAPI app, public pages, admin/customer dashboards, marketing/automation/growth tools.
- API layer: `app/api/*`, auth/RBAC deps, rate-limit middleware, activation/readiness endpoints, admin ops, agent APIs, billing APIs.
- Domain services:
  - Lead/CRM: prospecting, lead harvester, pipeline ops, CRM sync, cadence, customer CRM.
  - Voice: vobiz stream/handler, call manager, voice agent brain, STT/TTS/LLM fallback chain, telephony readiness.
  - Marketing/content: auto content, content schedule, social autopost, video ad cycle, newsletters, winback, rank tracker.
  - Billing: plans, UPI/manual activation, Stripe path, invoice/usage/dunning/meter watch.
  - Workflow: Flow Runner, process engine, process library, flow triggers, process ticks.
  - Agent runtime: coordinator, LLM council, staff jobs, self-improve, engineer agents.
- Infra/runtime: Docker app + Postgres/PgBouncer + Redis + Celery worker/beat + optional heavy queue + observability stack.
- State/event stores: Postgres models, Redis queues/DLQ, JSONL journals for process runs/flows/self-improve, agent_events DB table, Obsidian staging notes.

## 2. Agent Map

- Total staff: 24.
- Platform: manager, kavya, hermes, nikhil, vikram, guru, pranav, vidya, arnav, kabir, diya, aryan.
- Voice: swara, ananya, riya, arjun, meera, tara.
- Marketing: dev, rohan, isha, ravi, neha, kiran.
- Runtime patterns: sequential coordinator, fan-out, Reflexion, hierarchical teams, AgentVerse-style recruitment, engineering crew, LLM council.
- Governance gap: role definitions exist in code and docs, but not every individual agent has a formal versioned runtime contract with owner/inputs/outputs/eval threshold in a single registry.

## 3. Workflow Map

- Playbook critical workflows covered in code:
  - Customer onboarding: `app.marketing.onboarding`, `onboard` job.
  - Daily content: `content`, `afternoon_content`, content schedule, social autopost.
  - Lead ingestion/enrichment: prospect, midday/evening harvest, lead scoring, pipeline ops.
  - Voice calling: call manager, vobiz stream, post-call hooks, call qualifier.
  - Email follow-up: `email_outreach`, `email_followup`, cadence.
  - CRM update: pipeline ops, CRM sync, sales pipeline.
  - Billing/invoice: billing APIs, dunning, usage, meter watch, UPI activation.
  - Admin intervention: admin ops, flow/process approval, code-upgrader proposals.
  - Reporting/analytics: digest, readiness digest, dashboards, reports.
- Deterministic workflow engine: `process_engine` with journal replay and breakpoints; process keys: `lead_campaign`, `client_content`, `growth_audit`.
- Flow Runner: saved flows with manual/cron/event triggers; gated by `FLOW_RUNNER` and `FLOW_AUTO_TRIGGERS`.

## 4. Scheduler Map

- Live durable scheduler: Celery beat + `app.tasks.staff_jobs.run_staff_job`.
- Staff jobs after audit: 34 dispatchable jobs, 35 staff beat entries including `self_improve_revive`.
- Key cadence:
  - `growth` every 15 min; `flow_cron` every 5 min.
  - Hourly: ops, reply triage, watchdog, onboard, engineer_sre, meter_watch.
  - Daily: revenue snapshot, qa, trainer, blog, content, digest, prospect, pipeline, standup, readiness digest, engineer_finops/security/dbre/dataquality, process_autostart, obsidian_push.
  - Workday hourly: email outreach/follow-up, 9-19 IST.
  - Weekly: kb_refresh, weekly_marketing, saturday_hygiene, engineer_deps.
- Rollback scheduler: `team_scheduler.scheduler_loop()` with lock file and `_last_ran` dedupe.

## 5. Queue Map

- Celery default queue: `celery`.
- Heavy queue: `heavy` for qa/trainer/blog/content/digest/prospect when `CELERY_HEAVY_QUEUE=1`.
- Domain queues: `scraping`, `calling`, `reporting`, `sync`, `training`.
- DLQ: Redis `dlq:failed_tasks`; exhausted/unknown retry bucket `dlq:dead`.
- Self-requeue queues: `self_improve_tick`, `process_tick`.
- Queue observability: `automation_health.queue_depth()` now backs CLI `--dlq-status`.

## 6. Gaps

- Some legacy workflows still directly call domain modules rather than a single persisted workflow state machine.
- Event bus exists in pieces, but all domain events are not yet uniformly schema-versioned and replay-documented.
- Queue messages are Celery args for many jobs; not every message has explicit correlation_id/trace_id/workflow_execution_id.
- Full playbook certification evidence is incomplete locally: load, chaos, and complete E2E suite were not run in this batch.
- Agent governance is strong operationally, but per-agent contracts/eval thresholds are not fully normalized in one machine-readable registry.
- Explorer graph reports informational drift: `engineer_dbre` not named on graph view.

## 7. Critical Blockers

- Code blockers found and fixed in this audit:
  - In-process scheduler rollback path referenced undefined `now_ist`.
  - Automation DLQ CLI read stale file-only source instead of actual Redis queues.
  - Durable scheduler parity missed `obsidian_push`.
  - Automation dead-man map missed `engineer_dbre`, `engineer_dataquality`, `engineer_deps`.
- Remaining launch blockers:
  - Product 2 voice cold-calling remains externally blocked by Vobiz recharge/DID/DLT.
  - Full enterprise certification cannot be claimed until load/chaos/full E2E evidence is run and archived.

## 8. Implementation Plan

Batch 1 completed:
- Fixed scheduler rollback clock reference (`now.hour`).
- Added regression test to prevent `now_ist` reintroduction.
- Made automation health DLQ CLI use actual queue depth / Redis DLQ with legacy fallback.

Batch 2 completed:
- Added `obsidian_push` to durable staff job dispatcher and Celery beat.
- Aligned in-process `obsidian_push` window to documented 02:15 IST.
- Added engineer DBRE/DataQuality/Deps jobs to automation dead-man monitor.
- Added parity tests.

Next safe batches:
- Add a machine-readable agent contract registry generated from `STAFF`.
- Add queue message contract helpers for staff jobs/process ticks with correlation IDs.
- Add event schema/version registry for `lead.created`, `lead.qualified`, `call.completed`, billing/subscription events.
- Add an enterprise certification command that bundles prod_check, wiring audits, targeted E2E, queue/DLQ checks, and report output.

## 9. Test Plan

Executed:
- `.venv\Scripts\python.exe -m pytest tests\test_pipeline_automation.py tests\test_infra_observability.py -q` -> 20 passed.
- `.venv\Scripts\python.exe scripts\automation_wiring_audit.py` -> OK, 178 flags wired, 34 staff jobs dispatchable, 35 beat tasks recognized.
- `.venv\Scripts\python.exe scripts\explorer_sync.py --check` -> OK, 73/73 engine modules represented, no dangling edges/orphans.
- `.venv\Scripts\python.exe scripts\automation_health_audit.py --dlq-status --format=json` -> command works; local Redis unavailable returns unknown depths.
- `.venv\Scripts\python.exe scripts\cross_path_audit.py` -> OK, cross-path telephony + automation parity.
- `.venv\Scripts\python.exe scripts\prod_check.py` -> OK, all checks passed after fixes.

Still required for full certification:
- Run targeted billing, telephony, workflow, and agent governance tests.
- Run load/chaos tests or explicitly mark as not-run with risk.

## 10. Production Readiness Score

- Product 1 Marketing: 92/100 local code readiness. Main remaining evidence gap is full E2E/load/chaos archive.
- Product 2 Voice standalone: 78/100 commercial readiness because DLT/Vobiz external blockers remain.
- Enterprise playbook compliance overall: 88/100 after Batch 1 and Batch 2.

No ADR created: fixes were implementation parity and observability corrections, not a new architecture decision.
