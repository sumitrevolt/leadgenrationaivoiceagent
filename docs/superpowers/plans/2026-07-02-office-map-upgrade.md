# Admin Virtual Office Upgrade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `/app/office` (Admin Virtual Office) to surface project architecture and
workflow (by embedding the already-built Control Center graph), enhance coordination
visualization with the spec'd-but-never-shipped Coordinator Room ticker, fix 4 agents that
show zero activity despite their automation flags being ON, tighten real-time freshness, and
make offline/idle status self-explanatory for a non-technical admin.

**Architecture:** Additive changes to 3 existing files (`app/platform/office_hq.py`,
`frontend/office_map.html`, `frontend/control_center_graph.html`) plus one new scheduled job
(`call_kpi_digest`) wired into `app/platform/team_scheduler.py`. No new database tables, no new
API endpoints except one tiny query-param addition already-supported by existing infra. Reuses
Control Center's already-vendored Sigma.js/Graphology/ELK graph via iframe rather than building
a second graph engine.

**Tech Stack:** FastAPI (Python 3.12), vanilla JS + Phaser 3.80 (office_map.html), Sigma.js v3 +
Graphology (control_center_graph.html, unchanged — only a tiny bootstrap addition), pytest.

## Global Constraints
- Never-raise / graceful-degrade convention: every new backend function wraps its body in
  try/except and returns a safe default on failure (matches every function in `office_hq.py`).
- No new DB tables/migrations — reuse `agent_events` (via `team.log_event`) for all new activity.
- No fabricated numbers — every new UI element must be backed by a real data source or omitted.
- Frontend has no JS test harness in this project — verification is manual via the
  `preview_*` browser tools (screenshot, console-error check, mobile 375px resize, click-through).
- Deploy to the live VPS uses the project's proven surgical pattern: `docker cp` into
  `leadgen_app` (+ `leadgen_worker`/`leadgen_scheduler` for the new job) followed by
  `docker restart`, never a blind `git pull` on the VPS (see project memory
  `vps-uncommitted-migrations-audit-2026-07-01.md` for why). This plan's tasks are Windows-local
  implementation + tests; deployment is a separate final step done the same way as every other
  batch this session.

---

## Task 1: `offline_reason` field in `build_rooms_and_agents()`

**Files:**
- Modify: `app/platform/office_hq.py:263-351` (`build_rooms_and_agents`)
- Test: `tests/test_office_hq.py` (new file)

**Interfaces:**
- Produces: each agent dict in the `agents` list returned by `build_rooms_and_agents()` gains
  a new key `offline_reason: str | None` — `None` when `status != "offline"`; one of
  `"flag_off:<FLAG_NAME>"`, `"no_data_today"`, or `"unknown"` when `status == "offline"`.
  Consumed by Task 5 (frontend tooltip).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_office_hq.py
"""Tests for app.platform.office_hq — offline_reason classification (Task 1)."""
from __future__ import annotations

from app.platform import office_hq


def test_offline_reason_flag_off(monkeypatch):
    monkeypatch.delenv("SOCIAL_ENGINE", raising=False)  # unset = off
    reason = office_hq.classify_offline_reason("zara")
    assert reason == "flag_off:SOCIAL_ENGINE"


def test_offline_reason_flag_on_no_data(monkeypatch):
    monkeypatch.setenv("CADENCE_ENGINE", "1")
    reason = office_hq.classify_offline_reason("anika")
    assert reason == "no_data_today"


def test_offline_reason_unknown_member():
    reason = office_hq.classify_offline_reason("not_a_real_key")
    assert reason == "unknown"


def test_offline_reason_never_raises(monkeypatch):
    # Simulate a broken env read — must still return a string, never raise.
    monkeypatch.setattr(office_hq.os, "environ", None)
    reason = office_hq.classify_offline_reason("zara")
    assert isinstance(reason, str)


def test_build_rooms_and_agents_includes_offline_reason_only_when_offline():
    rooms, agents = office_hq.build_rooms_and_agents()
    for a in agents:
        if a["status"] == "offline":
            assert a["offline_reason"] is not None
            assert isinstance(a["offline_reason"], str)
        else:
            assert a["offline_reason"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_office_hq.py -v`
Expected: FAIL with `AttributeError: module 'app.platform.office_hq' has no attribute 'classify_offline_reason'`

- [ ] **Step 3: Write minimal implementation**

Add to `app/platform/office_hq.py`, right after the `RUNNABLE_MEMBERS` constant (after line 103):

```python
# Member key -> the single env flag that gates their underlying automation
# engine, for offline_reason classification. Only members whose "offline"
# state is EXPLAINED by a known off-by-design flag go here — everyone else
# offline is either genuinely idle (no matching data today) or unknown.
_MEMBER_GATING_FLAG: dict[str, str] = {
    "priya": "CRM_SYNC",
    "zara": "SOCIAL_ENGINE",
    "anika": "CADENCE_ENGINE",
    "ira": "JOURNEY_ENGINE",
    "raksha": "CALL_TRANSFER",
}


def classify_offline_reason(key: str) -> str:
    """Why a member shows offline — 'flag_off:X' / 'no_data_today' / 'unknown'.

    Never raises (env read wrapped). Pure function, no IO beyond os.environ."""
    try:
        import os

        flag = _MEMBER_GATING_FLAG.get(key)
        if flag:
            val = (os.environ.get(flag) or "").strip().lower()
            if val not in ("1", "true", "yes"):
                return f"flag_off:{flag}"
            return "no_data_today"
        if key in STAFF:
            return "no_data_today"
        return "unknown"
    except Exception:
        return "unknown"
```

Note: `STAFF` must be imported for this function — it's already imported inside
`build_rooms_and_agents()` at runtime (`from app.platform.team import STAFF, team_status`),
which is NOT visible at module scope where `classify_offline_reason` is defined. Add a
module-level import instead. Change the import block at the top of `office_hq.py` (after the
existing `from app.utils.logger import setup_logger` line) to add:

```python
from app.platform.team import STAFF
```

This is safe — `team.py` has no dependency back on `office_hq.py` (checked: `grep -n
"office_hq" app/platform/team.py` returns nothing), so no circular import.

Now update `build_rooms_and_agents()` (`app/platform/office_hq.py:263-296`) — inside the `for
key, meta in STAFF.items():` loop, change the `agent = {...}` dict construction to add the new
field:

```python
            agent = {
                "id": key,
                "key": key,
                "name": meta.get("name", key),
                "emoji": meta.get("emoji", "🤖"),
                "title": meta.get("title", ""),
                "duties": meta.get("duties", ""),
                "room": room_id,
                "status": state,  # working|active|offline (see team.py windows)
                "offline_reason": classify_offline_reason(key) if state == "offline" else None,
                "todayActions": int(live.get("today_actions") or 0),
                "todayErrors": int(live.get("today_errors") or 0),
                "lastActivityAt": live.get("last_activity"),
                "runnable": key in RUNNABLE_MEMBERS,
                "paused": key in paused_set,
            }
```

Also remove the now-redundant local `from app.platform.team import STAFF, team_status` inside
`build_rooms_and_agents()` (line 272) — change it to just `from app.platform.team import
team_status` since `STAFF` is now module-level.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_office_hq.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add app/platform/office_hq.py tests/test_office_hq.py
git commit -m "feat(office): classify why an agent shows offline (flag-off vs no-data-today)"
```

---

## Task 2: Investigate + fix Priya/Anika/Ira (flag ON, zero activity)

**Files:**
- Read (investigation only, no edit expected unless a bug is confirmed):
  `app/telephony/post_call_hooks.py:90-124` (Priya/crm_sync — already traced this session,
  confirmed correctly wired from `vobiz_stream.py:2691`, no code change needed here)
  `app/marketing/cadence.py:167-` (`run_due`), `app/platform/team_scheduler.py:390`
  (Anika — scheduler wiring confirmed present)
  `app/marketing/journeys.py:329-` (`emit_event`), `app/platform/inquiry_hooks.py:229`
  (Ira — hook wiring confirmed present)
- Test: `tests/test_office_hq.py` (extend from Task 1)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — this task is a diagnostic gate. It either confirms "no bug, these 3
  are legitimately idle today" (already the working hypothesis from same-session investigation:
  all 3 have confirmed real trigger wiring — `apply_qualified_downstream` for Priya IS called
  from `vobiz_stream.py:2691`; `cadence.run_due()` IS called from `team_scheduler.py:390`;
  `journeys.emit_event()` IS called from `inquiry_hooks.py:229`) — in which case Task 1's
  `offline_reason="no_data_today"` classification is the correct and complete fix, OR it
  surfaces a genuine bug, in which case add a fix sub-step here before committing.

