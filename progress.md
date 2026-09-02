# Loop Run — 2026-08-27 — ADR-OWNER-1 Ship

**Date:** 2026-08-27
**Goal:** Ship a daily 9:00 IST "owner action pack" (CSV+MD+nfty) that turns the 42 un-actioned `calling_flagged` leads in `/api/ops/hotqueue` into click-ready wa.me messages the owner can send from the phone in 10 minutes.

## Inspected
- `app/platform/reply_agent.py:2461-2627` — `hot_queue(scope="boss")` engine
- `app/api/ops_mcp_tools.py:37-63` — `GET /api/ops/hotqueue` route
- `app/platform/team_scheduler.py:184,1585-1591` — beat routing pattern
- `app/tasks/staff_jobs.py:115-134` — `STAFF_JOBS` valid-set
- `app/worker.py:564-572` — `staff-hot-queue-brief-daily` beat entry (model)
- `app/platform/office_briefing.py:544-595` — `run_scheduled()` pattern (env-gated health check)
- `app/platform/runtime_data_allowlist_entries.py:608-629` — `ops.office_briefing` allowlist pattern
- `app/platform/runtime_data_manifest.py:309-340` — `ops.office_briefing` manifest pattern
- `app/platform/automation_health.py:73-78` — `EXPECTED_GAP_MIN`
- `app/platform/scheduler_config.py:194-198` — `JOB_META` (label/cadence/owner)
- `app/platform/today_overview.py:51,145-148,594` — `(h,m)` window + `JOB_INFO` (Hinglish)
- `tests/test_runtime_data_a*_ratchet.py:73` — `EXPECTED_ALLOWLIST_ENTRIES` ratchet
- `tests/test_runtime_data_path_allowlist.py:147-148,451` — entry count + unique families
- `tests/test_scheduler_multi_registry_parity.py:76` — `staff_job_count`
- `tests/test_today_overview.py:93` — `JOB_INFO` Hinglish coverage
- `tests/test_explorer_sync.py:8-10` — engine module graph coverage
- `frontend/explorer.html:958,1078-1079` — node + edge insertion points
- `.github/workflows/ci.yml:140-189` — 3 required checks (`Lint`, `prod_check runtime gates`, `pytest shards 1-4`)
- `scripts/deploy_vps.sh:111-117,221-249` — kill-fence gate + ff-only live checkout
- `scripts/_deploy_gate_container.sh:151-162` — `gate_kill_env_proof` semantics

## Problems Found
1. **42 hot leads sitting un-actioned** in `/app/inbox` for 24+ days. MRR flat at ₹5,997. No new paid customer since Jiya (2026-07-05).
2. The existing 8:15 IST `hot_queue_brief` job produces a *narrative* brief — owner reads but doesn't act.
3. No daily 9:00 IST automation existed that produces a *click-ready* file (CSV+MD with wa.me links).
4. Manual UPI auto-activation is OFF (`UPI_AUTO_ACTIVATE=0`); cold WA is OFF (`SALES_AUTOPILOT_WHATSAPP_ENABLED=0`) — by design. The owner is the only entity that can convert a "calling_flagged interested" reply to a paid UPI.
5. CI gate suite: 4 things check the allowlist, manifest, JOB_META, JOB_INFO, ratchet baseline, family count, and explorer graph — every new staff job needs a coordinated registration or CI fails. The ratchet also forces `EXPECTED_ALLOWLIST_ENTRIES` to be bumped by exactly the right number.
6. Deploy gate requires `VOICE_LAUNCH_KILL=1` (kill-fence). Production was at `=0` (calling live). Need 2-step deploy: flip kill ON, ship, flip kill OFF, recreate leadgen_app.

