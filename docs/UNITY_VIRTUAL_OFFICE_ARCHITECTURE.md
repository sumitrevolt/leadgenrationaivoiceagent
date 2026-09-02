# UNITY VIRTUAL OFFICE — ARCHITECTURE (2026-07-12)

> Unity = OPTIONAL spatial layer over the existing system. Existing dashboards stay the operational
> source of truth. No business logic in Unity. No direct DB/Redis/secret access from Unity — ever.

## 1. System diagram

```
Existing FastAPI backend (app/main.py, ~1100 routes)
  │
  ├── Existing pages (UNTOUCHED): /app/admin · /app/customer · /app/explorer
  │     /app/control-center(+/graph) · /app/delivery-command-center · /app/office (Phaser map)
  │
  ├── REUSED state APIs (no new business logic):
  │     admin:    GET /api/platform/office/snapshot        (office_hq aggregator, Redis-cached 18s)
  │               GET /api/control-center/overview · /api/admin/system-health-detail
  │               GET /api/activation/readiness · GET /api/events/stream (SSE)
  │     customer: GET /api/customer/office · /dashboard · /delivery-proof · /approvals/pending
  │               /social/accounts · /timeline   (all Depends(require_customer))
  │
  ├── NEW (this program, all flag-gated INERT):
  │     GET /app/office?mode=3d  → frontend/office_blueprint.html   (admin Unity shell)
  │     /static/office-unity/*   → Unity WebGL build artifacts (mount only if dir exists)
  │
  ├── Unity Admin Blueprint Office   (WebGL, scene AdminBlueprintOffice)
  └── Unity Customer Blueprint Office (WebGL, scene CustomerBlueprintOffice — Milestone E)
```

## 2. Web shell (`frontend/office_blueprint.html`)

Responsibilities (Phase 8/9 Bootstrap duties live in the SHELL, not a Unity scene, so failures
degrade to HTML): auth check (`localStorage.accessToken`, same as office_map), feature-flag check
(shell is only served when flag on; JS re-verifies), capability detection (WebGL2 + deviceMemory +
reduced-motion), Unity loader with progress + 20s timeout, error/disabled/expired states, escape
link to `/app/office?mode=map` and `/app/admin`, last-updated timestamp, refresh action, HTML side
panel (selection detail), minimap, JS bridge (allowlist), SSE/poll wiring.

Mode routing (`/app/office` handler in `app/main.py`):
```
mode=map            → office_map.html (existing, always available)
mode=3d + flag ON   → office_blueprint.html
mode=3d + flag OFF  → office_map.html (INERT — zero behavior change until flag flips)
default (no mode)   → office_map.html (UNITY_LIGHTWEIGHT_MODE_DEFAULT stays true)
```

## 3. Unity project (`unity/LeadGenVirtualOffice/`)

- Unity 2022.3 LTS (or 6000.x LTS), WebGL target, compressed (Brotli), IL2CPP default.
- Scenes: `Bootstrap.unity` (config handshake from shell → scene route), `AdminBlueprintOffice.unity`,
  `CustomerBlueprintOffice.unity`. No per-department scenes (Phase 9).
- Prefabs (Phase 10): RoomNode, DepartmentZone, AgentDesk, AgentAvatar, CustomerNode, StatusBeacon,
  WorkflowPath, AlertMarker, DeliveryShelfItem, BlueprintPanel, MapLegend, Minimap, HTMLActionButton,
  LoadingState, EmptyState, ErrorState, StaleDataIndicator, ConnectionStatus.
- Scripts (`Assets/Scripts/`, committed): `OfficeStateClient.cs` (fetch via shell-injected JSON —
  Unity itself performs NO authenticated HTTP; the SHELL fetches with the user's token and pushes
  state in via `SendMessage`, so tokens never enter Unity memory), `SelectionSync.cs`,
  `RoomLayout.cs` (builds rooms from `snapshot.rooms[]` + OFFICE_MAP_UNITY_MAPPING scale),
  `StatusPalette.cs` (style-guide hexes), `HostBridge.jslib` (allowlisted window calls only).
- Committed: `Assets/`, `Packages/manifest.json`, `ProjectSettings/`, build script, docs.
  Ignored: `Library/ Temp/ Logs/ obj/ Build*/ UserSettings/ MemoryCaptures/` (unity/.gitignore).

## 4. Data flow & real-time (Phase 12)

- REST initial state: shell fetches snapshot (admin) / customer office (customer) → validates
  schema_version-ish shape → pushes to Unity.
- Live: admin = existing SSE `/api/events/stream` (Redis pub/sub `lgai:events`, heartbeat 20s,
  DB-poll fallback already server-side) with client reconnect = bounded exponential backoff
  (2s→60s, jitter); customer = 15s poll (existing office_map pattern; no tenant SSE exists —
  building one is future work, NOT vertical slice).
- Dedup: event `id` ring-buffer (last 512) in shell; stale detection: no data > 45s → Unity
  StaleDataIndicator + shell banner; session expiry (401) → login-required state, SSE resubscribe
  revalidates auth by nature of cookie/bearer re-send.

## 5. Explicit non-goals

No duplicate approve/pay/publish logic in Unity; no Unity-side entitlement math
(packages.py is truth, delivered via APIs); no auto-posting claims where system is manual;
no new room/department/status vocabularies (office_hq + style guide are canonical);
no replacement of /app/office default until preview proven (Phase 33).

## 6. Milestones (Phase 27) & current status

| Milestone | Status 2026-07-12 |
|---|---|
| A Asset audit | DONE — EXISTING_BLUEPRINT_ASSET_INVENTORY.md |
| B Shared office model + contracts | DONE — this doc + API_CONTRACT + SECURITY + mappings |
| C Blueprint web shell + flags + bridge | Shell + flags implemented (INERT); verification pending Windows venv gates |
| D Admin vertical slice (Unity) | BLOCKED — Unity Editor not installed on dev machine |
| E Customer vertical slice | Not started (needs D) |
| F Sync wiring | Shell-side implemented; Unity-side pending D |
| G Remaining rooms | Not started |
| H Mobile/perf | Fallback path DONE by design (existing map); Unity perf pending D |
| I Preview deploy | BLOCKED on D + repo commit state + user-run deploy |