- [ ] **Step 1: Confirm live trigger data exists/doesn't exist today (VPS, read-only)**

Run via SSH (same pattern used earlier this session):

```bash
"/c/Program Files/Git/usr/bin/ssh.exe" -i "C:/Users/Ratanshila/.ssh/id_rsa" -o StrictHostKeyChecking=no root@72.61.245.204 "docker exec leadgen_app python -c \"
import asyncio
from datetime import datetime, timedelta, timezone
async def main():
    from sqlalchemy import select
    from app.models.base import get_async_session
    from app.models.lead import Lead
    async with get_async_session() as session:
        today = (datetime.now(timezone.utc) - timedelta(hours=5, minutes=30)).replace(hour=0,minute=0,second=0,microsecond=0)
        rows = (await session.execute(select(Lead).limit(3000))).scalars().all()
        qualified_today = [r for r in rows if r.created_at and r.created_at >= today.replace(tzinfo=None) and int(r.lead_score or 0) >= 70]
        due_calls_today = [r for r in rows if r.next_call_at and r.next_call_at <= datetime.utcnow()]
        print('qualified_leads_today (Priya trigger candidates):', len(qualified_today))
        print('due_calls_today (proxy for cadence-due, Anika):', len(due_calls_today))
asyncio.run(main())
\" 2>&1 | grep -v '\"timestamp\"'"
```

Expected/likely outcome (per this session's earlier live snapshot check showing 0 today
actions across the board and low overall lead volume): both counts are 0 or very low, which
confirms "no matching data today", not a bug. **If either count is meaningfully positive** (say
>3) while the corresponding agent still shows 0 actions, that IS a real bug — stop here and
investigate the specific hook path with a debugger/print-trace before proceeding, do not
fabricate a fix without reproducing the gap.

- [ ] **Step 2: Write a regression test locking in the confirmed-correct wiring**

```python
# tests/test_office_hq.py (append)

def test_priya_downstream_hook_exists():
    """Regression guard: apply_qualified_downstream (which pushes to CRM as
    'priya') must still be called from the live Vobiz call-completion path.
    Confirmed present 2026-07-02 (app/telephony/vobiz_stream.py:2691) — this
    test fails loudly if that call site is ever removed/renamed, since a
    prior incident (2026-06-18) had exactly this class of cross-path-parity
    regression (AUTO_QUALIFY wired in call_manager but not vobiz_stream)."""
    import inspect

    from app.telephony import vobiz_stream

    src = inspect.getsource(vobiz_stream)
    assert "apply_qualified_downstream" in src


def test_anika_cadence_scheduler_wiring_exists():
    """Regression guard: cadence.run_due() must still be called from the
    scheduler. Confirmed present 2026-07-02 (team_scheduler.py:390)."""
    import inspect

    from app.platform import team_scheduler

    src = inspect.getsource(team_scheduler)
    assert "cadence.run_due" in src or "await cadence.run_due()" in src


def test_ira_journey_hook_wiring_exists():
    """Regression guard: journeys.emit_event() must still be called from the
    inquiry hook. Confirmed present 2026-07-02 (inquiry_hooks.py:229)."""
    import inspect

    from app.platform import inquiry_hooks

    src = inspect.getsource(inquiry_hooks)
    assert "journeys.emit_event" in src or "emit_event(" in src
```

- [ ] **Step 3: Run tests to verify they pass (confirming wiring is intact today)**

Run: `.venv/Scripts/python.exe -m pytest tests/test_office_hq.py -v -k "priya_downstream or anika_cadence or ira_journey"`
Expected: PASS (3 passed) — if any FAILS, the wiring regressed since this session's
investigation; stop and fix the specific broken call site before continuing to Task 3.

- [ ] **Step 4: Commit**

```bash
git add tests/test_office_hq.py
git commit -m "test(office): lock in Priya/Anika/Ira trigger-wiring as regression guards"
```

---

## Task 3: Fix Lekha (Call Analytics) — genuine bug, no scheduled job exists

**Files:**
- Modify: `app/voice_agent/call_analytics.py` (add a digest wrapper function)
- Modify: `app/platform/team_scheduler.py` (register new `call_kpi_digest` job)
- Modify: `app/platform/office_hq.py` (add `JOB_ROOM` entry)
- Test: `tests/test_call_analytics_digest.py` (new file)

**Interfaces:**
- Consumes: `compute_call_kpis(days: int = 7) -> dict[str, Any]` (existing function,
  `app/voice_agent/call_analytics.py:70`, unchanged signature).
- Produces: `run_daily_digest() -> dict[str, Any]` (new, in `call_analytics.py`) — calls
  `compute_call_kpis()`, logs a `team.log_event("lekha", "call_kpi_digest", <summary>)`, returns
  the KPI dict. Called by the new scheduler job.