## Changed
- `app/platform/hot_queue_owner_pack.py` (new) — `build_owner_pack(limit, push_ntfy)` engine: writes `data/hot_queue_for_owner_<date>.{csv,md}` from `reply_agent.hot_queue(scope="boss")`, optional ntfy push to owner topic. Idempotent (re-runs overwrite same-day file). Never raises (defensive surface).
- `app/platform/team_scheduler.py` — register `hot_queue_owner_pack` in `STAFF_JOBS_VALID` dict; add `elif job == "hot_queue_owner_pack"` branch in `_run_job` that calls `build_owner_pack` + `team.log_event`.
- `app/tasks/staff_jobs.py` — add `"hot_queue_owner_pack"` to valid-set with ADR comment.
- `app/worker.py` — add `"hot_queue_owner_pack"` to `HEAVY_STAFF_JOBS` allowlist; add `staff-hot-queue-owner-pack-daily` beat entry at 09:00 IST.
- `app/platform/scheduler_config.py` — `JOB_META["hot_queue_owner_pack"]` with label/cadence/owner.
- `app/platform/automation_health.py` — `EXPECTED_GAP_MIN["hot_queue_owner_pack"] = 30*60` (30-min health-gate).
- `app/platform/today_overview.py` — `(9, 0)` window + `JOB_INFO["hot_queue_owner_pack"]` Hinglish label + `kya`.
- `app/platform/runtime_data_allowlist_entries.py` — 2 new allowlist entries: `ops.hot_queue_owner_pack_csv` + `ops.hot_queue_owner_pack_md` (path_pattern matches the actual double-quoted f-string in source).
- `app/platform/runtime_data_manifest.py` — 2 new `_e(...)` store entries with the same store_ids.
- `frontend/explorer.html` — add `hot_queue_owner_pack` node + 2 edges (worker→node, reply→node).
- `tests/test_hot_queue_owner_pack.py` (new) — 4 tests: importable, empty rows, 3-row CSV+MD, error path.
- `tests/test_runtime_data_a1_ratchet.py` — bump `EXPECTED_ALLOWLIST_ENTRIES` 83→85.
- `tests/test_runtime_data_path_allowlist.py` — bump entry count 83→85, family count 26→28, add 2 new family store_ids to pinned set.
- `tests/test_scheduler_multi_registry_parity.py` — bump staff_job_count 50→51.
- `.env` on prod — `OUTREACH_DAILY_CAP` 20→80 (high-blast for sprint); deploy-time `VOICE_LAUNCH_KILL` 0→1→0 (kill-fence + restore).
- `memory/decisions.md` — ADR-OWNER-1 entry.
- PR #450 (`hotfix/hot-queue-owner-pack`) — MERGED to main.
- Prod `origin/main` — `bc5800cb` deployed; `/health=bc5800cb` confirmed.

## Tests Run
- Local: `pytest tests/test_hot_queue_owner_pack.py` — 4/4 PASS
- Local: `pytest tests/test_hot_queue.py tests/test_hot_queue_brief_schedule.py tests/test_hot_queue_payment_path.py tests/test_hot_queue_quick_actions.py tests/test_hot_queue_sla_visibility.py tests/test_reply_agent_spam_guard.py` — 38/38 PASS
- Local: `pytest tests/test_runtime_data_a1..a9_ratchet.py` — 9/9 PASS (after bumping constants)
- Local: `pytest tests/test_runtime_data_path_allowlist.py` — PASS (after bumping + adding 2 family store_ids)
- Local: `pytest tests/test_scheduler_multi_registry_parity.py` — 12/12 PASS
- Local: `pytest tests/test_today_overview.py` — 18/18 PASS
- Local: `pytest tests/test_explorer_sync.py` — 6/6 PASS
- Local: `scripts/prod_check.py` — ALL CHECKS PASSED (1348 routes / 97/97 engines / 360 edges / 0 orphans)
- CI PR #450 final: Lint, Trivy image + repo scan, CodeQL, pip-audit, harness real-redis, **prod_check runtime gates PASS**, **pytest shards 1/2/3/4 ALL PASS**, prod_check+pytest aggregate PASS, GitGuardian PASS. (Gate A is non-required sketch.)
- Prod smoke (post-deploy): `docker exec leadgen_app python -c "from app.platform import hot_queue_owner_pack; ..."` — returns `{'ok': True, 'rows': 42, 'csv': ..., 'md': ..., 'ntfy': 'sent_200'}`. Owner phone received ntfy push (id `AWZXyeD0XDYf`).

## Verification Evidence
- `git log --oneline -3 origin/main` → `bc5800cb feat(ops): hot_queue_owner_pack (#450) ...`
- `curl http://127.0.0.1:8000/health` → `{"version": "bc5800cb", "uptime": "0h 0m 33s", ...}`
- `/api/ops/hotqueue` (prod) → `scope=boss count=5 (limit=5)`; first 3 leads are `afmsolarsystem.com`, `savemaxsolar.com`, `solarsquare.in` — all `interested`, all `solar_residential`, all Pune.
- `data/hot_queue_for_owner_2026-08-27.csv` — 42 rows, 32KB
- `data/hot_queue_for_owner_2026-08-27.md` — 12KB
- ntfy push id `AWZXyeD0XDYf` — confirmed accepted on `leadgen-d6b984bd` topic
- `/opt/leadgen/.env` restored to `VOICE_LAUNCH_KILL=0` (calling LIVE) after deploy

## Risks
- **n=1 deploy gate failure recovery** — if any worker fails to pick up the new beat entry, the 9:00 IST job will silently skip. Mitigation: scheduler was `docker restart`ed, beat file `/app/data/celerybeat-schedule` is in place, the manual smoke run confirmed the function works in the prod container.
- **Owner action** — system can only push; closing still needs the owner. If owner doesn't act for 7 days, the system is no better off than before.
- **Voice kill-fence** — every future deploy will need the same 2-step pattern. Could be automated but per repo discipline (kill-fence is a safety belt), a script that does both is a "bypass waiting to happen" per `deploy_vps.sh` comments.

