# Office HQ Enterprise Command Center Design

Date: 2026-07-03
Surface: `/app/office`
Goal: make the office feel like an enterprise-grade AI command center, not a map plus dashboard cards.

## Problem

The current office page has many useful parts: map, agents, feed, pipeline, approvals, DLQ, hot queue, schedule, briefing, and an advanced feature matrix. But the first impression is still not premium enough. It feels like a long admin dashboard with a virtual-office skin.

Enterprise-grade means the page should answer three questions immediately:

1. What matters right now?
2. Who or which agent owns it?
3. What action can I take in one click?

The map should support that story, not be the main thing by default.

## Recommended Approach

Use a hybrid "AI CEO Command Center" layout:

1. CEO War Room becomes the first screen.
2. The virtual office map becomes a living operations layer underneath.
3. A command bar sits at the top so the admin can ask Boss, assign work, and route tasks.

This is better than only improving the map because enterprise buyers judge the system by command, control, auditability, and speed to action. It is also better than replacing the page with a plain dashboard because the virtual office is part of the product personality and should remain.

## Alternatives Considered

### Option A: Polish Current Page
Improve spacing, colors, icons, cards, and order. Fast, but still feels like "more cards".

### Option B: Full 3D/Simulation Office
Make the office map the hero with richer animation. High wow factor, but weaker for repeated operator use and riskier on mobile.

### Option C: AI CEO Command Center
Lead with decisions, risks, action queue, and live staff ownership. Keep the map as a visual operations layer. This is the chosen approach.

## First Screen

The first viewport should have five zones:

1. Command Bar
   - Placeholder: "Boss se pucho ya kaam do..."
   - Supports question mode and task mode.
   - Examples: "Aaj kya priority hai?", "Rohan ko hot replies pe lagao", "kaunse clients risk me hain?"

2. Boss Brief
   - Short executive answer generated from real snapshot facts.
   - Shows one sentence summary, top risk, top opportunity, and next move.
   - Must not fabricate numbers.

3. War Room KPIs
   - Revenue impact
   - Hot queue value
   - Follow-up risk
   - Automation health
   - Approvals pending

4. Priority Action Stack
   - Top 5 actionable items, ranked.
   - Each item has severity, owner, ETA or age, source, and CTA.
   - CTAs route to existing panels or existing endpoints.

5. Office Pulse Strip
   - Active agents, stuck agents, active workflows, latest meaningful event.
   - This should feel alive without overwhelming the user.

## Information Architecture

Use these sections in order:

1. CEO War Room
2. Priority Actions
3. Living Office Map
4. Sales and Revenue Pipeline
5. Approvals and Boss Review
6. Reliability and Automation Health
7. Schedule and Replay
8. System Map and Workflow Runs

The current "Advanced Virtual Office" matrix should not stay as a large grid near the top. It can move into a compact "Capabilities" drawer or footer proof panel.

## New Core Features

### 1. Boss Command Bar

Use existing `hq_ask` backend if present. If route wiring is missing, add a thin admin-gated endpoint:

`POST /api/platform/office/ask`

Response shape:

```json
{
  "ok": true,
  "kind": "question",
  "text": "...",
  "member": "manager",
  "scope": "team",
  "run_id": ""
}
```

Rules:

- Admin-gated.
- Rate-limited.
- Bounded timeout.
- No auto-send or destructive side effects.
- Task routing uses existing draft-safe `run_agent_task`.

### 2. Boss Brief

Build from the same snapshot:

- headline
- risk
- opportunity
- recommendation
- confidence

Backend helper:

`build_boss_brief(snapshot) -> dict`

No extra slow IO. It should be a pure helper over the assembled snapshot.

### 3. Priority Action Stack

Upgrade `next_best_actions` from label-only to structured items:

```json
{
  "id": "hot_queue",
  "title": "7 hot replies pending",
  "why": "Interested/question replies are warmest sales intent.",
  "severity": "high",
  "owner": "rohan",
  "room": "sales_crm",
  "age": "2h",
  "cta_label": "Open Hot Queue",
  "cta_target": "hotQueueCard"
}
```

Sources:

- hot queue
- approvals
- overdue jobs
- failed jobs
- stuck pipeline items
- dunning
- retention red-band
- no-owner high-score leads