**Root cause (confirmed this session):** `compute_call_kpis()` is only invoked from
`app/api/web_call_admin.py:69` — an on-demand admin-page endpoint, not an autonomous scheduled
job — and never calls `team.log_event()`. So Lekha can never show as "working"/"active" no
matter how much call data exists, because nothing ever logs an event under her key. This is a
missing-wiring bug, matching the exact class of bug the original 2026-07-01 spec already found
and partially fixed for 3 other agents (speed-to-lead digest, revenue_digest, growth_optimizer,
approvals_bridge — same "no log_event call" pattern).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_call_analytics_digest.py
"""Tests for the Lekha call-KPI daily digest (Task 3 — fixes missing log_event wiring)."""
from __future__ import annotations

from unittest.mock import patch

from app.voice_agent import call_analytics


def test_run_daily_digest_calls_compute_call_kpis():
    fake_kpis = {
        "total_calls": 12, "avg_duration_s": 145.2, "qualified_rate": 0.33,
        "booking_rate": 0.1, "p50_reply_latency_ms": 900, "p95_reply_latency_ms": 2200,
    }
    with patch.object(call_analytics, "compute_call_kpis", return_value=fake_kpis) as m:
        result = call_analytics.run_daily_digest()
    m.assert_called_once_with(days=1)
    assert result == fake_kpis


def test_run_daily_digest_logs_event_under_lekha():
    fake_kpis = {"total_calls": 5, "avg_duration_s": 88.0, "qualified_rate": 0.2}
    with patch.object(call_analytics, "compute_call_kpis", return_value=fake_kpis):
        with patch("app.platform.team.log_event") as mock_log:
            call_analytics.run_daily_digest()
    mock_log.assert_called_once()
    args, kwargs = mock_log.call_args
    assert args[0] == "lekha"
    assert args[1] == "call_kpi_digest"
    assert "5" in (args[2] if len(args) > 2 else kwargs.get("detail", ""))


def test_run_daily_digest_never_raises_on_compute_failure():
    with patch.object(call_analytics, "compute_call_kpis", side_effect=RuntimeError("boom")):
        result = call_analytics.run_daily_digest()
    assert result == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_call_analytics_digest.py -v`
Expected: FAIL with `AttributeError: module 'app.voice_agent.call_analytics' has no attribute 'run_daily_digest'`

- [ ] **Step 3: Write minimal implementation**

Add to `app/voice_agent/call_analytics.py`, after the existing `compute_call_kpis` function:

```python
def run_daily_digest() -> dict[str, Any]:
    """Lekha's daily call-KPI digest — the missing piece that makes her show
    'working' on the office map. compute_call_kpis() itself is only called
    on-demand from the admin dashboard today (app/api/web_call_admin.py) and
    never logs a team event; this wrapper is what a scheduled job calls.
    Never raises — degrades to {} on any failure so a scheduler tick can't
    break on this job."""
    try:
        kpis = compute_call_kpis(days=1)
    except Exception as e:
        logger.warning(f"[call_analytics] run_daily_digest compute failed: {e}")
        return {}
    try:
        from app.platform import team

        total = kpis.get("total_calls", 0)
        qrate = kpis.get("qualified_rate", 0)
        detail = f"Aaj {total} calls · qualified-rate {qrate:.0%}" if isinstance(qrate, (int, float)) else f"Aaj {total} calls"
        team.log_event("lekha", "call_kpi_digest", detail, status="ok")
    except Exception as e:
        logger.debug(f"[call_analytics] run_daily_digest log_event skipped: {e}")
    return kpis
```

Check `app/voice_agent/call_analytics.py` already imports `logger` and `Any` at the top — if
not, add `from typing import Any` and the project's standard `from app.utils.logger import
setup_logger; logger = setup_logger(__name__)` pattern (check the file's existing imports
first; this file already has other functions, so a logger likely already exists — reuse it,
don't create a second one).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_call_analytics_digest.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Wire into the scheduler**

In `app/platform/team_scheduler.py`, add `"call_kpi_digest": None,` to the `_last_ran` dict
(after the `"evening_wrap": None,` line, ~line 125).

Add a new `elif` branch inside `_run_job_inner` (after the `elif job == "digest":` block ends,
before the next `elif`):

```python
        elif job == "call_kpi_digest":
            from app.voice_agent import call_analytics

            call_analytics.run_daily_digest()
```

Add a new time-window check in the main scheduling loop (after the `evening_wrap` check, using
the (19,30)-(20,30) IST window — free, non-colliding with existing windows per the boot-grace
dict at lines 810-827):

```python
            if (19, 30) <= hm < (20, 30) and _last_ran["call_kpi_digest"] != day_key:
                _last_ran["call_kpi_digest"] = day_key
                await _run_job("call_kpi_digest")
```

- [ ] **Step 6: Add the JOB_ROOM mapping so blocked/error status surfaces correctly**

In `app/platform/office_hq.py`, add `"call_kpi_digest": "voice_team",` to the `JOB_ROOM` dict
(after the `"trainer": "qa_audit",` line, ~line 110).

- [ ] **Step 7: Verify import-safety**

Run: `.venv/Scripts/python.exe -c "import ast; ast.parse(open('app/platform/team_scheduler.py', encoding='utf-8').read()); ast.parse(open('app/voice_agent/call_analytics.py', encoding='utf-8').read()); ast.parse(open('app/platform/office_hq.py', encoding='utf-8').read()); print('SYNTAX_OK')"`
Expected: `SYNTAX_OK`

Run: `.venv/Scripts/python.exe -c "from app.platform import team_scheduler, office_hq; from app.voice_agent import call_analytics; print('IMPORT_OK')"`
Expected: `IMPORT_OK`

- [ ] **Step 8: Commit**

```bash
git add app/voice_agent/call_analytics.py app/platform/team_scheduler.py app/platform/office_hq.py tests/test_call_analytics_digest.py
git commit -m "fix(office): wire Lekha's call-KPI digest into the scheduler — was never scheduled, never logged"
```

---

## Task 4: Embed System Map panel (architecture) in office_map.html

**Files:**
- Modify: `frontend/control_center_graph.html:920-933` (`boot()` — read initial view from URL)
- Modify: `frontend/office_map.html` (new collapsible panel + iframe)

**Interfaces:**
- Consumes: `control_center_graph.html`'s existing iframe-embed design (already documented in
  its own header comment as "Standalone page meant to be embedded via `<iframe>`") and its
  existing `switchTo(viewKey)` function (`frontend/control_center_graph.html:879-886`).
- Produces: `control_center_graph.html` now accepts `?view=automation|structural|products` as
  an optional query param on initial load (defaults to `structural` if absent/invalid — zero
  behavior change for the existing Control Center L2 embed, which doesn't pass this param).

- [ ] **Step 1: Add URL-param initial-view support to control_center_graph.html**

Change `frontend/control_center_graph.html:920-933` (`boot()`) from:

```javascript
  function boot(){
    buildLegend();
    wireUI();
    const keys = Object.keys(VIEWS);
    keys.forEach(k => { graphCache[k] = buildGraph(k); });

    Promise.all(keys.map(k => layoutGraph(graphCache[k], k).then(pos => { layoutCache[k] = pos; })))
      .then(() => {
        loadingEl.classList.add('hidden');
        renderView('structural');
      })
      .catch(err => fail('Layout error: ' + (err && err.message ? err.message : err)));
  }
