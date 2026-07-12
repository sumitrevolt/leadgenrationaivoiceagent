# EXISTING BLUEPRINT ASSET INVENTORY (2026-07-12)

> Phase-2 audit for the Unity Blueprint Virtual Office program. Source-backed: every row was
> verified against the working tree at SHA `1c7441b3` (branch `recovery/loop27-loop28-20260711`).
> Rule: Unity REUSES these assets — it must never duplicate them.

## 0. Headline findings

1. **A Virtual Office already exists and is live**: `/app/office` → `frontend/office_map.html`
   (Phaser 3.80.1, vendored) — 8 named rooms on a 1200×820 grid, 31 AI-staff avatars, day/night
   ambience, DLQ/reception props driven by REAL counts, 15s poll of
   `GET /api/platform/office/snapshot`. This is the primary reuse source for Unity.
2. **The Blueprint Explorer exists**: `/app/explorer` → `frontend/explorer.html` — custom DOM-node
   graph with HAND-AUTHORED x/y positions, dark `#0a0a0c` dotted-grid blueprint style, drift-sync
   panel (`GET /api/growth/infra/explorer-drift`, 81/81 engines).
3. **Two command centers exist**: `/app/control-center` (L1 cockpit + right inspector + L2 Sigma.js
   WebGL graph iframe at `/app/control-center/graph`) and `/app/delivery-command-center`
   (business-outcome delivery OS). `/app/command-center` = 307 redirect (ADR-034, deleted).
4. **Backend aggregation largely exists**: `office_hq.build_snapshot()` (admin) and
   `GET /api/customer/office` (tenant-scoped, flag `CUSTOMER_OFFICE`) — new endpoints are mostly
   unnecessary for a vertical slice.

## 1. Inventory table