### 4. Room Workload Boards

Each room panel should show:

- current workload
- blocked count
- errors
- pending approvals
- top 3 work items
- owners
- "Ask room" or "Give room task" action

No fake room tasks. If a queue is not available, show "not wired yet" with exact source missing.

### 5. Replay Mode

Add "Aaj ka replay" panel:

- last 24h events grouped into a timeline
- lead created -> scored -> outreach -> reply -> follow-up -> booked/payment
- show actor, action, outcome, time

Backend can start with existing `agent_events` and pipeline items. No new DB needed for v1.

### 6. Operator Mode vs Theatre Mode

Add a segmented control:

- Operator: dense, actionable, production-use view.
- Theatre: map-first, animated, good for demo/screenshare.

Default should be Operator for logged-in admin.

### 7. Enterprise Trust Layer

Add a small audit/status strip:

- auth/admin-gated
- no destructive auto-action
- DND/AI disclosure gates intact
- last snapshot time
- cached vs fresh
- build/version SHA if available

This creates enterprise confidence without adding clutter.

## Frontend Design

Style direction:

- Quiet SaaS control room, not marketing hero.
- Dense but readable.
- Less emoji in primary controls.
- Use status colors sparingly: green ok, amber attention, red action needed.
- Cards should be compact and rectangular with 8-12px radius.
- The map can stay expressive, but the first screen should be calmer.

Desktop layout:

- Top sticky command bar.
- War Room grid: 2 columns, left Boss Brief and actions, right KPI/risk panels.
- Map full-width below the fold.

Mobile layout:

- Command bar first.
- Boss Brief.
- Priority actions.
- KPI strip.
- Room list instead of map.

## Backend Design

Add only pure snapshot builders unless an endpoint is required:

- `build_boss_brief(snapshot)`
- `build_priority_actions(snapshot)`
- `build_room_workloads(snapshot)`
- `build_replay(snapshot)`

Keep `build_snapshot()` as the single primary payload. Avoid adding extra frontend fetches unless the data is heavy or interactive.

Endpoint additions:

- `POST /api/platform/office/ask` only if not already wired.
- Optional later: `GET /api/platform/office/replay?hours=24` if replay becomes heavy.

## Data Rules

- No fabricated metrics.
- Every card must show source or route to source.
- If data is absent, show "not wired" or "no data yet", not fake zero confidence.
- Any mutation must be admin-gated, existing-action-backed, and snapshot-cache-invalidating.

## Safety Rules

- No outbound calls or auto-send from this page unless existing compliance gates pass.
- Task dispatch stays draft-safe.
- Boss recommendations remain recommend-only.
- DLQ clear/retry stays confirm-gated.
- No secrets in UI or logs.

## Testing

Backend:

- snapshot includes new sections
- builders are pure and never raise
- priority ordering is deterministic
- ask endpoint is admin-gated and rate-limited
- absent-data fallback is honest

Frontend:

- JS parse check
- mobile 380px no overlap
- command bar submit and result states
- action cards route correctly
- map still loads

Deploy:

- `prod_check.py`
- targeted office tests
- `node --check` extracted script
- live `/app/office` 200
- live marker for CEO War Room present

## Implementation Phases

### Phase 1: First-Screen Transformation

- Replace top area with CEO War Room.
- Move feature matrix lower or into capabilities drawer.
- Add command bar shell.
- Add structured priority actions.

### Phase 2: Real Boss Command

- Wire `POST /api/platform/office/ask` if needed.
- Add response panel with question/task states.
- Add route-to-agent confirmations.

### Phase 3: Room Workload and Replay

- Upgrade room drawer with workload.
- Add 24h replay timeline.
- Add Operator/Theatre toggle.

### Phase 4: Polish and Trust

- Visual cleanup.
- Mobile craft pass.
- Enterprise trust strip.
- Browser screenshot verification.

## Acceptance Criteria

The page is accepted only when:

1. First viewport clearly feels like a command center.
2. Top 5 priorities are visible without scrolling.
3. Every priority has owner and action.
4. Boss command bar works or honestly degrades.
5. Map remains useful but is not the only experience.
6. Mobile is usable at 380px.
7. No fake numbers or pretend actions.
8. Live deploy shows health production and `/app/office` 200.