```

to:

```javascript
  function boot(){
    buildLegend();
    wireUI();
    const keys = Object.keys(VIEWS);
    keys.forEach(k => { graphCache[k] = buildGraph(k); });

    Promise.all(keys.map(k => layoutGraph(graphCache[k], k).then(pos => { layoutCache[k] = pos; })))
      .then(() => {
        loadingEl.classList.add('hidden');
        // Optional ?view=automation|structural|products — lets an embedder
        // (e.g. /app/office's System Map panel) open directly on a specific
        // view. Unknown/absent -> unchanged default 'structural' behavior.
        const params = new URLSearchParams(window.location.search);
        const requestedView = params.get('view');
        if (requestedView && VIEWS[requestedView]) {
          switchTo(requestedView);
        } else {
          renderView('structural');
        }
      })
      .catch(err => fail('Layout error: ' + (err && err.message ? err.message : err)));
  }
```

- [ ] **Step 2: Add the System Map panel to office_map.html**

Insert a new collapsible section into `frontend/office_map.html`, right after the pipeline
board closing `</div>` and before the `<div class="two-col">` (i.e. after line 190, before
line 192):

```html
    <div id="systemMapCard" class="panel-box">
      <h3 id="systemMapToggle" style="cursor:pointer;user-select:none">
        🏗️ System Map <span id="systemMapChevron">▸</span>
        <span style="font-weight:400;font-size:12px;color:var(--muted)">— live architecture (click to expand)</span>
      </h3>
      <div id="systemMapBody" style="display:none">
        <iframe id="systemMapFrame" src="" style="width:100%;height:520px;border:1px solid var(--line);border-radius:10px;background:#0f1117"
          title="Live architecture map"></iframe>
        <div style="margin-top:8px;font-size:12.5px">
          <a href="/app/control-center" target="_blank" rel="noopener">Open full Control Center →</a>
        </div>
      </div>
    </div>
```

Add the toggle behavior in the `<script>` block, near the other `document.getElementById(...).onclick`
wiring (after the `bannerRetry` onclick, ~line 982):

```javascript
  var systemMapLoaded = false;
  document.getElementById("systemMapToggle").onclick = function(){
    var body = document.getElementById("systemMapBody");
    var chevron = document.getElementById("systemMapChevron");
    var expanded = body.style.display !== "none";
    body.style.display = expanded ? "none" : "block";
    chevron.textContent = expanded ? "▸" : "▾";
    if (!expanded && !systemMapLoaded) {
      systemMapLoaded = true;
      document.getElementById("systemMapFrame").src = "/app/control-center/graph?view=automation";
    }
  };
```

Lazy-loads the iframe only on first expand (keeps initial page load light, matching the
project's collapsed-by-default admin-dashboard pattern this session already referenced).

- [ ] **Step 3: Browser-verify (manual — no JS test harness for this project's frontend)**

Use the `preview_start`/`preview_navigate` tools to load `/app/office` locally:
1. `preview_screenshot` — confirm the "🏗️ System Map" card renders collapsed by default.
2. `preview_click` on `#systemMapToggle` — confirm it expands and the iframe loads.
3. `preview_console_logs` (level: error) — confirm zero console errors from the iframe load.
4. `preview_click` the "Open full Control Center →" link — confirm it navigates correctly (or
   opens a new tab, per `target="_blank"`).

- [ ] **Step 4: Commit**

```bash
git add frontend/control_center_graph.html frontend/office_map.html
git commit -m "feat(office): embed live architecture map (Control Center L2) as a collapsible panel"
```

---

## Task 5: Recent Workflow Runs strip

**Files:**
- Modify: `frontend/office_map.html`

**Interfaces:**
- Consumes: `GET /api/growth/process/runs` (existing endpoint, already powers Control Center
  L3 — verify its exact response shape first via `grep -n "def.*process/runs\|@router.get.*process" app/api/growth_*.py` before writing the fetch, since this task must not guess field
  names).

- [ ] **Step 1: Confirm the exact endpoint path and response shape**

Run: `grep -rn "process/runs" app/api/*.py`

Read the matched handler function fully and note its exact response field names (e.g. `run_id`,
`mode`, `status`, `agents`, `started_at` — do not assume, confirm from the actual code before
Step 2).

- [ ] **Step 2: Add the strip to office_map.html**

