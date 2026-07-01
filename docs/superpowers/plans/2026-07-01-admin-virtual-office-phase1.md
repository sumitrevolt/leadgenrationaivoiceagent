# Admin Virtual Office — Phase 1 (static rooms + live status + click-log) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **STATUS: SHIPPED (2026-07-01), with 2 deviations from the plan below — both driven by mid-build user feedback, both applied and committed:**
> 1. **Vendored Phaser instead of CDN** (`frontend/design-system/vendor/phaser.min.js`) — the plan's CDN `<script>` URL turned out to be unreachable from the sandboxed browser-preview tool used to verify this build (confirmed it's a tool-sandbox restriction, not a code bug — Chart.js's CDN fails the same way there). Vendoring matches the existing sigma/graphology/elkjs pattern in `control_center_graph.html` and removes a third-party runtime dependency besides.
> 2. **Real pixel-art character sprites instead of Graphics circles** — after seeing Phase 1's plain-circle avatars next to the Gather.town reference image, the user said it looked nothing like what they wanted. Added `frontend/design-system/vendor/office-sprites/char_01..10.png` (10 tiles hand-picked from Kenney's CC0 "RPG Urban Pack") — see CREDITS.txt in that folder. 31 staff deterministically hash to one of the 10 looks. Status is a small color badge (not a ring — reads better against an irregular sprite silhouette). Desks are still procedural (no matching free desk sprite was found).
>
> Task 2 and Task 3 below were executed as one combined commit because of deviation #2 (Task 2's original commit was superseded before it landed). Everything else matches the plan as written.

**Goal:** Ship a new admin-only page `/app/office` that renders all 31 AI staff (`app/platform/team.py` `STAFF`) as avatars grouped into 4 visual rooms (Coordinator/Voice/Marketing/Platform), with live status-color rings and a click-to-expand activity panel — replacing zero visual "office map" today with a working, data-driven one.

**Architecture:** One new self-contained frontend page (`frontend/office_map.html`, same pattern as `team_dashboard.html`/`control_center.html` — inline `<style>`+`<script>`, no build step) using Phaser.js (vendored locally, not CDN — see status note above; MIT license) for canvas layout/interactivity. Rooms are drawn with Phaser `Graphics`/`Text` primitives; avatars use real vendored character-sprite images (see status note above), not Graphics primitives as originally planned. All data comes from two already-existing, unmodified endpoints: `GET /api/platform/team` (roster + live state) and `GET /api/platform/team/events?member=&limit=` (per-agent event log). Zero backend changes.

**Tech Stack:** Phaser 3.80 (vendored at `frontend/design-system/vendor/phaser.min.js` — see status note; originally planned as CDN, same CDN-script pattern as Chart.js in `frontend/admin_dashboard.html:7`), vanilla JS (no framework, matches every other admin page in this repo), existing `/design-system/styles.css`.

## Global Constraints

