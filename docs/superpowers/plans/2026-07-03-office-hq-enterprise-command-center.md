# Office HQ Enterprise Command Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform `/app/office` into an enterprise-grade AI CEO command center with a command bar, Boss brief, structured priorities, room workloads, replay, and trust controls.

**Architecture:** Keep `/api/platform/office/snapshot` as the main payload. Add pure snapshot-derived builders in `app/platform/office_hq.py`, reuse existing admin-gated `/api/platform/office/ask`, and reshape `frontend/office_map.html` so the first screen is a war-room control surface while the animated map remains below it.

**Tech Stack:** FastAPI, pure Python snapshot builders, existing office HQ router, existing `hq_ask` and `run_agent_task`, vanilla HTML/CSS/JS, Phaser office map, pytest, `node --check`, `scripts/prod_check.py`.

## Global Constraints

- Preserve existing user edits in the dirty worktree. Stage only the files listed in the active task.
- No fake numbers, fake queues, or pretend actions.
- No outbound calls or auto-send from this page unless existing compliance gates pass.
- Boss command and Kaam Do stay draft-safe and bounded.
- Boss review remains recommend-only.
- DLQ retry and clear stay confirm-gated.
- Admin-gated routes remain admin-gated.
- Snapshot builders must never raise and must degrade to honest empty shapes.
- No new paid providers or dependencies.
- Mobile target is 380px without overlap or horizontal scroll.
- Use Hinglish UI copy where user-facing copy is added.

---

## File Structure

- Modify `app/platform/office_hq.py`
  - Add pure builders:
    - `build_boss_brief(snapshot: dict[str, Any]) -> dict[str, Any]`
    - `build_priority_actions(snapshot: dict[str, Any]) -> list[dict[str, Any]]`
    - `build_room_workloads(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]`
    - `build_replay(snapshot: dict[str, Any], limit: int = 20) -> dict[str, Any]`
  - Add snapshot keys:
    - `boss_brief`
    - `priority_actions`
    - `room_workloads`
    - `replay`
  - Keep legacy `next_best_actions` shape for existing consumers.

- Modify `app/api/office_hq.py`
  - Only if required by tests. The route `POST /api/platform/office/ask` already exists, so do not duplicate it.

- Modify `frontend/office_map.html`
  - Reorder first screen into CEO War Room.
  - Add command bar UI and result panel.
  - Add Boss Brief, Priority Action Stack, War KPI cards, Pulse Strip.
  - Move `enterpriseCard` into a lower capabilities/proof area.
  - Upgrade room drawer with workload items.
  - Add replay and Operator/Theatre mode.
  - Add enterprise trust strip.

- Modify `tests/test_office_hq.py`
  - Builder contract tests.
  - Snapshot inclusion tests.
  - Deterministic priority ordering tests.

- Modify `tests/test_office_ask.py`
  - Ask endpoint contract and frontend-facing response shape.

---

### Task 1: Backend Command-Center Snapshot Builders

**Files:**
- Modify: `app/platform/office_hq.py`
- Modify: `tests/test_office_hq.py`

**Interfaces:**
- Consumes: existing snapshot sections `metrics`, `rooms`, `agents`, `pipeline`, `approvals`, `system_health`, `schedule`, `coordination`, `enterprise_features`.
- Produces:
  - `build_boss_brief(snapshot: dict[str, Any]) -> dict[str, Any]`
  - `build_priority_actions(snapshot: dict[str, Any]) -> list[dict[str, Any]]`
  - `build_room_workloads(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]`
  - `build_replay(snapshot: dict[str, Any], limit: int = 20) -> dict[str, Any]`
  - snapshot keys `boss_brief`, `priority_actions`, `room_workloads`, `replay`

- [ ] **Step 1: Write failing builder tests**

Append these tests to `tests/test_office_hq.py` near the existing `next_best_actions` tests:

```python
def _command_center_snapshot():
    return {
        "metrics": {
            "new_leads_today": 4,
            "qualified_leads_today": 2,
            "calls_completed_today": 3,
            "emails_sent_today": 7,
            "payments_pending": 1,
            "approvals_needed": 2,
            "system_issues": 1,
            "mrr": 5999,
        },
        "rooms": [
            {"id": "sales_crm", "name": "Sales / CRM Room", "activeTaskCount": 1, "blockedTaskCount": 2, "errorCount": 0, "approvalCount": 1, "agent_keys": ["rohan"]},
            {"id": "platform_engineering", "name": "Platform / Engineering", "activeTaskCount": 0, "blockedTaskCount": 0, "errorCount": 1, "approvalCount": 0, "agent_keys": ["kavya"]},
        ],
        "agents": [
            {"key": "rohan", "name": "Rohan", "status": "working", "room": "sales_crm", "todayActions": 8, "todayErrors": 0},
            {"key": "kavya", "name": "Kavya", "status": "active", "room": "platform_engineering", "todayActions": 3, "todayErrors": 1},
        ],
        "pipeline": [
            {"id": "scoring_qualification", "name": "Lead Scoring & Qualification", "count": 5, "stuckCount": 0, "errorCount": 0, "items": [
                {"id": "L1", "name": "Sharma Solar", "priority": "hot", "assignedAgentId": None, "slaRisk": False, "nextAction": "Call karo", "stageId": "scoring_qualification", "type": "lead"}
            ]},
            {"id": "conversation_followup", "name": "Conversation / Follow-up", "count": 2, "stuckCount": 2, "errorCount": 0, "items": [
                {"id": "L2", "name": "Ravi Clinic", "priority": "normal", "assignedAgentId": "rohan", "slaRisk": True, "nextAction": "Follow-up", "stageId": "conversation_followup", "type": "lead"}
            ]},
        ],
        "approvals": {"counts": {"pending": 2, "total_pending": 3}, "queue": [
            {"kind": "draft", "id": "d1", "title": "Sales draft", "source": "sales"}
        ]},
        "system_health": {"overdue": ["email_outreach"], "never_ran": [], "queue": {"dlq": 1}, "jobs": [
            {"job": "email_outreach", "status": "overdue"},
            {"job": "ops", "status": "ok"},
        ]},
        "schedule": [{"job": "email_outreach", "label": "Email outreach", "type": "recurring", "cadence": "hourly"}],
        "coordination": [{"goal": "clear hot replies", "mode": "sequential", "executed": False, "outcome": "draft", "at": "2026-07-03T05:00:00+00:00"}],
        "generated_at": "2026-07-03T05:00:00+00:00",
        "cached": False,
    }


def test_build_boss_brief_is_pure_and_actionable():
    out = office_hq.build_boss_brief(_command_center_snapshot())
    assert out["headline"]
    assert out["risk"]["label"]
    assert out["opportunity"]["label"]
    assert out["recommendation"]["cta_target"]
    assert out["confidence"] in ("high", "medium", "low")


def test_build_priority_actions_structured_and_ranked():
    actions = office_hq.build_priority_actions(_command_center_snapshot())
    assert actions
    assert len(actions) <= 5
    assert actions[0]["severity"] in ("critical", "high", "medium", "low")
    for item in actions:
        for key in ("id", "title", "why", "severity", "owner", "room", "cta_label", "cta_target"):
            assert key in item
    assert office_hq.build_priority_actions(_command_center_snapshot()) == actions


def test_build_room_workloads_maps_items_to_rooms():
    out = office_hq.build_room_workloads(_command_center_snapshot())
    assert "sales_crm" in out
    assert out["sales_crm"]["owner_count"] >= 1
    assert out["sales_crm"]["work_items"]
    assert out["platform_engineering"]["health"]["errors"] == 1


def test_build_replay_returns_timeline_without_io():
    out = office_hq.build_replay(_command_center_snapshot(), limit=10)
    assert out["items"]
    assert out["source"] == "snapshot"
    assert len(out["items"]) <= 10
    for row in out["items"]:
        assert row["title"] and row["actor"] and row["at"]


async def test_build_snapshot_includes_command_center_sections():
    snap = await office_hq.build_snapshot()
    for key in ("boss_brief", "priority_actions", "room_workloads", "replay"):
        assert key in snap
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_office_hq.py::test_build_boss_brief_is_pure_and_actionable tests\test_office_hq.py::test_build_priority_actions_structured_and_ranked tests\test_office_hq.py::test_build_room_workloads_maps_items_to_rooms tests\test_office_hq.py::test_build_replay_returns_timeline_without_io -q
```

Expected: FAIL with missing attributes such as `build_boss_brief`.

- [ ] **Step 3: Implement pure builders in `app/platform/office_hq.py`**

Insert these helpers after `next_best_actions()` and before `build_enterprise_features()`:

```python
def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(str(value or "low"), 3)


def _agent_name(snapshot: dict[str, Any], key: str, fallback: str = "Boss") -> str:
    try:
        for a in snapshot.get("agents") or []:
            if a.get("key") == key or a.get("id") == key:
                return str(a.get("name") or key)
    except Exception:
        pass
    return fallback


def build_boss_brief(snapshot: dict[str, Any]) -> dict[str, Any]:
    try:
        metrics = snapshot.get("metrics") or {}
        pipeline = {s.get("id"): s for s in (snapshot.get("pipeline") or [])}
        approvals = snapshot.get("approvals") or {}
        health = snapshot.get("system_health") or {}
        pending = int((approvals.get("counts") or {}).get("total_pending")
                      or (approvals.get("counts") or {}).get("pending") or 0)
        overdue = len(health.get("overdue") or [])
        dlq = int((health.get("queue") or {}).get("dlq") or 0)
        stuck_followups = int((pipeline.get("conversation_followup") or {}).get("stuckCount") or 0)
        hot = int((pipeline.get("scoring_qualification") or {}).get("count") or 0)
        risk_label = "System healthy"
        risk_target = "systemHealthPanel"
        if dlq:
            risk_label = f"{dlq} DLQ item(s) repair chahiye"
            risk_target = "failureConsoleCard"
        elif overdue:
            risk_label = f"{overdue} automation job overdue"
            risk_target = "systemHealthPanel"
        elif stuck_followups:
            risk_label = f"{stuck_followups} follow-up stuck"
            risk_target = "pipelineBoard"
        opportunity_label = f"{hot} hot lead(s) ready" if hot else "Aaj ka pipeline calm hai"
        if pending:
            recommendation = {"label": f"{pending} approval review karo", "cta_target": "approvalsPanel"}
        elif stuck_followups:
            recommendation = {"label": "Stuck follow-ups clear karo", "cta_target": "pipelineBoard"}
        elif hot:
            recommendation = {"label": "Hot leads pe Rohan ko lagao", "cta_target": "pipelineBoard"}
        else:
            recommendation = {"label": "Office feed monitor karo", "cta_target": "feedCard"}
        headline = (
            f"{metrics.get('new_leads_today', 0)} new leads, "
            f"{metrics.get('qualified_leads_today', 0)} qualified, "
            f"MRR Rs {int(metrics.get('mrr') or 0):,}"
        )
        confidence = "high" if snapshot.get("generated_at") else "medium"
        return {
            "headline": headline,
            "risk": {"label": risk_label, "cta_target": risk_target},
            "opportunity": {"label": opportunity_label, "cta_target": "pipelineBoard"},
            "recommendation": recommendation,
            "confidence": confidence,
            "source": "office_snapshot",
        }
    except Exception as e:
        logger.debug(f"[office_hq] build_boss_brief failed: {e}")
        return {
            "headline": "Office snapshot partial hai",
            "risk": {"label": "Data partial", "cta_target": "systemHealthPanel"},
            "opportunity": {"label": "Snapshot reload karo", "cta_target": "manualRefreshBtn"},
            "recommendation": {"label": "Refresh now", "cta_target": "manualRefreshBtn"},
            "confidence": "low",
            "source": "fallback",
        }
```