| Asset/component | File | Route | Selector/function | Current purpose | Data source | Status | Reusable? | Reuse method | Unity mapping |
|---|---|---|---|---|---|---|---|---|---|
| Virtual Office (Phaser) | `frontend/office_map.html` (~4100 ln) | `/app/office` (main.py:1263) | `OFFICE.ROOMS` (873–881), `drawRoomFurniture`, `drawDlqPile`, `drawReceptionTray` | Live 2D spatial HQ: rooms, staff, standup walks, ambience | `GET /api/platform/office/snapshot` (15s poll), `/api/platform/team/*`, `/api/growth/infra/dlq*`, `/api/growth/reply/hot-queue*` | LIVE | **YES — primary** | Room grid + agent→room mapping + snapshot contract consumed verbatim by Unity | Floor plan for `AdminBlueprintOffice.unity`; also the LIGHTWEIGHT fallback mode |
| Room definitions (canonical) | `app/platform/office_hq.py` | — | `ROOM_DEFS` (42–59), `MEMBER_ROOM` (62–101), `PIPELINE_STAGE_META` (225–238) | Single source of rooms/staff-to-room/stages | code | LIVE | **YES — canonical** | Unity reads rooms[] from snapshot; NEVER re-declares rooms | RoomNode/DepartmentZone prefab data |
| Blueprint Explorer | `frontend/explorer.html` (~2700 ln) | `/app/explorer` (main.py:1424) | inline `NODES` (x,y,w,h; e.g. 548), `edges` (597–988), `TYPE_COLORS` (1211), `exportArch()` (392) | Architecture graph, wiring audit, flow Builder | `GET /api/growth/infra/explorer-drift` | LIVE | **YES** | Graph dataset + type palette = Workflow/Infrastructure modes | Blueprint minimap + Workflow Mode overlays |
| Control Center L1 | `frontend/control_center.html` | `/app/control-center` (main.py:1430) | `#metrics` 6-card row, `#rail`, `#inspector` (360px), inline token set (10–16) | Enterprise cockpit shell | `/api/control-center/overview`, `/agents/metrics`, `/node-stats`, `/rca`, `/cost-rollup` | LIVE | **YES** | Canonical dark-blueprint tokens; inspector = pattern for Unity HTML side panel | Command-center HUD framing + selection panel |
| L2 WebGL graph | `frontend/control_center_graph.html` | `/app/control-center/graph` (main.py:1436) | Sigma.js v3 + Graphology + elkjs (vendored, 163–165); status legend (116–120) | Auto-laid architecture graph, iframe-embeddable, postMessage to parent | same node dataset as explorer | LIVE (live-status wiring pending) | **YES** | Status palette healthy/processing/waiting/retry/failed = canonical node states | StatusBeacon color states; graph iframe alternative to Unity Workflow Mode |
| Delivery Command Center | `frontend/delivery_command_center.html` | `/app/delivery-command-center` (main.py:1358) | outcome cards, 7-state delivery-health badges | Business-outcome delivery OS | delivery/activation APIs | LIVE | YES (labels/states) | Delivery state vocabulary reused in Delivery Department room | DeliveryShelfItem states |
| Admin dashboard | `frontend/admin_dashboard.html` | `/app/admin` (main.py:1229) | `showAdminView` (`command_center`,`office`,`customer_360`,`approvals`,`delivery_queue`…), `sec-*` cards, `adminToast()` | Operational admin command center | `/api/admin/*` | LIVE (Loop 27/28 fixes uncommitted) | YES (deep links) | Unity bridge opens `/app/admin#<view>` for complex actions | HTMLActionButton targets |
| Customer dashboard | `frontend/customer_dashboard.html` | `/app/customer` (main.py:1203) | `showView()` (home/delivery/setup/leads/reports/billing/support), Setup Wizard, mobile nav | Customer "Aapka AI Office" | `/api/customer/*` | LIVE | YES (deep links + naming) | Unity customer office opens existing setup/approval/report views | Customer rooms → existing views |
| Team roster page | `frontend/team_dashboard.html` | `/app/team` (main.py:1257) | roster list | Non-spatial twin of office | `/api/platform/team*` | LIVE | YES | Same team API | AgentDesk/AgentAvatar data |
| Automation Mission Control | `frontend/automation.html` | `/app/automation` (main.py:1375) | `.tabsec` tabs | Automation ops | `/api/growth/*` | LIVE | partial | Deep-link target | Bridge target |
| Journeys | `frontend/journeys.html` | `/app/journeys` (main.py:1330) | rule cards | Trigger→action rules | `/api/journeys*` | LIVE | low | — | — |
| Vendored engines | `frontend/design-system/vendor/` | `/design-system/*` (main.py:1063) | phaser.min.js, sigma.min.js, graphology, elk.bundled.js | Graph/game runtimes (no CDN) | — | LIVE | YES | Lightweight mode keeps using them | n/a (Unity replaces only in 3d mode) |
| Design tokens (light "AI Office") | `frontend/design-system/tokens/{colors,ai-office}.css` | all dashboards | `--indigo-600 #4f46e5`, `--violet-500 #7c3aed`, `--success/--warning/--danger`, `--ao-*` | Customer/admin visual language | — | LIVE | **YES** | See `UNITY_BLUEPRINT_STYLE_GUIDE.md` | Customer office palette |
| Design tokens (dark "Blueprint") | inline `control_center.html:10–16` (+ explorer/graph) | control-center, explorer | `--bg #0a0a0c`, `--amber #f59e0b`, `--healthy/--processing/--waiting/--retry/--failed`, dotted grid | Blueprint visual language | — | LIVE | **YES — primary Unity palette** | See style guide | Admin blueprint materials/UI |
| Office snapshot API | `app/api/office_hq.py` | `/api/platform/office/*` (main.py:454) | `/snapshot`(25), `/pipeline/{stage}`(54), pause/resume(72/83), pipeline overrides(154–189), `/briefing`(223) | Admin office state + safe actions | office_hq aggregator (Redis cache 18s TTL) | LIVE | **YES — the spine** | Unity admin scene consumes verbatim | Admin office state feed |
| Customer office API | `app/api/customer_dashboard.py:120` | `GET /api/customer/office` | `_build_office`, flag `CUSTOMER_OFFICE` | Tenant-scoped customer office state | JWT `require_customer` | LIVE | **YES** | Unity customer scene consumes verbatim | Customer office state feed |
| Delivery proof API | `customer_dashboard.py:1927` | `GET /api/customer/delivery-proof` | — | Evidence-backed deliverables | delivery_ledger + product_one_delivery | LIVE | **YES** | Delivery Shelf truth | DeliveryShelfItem feed |
| Approvals APIs | `customer_dashboard.py:2026/2048`; `office_hq.build_approval_queue()` (955) | `/api/customer/approvals/*`; snapshot.approvals | `decide_for_client` | Customer + admin unified approvals | content_approval + approvals_bridge | LIVE | **YES** | Approval Desk/Table actions | ApprovalTable feed+actions |
| System health APIs | `app/api/system_health.py:138`; `app/api/health.py`; `automation_health.health()` | `/api/admin/system-health-detail`, `/health*`, `/metrics` | flag `SYS_HEALTH_DETAIL` | Infra wall (cpu/mem/redis/queue/worker) | psutil+redis | LIVE | **YES** | Server Room feed | Infrastructure Mode |
| Events stream (SSE) | `app/api/events.py` | `GET /api/events/stream` (admin) | Redis pub/sub `lgai:events` + 10s DB-poll fallback, 20s heartbeat | Live admin event feed | team.log_event | LIVE | **YES (admin)** | Unity admin live events; customer = polling (no tenant SSE exists) | event transport |
| Compliance state | `app/telephony/compliance.py`, `app/platform/platform_dial.py`, `activation._compliance_env()` (503) | via `/api/activation/readiness` | `effective_promo_window()`, `ComplianceGate.check`, `platform_dial.enabled()` | DND/TRAI/DLT/platform_dial truth | env + data/platform_dial.json | LIVE | **YES** | Compliance Room reads REAL state (platform_dial must show HARD OFF) | Compliance Mode |
| Feature flags | `app/api/automation_flags.py` (env, ~250 flags) + `app/infrastructure/feature_flags.py` (per-tenant Redis) | `GET /api/growth/infra/flags`; `/api/growth/infra/feature-flags*` | append-string registry; tenant rollout states | Flag truth + progressive rollout | env / Redis | LIVE | **YES** | New UNITY_* flags go in AUTOMATION_FLAGS; per-tenant rollout via feature_flags | Rollout gating |
| Packages truth | `app/marketing/packages.py` | `/api/marketing/packages`, `/api/billing/plans` | `get_public_packages()` (282), `_STARTER_FEATURE_GROUPS` (75) | ₹1,999/₹5,999 entitlement truth | code | LIVE | **YES** | Delivery Shelf derives entitled deliverables from here — NEVER hard-coded | Plan/deliverables feed |

