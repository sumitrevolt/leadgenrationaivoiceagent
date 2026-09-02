# Admin Virtual Office Map — Design Spec (2026-07-01)

## Problem
Admin ne poocha: "sab agents kya kar rahe automation step-by-step, alag office jaisa alag rooms,
coordinator room, complete map with realtime working" (Gather.town screenshot reference). Aaj
`/app/team` sirf ek flat card-grid dikhata hai (`frontend/team_dashboard.html`) — koi spatial
"office" nahi, koi live task-flow visualization nahi. Admin ko samajh nahi aata **abhi background
me kya ho raha hai, kisne kya task assign kiya, agents aapas me kya "baat" kar rahe** (task handoff).

## Non-goals (explicitly rejected, with reasoning)
- **Unity / Unreal Engine** — yeh web-native FastAPI+HTML admin console hai, koi standalone
  game/app nahi. Native engine = WebGL export (20-50MB+), alag C#/C++ skillset, aur Unity/Unreal
  ki licensing (revenue-share / subscription) project ke "sab free stack" rule (CLAUDE.md) se
  clash karti hai. Khud Gather.town bhi web-native hai, Unity/Unreal pe nahi bana.
- **Full walk-cycle sprite animation** (4-directional per-character frames) — 27 alag agents ke
  liye yeh asset-work bahut zyada hai bina proportional value ke. Movement = position-tween
  (smooth slide), asli animated walk-frames nahi.
- **Exact 1:1 workflow/process graph** — coordinator dispatch ek approximate stage-sequence
  visualization dega (real event-order se), formal DAG-diagram nahi (woh already `/app/explorer` /
  Control Center ka scope hai — is feature ka overlap nahi).

## Approach: Phaser.js pixel-art office map, phased delivery
Free (MIT), pure-JS, browser-native 2D game framework — koi build/export pipeline nahi, seedha
`frontend/` me ek script ki tarah chalta hai. Room floor/wall tiles = free CC0 tileset (Kenney.nl
public-domain, zero attribution/licensing risk) — implementation phase me specific pack chunna hai.

### Data sources — ZERO backend changes
Sab kuch already-existing endpoints se aata hai (`app/platform/team.py` + `app/api/team.py`):
- `GET /api/platform/team` → roster + per-member live state (working/active/offline) +
  today_actions/errors + last_activity. (`team_status()`)
- `GET /api/platform/team/events?member=&limit=` → per-agent or global recent event feed, already
  supports `member` filter. (`recent_events()`)
- Coordinator/task-assignment data **already flows into `agent_events`** via
  `app/agents/coordinator.py` `_log(member, action, detail)`: Boss (`manager`) logs
  `coordinate_start`/`coordinate_done`/`hier_start`/`council_start` with the goal/summary; each
  dispatched agent logs `coordinated_step`/`fanout_step`/`hier_step`/`adv_step` with the specific
  task text. This is the literal "who's coordinating what, who's doing what" feed the admin asked
  for — it just isn't surfaced anywhere visual today.

No new DB tables, no new endpoints, no new query params (the one used, `member=`, already exists).

### Room model (data-driven from `STAFF` dict, NOT hardcoded per-agent)
`STAFF` (`app/platform/team.py`) already has a `product` field. Client-side grouping:
1. 🧑‍💼 **Coordinator Room** — `manager` (Boss) only — singled out from `product:"platform"`
   because Boss's role IS literally "team coordination" (duties field).
2. 📞 **Voice Team Room** — remaining `product:"voice"` members (8 today: Swara, Ananya, Riya,
   Arjun, Meera, Lekha, Raksha, Tara).
3. 📣 **Marketing Team Room** — `product:"marketing"` members (10 today: Dev, Rohan, Isha, Ravi,
   Neha, Kiran, **Priya** — CRM Sync Specialist, **Zara** — Social Media Manager, **Anika** —
   Cadence Manager, **Ira** — Journey Automation Manager).
4. 🛠️ **Platform / Engineering Room** — remaining `product:"platform"` members (12 today: Kavya,
   Hermes, Nikhil, Vikram, Guru, Pranav, Vidya, Arnav, Kabir, Diya, Aryan, Arya).

**2026-07-01 roster audit (real workers, not decoration) — 2 rounds:** before drawing the map,
audited every automation module for `team.log_event()` attribution. Round 1 found
`app/platform/crm_sync.py` and `app/social_engine/engine.py` run real, already-scheduled/
queue-driven automation with **zero** staff attribution — wired as Priya / Zara. Round 2 (user
asked for "2 more") found `app/marketing/cadence.py` (scheduled omnichannel sequencing) and
`app/marketing/journeys.py` (event-rule automation, wired into inquiry/booking/reply-triage/
pipeline-ops hooks) — same gap, wired as Anika / Ira. No decorative personas invented in either
round — every addition wraps a real, already-running code path. Also fixed a pre-existing bug:
`team_scheduler.py` logged the speed-to-lead digest under member key `"boss"`, which is not a
`STAFF` key (`"manager"` is) — silently invisible in `team_status()`; now logs under `"manager"`.
(3 more instances of this same key-mismatch bug were found — `revenue_digest.py`,
`growth_optimizer.py`, `approvals_bridge.py` — logged as a known-but-deferred follow-up, not fixed
this round since the user capped scope at "2 more".) Total roster: **31** (was 27).