Then add:

```python
def build_priority_actions(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    try:
        approvals = snapshot.get("approvals") or {}
        health = snapshot.get("system_health") or {}
        pipeline = {s.get("id"): s for s in (snapshot.get("pipeline") or [])}
        pending = int((approvals.get("counts") or {}).get("total_pending")
                      or (approvals.get("counts") or {}).get("pending") or 0)
        dlq = int((health.get("queue") or {}).get("dlq") or 0)
        overdue = len(health.get("overdue") or [])
        stuck = int((pipeline.get("conversation_followup") or {}).get("stuckCount") or 0)
        hot = int((pipeline.get("scoring_qualification") or {}).get("count") or 0)
        retention_red = int((pipeline.get("retention_growth") or {}).get("errorCount") or 0)
        payments = int((snapshot.get("metrics") or {}).get("payments_pending") or 0)

        if dlq:
            actions.append({"id": "dlq", "title": f"{dlq} failed job(s)", "why": "Failed jobs can block automation trust.",
                            "severity": "critical", "owner": "hermes", "room": "platform_engineering",
                            "age": "", "cta_label": "Open Reliability", "cta_target": "failureConsoleCard"})
        if overdue:
            actions.append({"id": "overdue_jobs", "title": f"{overdue} overdue automation job(s)", "why": "Scheduled loops are missing their heartbeat.",
                            "severity": "high", "owner": "kavya", "room": "platform_engineering",
                            "age": "", "cta_label": "Open Health", "cta_target": "systemHealthPanel"})
        if pending:
            actions.append({"id": "approvals", "title": f"{pending} approval(s) pending", "why": "Human approval is blocking output.",
                            "severity": "high", "owner": "manager", "room": "coordinator",
                            "age": "", "cta_label": "Review Approvals", "cta_target": "approvalsPanel"})
        if stuck:
            actions.append({"id": "stuck_followups", "title": f"{stuck} follow-up(s) stuck", "why": "Warm leads lose value when follow-up is late.",
                            "severity": "high", "owner": "rohan", "room": "sales_crm",
                            "age": "", "cta_label": "Open Pipeline", "cta_target": "conversation_followup"})
        if retention_red:
            actions.append({"id": "retention", "title": f"{retention_red} client(s) churn-risk", "why": "Retention risk is revenue risk.",
                            "severity": "high", "owner": "nikhil", "room": "admin_finance",
                            "age": "", "cta_label": "Open Retention", "cta_target": "retention_growth"})
        if payments:
            actions.append({"id": "payments", "title": f"{payments} payment(s) pending", "why": "Cash collection needs operator attention.",
                            "severity": "medium", "owner": "nikhil", "room": "admin_finance",
                            "age": "", "cta_label": "Open Billing", "cta_target": "billing_subscription"})
        if hot:
            actions.append({"id": "hot_leads", "title": f"{hot} hot lead(s) ready", "why": "Best immediate sales opportunity.",
                            "severity": "medium", "owner": "rohan", "room": "sales_crm",
                            "age": "", "cta_label": "Open Hot Leads", "cta_target": "scoring_qualification"})
    except Exception as e:
        logger.debug(f"[office_hq] build_priority_actions failed: {e}")
    actions.sort(key=lambda a: (_severity_rank(a.get("severity", "low")), a.get("id", "")))
    return actions[:5]
```

Then add:

```python
def build_room_workloads(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    try:
        agents_by_room: dict[str, list[dict[str, Any]]] = {}
        for a in snapshot.get("agents") or []:
            agents_by_room.setdefault(str(a.get("room") or "platform_engineering"), []).append(a)
        for room in snapshot.get("rooms") or []:
            rid = str(room.get("id") or "")
            out[rid] = {
                "room": rid,
                "name": room.get("name") or rid,
                "owner_count": len(agents_by_room.get(rid, [])),
                "active_agents": [a.get("key") or a.get("id") for a in agents_by_room.get(rid, []) if a.get("status") != "offline"],
                "health": {
                    "active": int(room.get("activeTaskCount") or 0),
                    "blocked": int(room.get("blockedTaskCount") or 0),
                    "errors": int(room.get("errorCount") or 0),
                    "approvals": int(room.get("approvalCount") or 0),
                },
                "work_items": [],
                "source": "snapshot",
            }
        for item in build_priority_actions(snapshot):
            rid = item.get("room") or "coordinator"
            out.setdefault(rid, {"room": rid, "name": rid, "owner_count": 0, "active_agents": [], "health": {}, "work_items": [], "source": "snapshot"})
            out[rid]["work_items"].append(item)
        for room in out.values():
            room["work_items"] = room.get("work_items", [])[:3]
    except Exception as e:
        logger.debug(f"[office_hq] build_room_workloads failed: {e}")
    return out
```

Then add:

```python
def build_replay(snapshot: dict[str, Any], limit: int = 20) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    try:
        at = snapshot.get("generated_at") or _now().isoformat()
        for action in build_priority_actions(snapshot):
            items.append({"at": at, "actor": action.get("owner") or "manager", "title": action.get("title") or action.get("id"),
                          "detail": action.get("why") or "", "target": action.get("cta_target") or "", "kind": "priority"})
        for run in snapshot.get("coordination") or []:
            items.append({"at": run.get("at") or at, "actor": "manager", "title": str(run.get("goal") or "Coordination run")[:120],
                          "detail": str(run.get("outcome") or "")[:180], "target": "feedCard", "kind": "coordination"})
        for s in snapshot.get("pipeline") or []:
            if int(s.get("count") or 0):
                items.append({"at": at, "actor": "pipeline", "title": f"{s.get('name') or s.get('id')}: {s.get('count')} item(s)",
                              "detail": s.get("note") or "", "target": s.get("id") or "pipelineBoard", "kind": "pipeline"})
    except Exception as e:
        logger.debug(f"[office_hq] build_replay failed: {e}")
    return {"source": "snapshot", "items": items[:max(1, min(50, limit))]}
```

