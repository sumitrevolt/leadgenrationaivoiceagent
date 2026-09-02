# Admin Virtual Office — Upgrade Design (2026-07-02)

## Problem
`/app/office` (shipped 2026-07-01, see [2026-07-01-admin-virtual-office-map-design.md](2026-07-01-admin-virtual-office-map-design.md))
shows 31 agents across 8 rooms with live status, speech bubbles, and a basic coordination
token. Admin feedback: the page only shows *agents* — it doesn't show project architecture,
doesn't show workflow, coordination between agents feels thin, some agents visibly aren't
working, and it needs to feel more "advanced" and be easier for a non-technical admin to read
at a glance.

## Investigation findings (ground truth, checked live 2026-07-02)

**Architecture/workflow already exist elsewhere.** `/app/control-center` is a separate,
already-shipped, browser-verified 4-level cockpit (`docs/EXPLORER_V2_CONTROL_CENTER_BLUEPRINT.md`):
L1 executive overview, L2 live architecture graph (Sigma.js WebGL + Graphology + elkjs, vendored
locally, 3 views — structural/automation/products, 46/79/27 nodes), L3 workflow/process explorer
(`/api/growth/process/*` — runs/journal/replay/approve-reject), L4 agent explorer. This is
exactly what "architecture" and "workflow" need. Building a second graph engine inside
`/app/office` would duplicate hard-won, already-working code (Sigma container-width bug fix,
vendored CDN libs, ELK layout). **Decision: embed/link, don't rebuild** (user-confirmed).

**Coordination is real but architecturally hub-and-spoke, not peer-to-peer.** Checked
`app/agents/coordinator.py` directly: every coordination action (`coordinated_step`,
`fanout_step`, `hier_step`, `adv_step`, `av_contrib`) is dispatched centrally by `manager`
(Boss) — there is no agent-to-agent handoff in the actual code. So a "agent talks to agent"
token would misrepresent the architecture. What's real and currently *missing*: the
**Coordinator Room ticker was spec'd in Phase 2 of the original design but never built** — no
visible log of `manager`-only session bookends (`coordinate_start/done`, `hier_start/done`,
`advanced_start/done`, `council_start/done`). Individual step-tokens fire as isolated blips
with no visible "this is one multi-agent run" framing.

**6 of 31 agents show `status=offline`, 0 actions today** (checked via direct snapshot call,
not the UI): Zara, Raksha, Priya, Anika, Ira, Lekha.
- Zara (`SOCIAL_ENGINE`) and Raksha (`CALL_TRANSFER`) — flags are unset (OFF) on the VPS,
  **correctly idle by design** (documented blockers: SOCIAL_ENGINE never enabled;
  CALL_TRANSFER pending Vobiz recharge + DLT). Not a bug — will stay grey until those
  flags are turned on.
- Priya (`CRM_SYNC=1`), Anika (`CADENCE_ENGINE=1`), Ira (`JOURNEY_ENGINE=1`) — **flags are ON**
  on the VPS yet zero activity today. Needs root-cause: could be legitimately "no matching
  data today" (no qualified lead to push, no enrolled lead due, no trigger event fired) or a
  genuine wiring bug. Investigate during implementation.
- Lekha (Call Analytics, no engine flag — a scheduled reporting job) — needs checking whether
  her job is actually registered in `team_scheduler.py`.

**Real-time is polling, not push.** Snapshot every 25s (`/api/platform/office/snapshot`,
Redis-cached 35s TTL — fixed 2026-07-01 from a 15s TTL that always expired before the next
poll), events every 8s. No visible "how fresh is this" indicator for the admin.

## Non-goals (explicitly rejected)
- **A second architecture/workflow graph engine inside `/app/office`.** Control Center already
  does this; embedding beats rebuilding.
- **Fabricated agent-to-agent coordination.** The system is hub-and-spoke (manager dispatches);
  visualizing a peer link that doesn't exist in the code would be dishonest UI, same principle
  the original spec used to reject a "guaranteed-accurate live process graph".