## 2. Gaps found (aggregation only where fragmented — Phase 3 rule)

| Gap | Evidence | Disposition |
|---|---|---|
| No tenant-scoped SSE (events stream is admin-only) | `events.py:158 require_admin` | Customer office keeps POLLING (matches existing office_map 15s pattern). Tenant SSE = future work, not vertical slice. |
| No `/support` or `/tickets` API | grep: none | Support Desk room = deep-link to existing support view in customer dashboard + WhatsApp 1-click. No fake ticket UI. |
| No `/static` Unity mount | main.py: only `/site`, `/design-system`, `/` catch-all (2089) | Add guarded mount before catch-all when Unity build exists (see DEPLOYMENT doc). |
| L2 graph live-status not wired | control_center_graph.html header comment (line 16) | Out of Unity scope; noted. |
| Room defs duplicated FE/BE | `OFFICE.ROOMS` (office_map.html:873) vs `ROOM_DEFS` (office_hq.py:42) | Canonical = `office_hq.ROOM_DEFS` served in `snapshot.rooms[]`. Unity consumes API only. Frontend literal = existing debt, do NOT add a third copy. |

## 3. Constraint notes for the Unity layer

- Working tree is DIRTY with unshipped Loop 27/28 dashboard work (see CLAUDE.md Current State) — Unity work = NEW files only wherever possible; `main.py`/`automation_flags.py` touches must stay additive + separable.
- Unity Editor is NOT installed on the dev machine (Start-menu app list, 2026-07-12) — WebGL builds are blocked until user installs Unity (see DEPLOYMENT doc).
- Sandbox FUSE mount truncates large file reads (`main.py` 2099→2067 in bash) — verification gates (`prod_check.py`, pytest) must run on Windows venv or VPS, not the sandbox.