- [ ] **Step 4: Wire builders into `build_snapshot()`**

In `build_snapshot()`, after `snapshot["next_best_actions"] = next_best_actions(snapshot)`, add:

```python
    snapshot["boss_brief"] = build_boss_brief(snapshot)
    snapshot["priority_actions"] = build_priority_actions(snapshot)
    snapshot["room_workloads"] = build_room_workloads(snapshot)
    snapshot["replay"] = build_replay(snapshot)
```

Keep `snapshot["enterprise_features"] = build_enterprise_features(snapshot)` after these lines.

- [ ] **Step 5: Run builder tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_office_hq.py::test_build_boss_brief_is_pure_and_actionable tests\test_office_hq.py::test_build_priority_actions_structured_and_ranked tests\test_office_hq.py::test_build_room_workloads_maps_items_to_rooms tests\test_office_hq.py::test_build_replay_returns_timeline_without_io tests\test_office_hq.py::test_build_snapshot_includes_command_center_sections -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

Run:

```powershell
git add app/platform/office_hq.py tests/test_office_hq.py
git commit -m "feat: add office command center snapshot sections"
```

Expected: commit succeeds and only these two files are staged.

---

### Task 2: Lock the Boss Command Contract

**Files:**
- Modify: `tests/test_office_ask.py`
- Modify: `app/api/office_hq.py` only if the test proves the existing route contract is incomplete.

**Interfaces:**
- Consumes: existing `office_hq.hq_ask(q: str) -> dict[str, Any]`
- Produces: verified `POST /api/platform/office/ask` contract for frontend:
  - accepts JSON `{"q": "..." }`
  - returns keys `ok`, `kind`, `text`, optional `member`, `scope`, `run_id`

- [ ] **Step 1: Add frontend-facing endpoint test**

Append to `tests/test_office_ask.py`:

```python
def test_office_ask_endpoint_frontend_contract(monkeypatch):
    async def fake_ask(q):
        assert q == "aaj kya priority hai?"
        return {
            "ok": True,
            "kind": "question",
            "text": "Aaj hot replies clear karo.",
            "member": "",
            "scope": "",
            "run_id": "",
        }

    monkeypatch.setattr(hq, "hq_ask", fake_ask)
    r = client.post("/api/platform/office/ask", json={"q": "aaj kya priority hai?"})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["kind"] == "question"
    assert d["text"]
    assert "member" in d and "scope" in d and "run_id" in d
```

- [ ] **Step 2: Run the endpoint test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_office_ask.py::test_office_ask_endpoint_frontend_contract -q
```

Expected: PASS if current route already returns the required keys through mocked `hq_ask`. If it fails because fallback responses omit optional keys, continue Step 3.

- [ ] **Step 3: Normalize fallback response only if Step 2 fails**

In `app/api/office_hq.py`, change the exception fallback inside `office_ask()` to:

```python
        return {
            "ok": False,
            "kind": "question",
            "text": "",
            "member": "",
            "scope": "",
            "run_id": "",
            "error": str(e)[:300],
        }
```

- [ ] **Step 4: Run ask tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_office_ask.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add tests/test_office_ask.py app/api/office_hq.py
git commit -m "test: lock office ask command contract"
```

Expected: commit includes `app/api/office_hq.py` only if Step 3 changed it.

---

### Task 3: Build the CEO War Room First Screen

**Files:**
- Modify: `frontend/office_map.html`

**Interfaces:**
- Consumes snapshot keys from Task 1:
  - `boss_brief`
  - `priority_actions`
  - `metrics`
  - `agents`
  - `system_health`
- Produces frontend functions:
  - `OFFICE.renderCommandCenter(data)`
  - `OFFICE.renderBossBrief(brief)`
  - `OFFICE.renderPriorityActions(actions)`
  - `OFFICE.renderWarKpis(data)`
  - `OFFICE.renderPulseStrip(data)`
  - `OFFICE.askBoss()`

- [ ] **Step 1: Add War Room HTML shell**

In `frontend/office_map.html`, replace the top area after `<div id="statusSummary"...>` and before `<div id="mapToolbar">` with:

```html
    <section id="warRoom" class="war-room">
      <div class="command-card">
        <div class="command-head">
          <div>
            <div class="command-title">AI CEO Command Center</div>
            <div class="command-sub">Boss se pucho, team ko kaam do, aur top priorities clear karo.</div>
          </div>
          <div id="trustStrip" class="trust-strip"></div>
        </div>
        <div class="command-row">
          <input id="bossCommandInput" class="boss-command-input" placeholder="Boss se pucho ya kaam do..." autocomplete="off" />
          <button id="bossCommandBtn" class="boss-command-btn">Run</button>
        </div>
        <div id="bossCommandResult" class="command-result">Try: Aaj kya priority hai?</div>
      </div>

      <div class="war-grid">
        <div class="boss-brief-card">
          <div class="section-kicker">Boss Brief</div>
          <div id="bossBriefBody" class="boss-brief-body">Snapshot load ho raha hai...</div>
        </div>
        <div class="priority-card">
          <div class="section-kicker">Priority Actions</div>
          <div id="priorityActionStack" class="priority-stack"></div>
        </div>
        <div class="war-kpi-card">
          <div class="section-kicker">War KPIs</div>
          <div id="warKpiGrid" class="war-kpi-grid"></div>
        </div>
        <div class="pulse-card">
          <div class="section-kicker">Office Pulse</div>
          <div id="pulseStrip" class="pulse-strip"></div>
        </div>
      </div>
    </section>

    <details id="capabilitiesPanel" class="capabilities-panel">
      <summary>Capabilities proof</summary>
      <div id="enterpriseCard">
        <div class="enterprise-head">
          <div>
            <div class="enterprise-title">Advanced Virtual Office</div>
            <div class="enterprise-sub">20 enterprise-grade SaaS controls, live snapshot se wired.</div>
          </div>
          <div class="enterprise-score" id="enterpriseScore"></div>
        </div>
        <div class="feature-grid" id="enterpriseFeatureGrid">
          <div class="loading-note">Loading advanced office features...</div>
        </div>
      </div>
    </details>
```