## Remaining
- **WS-2 (Daily Pipeline Expansion):** DONE in part — `OUTREACH_DAILY_CAP=80` is live. The cron already runs every hour 9-19, so 80/day goes out without code change. Wait 24-48h to measure reply-rate lift.
- **WS-3 (High-ACV Offer):** PROPOSAL written to `data/council_proposal_high_acv_2026-08-27.md`. Default = Option 1 (annual-prepaid bundle, 2-months-free hook) if no owner input in 4h. No code changes until owner picks.
- **Owner Hot Queue close-loop:** The only true revenue lever remaining. 42 cards × ~25% close × ₹1,999 = **₹20,990 in 7 days** best case. Need owner to action `/app/inbox` daily.

## Next Highest Priority
**Owner action** on the 9:00 IST ntfy push (which will fire tomorrow 2026-08-28 09:00 IST) and the 5-step list in `data/hot_queue_owner_brief_2026-08-27.md`. The system has done everything it can autonomously; the ₹5L target requires 247 sales which is mathematically unachievable at current ACV without (a) owner action on the 42 hot leads and (b) an ACV lift to ₹9,999+ bundle. **OWNER ACTION REQUIRED: pick 1 of 3 options in `data/council_proposal_high_acv_2026-08-27.md` within 4h.**

# Loop Run — 2026-08-28 — Agentic Knowledge + Execution OS Upgrade

**Date:** 2026-08-28
**Goal:** Upgrade the project into an enterprise-grade Agentic Knowledge + Execution Operating System (owner master prompt): knowledge brain → playbooks → runbooks → retrieval → evidence → learning. Build as normalization/registry/retrieval layer over existing authoritative docs (no duplication).

## Inspected
- Existing layers: `knowledge/` (OKF bundle, 11 dirs), `memory/` KB (INDEX, decisions, incidents, integrations, playbooks, backlog), `docs/` (OPERATIONAL_RUNBOOKS RB-001..010, ADR-104 deploy, GTM/PILOT playbooks, context/), `_tasks_sync.json` (kanban), `HERMES_AGENT_ROSTER.yaml`, `progress.md` loop ledger.
- CLAUDE.md ##5 compliance invariants, ##6 testing protocol, ##8 operating rules, landmines (kill fence, deploy_vps.sh, APP_VERSION, causal-claim discipline, secret handling).

## Problems Found
1. Knowledge scattered across memory/ + docs/ + knowledge/ with no machine-readable index or risk classifier.
2. No Owner Truth as machine-readable single source (markdown only, no YAML/API-backed).
3. No runbook/playbook registry with GREEN/AMBER/RED execution classes.
4. No retrieval path: agents needed giant prompts; no query → runbook/playbook/incident bundle.
5. No notebook-ready export; no freshness metadata; no learning-loop template.

## Changed
- `ops/owner_truth.yaml` — machine-readable Owner Truth (production, priorities, revenue truth, blockers, authority, kill switches, automation status).
- `ops/runbooks/registry.yaml` — 37 runbooks across voice/infra/sales/video/agent, classed GREEN/AMBER/RED with fail-closed policy.
- `ops/playbooks/registry.yaml` — 21 playbooks indexed (P0-P2) + selection policy.
- `ops/playbooks/PB-*.md` — 6 P0 playbooks (Sales, Payment Verification, Voice Calling, Deployment, Customer Onboarding, Provider Failover).
- `knowledge/00..10/` — 11 domain dirs with INDEX.md + briefs referencing authoritative sources.
- `notebook_exports/` — 11 Gemini Notebook-ready bundles (secret-scrubbed) + INDEX.md.
- `incidents/TEMPLATE.md` — incident knowledge record template.
- `ops/README.md` — operating-loop map + usage rules.
- `scripts/` — knowledge_query.py (retrieval), validate_knowledge_os.py (validator + acceptance), gen_notebook_export.py, gen_knowledge_domains.py, gen_p0_playbooks.py.
- `tests/test_knowledge_os.py` — 12 contract tests.

## Tests Run
- `pytest tests/test_knowledge_os.py -q` → 12 passed.
- `scripts/validate_knowledge_os.py` → 0 errors; acceptance A-D all ✓.
- `scripts/check_secrets.py` → 131 files scanned, no secrets.

## Verification Evidence
- TEST A "Calls failing Busy Line" → voice domain + RB-VOICE-002 [AMBER].
- TEST B "Deploy latest safe change" → infra + PB-DEPLOYMENT + RB-INFRA-007/009.
- TEST C "Follow up hot leads" → PB-SALES + RB-SALES (suppression-aware).
- TEST D "Last Swara outage" → RB-VOICE-009 grounded.

## Risks
- Hand edits to registry YAML can break the contract — validator is the gate.
- Notebook bundles pull head of sources — secret scrubber + test guard it.
- No /api/owner/truth endpoint yet (Phase 2 extension).

## Remaining
- Phase 2 API: expose owner truth via admin endpoint when a route slot opens.
- Phase 6 sandbox provider abstraction (local/VPS/Daytona) — no code yet.
- Phase 7 owner-orchestrator formal wiring into scheduler — retrieval + registries exist.
- Commit the layer (owner decision) — all new files untracked.

## Next Highest Priority
Owner reviews and commits the knowledge-OS layer. Meanwhile the revenue path remains **OWNER Hot Queue action** (42 cards, /app/inbox) + WS-3 ACV decision.