Insert after the System Map card from Task 4 (or merge into the same panel area — decide based
on visual balance during Step 3's browser check):

```html
    <div id="workflowRunsCard" class="panel-box">
      <h3>⚙️ Recent Workflow Runs</h3>
      <div id="workflowRunsList"><div class="loading-note">⏳ Loading…</div></div>
    </div>
```

Add a render function (exact field mapping filled in from Step 1's findings — placeholder field
names below MUST be replaced with the real ones before this step is considered done):

```javascript
  OFFICE.fetchWorkflowRuns = async function(){
    try {
      var r = await fetch("/api/growth/process/runs?limit=5", { headers: hdrs() });
      if (!r.ok) throw new Error("HTTP " + r.status);
      var d = await r.json();
      return (d && (d.runs || d)) || [];
    } catch (e) {
      return [];
    }
  };

  OFFICE.renderWorkflowRuns = function(runs){
    var card = document.getElementById("workflowRunsCard");
    var list = document.getElementById("workflowRunsList");
    if (!runs || !runs.length) { card.style.display = "none"; return; }
    card.style.display = "block";
    list.innerHTML = runs.slice(0, 5).map(function(run){
      return '<div class="panel-event" data-run="' + esc(run.run_id || "") + '">' +
        '<div><b>' + esc(run.mode || "run") + '</b> — ' + esc(run.status || "?") + '</div>' +
        '<div class="pe-when">' + (run.agents ? run.agents.length + " agents · " : "") + relTime(run.started_at) + '</div>' +
      '</div>';
    }).join("");
    list.querySelectorAll("[data-run]").forEach(function(el){
      el.style.cursor = "pointer";
      el.onclick = function(){
        window.open("/app/control-center#workflow?run=" + encodeURIComponent(el.getAttribute("data-run")), "_blank");
      };
    });
  };
```

Wire it into the refresh cycle — add to `OFFICE.refreshSnapshot` (`frontend/office_map.html:985-995`):

```javascript
  OFFICE.refreshSnapshot = async function(){
    var data = await OFFICE.fetchSnapshot();
    if (!data) return;
    OFFICE.lastSnapshot = data;
    OFFICE.renderMembers(data);
    OFFICE.renderMetrics(data.metrics);
    OFFICE.renderNextActions(data.next_best_actions);
    OFFICE.renderPipeline(data.pipeline);
    OFFICE.renderApprovals(data.approvals);
    OFFICE.renderSystemHealth(data.system_health);
    OFFICE.fetchWorkflowRuns().then(OFFICE.renderWorkflowRuns);
  };
```

(Separate fetch, not blocking the main snapshot render — matches this session's earlier fix
philosophy on `command_center.html`: independent data sources should resolve independently, not
serialize.)

- [ ] **Step 3: Browser-verify**

`preview_screenshot` + `preview_network` (check the `/api/growth/process/runs` call succeeds
and the panel either shows real runs or correctly hides itself when there are none — per the
design's error-handling rule "empty/failed → hidden section, no error banner for an
empty-but-healthy state").

- [ ] **Step 4: Commit**

```bash
git add frontend/office_map.html
git commit -m "feat(office): recent workflow runs strip, deep-links to Control Center L3"
```

---

## Task 6: Coordinator Room ticker (the actual spec gap)

**Files:**
- Modify: `frontend/office_map.html`

**Interfaces:**
- Consumes: the existing `OFFICE.pollEvents` event stream (`frontend/office_map.html:895-912`)
  and `OFFICE.avatars` (existing per-avatar Phaser objects, `frontend/office_map.html:348`).
- Produces: `OFFICE.MANAGER_SESSION_ACTIONS` (new constant, session-bookend action names) and
  `OFFICE.updateCoordinatorTicker(event)` (new function).

- [ ] **Step 1: Add the session-bookend action set and ticker rendering**

Add near the existing `OFFICE.COORD_ACTIONS` constant (`frontend/office_map.html:871`):

```javascript
  OFFICE.COORD_ACTIONS = { coordinated_step: 1, fanout_step: 1, hier_step: 1, adv_step: 1, av_contrib: 1 };

  // Session bookends — manager-only events marking a multi-agent run's start/end.
  // These were spec'd (2026-07-01 design, "Coordinator Room ticker") but never
  // shipped — the office map only ever showed individual step-tokens with no
  // "this is one run" framing. Confirmed live in app/agents/coordinator.py.
  OFFICE.MANAGER_START_ACTIONS = { coordinate_start: 1, hier_start: 1, advanced_start: 1, council_start: 1 };
  OFFICE.MANAGER_DONE_ACTIONS = { coordinate_done: 1, hier_done: 1, advanced_done: 1, council_done: 1 };
  OFFICE.coordinatorTickerLines = [];  // most-recent-first, capped at 6

  OFFICE.pushCoordinatorTicker = function(text){
    OFFICE.coordinatorTickerLines.unshift(text);
    OFFICE.coordinatorTickerLines = OFFICE.coordinatorTickerLines.slice(0, 6);
    var el = document.getElementById("coordinatorTicker");
    if (el) {
      el.innerHTML = OFFICE.coordinatorTickerLines.map(function(l){
        return '<div class="pe-when">' + esc(l) + '</div>';
      }).join("");
    }
  };
```

- [ ] **Step 2: Hook the bookend detection into pollEvents**

Modify `OFFICE.pollEvents` (`frontend/office_map.html:895-912`) — inside the
`fresh.slice().reverse().forEach(function(e){...})` loop, after the existing
`OFFICE.spawnBubble(...)` and `OFFICE.COORD_ACTIONS` check block, add:

```javascript
      if (e.member === "manager" && OFFICE.MANAGER_START_ACTIONS[e.action]) {
        OFFICE.pushCoordinatorTicker("▶ " + (e.detail || e.action));
      } else if (e.member === "manager" && OFFICE.MANAGER_DONE_ACTIONS[e.action]) {
        OFFICE.pushCoordinatorTicker("✓ " + (e.detail || e.action));
      }
```

(Full modified function, for clarity — this replaces `frontend/office_map.html:895-912`:)

```javascript
  OFFICE.pollEvents = async function(){
    var events = await OFFICE.fetchEvents(60);
    OFFICE.allEvents = events;
    OFFICE.renderTicker(events);
    if (!OFFICE.eventsSeeded){
      events.forEach(function(e){ OFFICE.seenEventIds[e.id] = true; });
      OFFICE.eventsSeeded = true;
      return;
    }
    var fresh = events.filter(function(e){ return !OFFICE.seenEventIds[e.id]; });
    fresh.slice().reverse().forEach(function(e){
      OFFICE.seenEventIds[e.id] = true;
      OFFICE.spawnBubble(e.member, e.detail || e.action);
      if (OFFICE.COORD_ACTIONS[e.action] && e.member !== "manager") {
        OFFICE.spawnWorkflowToken("manager", e.member);
      }
      if (e.member === "manager" && OFFICE.MANAGER_START_ACTIONS[e.action]) {
        OFFICE.pushCoordinatorTicker("▶ " + (e.detail || e.action));
      } else if (e.member === "manager" && OFFICE.MANAGER_DONE_ACTIONS[e.action]) {
        OFFICE.pushCoordinatorTicker("✓ " + (e.detail || e.action));
      }
    });
  };
```

- [ ] **Step 3: Add the ticker's DOM element inside the Coordinator room**

The Coordinator room is drawn via Phaser (`OFFICE.drawRooms`, `frontend/office_map.html:297-318`)
— it's a canvas, not real DOM, so an HTML ticker can't live "inside" it directly. Add it as a
small overlay positioned near the room's on-screen bounds instead: insert into
`frontend/office_map.html` right after the `<div id="roomTooltip"></div>` line (~204):

```html
  <div id="coordinatorTickerBox" style="position:absolute;display:none;background:#fff;border:1px solid var(--line);
    border-radius:8px;padding:6px 10px;max-width:280px;font-size:11px;box-shadow:0 2px 8px rgba(0,0,0,.08);z-index:15">
    <div style="font-weight:700;margin-bottom:3px">🧑‍💼 Coordinator log</div>
    <div id="coordinatorTicker"></div>
  </div>
```

Position it using the same `OFFICE.worldToPage` helper already used for `roomTooltip`
(`frontend/office_map.html:289-295`). Add positioning logic to `OFFICE.drawRooms` right after
the Coordinator room's label is created (the Coordinator room is `OFFICE.ROOMS[0]`, `x:0, y:0,
w:1200, h:120`) — after the `OFFICE.drawRoomDecor(room, ix, iy, iw, ih);` line inside the
`OFFICE.ROOMS.forEach` loop, add:

```javascript
      if (room.id === "coordinator") {
        var tickerBox = document.getElementById("coordinatorTickerBox");
        var pagePos = OFFICE.worldToPage(room.x + room.w - 290, room.y + 30);
        tickerBox.style.left = pagePos.x + "px";
        tickerBox.style.top = pagePos.y + "px";
        tickerBox.style.display = "block";
      }
```

- [ ] **Step 4: Browser-verify**

Use `preview_click` to trigger a manual "Run now" on the `manager` agent (via the existing
agent panel — `manager` is in `RUNNABLE_MEMBERS`), then `preview_screenshot` to confirm the
Coordinator ticker box appears near the Coordinator room and shows a "▶ ..." line, and (once
the mock/real coordinate flow completes) a "✓ ..." line. If no real coordinator run is easy to
trigger in the local dev environment, verify via `preview_eval` by manually calling
`OFFICE.pushCoordinatorTicker("▶ test session")` in the console and confirming the box renders.

- [ ] **Step 5: Commit**

```bash
git add frontend/office_map.html
git commit -m "feat(office): Coordinator Room ticker — session start/end log (2026-07-01 spec gap, never shipped)"
```

---

## Task 7: Active Coordination panel

**Files:**
- Modify: `frontend/office_map.html`

**Interfaces:**
- Consumes: the same `OFFICE.MANAGER_START_ACTIONS`/`OFFICE.MANAGER_DONE_ACTIONS` from Task 6.
- Produces: `OFFICE.activeCoordinations` (in-memory session tracker, keyed by a synthetic
  session id derived from the start event's `id`).

- [ ] **Step 1: Track sessions client-side in pollEvents**

Add near the Task 6 constants:

```javascript
  OFFICE.activeCoordinations = {};  // sessionId -> {mode, startedAt, agentsInvolved: Set}

  OFFICE.renderActiveCoordinations = function(){
    var el = document.getElementById("activeCoordList");
    var card = document.getElementById("activeCoordCard");
    var sessions = Object.keys(OFFICE.activeCoordinations).map(function(k){ return OFFICE.activeCoordinations[k]; });
    if (!sessions.length) { card.style.display = "none"; return; }
    card.style.display = "block";
    el.innerHTML = sessions.map(function(s){
      return '<div class="panel-event"><div><b>' + esc(s.mode) + '</b> — ' + s.agentsInvolved.size + ' agent(s) so far</div>' +
        '<div class="pe-when">Shuru hua ' + relTime(s.startedAt) + '</div></div>';
    }).join("");
  };
```

- [ ] **Step 2: Extend the pollEvents loop from Task 6**

In the same `fresh.slice().reverse().forEach` block, extend the bookend-detection branch (this
replaces the block added in Task 6 Step 2):

```javascript
      if (e.member === "manager" && OFFICE.MANAGER_START_ACTIONS[e.action]) {
        OFFICE.pushCoordinatorTicker("▶ " + (e.detail || e.action));
        OFFICE.activeCoordinations[e.id] = { mode: e.action.replace("_start", ""), startedAt: e.at, agentsInvolved: new Set() };
        OFFICE.renderActiveCoordinations();
      } else if (e.member === "manager" && OFFICE.MANAGER_DONE_ACTIONS[e.action]) {
        OFFICE.pushCoordinatorTicker("✓ " + (e.detail || e.action));
        // Close the OLDEST open session of a matching mode (best-effort pairing
        // — action tags don't carry a session id, so this is a heuristic, same
        // honesty caveat as the existing workflow-token: approximate, not a
        // guaranteed-accurate process graph).
        var doneMode = e.action.replace("_done", "");
        var openKey = Object.keys(OFFICE.activeCoordinations).find(function(k){
          return OFFICE.activeCoordinations[k].mode === doneMode;
        });
        if (openKey) delete OFFICE.activeCoordinations[openKey];
        OFFICE.renderActiveCoordinations();
      } else if (OFFICE.COORD_ACTIONS[e.action] && e.member !== "manager") {
        OFFICE.spawnWorkflowToken("manager", e.member);
        Object.keys(OFFICE.activeCoordinations).forEach(function(k){
          OFFICE.activeCoordinations[k].agentsInvolved.add(e.member);
        });
      }
```

Note this supersedes Task 6 Step 2's simpler version — apply this combined version instead (do
not apply both separately; if Task 6 was already committed, this is a follow-up edit to the
same block).

- [ ] **Step 3: Add the panel markup**

Insert after the `workflowRunsCard` from Task 5:

```html
    <div id="activeCoordCard" class="panel-box" style="display:none">
      <h3>🔗 Active Coordination</h3>
      <div id="activeCoordList"></div>
    </div>
```

- [ ] **Step 4: Browser-verify**

Same method as Task 6 Step 4 — trigger or simulate a `coordinate_start` event, confirm the
panel appears and shows agent count incrementing as `coordinated_step` events for non-manager
members arrive, then confirm it disappears on the matching `coordinate_done`.

- [ ] **Step 5: Commit**

```bash
git add frontend/office_map.html
git commit -m "feat(office): Active Coordination panel — persistent readable log of in-flight multi-agent runs"
```

---

## Task 8: Real-time tightening (poll/cache cadence + freshness badge)

**Files:**
- Modify: `app/platform/office_hq.py:157` (`_SNAPSHOT_CACHE_TTL`)
- Modify: `frontend/office_map.html:1032` (poll interval) + new freshness badge

**Interfaces:**
- No new interfaces — pure constant/UI tuning.

- [ ] **Step 1: Write the failing test for the cache/poll pairing invariant**

```python
# tests/test_office_hq.py (append)

def test_snapshot_cache_ttl_below_expected_poll_interval():
    """Regression guard for the exact bug class found+fixed 2026-07-01 (TTL 15s
    vs poll 25s meant the cache never once helped). TTL must stay BELOW the
    poll interval the frontend actually uses (15000ms, see office_map.html)
    so periodic polls benefit from the cache instead of always missing it."""
    FRONTEND_POLL_INTERVAL_S = 15  # frontend/office_map.html setInterval(...,15000)
    assert office_hq._SNAPSHOT_CACHE_TTL < FRONTEND_POLL_INTERVAL_S
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_office_hq.py::test_snapshot_cache_ttl_below_expected_poll_interval -v`
Expected: FAIL (`35 < 15` is False) — current TTL (35s) is above the OLD 25s poll, and this
test asserts against the NEW 15s poll interval, so it fails until Step 3 lands.

- [ ] **Step 3: Apply the tuning**

`app/platform/office_hq.py:157` — change:
```python
_SNAPSHOT_CACHE_TTL = 35
```
to:
```python
_SNAPSHOT_CACHE_TTL = 12
```

`frontend/office_map.html:1032` — change:
```javascript
  setInterval(function(){ OFFICE.refreshSnapshot(); }, 25000);
```
to:
```javascript
  setInterval(function(){ OFFICE.refreshSnapshot(); }, 15000);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_office_hq.py::test_snapshot_cache_ttl_below_expected_poll_interval -v`
Expected: PASS

- [ ] **Step 5: Add the freshness badge + manual refresh button**

Add to `frontend/office_map.html` inside the `.topbar` div, before `<div class="spacer">`
(~line 171):

```html
    <span id="freshnessBadge" style="font-size:11.5px;color:var(--muted)"></span>
    <button id="manualRefreshBtn" style="border:1px solid var(--line);background:#fff;border-radius:7px;
      padding:4px 10px;font-size:11.5px;font-weight:700;cursor:pointer">🔄 Refresh now</button>
```

Add the freshness-tracking + manual-refresh logic in the `<script>` block, right after
`OFFICE.refreshSnapshot` is defined (~after line 995):

```javascript
  OFFICE.lastRefreshAt = null;
  OFFICE.updateFreshnessBadge = function(){
    var el = document.getElementById("freshnessBadge");
    if (!el || !OFFICE.lastRefreshAt) return;
    var secs = Math.floor((Date.now() - OFFICE.lastRefreshAt) / 1000);
    el.textContent = "Updated " + secs + "s pehle";
  };
  setInterval(OFFICE.updateFreshnessBadge, 1000);

  document.getElementById("manualRefreshBtn").onclick = function(){
    var btn = document.getElementById("manualRefreshBtn");
    btn.disabled = true; btn.textContent = "⏳ Refreshing…";
    OFFICE.refreshSnapshot().finally(function(){
      btn.disabled = false; btn.textContent = "🔄 Refresh now";
    });
  };
```

Update `OFFICE.refreshSnapshot` itself to stamp `lastRefreshAt` — modify the top of the
function (`frontend/office_map.html:985-995`):

```javascript
  OFFICE.refreshSnapshot = async function(){
    var data = await OFFICE.fetchSnapshot();
    if (!data) return;
    OFFICE.lastSnapshot = data;
    OFFICE.lastRefreshAt = Date.now();
    OFFICE.updateFreshnessBadge();
    OFFICE.renderMembers(data);
    OFFICE.renderMetrics(data.metrics);
    OFFICE.renderNextActions(data.next_best_actions);
    OFFICE.renderPipeline(data.pipeline);
    OFFICE.renderApprovals(data.approvals);
    OFFICE.renderSystemHealth(data.system_health);
    OFFICE.fetchWorkflowRuns().then(OFFICE.renderWorkflowRuns);
  };
```

The manual refresh button intentionally calls the SAME `OFFICE.refreshSnapshot()` (which hits
the cached endpoint) rather than a cache-bypassing variant — with TTL now at 12s (below the
15s poll interval), a manual click will almost always get fresh data anyway since the cache
window is short; adding a separate cache-bust query param is unnecessary complexity for the
value it'd add (YAGNI).

- [ ] **Step 6: Browser-verify**

`preview_screenshot` — confirm "Updated Xs pehle" ticks up in real time and the manual refresh
button resets it to "Updated 0s pehle" (or close) on click.

- [ ] **Step 7: Commit**

```bash
git add app/platform/office_hq.py frontend/office_map.html tests/test_office_hq.py
git commit -m "perf(office): tighten poll/cache pairing 25s/35s -> 15s/12s + add freshness badge"
```

---

## Task 9: Admin-friendly clarity (legend + offline-reason tooltip + summary line)

**Files:**
- Modify: `frontend/office_map.html`

**Interfaces:**
- Consumes: `agent.offline_reason` from Task 1's backend change.

- [ ] **Step 1: Add the legend popover**

Add a `(?)` icon next to the page title (`frontend/office_map.html:169`, inside `.brand`):

```html
  <div class="topbar">
    <a class="brand" href="/app/admin"><span class="logo">🏢</span> Operating HQ</a>
    <span id="legendToggle" style="cursor:pointer;font-size:13px;color:var(--muted);
      border:1px solid var(--line);border-radius:50%;width:18px;height:18px;
      display:inline-flex;align-items:center;justify-content:center" title="Legend">?</span>
    <a class="back" href="/app/team">AI Staff Team (list view) →</a>
    <div class="spacer"></div>
    <span id="freshnessBadge" style="font-size:11.5px;color:var(--muted)"></span>
    <button id="manualRefreshBtn" style="border:1px solid var(--line);background:#fff;border-radius:7px;
      padding:4px 10px;font-size:11.5px;font-weight:700;cursor:pointer">🔄 Refresh now</button>
  </div>
  <div id="legendPopover" style="display:none;position:fixed;top:50px;left:16px;background:#fff;
    border:1px solid var(--line);border-radius:10px;padding:14px 16px;font-size:12.5px;
    box-shadow:0 8px 24px rgba(0,0,0,.12);z-index:30;max-width:320px">
    <div style="font-weight:800;margin-bottom:8px">Kaise padhein</div>
    <div>🟢 <b>Working</b> — abhi active</div>
    <div>🟡 <b>Active</b> — aaj kaam kiya, abhi rest</div>
    <div>⚪ <b>Offline</b> — aaj kuch nahi (hover karke reason dekho)</div>
    <div style="margin-top:6px">🟡 Golden dot — Coordinator ne kisi agent ko task diya</div>
    <div style="margin-top:6px">🏗️ System Map — live architecture, click to expand</div>
    <button id="legendClose" style="margin-top:10px;border:1px solid var(--line);background:#fff;
      border-radius:6px;padding:3px 10px;font-size:11.5px;cursor:pointer">Band karo</button>
  </div>
```

```javascript
  document.getElementById("legendToggle").onclick = function(){
    document.getElementById("legendPopover").style.display = "block";
  };
  document.getElementById("legendClose").onclick = function(){
    document.getElementById("legendPopover").style.display = "none";
  };
```

- [ ] **Step 2: Add the offline-reason tooltip on avatars**

Find `OFFICE.drawAvatar` (`frontend/office_map.html:377`) — it already wires a `pointerover`
handler for room tooltips at the room level (`OFFICE.showRoomTooltip`); avatars need their own.
Add an `OFFICE.OFFLINE_REASON_LABEL` map and extend the avatar's interactive handlers. First
add the label map near `OFFICE.STATE_COLOR` (`frontend/office_map.html:347`):

```javascript
  OFFICE.OFFLINE_REASON_LABEL = {
    "no_data_today": "Koi matching data aaj nahi mila — flag ON hai, bas kaam nahi aaya",
    "unknown": "Wajah pata nahi — dekho logs",
  };
  OFFICE.offlineReasonText = function(reason){
    if (!reason) return "";
    if (reason.indexOf("flag_off:") === 0) {
      return "Flag " + reason.slice(9) + " OFF hai (design se — enable nahi kiya gaya)";
    }
    return OFFICE.OFFLINE_REASON_LABEL[reason] || OFFICE.OFFLINE_REASON_LABEL.unknown;
  };
```

Then in `OFFICE.renderMembers` (`frontend/office_map.html:431-`), where the per-avatar `m`
object is built (line 443: `var m = { key: a.key, name: a.name, ... state: a.status };`), add
`offlineReason: a.offline_reason` to that object:

```javascript
        var m = { key: a.key, name: a.name, emoji: a.emoji, title: a.title, duties: a.duties, state: a.status, offlineReason: a.offline_reason };
```

In `OFFICE.drawAvatar` (need to check its exact body around line 377+ for where the avatar
sprite's interactive pointer handlers are attached — mirror the existing room-label
`pointerover`/`pointerout` pattern at `frontend/office_map.html:313-315`) — add:

```javascript
      if (m.state === "offline" && m.offlineReason) {
        sprite.on("pointerover", function(p){
          var tip = document.getElementById("roomTooltip");
          tip.innerHTML = "<b>" + esc(m.name) + " — offline</b><br>" + esc(OFFICE.offlineReasonText(m.offlineReason));
          tip.style.display = "block";
          OFFICE.moveRoomTooltip(p);
        });
        sprite.on("pointermove", function(p){ OFFICE.moveRoomTooltip(p); });
        sprite.on("pointerout", function(){ OFFICE.hideRoomTooltip(); });
      }
```

(Exact variable name for the avatar's Phaser sprite object must be confirmed by reading
`OFFICE.drawAvatar`'s full body before this edit — the plan's placeholder name is `sprite`;
replace with whatever the function actually calls it, found during Step 3's implementation.)

- [ ] **Step 3: Read the exact drawAvatar body before editing (implementer step, not skippable)**

Run: `sed -n '377,431p' frontend/office_map.html` (or open the file) to get the exact sprite
variable name and existing interactive setup, then adapt Step 2's snippet to match exactly —
this is called out explicitly because guessing the variable name would silently break avatar
rendering.

- [ ] **Step 4: Add the one-line plain-Hinglish summary**

Add above the KPI row (`frontend/office_map.html:175`, before `<div class="kpi-row"...>`):

```html
    <div id="statusSummary" style="font-size:13px;font-weight:600;color:var(--ink);margin-bottom:4px"></div>
```

Add the render logic — extend `OFFICE.renderMetrics` (`frontend/office_map.html:496-506`) to
also compute this line, since it already receives the full `metrics` object and has access to
`OFFICE.lastSnapshot` for agent counts:

```javascript
  OFFICE.renderStatusSummary = function(snapshot){
    var el = document.getElementById("statusSummary");
    if (!snapshot) return;
    var agents = snapshot.agents || [];
    var activeCount = agents.filter(function(a){ return a.status !== "offline"; }).length;
    var pending = ((snapshot.approvals || {}).counts || {}).pending || 0;
    var issues = (snapshot.system_health || {}).overdue ? snapshot.system_health.overdue.length : 0;
    var healthLine = issues > 0 ? issues + " automation issue(s)" : "sab automation healthy";
    el.textContent = activeCount + "/" + agents.length + " agents active · " +
      pending + " approvals pending · " + healthLine;
  };
```

Call it from `OFFICE.refreshSnapshot` (add alongside the other render calls, after
`OFFICE.renderMembers(data);`):

```javascript
    OFFICE.renderStatusSummary(data);
```

- [ ] **Step 5: Browser-verify**

`preview_screenshot` — confirm the summary line reads sensibly, the `(?)` legend opens/closes,
and hovering an offline avatar (e.g. Zara) shows "Flag SOCIAL_ENGINE OFF hai (design se —
enable nahi kiya gaya)" rather than a bare grey dot with no explanation.

- [ ] **Step 6: Commit**

```bash
git add frontend/office_map.html
git commit -m "feat(office): legend popover + offline-reason tooltip + plain-Hinglish status summary"
```

---

## Task 10: Full regression pass + deploy

**Files:** none new — verification + deploy only.

- [ ] **Step 1: Run the full new/touched test suite**

Run: `.venv/Scripts/python.exe -m pytest tests/test_office_hq.py tests/test_call_analytics_digest.py -v`
Expected: all PASS.

- [ ] **Step 2: Run prod_check.py**

Run: `.venv/Scripts/python.exe scripts/prod_check.py`
Expected: `[OK] ALL CHECKS PASSED`.

- [ ] **Step 3: Browser-verify the full page end-to-end**

Load `/app/office` in the preview browser, `preview_resize` to mobile (375px), confirm the
compact room-list view still works and the new panels degrade sensibly (stack vertically, no
horizontal overflow). `preview_console_logs` (level: error) for a final zero-error check.

- [ ] **Step 4: Commit any final fixes, then deploy**

Follow this session's proven surgical deploy pattern (docker cp into `leadgen_app` +
`leadgen_worker` + `leadgen_scheduler` for the new `call_kpi_digest` job, since it needs to run
from whichever process executes `team_scheduler.py`'s loop — confirm via `docker exec
leadgen_app printenv RUN_IN_PROCESS_SCHEDULER` which process that is before copying, matching
the pattern already used twice this session). Dry-run `git apply --check --3way` is NOT
reliable on this VPS (documented gotcha, see memory) — go straight to `docker cp` + syntax
check + restart, same as every other deploy this session.

---

## Self-Review Notes (author's own pass, not a subagent dispatch)

**Spec coverage:** §1 (System Map) → Task 4. §2 (Workflow Runs) → Task 5. §3 (Coordinator
ticker) → Task 6. §4 (Active Coordination panel) → Task 7. §5 (broken agents) → Tasks 2-3. §6
(real-time) → Task 8. §7 (admin-friendly) → Task 9. All spec sections covered.

**Placeholder scan:** Task 5 Step 2 and Task 9 Step 2 both contain an explicit, flagged
"confirm before writing" sub-step (exact response field names; exact sprite variable name)
rather than guessing — this is intentional, not a forbidden placeholder: guessing either would
silently break code, and both are called out as required investigation steps with a concrete
follow-up action, not left as "TODO: figure this out". Every other step has complete code.

**Type/name consistency:** `offline_reason` (Task 1, backend) → `offlineReason`/`offline_reason`
(Task 9, frontend `m.offlineReason` field mirrors backend `a.offline_reason` key) — consistent.
`classify_offline_reason` defined once (Task 1), consumed nowhere else redundantly.
`call_analytics.run_daily_digest` (Task 3) is the single new function name used consistently
across the scheduler wiring and its test.