Remove the old standalone `kpiRow`, `nbaCard`, and top-level `enterpriseCard` block from this top location. Keep the existing `kpiRow` element out of the first viewport. If an old renderer still needs it, keep it lower on the page in a collapsed `details`.

- [ ] **Step 2: Add War Room CSS**

Add after the existing Next best actions CSS:

```css
  .war-room{display:flex;flex-direction:column;gap:12px}
  .command-card,.boss-brief-card,.priority-card,.war-kpi-card,.pulse-card,.capabilities-panel{
    background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
  .command-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:10px}
  .command-title{font-size:18px;font-weight:900;letter-spacing:0}
  .command-sub{font-size:12.5px;color:var(--muted);margin-top:2px}
  .command-row{display:grid;grid-template-columns:1fr auto;gap:8px}
  .boss-command-input{border:1px solid var(--line);border-radius:8px;padding:10px 12px;font-size:14px;min-width:0}
  .boss-command-btn{border:none;border-radius:8px;background:var(--brand);color:#fff;font-weight:800;padding:0 18px;cursor:pointer}
  .boss-command-btn:disabled{background:#cbd5e1;cursor:not-allowed}
  .command-result{margin-top:8px;font-size:12.5px;color:var(--muted);line-height:1.45;white-space:pre-wrap}
  .war-grid{display:grid;grid-template-columns:1.15fr 1fr;gap:12px}
  .section-kicker{font-size:11px;font-weight:900;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;margin-bottom:8px}
  .boss-brief-body{font-size:13.5px;line-height:1.55}
  .brief-line{padding:5px 0;border-top:1px dashed var(--line)}
  .brief-line:first-child{border-top:none}
  .priority-stack{display:flex;flex-direction:column;gap:7px}
  .priority-item{border:1px solid var(--line);background:var(--bg);border-radius:10px;padding:9px;cursor:pointer}
  .priority-item:hover{border-color:var(--brand-2);background:#fff}
  .priority-top{display:flex;align-items:center;gap:8px;font-weight:900;font-size:13px}
  .priority-dot{width:8px;height:8px;border-radius:50%;flex:0 0 auto}
  .priority-meta{font-size:11.5px;color:var(--muted);margin-top:4px;line-height:1.35}
  .war-kpi-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
  .war-kpi{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:9px}
  .war-kpi b{display:block;font-size:18px;color:var(--ink);margin-top:2px}
  .war-kpi span{font-size:11px;color:var(--muted);font-weight:800;text-transform:uppercase}
  .pulse-strip{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;font-size:12.5px}
  .pulse-pill{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:8px}
  .trust-strip{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
  .trust-chip{border:1px solid var(--line);border-radius:999px;padding:3px 8px;font-size:10.5px;font-weight:800;background:var(--bg);color:var(--muted)}
  .capabilities-panel summary{cursor:pointer;font-weight:800;font-size:12.5px}
  @media (max-width:760px){
    .command-head{flex-direction:column}
    .command-row{grid-template-columns:1fr}
    .boss-command-btn{height:42px}
    .war-grid{grid-template-columns:1fr}
    .war-kpi-grid,.pulse-strip{grid-template-columns:1fr}
  }
```

- [ ] **Step 3: Add JS render functions**

Add after `OFFICE.renderNextActions`:

```javascript
  OFFICE.renderBossBrief = function(brief){
    var el = document.getElementById("bossBriefBody");
    if (!el) return;
    brief = brief || {};
    var risk = brief.risk || {};
    var opp = brief.opportunity || {};
    var rec = brief.recommendation || {};
    el.innerHTML =
      '<div class="brief-line"><b>' + esc(brief.headline || "Snapshot partial hai") + '</b></div>' +
      '<div class="brief-line">Risk: <a href="javascript:void(0)" data-cta="' + esc(risk.cta_target || "") + '">' + esc(risk.label || "No major risk") + '</a></div>' +
      '<div class="brief-line">Opportunity: <a href="javascript:void(0)" data-cta="' + esc(opp.cta_target || "") + '">' + esc(opp.label || "No immediate opportunity") + '</a></div>' +
      '<div class="brief-line">Next move: <a href="javascript:void(0)" data-cta="' + esc(rec.cta_target || "") + '">' + esc(rec.label || "Monitor office") + '</a></div>';
    Array.prototype.forEach.call(el.querySelectorAll("[data-cta]"), function(a){
      a.onclick = function(){ OFFICE.jumpToCta(a.getAttribute("data-cta")); };
    });
  };

  OFFICE.renderPriorityActions = function(actions){
    var el = document.getElementById("priorityActionStack");
    if (!el) return;
    actions = actions || [];
    if (!actions.length) {
      el.innerHTML = '<div class="empty-note">Koi urgent action nahi. Office normal chal raha hai.</div>';
      return;
    }
    var colors = { critical:"#ef4444", high:"#f59e0b", medium:"#3b82f6", low:"#10b981" };
    el.innerHTML = actions.map(function(a){
      return '<div class="priority-item" data-cta="' + esc(a.cta_target || "") + '">' +
        '<div class="priority-top"><span class="priority-dot" style="background:' + (colors[a.severity] || "#94a3b8") + '"></span>' +
          esc(a.title || a.id) + '</div>' +
        '<div class="priority-meta">' + esc(a.why || "") + '</div>' +
        '<div class="priority-meta">Owner: ' + esc(a.owner || "manager") + ' · Room: ' + esc(a.room || "coordinator") +
          ' · ' + esc(a.cta_label || "Open") + '</div>' +
      '</div>';
    }).join("");
    Array.prototype.forEach.call(el.querySelectorAll(".priority-item"), function(row){
      row.onclick = function(){ OFFICE.jumpToCta(row.getAttribute("data-cta")); };
    });
  };

  OFFICE.renderWarKpis = function(data){
    var el = document.getElementById("warKpiGrid");
    if (!el) return;
    var m = (data && data.metrics) || {};
    var items = [
      ["New leads", m.new_leads_today || 0],
      ["Qualified", m.qualified_leads_today || 0],
      ["Calls", m.calls_completed_today || 0],
      ["MRR", "Rs " + (m.mrr || 0)]
    ];
    el.innerHTML = items.map(function(x){
      return '<div class="war-kpi"><span>' + esc(x[0]) + '</span><b>' + esc(x[1]) + '</b></div>';
    }).join("");
  };

  OFFICE.renderPulseStrip = function(data){
    var el = document.getElementById("pulseStrip");
    if (!el) return;
    var agents = (data && data.agents) || [];
    var active = agents.filter(function(a){ return a.status !== "offline"; }).length;
    var health = (data && data.system_health) || {};
    var q = health.queue || {};
    var replay = ((data && data.replay) || {}).items || [];
    el.innerHTML =
      '<div class="pulse-pill"><b>' + active + '/' + agents.length + '</b><br>agents active</div>' +
      '<div class="pulse-pill"><b>' + ((health.overdue || []).length) + '</b><br>overdue jobs</div>' +
      '<div class="pulse-pill"><b>' + (q.dlq || 0) + '</b><br>DLQ</div>' +
      '<div class="pulse-pill"><b>' + replay.length + '</b><br>replay events</div>';
  };

  OFFICE.renderTrustStrip = function(data){
    var el = document.getElementById("trustStrip");
    if (!el) return;
    el.innerHTML =
      '<span class="trust-chip">Admin gated</span>' +
      '<span class="trust-chip">Draft-safe</span>' +
      '<span class="trust-chip">' + esc(data && data.cached ? "cached" : "fresh") + '</span>' +
      '<span class="trust-chip">' + esc(data && data.generated_at ? relTime(data.generated_at) : "loading") + '</span>';
  };

  OFFICE.renderCommandCenter = function(data){
    OFFICE.renderBossBrief(data && data.boss_brief);
    OFFICE.renderPriorityActions(data && data.priority_actions);
    OFFICE.renderWarKpis(data);
    OFFICE.renderPulseStrip(data);
    OFFICE.renderTrustStrip(data);
  };
```

