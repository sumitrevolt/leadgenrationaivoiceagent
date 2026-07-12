# LeadGen AI — Blueprint Virtual Office (Unity WebGL)

Status 2026-07-12: **code scaffold only — no Unity Editor on this machine yet** (see
`docs/UNITY_VIRTUAL_OFFICE_DEPLOYMENT.md`). Scenes are created in-Editor on first open;
scripts/prefab logic below are committed and ready.

## Requirements
- Unity **2022.3 LTS** (WebGL Build Support module). Install via Unity Hub.
- Open this folder (`unity/LeadGenVirtualOffice`) as the project. Unity will generate
  `Library/` (ignored) and default `ProjectSettings/` — then set:
  - File → Build Settings → **WebGL**, compression **Brotli**, template Minimal.
  - Product name `Blueprint Virtual Office`, company `LeadGen AI`.
  - Color space Linear; strip engine code ON; exceptions None (size).

## Scenes to create (Phase 9 — minimal)
1. `Assets/Scenes/Bootstrap.unity` — empty scene with `Bridge` GameObject (add `HostBridge.cs`
   + `OfficeDirector.cs`). Loads AdminBlueprintOffice additively when first state arrives.
2. `Assets/Scenes/AdminBlueprintOffice.unity` — `RoomLayout` builds the 8 rooms at runtime from
   snapshot data (no hand-modeled rooms; geometry mirrors docs/OFFICE_MAP_UNITY_MAPPING.md).
3. `Assets/Scenes/CustomerBlueprintOffice.unity` — Milestone E (not yet).

## Data flow (SECURITY-CRITICAL — do not change)
Unity performs **NO authenticated HTTP**. The web shell (`frontend/office_blueprint.html`) fetches
state with the user's token and pushes JSON in via `SendMessage("Bridge","OnHostEvent", json)`.
Outbound, Unity may only call `window.LG_BRIDGE.invoke(json)` (allowlisted actions —
`docs/UNITY_OFFICE_API_CONTRACT.md` §4) via `Assets/Plugins/WebGL/HostBridge.jslib`.
Never add UnityWebRequest calls to /api/*, never store tokens, never hard-code customer data.

## Build
Editor: File → Build Settings → WebGL → Build to `Build/` with name `LeadGenVirtualOffice`.
CLI (after Editor install):
```
"C:\Program Files\Unity\Hub\Editor\<ver>\Editor\Unity.exe" -batchmode -quit ^
  -projectPath unity\LeadGenVirtualOffice ^
  -executeMethod LeadGen.Office.Editor.WebGLBuild.Build -logFile build.log
```
Output files `LeadGenVirtualOffice.{loader.js,data.br,framework.js.br,wasm.br}` →
copy `Build/` to `frontend/office_unity/Build/` (served at `/static/office-unity/Build/*`,
mount is auto-guarded in `app/main.py`).

## Performance budget (Phase 23)
Compressed build ≤ 12 MB target; ≤ 30 draw calls idle; no per-agent continuous animation
(status pulse on `processing` only); 1 directional light, no realtime shadows.
