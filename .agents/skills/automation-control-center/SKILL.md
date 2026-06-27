---
name: automation-control-center
description: Upgrade/extend the /app/automation Mission Control so it stays the SINGLE advanced cockpit for all automation — loops, agent schedules, completed tasks, next-task assignment, flags. Use this skill whenever the user mentions automation control center, mission control, /app/automation, automation dashboard, agent schedule UI, "loops ka control", "tasks assign karo UI se", "control center me X add karo", a new admin tab, or any API-only automation feature that needs a UI. Also use when auditing UI coverage of backend endpoints.
---

# Automation Control Center (advanced cockpit pattern)

`/app/automation` (`frontend/automation.html`) = poore automation stack ka EK cockpit. Rule (CLAUDE.md): **naya admin feature = UI tab saath hi** — API-only feature adhoora hai. Yeh skill batati hai control center kaise advanced rakhein aur naye controls kaise add karein, website/app conventions ke hisab se.

## 4 pillars — control center me HAMESHA yeh sab dikhna/chalna chahiye

### 1. Automation loops (status + run + control)
| Loop | Status | Action |
|---|---|---|
| Self-improve forever-loop | `GET /api/growth/selfimprove/status` (runs_today, last_action, queue_pending, state) · `/selfimprove/cost-status` · `/selfimprove/approvals-pending` | `POST /selfimprove/run` (manual tick) · `PATCH /selfimprove/approval/{id}/approve\|reject` (SELF_IMPROVE_APPROVAL gate) |
| Growth optimizer | `GET /optimizer/analysis` · `/optimizer/runs` | `POST /optimizer/run` |
| Processes (babysitter) | `GET /process/runs` · `/process/run/{id}` | `POST /process/start` · **breakpoint approve/reject** `/process/run/{id}/approve\|reject` |
| Code upgrader | `GET /upgrader/patches` | `POST /upgrader/scan` · patch status (approve = super-admin) |
| Revenue loops | dunning/lifecycle/warmup `GET`s | unke `run` POSTs |
| Hermes infra | `GET /infra/hermes` + `/scans` | — (read) |

### 2. Agent working schedule (kaun kab chalta hai)
- **Job registry**: `team_scheduler.py` ~17 jobs (growth 15-min · ops/reply_triage/watchdog/onboard hourly · qa/trainer/blog/content/digest/prospect/email_outreach daily IST windows · standup gated · NEW engineer agents `engineer_sre` :45 / `engineer_finops` 9am / `engineer_security` 9:30 + `readiness_digest`, gated SRE_AGENT/FINOPS_AGENT/SECURITY_AGENT). Same job logic Celery worker (primary) + APScheduler (rollback) dono me.
- **Dead-man heartbeats**: `GET /api/growth/infra/automation-health` — har job ka last-run + overdue (EXPECTED_GAP_MIN). Overdue = red badge.
- **Staff roster + live state**: `GET /api/platform/team` (`?product=marketing|voice`) — working/active/offline 3-tier, `last_active_mins`.
- **Manual trigger**: `POST /api/platform/team/run/{member}` — kisi bhi staff ka job abhi chalao.
- Schedule UI me job → window (IST) → last run → next expected → [Run now] ek hi table me dikhao.

### 3. Completed tasks (kya ho chuka)
- **Agent events**: `GET /api/platform/team/events` (agent_events table — har staff action log).
- **Run histories**: selfimprove `status.recent` + `data/self_improve_runs` · `/optimizer/runs` · process journal (`/process/run/{id}` events) · `data/coordination_runs.jsonl` · skill_library lessons (`GET /skills/library`).
- Pattern: "aaj kya hua" timeline — events ko time-desc, staff emoji + outcome ke saath.

### 4. Next task assignment (aage kya karna hai)
- **Queue a task**: `POST /api/growth/selfimprove/task` {task, action?} — self-improve loop agle tick pe uthayega (queue → weakest-stage fallback).
- **Multi-agent goal**: `POST /api/agents/coordinate` / `coordinate-advanced` (Reflexion) / `coordinate-hierarchical` — Boss plan→assign→execute.
- **Process start**: `POST /process/start` {definition} — deterministic workflow with human breakpoints.
- **Pending approvals = assigned-to-HUMAN tasks**: process breakpoints WAITING + upgrader patches proposed — inhe ek "📥 Approvals" jagah pe surface karo (count badge sidebar pe).

### 5. Flags (sab gates ek jagah)
`GET /api/growth/infra/flags` — ~100+ automation flags on/off/unset (incl. new F–M: EVAL_GATE, AGENT_MEMORY, SRE/FINOPS/SECURITY_AGENT, OPS_ALERTS, CUSTOMER_WEBHOOKS, MCP_PRODUCT, FEATURE_FLAGS). Control center me read-only pills theek hai; flag FLIP UI se mat karo (env `.env` + recreate ka kaam, `automation-flags` skill). Ban-risky flags (WHATSAPP_AUTO_SEND etc.) pe warning text.