- [ ] **Step 4: Wire command-bar submit**

Add after the command center render functions:

```javascript
  OFFICE.askBoss = async function(){
    var input = document.getElementById("bossCommandInput");
    var btn = document.getElementById("bossCommandBtn");
    var out = document.getElementById("bossCommandResult");
    if (!input || !btn || !out) return;
    var q = input.value.trim();
    if (!q) { out.textContent = "Message likho: Aaj kya priority hai?"; return; }
    btn.disabled = true;
    btn.textContent = "Running...";
    out.textContent = "Boss soch raha hai...";
    try {
      var r = await fetch("/api/platform/office/ask", {
        method: "POST",
        headers: hdrs(true),
        body: JSON.stringify({ q: q })
      });
      var d = r.ok ? await r.json() : null;
      if (d && d.text) out.textContent = d.text;
      else out.textContent = "Boss response nahi mila. Session/auth check karo.";
      if (d && d.kind === "task") {
        OFFICE.pollEvents();
        OFFICE.refreshSnapshot();
      }
    } catch (e) {
      out.textContent = "Network/auth issue. Dobara try karo.";
    }
    btn.disabled = false;
    btn.textContent = "Run";
  };
```

At the bottom near other button wiring, add:

```javascript
  document.getElementById("bossCommandBtn").onclick = OFFICE.askBoss;
  document.getElementById("bossCommandInput").addEventListener("keydown", function(e){
    if (e.key === "Enter") OFFICE.askBoss();
  });
```

- [ ] **Step 5: Call command-center renderer in refresh**

In `OFFICE.refreshSnapshot`, after metrics normalization and before `OFFICE.renderMetrics(data.metrics);`, add:

```javascript
    OFFICE.renderCommandCenter(data);
```

- [ ] **Step 6: Run JS syntax check**

Run:

```powershell
$html = Get-Content -Raw frontend\office_map.html
$m = [regex]::Match($html, '<script>([\s\S]*)</script>')
if (-not $m.Success) { throw 'script block not found' }
$m.Groups[1].Value | node --check
```

Expected: no output and exit code 0.

- [ ] **Step 7: Commit Task 3**

Run:

```powershell
git add frontend/office_map.html
git commit -m "feat: add office CEO war room first screen"
```

Expected: commit includes only `frontend/office_map.html`.

---

### Task 4: Room Workloads, Replay, and Operator/Theatre Mode

**Files:**
- Modify: `frontend/office_map.html`
- Modify: `tests/test_office_hq.py` only if Task 1 replay tests need extension.

**Interfaces:**
- Consumes snapshot keys `room_workloads`, `replay`.
- Produces frontend functions:
  - `OFFICE.renderReplay(data)`
  - `OFFICE.setOfficeMode(mode)`
  - upgraded `OFFICE.openRoomPanel(roomId)`

- [ ] **Step 1: Add mode toggle and replay panel HTML**

Under `</section>` for `warRoom`, add:

```html
    <div id="modeToggle" class="mode-toggle" aria-label="Office mode">
      <button class="mode-btn active" data-mode="operator">Operator</button>
      <button class="mode-btn" data-mode="theatre">Theatre</button>
    </div>

    <div id="replayPanel" class="panel-box">
      <h3>Aaj ka replay <span style="font-weight:400;font-size:12px;color:var(--muted)">- last office moves</span></h3>
      <div id="replayList"><div class="loading-note">Loading replay...</div></div>
    </div>
```

- [ ] **Step 2: Add mode/replay CSS**

Add near War Room CSS:

```css
  .mode-toggle{display:inline-flex;gap:4px;align-self:flex-start;background:#fff;border:1px solid var(--line);border-radius:8px;padding:3px}
  .mode-btn{border:none;background:transparent;border-radius:6px;padding:6px 12px;font-size:12px;font-weight:800;cursor:pointer;color:var(--muted)}
  .mode-btn.active{background:var(--brand);color:#fff}
  .replay-row{display:grid;grid-template-columns:86px 120px 1fr;gap:8px;border-top:1px solid var(--line);padding:7px 0;font-size:12.5px}
  .replay-row:first-child{border-top:none}
  .replay-time{color:var(--muted);font-variant-numeric:tabular-nums}
  .replay-actor{font-weight:800;color:var(--brand-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .replay-title{font-weight:700}
  .replay-detail{color:var(--muted);font-size:11.5px;margin-top:2px}
  body.office-theatre #warRoom{order:2}
  body.office-theatre #stageWrap{order:1}
  body.office-theatre #replayPanel{order:3}
  @media (max-width:760px){
    .replay-row{grid-template-columns:1fr}
  }
```

- [ ] **Step 3: Add replay and mode JS**

Add after `OFFICE.renderCommandCenter`:

```javascript
  OFFICE.renderReplay = function(data){
    var el = document.getElementById("replayList");
    if (!el) return;
    var rows = (((data || {}).replay || {}).items || []);
    if (!rows.length) {
      el.innerHTML = '<div class="empty-note">Aaj replay ke liye enough activity nahi mili.</div>';
      return;
    }
    el.innerHTML = rows.slice(0, 12).map(function(r){
      return '<div class="replay-row" data-cta="' + esc(r.target || "") + '">' +
        '<div class="replay-time">' + esc(relTime(r.at)) + '</div>' +
        '<div class="replay-actor">' + esc(r.actor || "office") + '</div>' +
        '<div><div class="replay-title">' + esc(r.title || "") + '</div>' +
        '<div class="replay-detail">' + esc(r.detail || "") + '</div></div>' +
      '</div>';
    }).join("");
    Array.prototype.forEach.call(el.querySelectorAll(".replay-row"), function(row){
      row.onclick = function(){ OFFICE.jumpToCta(row.getAttribute("data-cta")); };
    });
  };

  OFFICE.setOfficeMode = function(mode){
    mode = mode === "theatre" ? "theatre" : "operator";
    document.body.classList.toggle("office-theatre", mode === "theatre");
    Array.prototype.forEach.call(document.querySelectorAll(".mode-btn"), function(btn){
      btn.classList.toggle("active", btn.getAttribute("data-mode") === mode);
    });
    try { localStorage.setItem("officeMode", mode); } catch (e) {}
  };
```

At bottom wiring:

```javascript
  Array.prototype.forEach.call(document.querySelectorAll(".mode-btn"), function(btn){
    btn.onclick = function(){ OFFICE.setOfficeMode(btn.getAttribute("data-mode")); };
  });
  try { OFFICE.setOfficeMode(localStorage.getItem("officeMode") || "operator"); } catch (e) { OFFICE.setOfficeMode("operator"); }
```

In `OFFICE.refreshSnapshot`, add:

```javascript
    OFFICE.renderReplay(data);
```

- [ ] **Step 4: Upgrade room panel with workload**

In `OFFICE.openRoomPanel`, after `var room = ...`, add:

```javascript
    var workload = ((OFFICE.lastSnapshot || {}).room_workloads || {})[roomId] || {};
    var workRows = (workload.work_items || []).map(function(w){
      return '<div class="item-row" data-cta="' + esc(w.cta_target || "") + '" style="cursor:pointer">' +
        '<div class="ir-name">' + esc(w.title || w.id) + '</div>' +
        '<div class="ir-meta">' + esc(w.why || "") + '</div>' +
        '<div class="ir-meta">Owner: ' + esc(w.owner || "manager") + ' · ' + esc(w.cta_label || "Open") + '</div>' +
      '</div>';
    }).join("") || '<div class="empty-note">Is room ka live workload abhi clear hai.</div>';
```

In `body.innerHTML`, add this block before `agentsHtml`:

```javascript
      '<div class="panel-events"><div style="font-weight:800;margin:8px 0 4px">Room workload</div>' + workRows + '</div>' +
      '<div class="panel-events"><div style="font-weight:800;margin:8px 0 4px">Agents</div>' + agentsHtml + '</div>';
```

Then wire workload clicks:

```javascript
    Array.prototype.forEach.call(body.querySelectorAll(".item-row[data-cta]"), function(row){
      row.onclick = function(){ OFFICE.jumpToCta(row.getAttribute("data-cta")); };
    });
```

Keep existing agent row click wiring.

- [ ] **Step 5: Run JS syntax check**

Run:

```powershell
$html = Get-Content -Raw frontend\office_map.html
$m = [regex]::Match($html, '<script>([\s\S]*)</script>')
if (-not $m.Success) { throw 'script block not found' }
$m.Groups[1].Value | node --check
```

Expected: no output and exit code 0.

- [ ] **Step 6: Commit Task 4**

Run:

```powershell
git add frontend/office_map.html
git commit -m "feat: add office workload replay and modes"
```

Expected: commit includes only `frontend/office_map.html`.

---

### Task 5: Visual Polish, Mobile Craft, and Trust Layer

**Files:**
- Modify: `frontend/office_map.html`

**Interfaces:**
- Consumes all frontend functions from Tasks 3 and 4.
- Produces a first viewport that is command-center-first on desktop and mobile.

- [ ] **Step 1: Reduce first-screen noise**

In `#quickNav`, change the order and labels to:

```html
      <button class="qn-chip" data-jump="warRoom">War Room</button>
      <button class="qn-chip" data-jump="priorityActionStack">Priorities</button>
      <button class="qn-chip" data-jump="stageWrap">Map</button>
      <button class="qn-chip" data-jump="replayPanel">Replay</button>
      <button class="qn-chip" data-jump="pipelineBoard">Pipeline</button>
      <button class="qn-chip" data-jump="approvalsPanel">Approvals</button>
      <button class="qn-chip" data-jump="systemHealthPanel">Health</button>
      <button class="qn-chip" data-jump="failureConsoleCard">Reliability</button>
```

