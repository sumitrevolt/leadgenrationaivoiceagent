# Flow Runner — Phase 5 (Richer palette + executors) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans. TDD on branch `flow-runner-phase2-5-specs`. Spec: `docs/superpowers/specs/2026-06-20-flow-runner-phase5-palette.md`.

**Goal:** Expand WHAT flows can do — 8 draft-safe / breakpoint-gated executors wrapping existing engines + 1 allowlisted SSRF-guarded HTTP node + palette items — keeping the Phase-1 safety envelope identical (no new auto-send surface).

**Architecture:** Pure-additive. New `_exec_*` wrappers (import-inside, never-raise, `{ok,count,detail}`) appended to `process_library.EXECUTORS` → the compiler whitelist auto-includes them (reads `EXECUTORS.keys()`). One new `flow_http.py` (host-allowlist + SSRF guard + GET/POST, no secrets). Compiler gains a non-fatal `warnings` list for side-effect nodes lacking an upstream breakpoint.

**Tech Stack:** Python 3.12, httpx (already in lockfile), pytest, vanilla JS. No new dep/container/DB/route/worker-job.

## Global Constraints
- Windows venv `.venv\Scripts\python.exe`; Windows git. Read before Edit; no parallel-edit same file.
- **The #1 rule:** every new executor is **draft-safe or breakpoint-gated**. No new auto-send/call/publish. Compliance (TRAI/DLT/DND/WhatsApp) stays server-side in the engines.
- Never-raise + import-safe (imports inside functions). Flag-gated `FLOW_RUNNER` (unchanged). HTTP node additionally inert until `FLOW_HTTP_ALLOWLIST` set.
- **Verified engine signatures (DO NOT re-guess):**
  - `revenue_digest.run(force=False)` · `telegram_publish.run_due()` · `whatsapp_campaign.send_campaign(items, delay_s=None)` · `crm_sync.push_lead(lead, client_id="", note="")` · `seo_blog.generate_article(niche, city="", topic=None)` · `brand_pulse.scan(business_name, city=None, niche=None)` · `review_monitor.run_check(max_clients=15)` · `client_report.build_report(client_id, month="", send=None)`.
  - `client_report` emails only if `CLIENT_REPORTS=1` OR `send=True` → wrapper passes `send=False` → draft-safe by default (flag off).

---

### P5-T1: `flow_http.py` — allowlisted HTTP node
**Files:** Create `app/automation/flow_http.py` (spec §4.1 verbatim — host-allowlist suffix match + `_is_public` SSRF guard mirrored from `website_auditor`, GET/POST, 8s timeout, 200KB cap, no redirects, no secret interpolation, never-raise). Test `tests/test_flow_http.py`.
- Tests: `_host_allowed` suffix logic (allow `leadsgenai.in` → `ntfy.leadsgenai.in` passes, `evil.com`/`notleadsgenai.in` fail, empty allowlist denies all); `_is_public` blocks `127.0.0.1`/`10.x`/`localhost`/`*.internal`/empty; `run()` rejects bad method / non-http scheme / host-not-allowlisted / empty-allowlist (ok:False, never raises); provider hosts (`api.telegram.org`, `graph.facebook.com`) rejected; GET/POST success via monkeypatched `httpx.AsyncClient` + `_is_public→True`.

### P5-T2: 9 executors in `process_library.py`
**Files:** Modify `app/agents/process_library.py` (add 9 `_exec_*` per spec §3.1 + 9 `EXECUTORS` entries; existing 9 untouched). Test `tests/test_flow_executors_phase5.py`.
- Tests: each wrapper monkeypatches its engine fn to a fake async returning a known dict → assert `{ok,count,detail}` mapping; assert never-raises when engine raises (patch→raise→`ok:False`). Specifically: `client_report_draft` calls `build_report` with `send=False`; `crm_queue` does NOT call `push_lead` when `CRM_SYNC` unset; `whatsapp_draft` returns link-count when `WHATSAPP_AUTO_SEND` unset; `http_request` delegates to `flow_http.run`.

### P5-T3: compiler side-effect warning (non-fatal)
**Files:** Modify `app/automation/flow_compiler.py`. Test `tests/test_flow_compiler_phase5.py`.
- `SIDE_EFFECT_ACTIONS = {"telegram_draft", "crm_queue"}`. After a successful compile, if a side-effect node has NO breakpoint preceding it (linear: earlier in `order`; dag: no breakpoint ancestor via `in`-edges), append `"⚠ '<id>' (<action>) has no upstream Approval — add a breakpoint before it"` to a **non-fatal** `result["warnings"]` list. Never adds to `errors` (stays runnable). New keys auto-whitelisted (no whitelist change).
- Tests: flow with new action compiles (kind linear/dag, errs empty); side-effect node without upstream breakpoint → `warnings` non-empty + `errs` empty; with an upstream breakpoint → `warnings` empty.

### P5-T4: builder palette + node files
**Files:** Modify `frontend/explorer.html` — append 9 `NODE_TEMPLATES` entries (spec §5; `telegram_draft`/`crm_queue` carry `warn:'breakpoint'`); add `flow_http.py` to the `flow_runner` node `files:`. (`flow_http` is not imported in team_scheduler → not an engine-module gate; only needs to exist on disk for the file-ref gate.)

### P5-T5: green gates
- `.venv\Scripts\python.exe scripts/explorer_sync.py --check` → [OK].
- `.venv\Scripts\python.exe scripts/prod_check.py` → ALL PASSED.
- Full flow suite + 3 new Phase-5 suites green. Import smoke: `import app.agents.process_library, app.automation.flow_http`.

## Rollout
Ship `FLOW_RUNNER` off + `FLOW_HTTP_ALLOWLIST` unset → recreate app+worker. New executors appear in palette when `FLOW_RUNNER=1`. HTTP node inert until `FLOW_HTTP_ALLOWLIST=leadsgenai.in,ntfy.leadsgenai.in` set. Smoke: draft-only flow (`brand_pulse`→`seo_blog_draft`→breakpoint→`telegram_draft`) pauses at breakpoint; `http_request` to `/health` → 200, non-allowlisted → ok:False. Rollback = unset `FLOW_RUNNER`.

## Seam (Phase 4): `http_request`/`crm_queue`/`whatsapp_draft`/`client_report_draft` read targets from run-level `inputs` — natural first consumers of node-output→input mapping.