- **Websockets/SSE.** Real-time is achieved by tightening poll+cache pairing (§6) and adding a
  freshness indicator, not by adding new streaming infra — matches the rest of the admin
  surface's polling convention, smaller blast radius. The poll/cache-TTL pairing lesson here is
  the same one already fixed once this session on `/app/command-center` (its `Promise.allSettled`
  fix) and once on this very page 2026-07-01 (the 15s-poll-vs-35s-cache bug) — cadence and cache
  TTL must be chosen together, not independently.
- **Flipping `SOCIAL_ENGINE`/`CALL_TRANSFER` on.** Zara/Raksha being idle is a legitimate,
  documented product/compliance decision (DLT/recharge pending for CALL_TRANSFER); not this
  task's call to make.

## Design

### 1. System Map panel (architecture, embedded)
A new collapsible panel on `/app/office`, below the room canvas: **"🏗 System Map"**.
- Embeds `frontend/control_center_graph.html` in an iframe, defaulted to the `automation` view
  (79 nodes — most relevant to "who talks to what" from an ops-agent perspective). Same-origin,
  same admin session — no auth/CORS work needed.
- Collapsed by default (matches the recent admin-dashboard God-Mode-collapse pattern — keep the
  page from feeling heavier at first paint); a small "N architecture nodes · view live map"
  teaser row expands it.
- Footer link: **"Open full Control Center →"** (`/app/control-center`) for the complete
  L1–L4 experience (metrics, workflow runs, agent explorer, cost).

### 2. Recent Workflow Runs strip
A compact horizontal strip (5 most recent multi-agent coordinator runs): mode
(coordinate/fanout/hierarchical/advanced/council), status, agent-count, started-when. Pulled
from the same `/api/growth/process/*` endpoint Control Center L3 already uses — no new backend
query, just a second lightweight consumer. Row click → deep-link to that run's detail in
Control Center L3 (`/app/control-center#workflow?run=<id>`).

### 3. Coordinator Room ticker (the actual spec gap)
Build the Phase-2 item that was speced but never shipped: inside the Coordinator room on the
Phaser canvas, a small scrolling log showing only `member=="manager"` session-bookend events
(`coordinate_start/done`, `hier_start/done`, `advanced_start/done`, `council_start/done`) —
e.g. "Boss ne 'Pune solar outreach' ko 4 agents me baanta". This gives the missing session
framing: an admin sees a run BEGIN, watches the step-tokens fire during it, then sees it END,
instead of disconnected blips.

### 4. Active Coordination panel
A small persistent panel (not just a fleeting animation) listing in-flight coordination
sessions: mode, agents involved so far, started-when, elapsed. Session tracked client-side —
opens on a `*_start` event for `manager`, closes on the matching `*_done`. Serves the same
purpose as the ticker but as a static, readable list (good for a session that started before
the admin opened the page, or ran long).