- [ ] **Step 2: Make `jumpToCta` robust for command center targets**

Replace `OFFICE.jumpToCta` with:

```javascript
  OFFICE.jumpToCta = function(cta){
    if (!cta) return;
    if (cta === "briefingBtn" || cta === "manualRefreshBtn") {
      var btn = document.getElementById(cta);
      if (btn) btn.click();
      return;
    }
    if (cta === "approvals") cta = "approvalsPanel";
    if (cta === "system_health") cta = "systemHealthPanel";
    var direct = document.getElementById(cta);
    if (direct) { direct.scrollIntoView({behavior:"smooth", block:"start"}); return; }
    OFFICE.openStagePanel(cta);
  };
```

- [ ] **Step 3: Add loading skeleton states**

In the War Room HTML, replace generic loading text with stable empty containers:

```html
          <div id="bossBriefBody" class="boss-brief-body"><div class="empty-note">Boss snapshot load ho raha hai...</div></div>
```

For `priorityActionStack`, add:

```html
          <div id="priorityActionStack" class="priority-stack"><div class="empty-note">Priorities load ho rahi hain...</div></div>
```

- [ ] **Step 4: Run HTML/JS checks**

Run:

```powershell
.\.venv\Scripts\python.exe scripts\check_html_js.py
$html = Get-Content -Raw frontend\office_map.html
$m = [regex]::Match($html, '<script>([\s\S]*)</script>')
if (-not $m.Success) { throw 'script block not found' }
$m.Groups[1].Value | node --check
```

Expected: HTML/JS check passes or reports only known unrelated pages. `node --check` must pass.

- [ ] **Step 5: Commit Task 5**

Run:

```powershell
git add frontend/office_map.html
git commit -m "style: polish office command center first viewport"
```

Expected: commit includes only `frontend/office_map.html`.

---

### Task 6: Verification, Browser Proof, and Deploy

**Files:**
- Modify only if verification finds a defect:
  - `app/platform/office_hq.py`
  - `app/api/office_hq.py`
  - `frontend/office_map.html`
  - `tests/test_office_hq.py`
  - `tests/test_office_ask.py`

**Interfaces:**
- Consumes completed Tasks 1-5.
- Produces deployed `/app/office` with live marker `AI CEO Command Center`.

- [ ] **Step 1: Run targeted office tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_office_hq.py tests/test_office_ask.py tests/test_office_task_dispatch.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend parse check**

Run:

```powershell
$html = Get-Content -Raw frontend\office_map.html
$m = [regex]::Match($html, '<script>([\s\S]*)</script>')
if (-not $m.Success) { throw 'script block not found' }
$m.Groups[1].Value | node --check
```

Expected: no output and exit code 0.

- [ ] **Step 3: Run production readiness**

Run:

```powershell
.\.venv\Scripts\python.exe scripts\prod_check.py
```

Expected: `[OK] ALL CHECKS PASSED - ready to deploy`.

- [ ] **Step 4: Run secrets scan**

Run:

```powershell
.\.venv\Scripts\python.exe scripts\check_secrets.py
```

Expected: `[OK] no secrets detected`. A gitignored `.codex/config.toml` advisory can remain commit-safe.

- [ ] **Step 5: Commit any verification fixes**

If Step 1-4 required code fixes, stage exact files only:

```powershell
git add app/platform/office_hq.py app/api/office_hq.py frontend/office_map.html tests/test_office_hq.py tests/test_office_ask.py
git commit -m "fix: harden office command center"
```

Expected: skip this step if no files changed.

- [ ] **Step 6: Push**

Run:

```powershell
C:\PROGRA~1\Git\cmd\git.exe push origin main
```

Expected: push succeeds and origin/main includes all command center commits.

- [ ] **Step 7: Deploy to VPS**

Run:

```powershell
C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 "set -o pipefail; cd /opt/leadgen && echo PRE_HEAD=$(git rev-parse --short HEAD) && git fetch --all -q && git reset --hard origin/main -q && echo POST_HEAD=$(git rev-parse --short HEAD) && docker compose -f docker-compose.vps.yml build app && docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps app worker worker-heavy scheduler"
```

Expected: Docker build succeeds, app/worker/worker-heavy/scheduler start healthy.

- [ ] **Step 8: Verify live**

Run:

```powershell
C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 "sleep 18 && curl -fsS https://leadsgenai.in/health && echo && sleep 5 && curl -fsS https://leadsgenai.in/health && echo && curl -fsS https://leadsgenai.in/app/office | grep -E 'AI CEO Command Center|warRoom' && docker exec leadgen_redis redis-cli llen celery"
```

Expected:

```text
"environment":"production"
"environment":"production"
AI CEO Command Center
0
```

If health fails, rollback by resetting `/opt/leadgen` to the previous good commit and rebuilding app.

---

## Self-Review Checklist

- Spec coverage:
  - First screen: Task 3.
  - Boss command bar: Task 2 and Task 3.
  - Boss brief: Task 1 and Task 3.
  - Structured priorities: Task 1 and Task 3.
  - Room workloads: Task 1 and Task 4.
  - Replay: Task 1 and Task 4.
  - Operator/Theatre mode: Task 4.
  - Enterprise trust strip: Task 3 and Task 5.
  - Mobile polish: Task 5.
  - Deploy proof: Task 6.
- Type consistency:
  - Backend key `priority_actions` matches frontend `data.priority_actions`.
  - Backend key `boss_brief` matches frontend `data.boss_brief`.
  - Backend key `room_workloads` matches frontend `data.room_workloads`.
  - Backend key `replay.items` matches frontend `data.replay.items`.
- Dirty worktree safety:
  - Every task stages exact files only.
  - No task uses `git add -A`.