**Scalability**: room membership is computed at render time from the live roster response, not
hardcoded per name. Each room auto-lays-out its members in a grid (fixed desk-slot per member,
deterministic by sorted key so slots don't reshuffle across refreshes); a room whose member-count
exceeds its visual grid capacity wraps to additional rows / scrolls internally. Adding a new
`STAFF` entry in code requires **zero map changes** — it appears in its product's room automatically.

### Visual behaviour
- **Idle state**: each agent = a small avatar chip (existing STAFF emoji + name) at their fixed
  desk-slot, with a status-ring color (🟢 working / 🟡 active-today-resting / ⚪ offline — same
  thresholds as `team_status()`).
- **Speech bubble** — on the agent's most-recent event (from the polled feed), a transient bubble
  shows the event's `detail` text (already human-readable, e.g. "Leads score kar raha hu — 12
  prospects [fanout]") — this directly answers "kya baat kar rahe agents".
- **Movement (position-tween, not walk-cycle)** — when a member gets a new event, their avatar
  tweens from desk-slot to room-center and back, synced with the speech bubble appearing/fading.
- **Coordinator Room ticker** — a small scrolling log inside the Coordinator room showing only
  `member == "manager"` events (`coordinate_start/done`, `hier_start`, `council_start`, …) — "Boss
  ne abhi yeh goal N agents me baanta" visibility.
- **Workflow token (cross-room)** — when a `coordinate_start`/`hier_start`/`agentverse_start` event
  fires for `manager`, and subsequent `coordinated_step`/`hier_step`/`av_contrib` events name
  specific agents, an animated token travels Coordinator-room → each named agent's room in event
  order, pausing briefly at each (syncing with that agent's own speech-bubble/tween), before
  returning to Coordinator room on the matching `*_done` event. Approximate, event-order-driven —
  not a guaranteed-accurate live process graph.
- **Click-to-expand** — clicking any avatar opens a side panel: title/duties (from `STAFF`),
  current state, today_actions/errors, and last 8 events for that member
  (`/api/platform/team/events?member=<key>&limit=8`).

### Refresh cadence
- `GET /api/platform/team` every 25s → status-dot / idle-active-offline updates (matches existing
  dashboard polling conventions elsewhere in the app).
- `GET /api/platform/team/events?limit=15` every ~8-10s → drives movement-tweens / speech-bubbles /
  coordinator ticker / workflow-token triggers (faster cadence needed so a flow feels "live").
- No websockets/SSE in v1 — plain polling, consistent with the rest of the admin dashboard, avoids
  new infra. Can be revisited later if polling proves too chatty.

### Placement
- New route `GET /app/office` (FastAPI `FileResponse`, `require_admin`-gated same as `/api/platform/team*`)
  → `frontend/office_map.html`.
- New admin sidebar link "🏢 Virtual Office" (grouped near "AI Staff Team" in Operations section).
- A small teaser card on `admin_dashboard.html` (pattern reused from the just-shipped
  `#sec-advtech-wrap` collapse-card): "N/27 agents working → Poora office dekho →" linking to
  `/app/office`. Kept intentionally light so it does not re-clutter the dashboard we just
  decluttered.

### Error handling
Same never-raise / graceful-degrade convention as the rest of the admin surface: if a poll fails,
show a small non-blocking banner ("Office data load nahi ho paya — retry") and keep the last-known
render frozen (don't blank the canvas). First paint before any data arrives shows empty room
outlines (skeleton), not a spinner-forever state.

### Testing
- **Backend**: unchanged — no new endpoints/params, so no new backend tests required.
- **Frontend**: no JS test harness exists in this project for frontend pages; verification is
  manual via the browser-preview tool (screenshot, click interactions, mobile 375px resize, console
  error check) — same method used for the `admin_dashboard.html` God-Mode-collapse fix earlier this
  session.

## Phased delivery (each phase independently useful/deployable)
- **Phase 1 (core, ships first)**: static rooms auto-laid-out from `STAFF`/`team_status()`,
  status-color rings, click-to-expand side panel with last-8-events. No movement/tokens yet — this
  alone already beats the current flat card-grid and is usable immediately.
- **Phase 2**: movement-tween on new events + speech bubbles + Coordinator Room ticker.
- **Phase 3**: cross-room workflow-token animation (polish layer on top of Phase 2's event-driven
  movement).

## Open implementation details (decide during build, not blocking this spec)
- Exact Kenney.nl (or equivalent CC0) tile/asset pack choice for room floor/walls.
- Exact desk-slot grid math / room pixel dimensions for 6-13 members per room without crowding.