- **No backend changes.** Every data need is already served by `GET /api/platform/team` (`app/api/team.py:18`, shape = `team_status()` in `app/platform/team.py:516`) and `GET /api/platform/team/events?member=&limit=` (`app/api/team.py:36`, already supports a `member` filter). Both are `Depends(require_admin)`-gated already.
- **Auth pattern**: mirror `frontend/team_dashboard.html` exactly — Bearer token read from `localStorage.getItem("accessToken")`, sent as `Authorization: Bearer <token>` header on every fetch. No server-side auth on the `/app/office` page route itself (matches every other `/app/*` page route in `app/main.py` — auth is enforced by the API calls the page makes, not the page route).
- **No new frontend test framework.** This project has no JS unit-test harness; frontend pages are verified by manually driving the browser-preview tool (`preview_start`/`preview_screenshot`/`preview_snapshot`/`preview_click`/`preview_console_logs`) — every task's "test" step in this plan uses that tool, not `pytest`.
- **Never raise / graceful degrade**: any fetch failure must show a small inline banner, never a blank crashed canvas, and must not throw an uncaught JS error (check via `preview_console_logs` after every task).
- **Colors** (reuse existing admin brand palette, do not invent new ones): status-ring `working=#10b981` (green), `active=#f59e0b` (amber), `offline=#94a3b8` (grey). Room fills: Coordinator `#ede9fe`/border `#8b5cf6`, Voice `#dbeafe`/border `#3b82f6`, Marketing `#fce7f3`/border `#ec4899`, Platform `#d1fae5`/border `#10b981`.
- **Room membership is computed from the API response at runtime** (`product` field per member, `key === "manager"` → Coordinator), never hardcoded per-name — so adding a 32nd `STAFF` entry later needs zero map-code changes (per the approved design spec's scalability requirement).

---

### Task 1: Backend route + skeleton page (Phaser boots, blank canvas)

**Files:**
- Modify: `app/main.py` — add `GET /app/office` route near the existing `GET /app/team` route (`app/main.py:1156`).
- Create: `frontend/office_map.html`

**Interfaces:**
- Produces: page reachable at `http://<host>/app/office`, containing a `<div id="stage">` that Phaser mounts into, and a global `OFFICE` JS namespace object later tasks attach functions to (`OFFICE.fetchTeam`, `OFFICE.render`, etc.) — Task 2 defines these.

- [ ] **Step 1: Add the page route**

In `app/main.py`, right after the existing `/app/team` route:

```python
@app.get("/app/team", tags=["Frontend"])
async def team_dashboard_page():
    """AI Staff / Team dashboard (roster, live activity, manual runs)."""
    return FileResponse(str(FRONTEND_DIR / "team_dashboard.html"))


@app.get("/app/office", tags=["Frontend"])
async def office_map_page():
    """Virtual office map — all AI staff grouped into rooms, live status + activity."""
    return FileResponse(str(FRONTEND_DIR / "office_map.html"))
```

- [ ] **Step 2: Create the skeleton page**

Create `frontend/office_map.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
<link rel="manifest" href="/manifest.json"><meta name="theme-color" content="#4f46e5">
<title>LeadGen AI — Virtual Office</title>
<link rel="stylesheet" href="/design-system/styles.css" />
<script src="https://cdn.jsdelivr.net/npm/phaser@3.80.1/dist/phaser.min.js"></script>
<style>
  :root{
    --brand:#6d28d9; --brand-2:#4f46e5; --brand-soft:#ede9fe;
    --ink:#1e1b2e; --muted:#6b7280; --line:#e9e7f2; --bg:#f6f5fb; --card:#ffffff;
    --ok:#10b981; --warn:#f59e0b; --err:#ef4444;
  }
  *{box-sizing:border-box}
  html,body{margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,Arial,sans-serif;
    background:var(--bg);color:var(--ink);font-size:14px}
  .topbar{position:sticky;top:0;z-index:20;background:#fff;border-bottom:1px solid var(--line);
    padding:12px 16px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
  .brand{display:flex;align-items:center;gap:9px;font-weight:800;font-size:15px;text-decoration:none;color:var(--ink)}
  .brand .logo{width:32px;height:32px;border-radius:9px;background:linear-gradient(135deg,#a78bfa,#6366f1);
    display:grid;place-items:center;font-size:16px;color:#fff}
  .back{font-size:12.5px;color:var(--muted);text-decoration:none;font-weight:600}
  .spacer{flex:1}
  #banner{display:none;max-width:1200px;margin:10px auto 0;padding:0 16px}
  #banner .b{background:#fef2f2;color:#991b1b;border:1px solid #fecaca;border-radius:10px;
    padding:8px 14px;font-size:12.5px;font-weight:600}
  #wrap{max-width:1200px;margin:16px auto;padding:0 16px}
  #stage{width:100%;border-radius:14px;overflow:hidden;box-shadow:0 1px 3px rgba(24,16,55,.06),0 8px 24px rgba(24,16,55,.05)}
</style>
</head>
<body>
  <div class="topbar">
    <a class="brand" href="/app/admin"><span class="logo">🏢</span> Virtual Office</a>
    <a class="back" href="/app/team">AI Staff Team (list view) →</a>
    <div class="spacer"></div>
  </div>
  <div id="banner"><div class="b" id="bannerMsg"></div></div>
  <div id="wrap"><div id="stage"></div></div>
<script>
  var OFFICE = {};
  OFFICE.game = new Phaser.Game({
    type: Phaser.AUTO,
    parent: "stage",
    width: 1200,
    height: 820,
    backgroundColor: "#f6f5fb",
    scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH },
    scene: { create: function(){ OFFICE.scene = this; } }
  });
</script>
</body>
</html>
```

- [ ] **Step 3: Verify it loads (browser-preview, no pytest)**

Run (dev server must already be up via `preview_start` on the `leadgen-app` config):
- `preview_eval`: `location.assign('/app/office')`
- `preview_console_logs` (level `error`) → expect **no errors**
- `preview_screenshot` → expect a blank light-grey canvas under the "🏢 Virtual Office" header

- [ ] **Step 4: Commit**

```bash
git add app/main.py frontend/office_map.html
git commit -m "feat(office): add /app/office route + Phaser skeleton page"
```

---

### Task 2: Data layer — fetch roster, compute room membership, draw room rectangles

**Files:**
- Modify: `frontend/office_map.html`

**Interfaces:**
- Consumes: `GET /api/platform/team` → `{members: [{key, product, name, emoji, title, duties, schedule, state, last_active_mins, today_actions, today_errors, last_activity}], totals: {...}}` (`app/platform/team.py:516` `team_status()`).
- Produces: `OFFICE.ROOMS` (array of room-def objects: `{id, label, x, y, w, h, fill, stroke}`), `OFFICE.roomForMember(m) -> roomId` (string), `OFFICE.fetchTeam() -> Promise<data>`, `OFFICE.drawRooms()` — later tasks (avatars, refresh) call these.

- [ ] **Step 1: Add auth header helper + fetch function**

In `frontend/office_map.html`, the `<script>` block from Task 1 currently reads:

```html
<script>
  var OFFICE = {};
  OFFICE.game = new Phaser.Game({
```

Insert the following **between** the `var OFFICE = {};` line and the `OFFICE.game = new Phaser.Game({` line (do NOT add a second `<script>` tag or a second `var OFFICE = {};` — this is new content inside the existing script block from Task 1):

```javascript
  // ---- Auth (same localStorage key as every other admin page) -------------
  function token(){ return localStorage.getItem("accessToken") || ""; }
  function hdrs(){
    var h = {};
    var t = token();
    if (t) h["Authorization"] = "Bearer " + t;
    return h;
  }
  function showBanner(msg){
    document.getElementById("bannerMsg").textContent = msg;
    document.getElementById("banner").style.display = "block";
  }
  function hideBanner(){ document.getElementById("banner").style.display = "none"; }

  OFFICE.fetchTeam = async function(){
    try {
      var r = await fetch("/api/platform/team", { headers: hdrs() });
      if (!r.ok) throw new Error("HTTP " + r.status);
      var data = await r.json();
      hideBanner();
      return data;
    } catch (e) {
      showBanner("Office data load nahi ho paya — retry karega automatically (25s me)");
      return null;
    }
  };

  // ---- Room layout (2x2-ish: Coordinator strip on top, 3 rooms below) -----
  OFFICE.ROOMS = [
    { id: "coordinator", label: "🧑‍💼 Coordinator Room", x: 0,   y: 0,   w: 1200, h: 130, fill: 0xede9fe, stroke: 0x8b5cf6 },
    { id: "voice",       label: "📞 Voice Team",              x: 0,   y: 130, w: 400,  h: 690, fill: 0xdbeafe, stroke: 0x3b82f6 },
    { id: "marketing",   label: "📣 Marketing Team",          x: 400, y: 130, w: 400,  h: 690, fill: 0xfce7f3, stroke: 0xec4899 },
    { id: "platform",    label: "🛠️ Platform / Engineering",  x: 800, y: 130, w: 400,  h: 690, fill: 0xd1fae5, stroke: 0x10b981 }
  ];

  OFFICE.roomForMember = function(m){
    if (m.key === "manager") return "coordinator";
    if (m.product === "voice") return "voice";
    if (m.product === "marketing") return "marketing";
    return "platform";
  };

  OFFICE.drawRooms = function(){
    var scene = OFFICE.scene;
    OFFICE.ROOMS.forEach(function(room){
      var g = scene.add.graphics();
      g.fillStyle(room.fill, 1);
      g.fillRoundedRect(room.x + 6, room.y + 6, room.w - 12, room.h - 12, 14);
      g.lineStyle(3, room.stroke, 1);
      g.strokeRoundedRect(room.x + 6, room.y + 6, room.w - 12, room.h - 12, 14);
      scene.add.text(room.x + 20, room.y + 16, room.label, {
        fontSize: "16px", fontFamily: "sans-serif", fontStyle: "bold", color: "#1e1b2e"
      });
    });
  };
```

After this insertion, the `<script>` block continues exactly as it did in Task 1 (the `OFFICE.game = new Phaser.Game({...})` call comes right after, unchanged for now — Step 2 below edits its `scene.create` function).

- [ ] **Step 2: Wire room-drawing into the Phaser scene create()**

Replace the `scene: { create: ... }` block:

```javascript
    scene: { create: function(){
      OFFICE.scene = this;
      OFFICE.drawRooms();
    } }
```

- [ ] **Step 3: Verify (browser-preview)**

- `preview_eval`: `location.reload()`
- `preview_screenshot` → expect 4 labeled, colored room rectangles (Coordinator strip on top, Voice/Marketing/Platform in a row below)
- `preview_console_logs` (error) → none

- [ ] **Step 4: Commit**

```bash
git add frontend/office_map.html
git commit -m "feat(office): draw 4 rooms from data-driven layout config"
```

---

### Task 3: Render agent avatars inside their rooms (status-color ring + emoji + name)

**Files:**
- Modify: `frontend/office_map.html`

**Interfaces:**
- Consumes: `OFFICE.ROOMS`, `OFFICE.roomForMember`, `OFFICE.fetchTeam()` (Task 2); each `member` object's `key, emoji, name, state` fields (from `/api/platform/team`).
- Produces: `OFFICE.layoutSlots(room, count) -> [{x,y}, ...]` (deterministic grid layout, scales to any count), `OFFICE.STATE_COLOR`, `OFFICE.avatars` (map `key -> {circle, emoji, label}` so later tasks can update in place without redrawing), `OFFICE.renderMembers(data)` (called on first load and every refresh).

- [ ] **Step 1: Add slot-layout math + avatar drawing + render orchestration**

Add to the `<script>` block in `frontend/office_map.html` (after `OFFICE.drawRooms`):

```javascript
  OFFICE.STATE_COLOR = { working: 0x10b981, active: 0xf59e0b, offline: 0x94a3b8 };
  OFFICE.avatars = {};

  // Deterministic grid slots inside a room — scales to any member count so a
  // 32nd STAFF entry later needs zero layout-code changes.
  OFFICE.layoutSlots = function(room, count){
    var padX = 24, padTop = 56, padBottom = 20;
    var usableW = room.w - padX * 2;
    var usableH = room.h - padTop - padBottom;
    var cols = Math.max(1, Math.min(count, Math.floor(usableW / 72)));
    var rows = Math.max(1, Math.ceil(count / cols));
    var pitchX = usableW / cols;
    var pitchY = Math.min(90, usableH / rows);
    var slots = [];
    for (var i = 0; i < count; i++){
      var r = Math.floor(i / cols), c = i % cols;
      slots.push({
        x: room.x + padX + pitchX * c + pitchX / 2,
        y: room.y + padTop + pitchY * r + pitchY / 2
      });
    }
    return slots;
  };

  OFFICE.drawAvatar = function(m, slot){
    var scene = OFFICE.scene;
    var color = OFFICE.STATE_COLOR[m.state] || OFFICE.STATE_COLOR.offline;
    var circle = scene.add.circle(slot.x, slot.y, 24, 0xffffff).setStrokeStyle(4, color);
    var emoji = scene.add.text(slot.x, slot.y, m.emoji || "🤖", { fontSize: "22px" }).setOrigin(0.5);
    var label = scene.add.text(slot.x, slot.y + 32, m.name, {
      fontSize: "11px", fontFamily: "sans-serif", color: "#1e293b"
    }).setOrigin(0.5, 0);
    [circle, emoji].forEach(function(obj){
      obj.setInteractive({ useHandCursor: true });
      obj.on("pointerdown", function(){ OFFICE.openAgentPanel(m.key); }); // Task 4 defines this
    });
    return { circle: circle, emoji: emoji, label: label };
  };

  OFFICE.renderMembers = function(data){
    if (!data || !data.members) return;
    var byRoom = {};
    OFFICE.ROOMS.forEach(function(r){ byRoom[r.id] = []; });
    data.members.forEach(function(m){ byRoom[OFFICE.roomForMember(m)].push(m); });
    OFFICE.ROOMS.forEach(function(room){
      var members = byRoom[room.id];
      var slots = OFFICE.layoutSlots(room, members.length);
      members.forEach(function(m, i){
        var existing = OFFICE.avatars[m.key];
        if (existing) {
          // Refresh path: just update the status-ring color, don't redraw.
          existing.circle.setStrokeStyle(4, OFFICE.STATE_COLOR[m.state] || OFFICE.STATE_COLOR.offline);
        } else {
          OFFICE.avatars[m.key] = OFFICE.drawAvatar(m, slots[i]);
        }
      });
    });
  };
```

- [ ] **Step 2: Wire initial fetch+render into scene create()**

Replace the `create` function body again:

```javascript
    scene: { create: function(){
      OFFICE.scene = this;
      OFFICE.drawRooms();
      OFFICE.fetchTeam().then(function(data){ OFFICE.renderMembers(data); });
    } }
```

- [ ] **Step 3: Verify (browser-preview)**

- `preview_eval`: `location.reload()`
- Wait for load, then `preview_eval`: `document.title` (sanity it didn't crash) and
  `preview_eval`: `Object.keys(OFFICE.avatars).length` → expect **31**
- `preview_screenshot` → expect ~31 small circular avatars with emoji + name labels, distributed across the 4 rooms, colored rings (mostly grey since this is a quiet dev DB, some green/amber if recent activity exists)
- `preview_console_logs` (error) → none

- [ ] **Step 4: Commit**

```bash
git add frontend/office_map.html
git commit -m "feat(office): render all 31 staff avatars with status-color rings"
```

---

### Task 4: Click-to-expand agent panel (title/duties/state/counts + last 8 events)

**Files:**
- Modify: `frontend/office_map.html`

**Interfaces:**
- Consumes: `GET /api/platform/team/events?member=<key>&limit=8` → `{events: [{id, member, action, detail, status, at}, ...]}` (`app/api/team.py:36`); `data.members` (already fetched, cached in `OFFICE.lastData`) for title/duties/state/counts.
- Produces: `OFFICE.openAgentPanel(key)` (referenced by Task 3's avatar click handler), a DOM side-panel `<div id="agentPanel">`.

- [ ] **Step 1: Add the panel markup + CSS**

Add inside `<body>`, right after `<div id="wrap">...</div>`:

```html
  <div id="agentPanel" class="panel-hidden">
    <div class="panel-card">
      <button id="panelClose" aria-label="Close">✕</button>
      <div id="panelBody">Loading…</div>
    </div>
  </div>
```

Add to the `<style>` block:

```css
  #agentPanel{position:fixed;inset:0;background:rgba(15,17,35,.35);z-index:50;display:flex;
    justify-content:flex-end}
  #agentPanel.panel-hidden{display:none}
  .panel-card{width:340px;max-width:92vw;height:100%;background:#fff;box-shadow:-8px 0 30px rgba(24,16,55,.18);
    padding:18px;overflow-y:auto;position:relative}
  .panel-card #panelClose{position:absolute;top:12px;right:12px;border:none;background:var(--bg);
    width:30px;height:30px;border-radius:8px;cursor:pointer;font-size:14px}
  .panel-title{font-size:17px;font-weight:800;margin:4px 0 2px;padding-right:34px}
  .panel-sub{color:var(--muted);font-size:12.5px;margin-bottom:12px}
  .panel-stats{display:flex;gap:8px;margin:10px 0}
  .panel-stat{background:var(--bg);border-radius:9px;padding:8px 10px;font-size:11.5px;color:var(--muted);flex:1}
  .panel-stat b{display:block;font-size:16px;color:var(--ink)}
  .panel-events{margin-top:14px;font-size:12.5px}
  .panel-event{border-left:3px solid var(--brand-2);padding:6px 10px;margin-bottom:6px;background:var(--bg);border-radius:0 8px 8px 0}
  .panel-event .pe-when{color:var(--muted);font-size:10.5px}
```

- [ ] **Step 2: Add the panel logic**

Add to the `<script>` block (`esc()` matches the same XSS-safe escaper used in `team_dashboard.html:255`):

```javascript
  function esc(s){
    return String(s == null ? "" : s).replace(/[&<>"']/g, function(c){
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];
    });
  }
  function relTime(iso){
    if (!iso) return "";
    var t = new Date(iso).getTime();
    if (isNaN(t)) return "";
    var s = Math.max(0, Math.floor((Date.now() - t) / 1000));
    if (s < 60) return "abhi";
    if (s < 3600) return Math.floor(s / 60) + " min pehle";
    if (s < 86400) return Math.floor(s / 3600) + " ghante pehle";
    return Math.floor(s / 86400) + " din pehle";
  }

  OFFICE.lastData = null; // set by refresh loop (Task 5); Task 3's initial fetch also sets it

  OFFICE.openAgentPanel = async function(key){
    var panel = document.getElementById("agentPanel");
    var body = document.getElementById("panelBody");
    panel.classList.remove("panel-hidden");
    body.innerHTML = "Loading…";
    var member = (OFFICE.lastData && OFFICE.lastData.members || []).filter(function(m){ return m.key === key; })[0];
    var eventsHtml = "";
    try {
      var r = await fetch("/api/platform/team/events?member=" + encodeURIComponent(key) + "&limit=8", { headers: hdrs() });
      var d = r.ok ? await r.json() : { events: [] };
      eventsHtml = (d.events || []).map(function(e){
        return '<div class="panel-event"><div>' + esc(e.detail || e.action) + '</div>' +
          '<div class="pe-when">' + esc(e.action) + ' · ' + relTime(e.at) + '</div></div>';
      }).join("") || '<div class="pe-when">Koi recent activity nahi mili.</div>';
    } catch (e) {
      eventsHtml = '<div class="pe-when">Events load nahi ho paye.</div>';
    }
    if (!member) { body.innerHTML = "Agent nahi mila."; return; }
    body.innerHTML =
      '<div class="panel-title">' + esc(member.emoji) + ' ' + esc(member.name) + '</div>' +
      '<div class="panel-sub">' + esc(member.title) + '</div>' +
      '<div class="panel-sub">' + esc(member.duties) + '</div>' +
      '<div class="panel-stats">' +
        '<div class="panel-stat">State<br><b>' + esc(member.state) + '</b></div>' +
        '<div class="panel-stat">Aaj actions<br><b>' + esc(member.today_actions) + '</b></div>' +
        '<div class="panel-stat">Aaj errors<br><b>' + esc(member.today_errors) + '</b></div>' +
      '</div>' +
      '<div class="panel-events">' + eventsHtml + '</div>';
  };

  document.getElementById("panelClose").onclick = function(){
    document.getElementById("agentPanel").classList.add("panel-hidden");
  };
```

- [ ] **Step 3: Make the initial fetch (Task 3) also populate `OFFICE.lastData`**

In the `scene.create` block, change:

```javascript
      OFFICE.fetchTeam().then(function(data){ OFFICE.renderMembers(data); });
```

to:

```javascript
      OFFICE.fetchTeam().then(function(data){ OFFICE.lastData = data; OFFICE.renderMembers(data); });
```

- [ ] **Step 4: Verify (browser-preview)**

- `preview_eval`: `location.reload()`
- `preview_click` on any avatar circle is not reliable for Phaser canvas objects (canvas has no DOM elements per-avatar) — instead verify via direct call: `preview_eval`: `OFFICE.openAgentPanel(Object.keys(OFFICE.avatars)[0])`
- `preview_snapshot` → expect the side panel visible with a name/title/duties/3 stat boxes/events list (or "Koi recent activity nahi mili.")
- `preview_eval`: `document.getElementById('panelClose').click(); document.getElementById('agentPanel').className` → expect `"panel-hidden"`
- `preview_console_logs` (error) → none

- [ ] **Step 5: Commit**

```bash
git add frontend/office_map.html
git commit -m "feat(office): click-to-expand agent panel with last-8-events"
```

---

### Task 5: Auto-refresh (25s poll) + error-banner on failure

**Files:**
- Modify: `frontend/office_map.html`

**Interfaces:**
- Consumes: `OFFICE.fetchTeam()`, `OFFICE.renderMembers()` (Task 2/3), `OFFICE.lastData` (Task 4).
- Produces: nothing new consumed by later tasks — this is the terminal polling loop for Phase 1.

- [ ] **Step 1: Add the interval**

Add at the end of the `<script>` block, after the `scene.create` wiring:

```javascript
  setInterval(function(){
    OFFICE.fetchTeam().then(function(data){
      if (!data) return; // fetchTeam already showed the error banner
      OFFICE.lastData = data;
      OFFICE.renderMembers(data);
    });
  }, 25000);
```

- [ ] **Step 2: Verify happy path (browser-preview)**

- `preview_eval`: `location.reload()`
- `preview_eval`: `OFFICE.fetchTeam().then(d => window.__t = d)` then `preview_eval`: `!!window.__t` → expect `true`
- `preview_console_logs` (error) → none

- [ ] **Step 3: Verify failure path shows the banner (simulate a broken fetch)**

- `preview_eval`:
  ```javascript
  (function(){
    var orig = window.fetch;
    window.fetch = function(){ return Promise.reject(new Error("simulated")); };
    return OFFICE.fetchTeam().then(function(r){ window.fetch = orig; return r; });
  })()
  ```
  Expect the returned promise to resolve to `null`.
- `preview_snapshot` → expect the red banner text "Office data load nahi ho paya — retry karega automatically (25s me)" visible
- Confirm the canvas underneath is **not** blank/crashed (still shows the last-rendered rooms+avatars) — `preview_screenshot`

- [ ] **Step 4: Commit**

```bash
git add frontend/office_map.html
git commit -m "feat(office): 25s auto-refresh + graceful error banner on fetch failure"
```

---

### Task 6: Admin sidebar link + live teaser card on the main admin dashboard

**Files:**
- Modify: `frontend/admin_dashboard.html:243` (sidebar, add link near "AI Staff Team")
- Modify: `frontend/admin_dashboard.html` (teaser card — placed right after the existing `#sec-advtech-wrap` collapse-card added earlier this session, so it doesn't reintroduce clutter above the fold)

**Interfaces:**
- Consumes: `GET /api/platform/team` via a **new small standalone fetch** (`loadOfficeTeaser()`), reusing the existing `abAuthHdr()` helper already defined in `frontend/admin_dashboard.html` (used by e.g. `frontend/admin_dashboard.html:987`). NOT reusing `loadAgents()` — that function calls a different endpoint (`/api/admin/agents`) for a different panel; hooking into it would be an unrelated coupling.

- [ ] **Step 1: Add the sidebar link**

In `frontend/admin_dashboard.html`, find the existing line:

```html
      <a href="/app/team" role="menuitem" aria-label="AI staff team"><span class="ic" aria-hidden="true">👥</span> AI Staff Team</a>
```

Add directly after it:

```html
      <a href="/app/office" role="menuitem" aria-label="Virtual office map"><span class="ic" aria-hidden="true">🏢</span> Virtual Office</a>
```

- [ ] **Step 2: Add the teaser card**

In `frontend/admin_dashboard.html`, find the closing of the `#sec-advtech-wrap` card added earlier this session:

```html
        </div><!-- /advTechBody -->
      </div><!-- /sec-advtech-wrap -->
```

Add directly after it:

```html
      <div class="card" id="officeTeaser" style="margin-bottom:14px;padding:14px 18px;display:flex;align-items:center;gap:12px;background:linear-gradient(90deg,#ede9fe,#dbeafe);border:1px solid #c7d2fe">
        <div style="font-size:26px">🏢</div>
        <div style="flex:1">
          <div style="font-weight:800;font-size:14px;color:#1e1b2e">Virtual Office</div>
          <div style="font-size:12px;color:#6b7280" id="officeTeaserLine">Loading team status…</div>
        </div>
        <a href="/app/office" class="btn" style="background:#6366f1;color:#fff;text-decoration:none;padding:8px 16px;font-size:12.5px;font-weight:700;border-radius:9px">Poora office dekho →</a>
      </div>
```

- [ ] **Step 3: Add a small standalone function to populate the teaser line**

Add this new function in `frontend/admin_dashboard.html`, right after the existing `loadAgents()` function (`frontend/admin_dashboard.html:1829`):

```javascript
async function loadOfficeTeaser(){
  const el = document.getElementById("officeTeaserLine");
  if (!el) return;
  try{
    const r = await fetch("/api/platform/team", {headers: abAuthHdr(), cache: "no-store"});
    if (!r.ok) { el.textContent = "Office status abhi load nahi ho paya."; return; }
    const d = await r.json();
    const t = (d && d.totals) || {};
    el.textContent = (t.working_members || 0) + "/" + (t.staff_count || 0) + " agents working abhi";
  }catch(e){
    el.textContent = "Office status abhi load nahi ho paya.";
  }
}
```

- [ ] **Step 3b: Call it on page load**

In the `document.addEventListener("DOMContentLoaded", ...)` block in `frontend/admin_dashboard.html` (already modified earlier this session to add the `advTechOpen` restore line), add a call to the new function:

```javascript
document.addEventListener("DOMContentLoaded", ()=>{
  try{ if(localStorage.getItem("admin_advTechOpen") === "1") _advTechSetOpen(true); }catch(e){}
  loadOfficeTeaser();
  adminAuthBoot();
  loadTodayBiz();
  ...
```

(Insert `loadOfficeTeaser();` as a new line — the surrounding lines already exist in the file exactly as shown; only the one new line is being added.)

- [ ] **Step 4: Verify (browser-preview)**

- `preview_eval`: `location.assign('/app/admin')` then wait for load
- `preview_snapshot` → expect a "Virtual Office" teaser card showing "N/31 agents working abhi" and a working "Poora office dekho →" link
- `preview_click` the link → `preview_eval`: `location.pathname` → expect `/app/office`
- `preview_console_logs` (error) → none

- [ ] **Step 5: Commit**

```bash
git add frontend/admin_dashboard.html
git commit -m "feat(office): sidebar link + live teaser card on main admin dashboard"
```

---

## Explicitly deferred (Phase 2 / Phase 3 — see design spec, do NOT build in this plan)

- Movement-tween (desk ↔ room-center on new events), speech bubbles from event `detail` text, Coordinator-room live ticker (`member === "manager"` events) — **Phase 2**.
- Cross-room animated workflow-token following `coordinate_start` → `coordinated_step` → `coordinate_done` sequences — **Phase 3**.
- `GET /api/events/stream` (SSE, already exists — `app/api/events.py:158`, same client pattern already used in `frontend/control_center.html:1537`) is the right transport for Phase 2's real-time triggers; Phase 1 deliberately uses plain 25s polling only, per the approved spec's phase boundaries.
- CC0 pixel-art tile/sprite assets (visual polish layer) — open implementation detail per the spec, not needed for Phase 1's Graphics-primitive rendering.