### 5. Broken-agent fixes
Investigate + fix Priya (CRM sync), Anika (cadence), Ira (journey automation), Lekha (call
analytics) per the findings above — root-cause each, ship whatever fix is real (could be "no
bug, just no data today, add a clearer idle-reason instead" for some of them — see §7).

### 6. Real-time tightening
- Snapshot poll: 25s → 15s.
- Redis cache TTL: 35s → **18s** (**correction, post-implementation review 2026-07-02**: an
  earlier draft of this spec said TTL must stay *below* the poll interval — that is backwards
  and was caught during implementation. The 2026-07-01 cache-TTL bug's actual lesson is the
  opposite: TTL must *exceed* the poll interval, or a cache write from poll N has always expired
  before poll N+1 fires, making the cache a permanent no-op for periodic refreshes — exactly what
  happened when TTL=15s/poll=25s. 18s keeps a comfortable margin above the tightened 15s poll,
  same invariant as the original 35s-over-25s fix, just retuned to the new cadence).
- Visible **"Updated Xs ago"** badge near the top of the page, ticking client-side between
  polls.
- Manual **"🔄 Refresh now"** button — currently calls the same (cached) snapshot endpoint rather
  than bypassing the cache; with TTL=18s this can return data up to ~18s stale on a manual click,
  which undersells the "force-check right now" framing below. Follow-up, not blocking: either add
  a cache-bust param, or key the freshness badge off the snapshot's own `generated_at` timestamp
  instead of client-side `Date.now()` so the badge honestly reflects data age, not fetch-recency.

### 7. Admin-friendly clarity
- **Legend**: a small `(?)` icon opening a one-time/toggleable popover explaining status-dot
  colors (🟢 working / 🟡 active-today / ⚪ offline) and the workflow-token.
- **Offline-reason tooltip**: hovering a grey/offline agent shows *why* — "Flag SOCIAL_ENGINE
  OFF" vs "Koi matching data aaj nahi mila" vs "Error — dekho log" — computed server-side from
  the same audit done in §"Investigation findings", not just a flat grey dot with no
  explanation. This directly turns the "kuch agents kaam nahi kar rahe" confusion into a
  self-explanatory answer, for every future agent too (not just today's 6).
- **One-line status summary** at the top in plain Hinglish, e.g. "25/31 agents active · 3
  approvals pending · sab automation healthy" — synthesized from the existing metrics payload,
  no new data source.

## Data flow / API changes
- No new endpoints for the System Map panel or Workflow Runs strip — both are new *consumers*
  of existing endpoints (`control_center_graph.html`'s own data path; `/api/growth/process/*`).
- `app/platform/office_hq.py`: `build_rooms_and_agents()` gains an `offline_reason` field per
  agent (flag-off / no-data-today / error — computed from existing flag-check helpers already
  used elsewhere in the codebase, e.g. `os.environ.get("CRM_SYNC")`-style checks). Additive
  field, no breaking change to the existing response shape.
- `_SNAPSHOT_CACHE_TTL`: 35 → 12 (single constant change).
- Frontend poll interval: 25000 → 15000ms (single constant change).
- Coordinator ticker + Active Coordination panel: pure frontend, consume the existing
  `/api/platform/team/events` stream (already polled every 8s), no backend change.

## Error handling
Same never-raise / graceful-degrade convention as the rest of `/app/office` and `office_hq.py`:
- System Map iframe failing to load → panel shows "Architecture map load nahi hua — Control
  Center me dekho →" fallback link, doesn't block the rest of the page.
- Workflow Runs strip empty/failed → hidden section (no error banner for an empty-but-healthy
  state), matches existing pattern elsewhere on this page.
- `offline_reason` computation failing → falls back to the existing flat "offline" label
  (no regression from today's behavior).

## Testing
- **Backend**: `app/platform/office_hq.py` gains `offline_reason` logic — add unit tests
  covering the 3 reason categories (flag-off, no-data-today, error) plus the existing "working"
  path staying unaffected. Whatever fix lands for Priya/Anika/Ira/Lekha gets its own targeted
  regression test (mirroring the pattern in `tests/test_call_event_client_id.py` etc. from the
  2026-07-02 campaign-launch batch — real root-cause, real test, not a trivial assert).
- **Frontend**: manual browser-preview verification (screenshot, console-error check, mobile
  375px resize, click-through the new panels) — same method used throughout this session,
  no JS test harness exists for this project's frontend pages.

## Phased delivery
- **Phase A**: broken-agent root-cause + fix (§5) + `offline_reason` field + tooltip (§7) —
  independently shippable, directly answers "kuch agents kaam nahi kar rahe".
- **Phase B**: System Map panel (§1) + Workflow Runs strip (§2) — directly answers
  "architecture/workflow nahi dikhta".
- **Phase C**: Coordinator ticker (§3) + Active Coordination panel (§4) — directly answers
  "coordination nahi dikhta".
- **Phase D**: real-time tightening (§6) + legend/summary line (§7 remainder) — polish layer,
  smallest individually but ties the page together.

Each phase is independently deployable (matches this project's proven surgical-deploy pattern);
order chosen so the most concretely-broken thing (agents that look dead) ships first.

## Open implementation details (decide during build, not blocking this spec)
- Exact `offline_reason` string templates (Hinglish wording) for each of the 3 categories.
- Whether the System Map iframe re-embeds the FULL `control_center_graph.html` (simplest, but
  carries its own top-bar/chrome) or a stripped query-param mode of the same file
  (`?embed=1` to hide chrome) — decide by checking whether `control_center_graph.html` already
  supports an embed/minimal-chrome mode (it's already iframed once, inside Control Center L2,
  so this likely already exists — verify during implementation).