## Naya control/tab add karne ka pattern (5 steps)

1. **Route precheck**: `grep '@router' app/api/growth.py` (ya relevant router) — endpoint PEHLE se hai kya? Duplicate route = FastAPI first-route-wins shadow bug (festivals lesson).
2. **Backend (agar missing)**: growth.py style — `require_admin` + rate-limit, never-raise, existing engine reuse. Heavy/ML/KB kaam endpoint me = `asyncio.to_thread` + hard timeout (widget-chat prod-down lesson).
3. **Tab**: `frontend/automation.html` — sidebar `<button id="tab-X" onclick="show('X')">` + `<section class="tabsec" id="sec-X">` + existing `api()` helper (accessToken localStorage, admin-login link). Dark theme CSS vars (`--bg --card --acc`) hi use karo — naya color system mat banao. Mobile: existing `@media(max-width:760px)` me sidebar wrap hota hai — wide tables ko `overflow:auto` wrapper do. PWA manifest link already head me hai.
4. **Verify**: `python scripts/check_html_js.py` (node --check) + targeted pytest. Status-fetch tabs me 60s auto-refresh sirf tab-visible pe (ops.html pattern) — har tab pe nahi (API load).
5. **Ship**: `leadgen-ops` loop. Naya `@app.get` page-route = **HARD RELOAD** on VPS. Done → SESSION_LOG append + CLAUDE.md tab-count 1-line.

## Coverage audit (control center "advanced" rakhne ka tarika)
Mahine me ek baar (ya naya router merge hote hi):
```bash
grep -c '@router' app/api/growth.py            # endpoints
grep -c 'onclick="show(' frontend/automation.html  # tabs
```
Phir endpoint-list vs tabs map karo — jo admin endpoint kisi tab/button se reachable nahi, woh gap hai. Kam-frequency cheezein (loyalty/nps/webhooks) backlog me likho, high-frequency turant tab do.

## Division of labour (duplicate UI mat banao)
- `/app/automation` = **action cockpit** (run/assign/approve) — yeh skill.
- `/app/ops` = system **health monitor** (dead-man table, LLM providers, DLQ) — sirf read.
- `/app/team` = staff events feed · `/app/agents` = coordinator/debate UI · `/app/growth-tools` = marketing drafters.
- Naya control kahan jaye confuse ho to: side-effect/approval wala = automation, read-only health = ops.

## Gotchas
- Token key **`accessToken`** (admin pages) — customer wala `lgai_token` use mat karo.
- Result render `pre` me JSON dump se behtar: table/badge/pill (existing helpers). User Hinglish copy expect karta hai.
- Side-effect buttons (send/call/auto-enable) = confirm() + flag-state dikhana; draft-only actions free chalao.
- Sandbox mount STALE — HTML edits Windows file-tools se, verify Windows pe.
- Bade parallel edits same file pe = truncation risk (parallel-batch-build skill).

## Enterprise gate

- **Operating loop**: Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). Naya tab/control = "Naya control add karne ka pattern" (upar 5 steps) hi hai — step-1 `grep '@router'` MANDATORY (duplicate-route-guard).
- **Risk-tier: Standard** (admin UI + read/trigger endpoints). Locks: `duplicate-route-guard` grep · `require_admin` + rate-limit on naya endpoint · flag-state surface · changed-file pytest + `check_html_js.py` · VPS **hard-reload** for naya `@app.get` page-route.
- **This page IS the observability surface** — control center hi `automation_health` (dead-man overdue), agent events, flags pills, run histories ko operator ke saamne laata. Naya backend automation merge = yahaan tab/badge bhi add karo, warna observability gap (CLAUDE.md: API-only = adhoora).
- **Safety boundaries**: side-effect buttons = `confirm()` + flag-state dikhao; **flag FLIP UI se KABHI nahi** (env `.env` + recreate ka kaam — `automation-flags`); ban-risky flags (`WHATSAPP_AUTO_SEND` etc.) pe warning text. Heavy/ML/KB endpoint kaam = `asyncio.to_thread` + hard timeout (widget-chat prod-down lesson).
- **Rollback (NAMED)**: bad UI/endpoint = revert frontend/HTML + container recreate (page-route hard-reload); naya endpoint flag-gated ho to flag OFF.
- **Evidence (done)**: `python scripts\check_html_js.py` (node --check) + `.venv\Scripts\python.exe scripts\prod_check.py` + targeted pytest + VPS pe page 200 (hard-reload ke baad, `scripts/check_route.py`) + tab live render.
