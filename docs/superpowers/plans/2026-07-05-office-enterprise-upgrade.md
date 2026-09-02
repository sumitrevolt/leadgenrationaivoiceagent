# Office Enterprise Upgrade (re-implementation) Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-implement the lost "office-enterprise-upgrade" patch on `frontend/office_map.html`: 6 map bug fixes, dark mode, 6 labelled sections + scroll-spy, card polish, Ctrl+K command palette, toast alerts, honest session-expiry messaging, and background-tab polling pause — all additive, zero feature removal.

**Architecture:** Single-file change (`frontend/office_map.html` — inline CSS + inline ES5-style JS, Hinglish UI copy/comments) plus one new pytest file of static HTML assertions + a node syntax gate. No backend changes. The Phaser map keeps its light pixel-art look in dark mode (only the DOM page themes).

**Tech Stack:** Vanilla JS (ES5 style, `var`, no modules), Phaser 3.80.1 (vendored), pytest for static assertions, `node --check` for JS syntax.

## Global Constraints

- Only files touched: `frontend/office_map.html`, `tests/test_office_map_frontend.py`, this plan file.
- All changes ADDITIVE — the no-removal guard test (Task 1) lists every pre-existing element ID and must pass after every task.
- This repo has live background automation editing files: NEVER `git add -A` / `git add .`. Stage explicit paths only.
- Match file style: `var` (not let/const), Hinglish comments, function-per-concern on the `OFFICE` namespace.
- JS must pass `node --check` after every task (test in Task 1 enforces this).
- Commit after every task with the exact message given; end commit messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Run tests with the repo venv: `cd C:\Users\Ratanshila\Documents\leadgenrationaiagent && .venv\Scripts\python -m pytest tests/test_office_map_frontend.py -v` (fall back to `python -m pytest` if `.venv` missing).

---

### Task 1: Test harness — syntax gate + no-removal guard

**Files:**
- Create: `tests/test_office_map_frontend.py`

**Interfaces:**
- Produces: module-level `SRC` (the HTML text) that later tasks' tests reuse; test `test_inline_js_syntax_ok` that every later task must keep green.

- [ ] **Step 1: Write the test file**

```python
"""Static assertions on frontend/office_map.html (office-enterprise-upgrade).

HTML is a single self-contained page (inline CSS+JS), so tests are
(1) a node --check syntax gate on the inline script,
(2) a no-removal guard: every pre-upgrade element ID must still exist,
(3) per-feature markers added task-by-task by the upgrade plan
    (docs/superpowers/plans/2026-07-05-office-enterprise-upgrade.md).
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HTML_PATH = Path(__file__).resolve().parents[1] / "frontend" / "office_map.html"
SRC = HTML_PATH.read_text(encoding="utf-8")

# Every interactive/panel ID that existed BEFORE the upgrade — none may vanish.
PRE_EXISTING_IDS = [
    "banner", "bannerRetry", "page", "quickNav", "statusSummary", "warRoom",
    "bossCommandInput", "bossCommandBtn", "bossCommandResult", "trustStrip",
    "bossBriefBody", "priorityActionStack", "warKpiGrid", "pulseStrip",
    "councilPanel", "councilTopic", "councilRunBtn", "councilDeeper", "councilResult",
    "capabilitiesPanel", "kpiRow", "nbaCard", "nbaList", "enterpriseCard",
    "enterpriseScore", "enterpriseFeatureGrid", "mapToolbar", "agentSearch",
    "agentSearchResults", "zoomInBtn", "zoomOutBtn", "zoomResetBtn", "mapHint",
    "modeToggle", "stageWrap", "stage", "previewOverlay", "roomListCompact",
    "replayPanel", "replayList", "feedCard", "filterRow", "tickerList",
    "coordHistoryWrap", "coordHistoryList", "leaderboardPanel", "leaderboardList",
    "activityPanel", "activityChart", "activityHours", "activityMeta",
    "pipelineBoard", "boardRow", "schedulePanel", "scheduleList", "recurringStrip",
    "systemMapCard", "systemMapToggle", "systemMapBody", "systemMapFrame",
    "workflowRunsCard", "workflowRunsList", "activeCoordCard", "activeCoordList",
    "approvalsPanel", "bossReviewBtn", "bossReviewNote", "approvalsList",
    "decisionTrail", "systemHealthPanel", "healthList", "schedulerPanel",
    "schedBadge", "schedList", "failureConsoleCard", "dlqSweepBtn",
    "failureConsoleList", "dlqRepairCard", "dlqRepairBadge", "dlqRepairSummary",
    "hotQueueCard", "hotQueueBadge", "hotQueueSummary", "roomTooltip",
    "coordinatorTickerBox", "coordinatorTicker", "agentPanel", "panelClose",
    "panelBody", "legendToggle", "legendPopover", "legendClose", "briefingBtn",
    "briefingModal", "briefingClose", "briefingDate", "briefingBody",
    "briefingPlay", "briefingAudioNote", "briefingRefresh", "istClock",
    "freshnessBadge", "viewModeBtn", "manualRefreshBtn",
]


def _inline_js() -> str:
    blocks = re.findall(r"<script>(.*?)</script>", SRC, re.S)
    assert blocks, "no inline <script> block found"
    return "\n;\n".join(blocks)


def test_inline_js_syntax_ok(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node not on PATH")
    f = tmp_path / "office_inline.js"
    f.write_text(_inline_js(), encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_no_pre_existing_id_removed():
    missing = [i for i in PRE_EXISTING_IDS if f'id="{i}"' not in SRC]
    assert not missing, f"pre-upgrade IDs vanished: {missing}"
```

- [ ] **Step 2: Run it — both tests must PASS on the untouched file**

Run: `.venv\Scripts\python -m pytest tests/test_office_map_frontend.py -v`
Expected: 2 passed (this is the baseline; no red phase for Task 1 itself).

- [ ] **Step 3: Commit**

```bash
git add tests/test_office_map_frontend.py
git commit -m "test(office): static guard for office_map.html — JS syntax gate + no-removal ID list"
```

---

### Task 2: Map bug fixes A — unique agent colors, overflow shrink, offline snap-back, unmapped "?" badge

**Files:**
- Modify: `frontend/office_map.html` (JS: `charKeyFor` area ~1083, `layoutSlots` ~1089, `drawAvatar` ~1108, `setAvatarState` ~1160, `enterPreviewMode` ~1295, `renderMembers` ~1339)
- Test: `tests/test_office_map_frontend.py`

**Interfaces:**
- Produces: `OFFICE.colorForKey(key) -> int`, `OFFICE.colorCssForKey(key) -> "#rrggbb"`, `OFFICE.layoutSlots(room, count) -> {slots: [{x,y}], scale: number}`, `OFFICE.drawAvatar(m, slot, room, sizeScale)`. Later tasks (palette) reuse `colorCssForKey`.

- [ ] **Step 1: Add failing tests** (append to `tests/test_office_map_frontend.py`)

```python
def test_bugfix_unique_agent_colors():
    assert "OFFICE.colorForKey" in SRC
    assert "colorCssForKey" in SRC
    assert "setTint(OFFICE.colorForKey" in SRC          # sprite + desk tinted


def test_bugfix_room_overflow_shrink():
    assert "return { slots: slots, scale:" in SRC        # layoutSlots new shape
    assert "sizeScale" in SRC                            # drawAvatar consumes it


def test_bugfix_offline_snapback():
    assert "killTweensOf(av.group)" in SRC               # instant desk return


def test_bugfix_unmapped_room_badge():
    assert "unmapped" in SRC
    assert "#f97316" in SRC                              # orange ? badge
```

- [ ] **Step 2: Run tests to verify the 4 new ones FAIL**

Run: `.venv\Scripts\python -m pytest tests/test_office_map_frontend.py -v`
Expected: 4 failed (new), 2 passed.

- [ ] **Step 3: Implement — unique colors.** Right after `OFFICE.charKeyFor` (after its closing `};`), insert:

```js
  // ---- BUGFIX: 31 staff / sirf 10 sprites → clones. Har agent (aur uski desk)
  // ka apna deterministic pastel color — golden-angle hue, roster order pe stable.
  OFFICE.AGENT_COLORS = {};
  OFFICE._colorSeq = 0;
  OFFICE.colorForKey = function(key){
    if (OFFICE.AGENT_COLORS[key] != null) return OFFICE.AGENT_COLORS[key];
    var hue = (OFFICE._colorSeq++ * 137.508) % 360;
    var c = Phaser.Display.Color.HSLToColor(hue / 360, 0.62, 0.72).color;
    OFFICE.AGENT_COLORS[key] = c;
    return c;
  };
  OFFICE.colorCssForKey = function(key){
    return "#" + ("00000" + OFFICE.colorForKey(key).toString(16)).slice(-6);
  };
```

- [ ] **Step 4: Implement — layoutSlots returns scale.** Replace the whole `OFFICE.layoutSlots` function with:

```js
  OFFICE.layoutSlots = function(room, count){
    var padX = 20, padTop = 46, padBottom = 16;
    var usableW = room.w - padX * 2;
    var usableH = room.h - padTop - padBottom;
    var cols = Math.max(1, Math.min(count, Math.floor(usableW / 62)));
    var rows = Math.max(1, Math.ceil(count / cols));
    var pitchX = usableW / cols;
    var pitchY = usableH / rows;
    // BUGFIX: room bhar jaye to avatars overlap hote the — ab pitch comfort-box
    // (62x74) se chhota hone par avatars gracefully shrink ho ke fit hote hain.
    var scale = Math.max(0.55, Math.min(1, pitchX / 62, pitchY / 74));
    pitchY = Math.min(74, pitchY);
    var slots = [];
    for (var i = 0; i < count; i++){
      var r = Math.floor(i / cols), c = i % cols;
      slots.push({
        x: room.x + padX + pitchX * c + pitchX / 2,
        y: room.y + padTop + pitchY * r + pitchY / 2
      });
    }
    return { slots: slots, scale: scale };
  };
```

- [ ] **Step 5: Implement — drawAvatar takes sizeScale, tints, ? badge.** Replace the whole `OFFICE.drawAvatar` function with (diff vs old: `sizeScale` param + `f` factor on every offset/scale, `setTint` on sprite+desk, label color from `colorCssForKey`, orange `?` badge when `m.unmapped`):

```js
  OFFICE.drawAvatar = function(m, slot, room, sizeScale){
    var scene = OFFICE.scene;
    var color = OFFICE.STATE_COLOR[m.state] || OFFICE.STATE_COLOR.offline;
    var f = sizeScale || 1;                    // room-density shrink factor
    var s = OFFICE.TILE_SCALE * f;
    var agentTint = OFFICE.colorForKey(m.key); // unique per-agent identity color
    var chair = scene.add.circle(slot.x, slot.y - 13 * f, 6.5 * f, 0x64748b).setStrokeStyle(1.5, 0x334155);
    var desk = scene.add.image(slot.x, slot.y + 13 * f, "desk_1").setScale(s);
    desk.setTint(OFFICE.colorForKey(m.key));
    var monitor = scene.add.rectangle(slot.x, slot.y + 9 * f, 11 * f, 8 * f, 0x0f172a).setStrokeStyle(1, 0x334155);
    var monitorGlow = scene.add.rectangle(slot.x, slot.y + 9 * f, 8 * f, 5 * f, 0x38bdf8, 0.95);
    var sprite = scene.add.image(0, -4 * f, OFFICE.charKeyFor(m.key)).setScale(s);
    sprite.setTint(OFFICE.colorForKey(m.key));
    sprite.setInteractive({ useHandCursor: true });
    sprite.on("pointerup", function(){ if (!OFFICE.dragMoved) OFFICE.openAgentPanel(m.key); });
    sprite.on("pointerover", function(p){
      var tip = document.getElementById("roomTooltip");
      var a = OFFICE.agentByKey[m.key] || m;
      var reason = a.offlineReason || a.offline_reason;
      var extra = (a.state || a.status) === "offline" && reason
        ? esc(OFFICE.offlineReasonText(reason))
        : "Aaj " + esc(a.todayActions != null ? a.todayActions : "?") + " action(s)";
      if (m.unmapped) extra = "⚠ Room map nahi mila — default room me dikh raha hai<br>" + extra;
      tip.innerHTML = "<b>" + esc(a.name || m.name) + " — " + esc(a.state || a.status || "?") + "</b><br>" + extra;
      tip.style.display = "block";
      OFFICE.moveRoomTooltip(p);
    });
    sprite.on("pointermove", function(p){ OFFICE.moveRoomTooltip(p); });
    sprite.on("pointerout", function(){ OFFICE.hideRoomTooltip(); });
    var badge = scene.add.circle(12 * f, 6 * f, 5.5 * f, color).setStrokeStyle(2, 0xffffff);
    var label = scene.add.text(0, 30 * f, String(m.name || "").slice(0, 10), {
      fontSize: "10px", fontFamily: "sans-serif", color: OFFICE.colorCssForKey(m.key), fontStyle: "bold"
    }).setOrigin(0.5, 0).setShadow(0, 1, "#1e293b", 2, false, true);
    var parts = [sprite, badge, label];
    // BUGFIX: naya staff jiska room map nahi — pehle chupchaap galat room me
    // chala jata tha. Ab orange "?" badge se turant dikhta hai.
    if (m.unmapped) {
      parts.push(scene.add.text(-14 * f, -22 * f, "?", {
        fontSize: "11px", fontFamily: "sans-serif", fontStyle: "bold",
        color: "#ffffff", backgroundColor: "#f97316", padding: { x: 3, y: 1 }
      }).setOrigin(0.5));
    }
    var group = scene.add.container(slot.x, slot.y, parts);
    var bobTween = scene.tweens.add({
      targets: sprite, y: -7 * f, duration: 1150 + Math.random() * 500,
      yoyo: true, repeat: -1, ease: "Sine.easeInOut"
    });
    var av = {
      desk: desk, sprite: sprite, badge: badge, label: label, group: group,
      extras: [chair, monitor, monitorGlow],
      homeX: slot.x, homeY: slot.y, wandering: false, pulse: null, pulseTween: null,
      bobTween: bobTween, room: room || null, state: m.state, sizeScale: f
    };
    OFFICE.setAvatarState(av, m.state);
    OFFICE.scheduleWander(m.key);
    return av;
  };
```

- [ ] **Step 6: Implement — offline snap-back.** In `OFFICE.setAvatarState`, immediately after `av.state = state;`, insert:

```js
    // BUGFIX: offline hote hi turant desk pe wapas — pehle chalu walk-tween
    // 2-3s tak chalta rehta tha (group tweens kill + position reset).
    if (state === "offline") {
      try { scene.tweens.killTweensOf(av.group); } catch (e) {}
      av.group.setPosition(av.homeX, av.homeY);
      try { av.sprite.setFlipX(false); } catch (e) {}
      av.wandering = false;
    }
```

Also update the bob reset line inside the same function: `av.sprite.y = -4;` → `av.sprite.y = -4 * (av.sizeScale || 1);`

- [ ] **Step 7: Update both layoutSlots call sites.**

In `OFFICE.enterPreviewMode`, replace:
```js
      var slots = OFFICE.layoutSlots(room, members.length);
```
with
```js
      var layout = OFFICE.layoutSlots(room, members.length);
```
and `OFFICE.drawAvatar(m, slots[i], room)` → `OFFICE.drawAvatar(m, layout.slots[i], room, layout.scale)`.

In `OFFICE.renderMembers`, replace the members loop:
```js
      snapshot.agents.forEach(function(a){
        var m = { key: a.key, name: a.name, emoji: a.emoji, title: a.title, duties: a.duties, state: a.status, offlineReason: a.offline_reason };
        (byRoom[a.room] || byRoom.platform_engineering).push(m);
      });
      OFFICE.ROOMS.forEach(function(room){
        var members = byRoom[room.id];
        var slots = OFFICE.layoutSlots(room, members.length);
        members.forEach(function(m, i){
          var existing = OFFICE.avatars[m.key];
          if (existing) {
            OFFICE.setAvatarState(existing, m.state);
          } else {
            OFFICE.avatars[m.key] = OFFICE.drawAvatar(m, slots[i], room);
          }
        });
      });
```
with
```js
      snapshot.agents.forEach(function(a){
        var m = { key: a.key, name: a.name, emoji: a.emoji, title: a.title, duties: a.duties,
                  state: a.status, offlineReason: a.offline_reason, unmapped: !byRoom[a.room] };
        a.unmapped = m.unmapped;   // tooltip/drawer ke liye bhi yaad rakho
        (byRoom[a.room] || byRoom.platform_engineering).push(m);
      });
      OFFICE.ROOMS.forEach(function(room){
        var members = byRoom[room.id];
        var layout = OFFICE.layoutSlots(room, members.length);
        members.forEach(function(m, i){
          var existing = OFFICE.avatars[m.key];
          if (existing) {
            OFFICE.setAvatarState(existing, m.state);
          } else {
            OFFICE.avatars[m.key] = OFFICE.drawAvatar(m, layout.slots[i], room, layout.scale);
          }
        });
      });
```

- [ ] **Step 8: Run tests — all green**

Run: `.venv\Scripts\python -m pytest tests/test_office_map_frontend.py -v`
Expected: 6 passed.

- [ ] **Step 9: Commit**

```bash
git add frontend/office_map.html tests/test_office_map_frontend.py
git commit -m "fix(office-map): unique per-agent colors, room-overflow shrink, instant offline snap-back, unmapped-room ? badge"
```

---

### Task 3: Map bug fixes B — coordinator ticker on mobile/simple + lazy Phaser boot (Simple→Pro blank map)

**Files:**
- Modify: `frontend/office_map.html` (CSS `@media (max-width:760px)` block ~330 & simple-mode block ~266; JS `updateTickerBoxPos` ~780, game construction ~3202, `setViewMode` ~3424, view-mode init ~3441)
- Test: `tests/test_office_map_frontend.py`

**Interfaces:**
- Produces: `OFFICE.GAME_CONFIG` (object), `OFFICE.bootGame()` (idempotent). `OFFICE.game` may now be `undefined` until first Pro view on desktop — all existing code already guards on `OFFICE.scene`.

- [ ] **Step 1: Add failing tests**

```python
def test_bugfix_ticker_box_hidden_on_mobile_and_simple():
    assert "#coordinatorTickerBox{display:none !important}" in SRC.replace(" ", "")


def test_bugfix_lazy_phaser_boot():
    assert "OFFICE.bootGame" in SRC
    assert "OFFICE.GAME_CONFIG" in SRC
    # game creation must be guarded, not unconditional
    assert "OFFICE.game = new Phaser.Game(OFFICE.GAME_CONFIG)" in SRC
```

- [ ] **Step 2: Run tests — 2 new FAIL**

Run: `.venv\Scripts\python -m pytest tests/test_office_map_frontend.py -v`
Expected: 2 failed, 6 passed.

- [ ] **Step 3: CSS — hide ticker box when map hidden.** Inside the existing `@media (max-width:760px){...}` block, after `#mapToolbar{display:none}`, add:

```css
    #coordinatorTickerBox{display:none !important}
```

And extend the simple-mode hide rule (the long `body.simple-mode ...` selector list ending `{display:none !important}`): add `body.simple-mode #coordinatorTickerBox` to the selector list.

- [ ] **Step 4: JS — guard updateTickerBoxPos against hidden/zero-size map.** At the top of `OFFICE.updateTickerBoxPos`, after the `if (!tickerBox ...) return;` line, add:

```js
    var wrap = document.getElementById("stageWrap");
    if (!wrap || wrap.clientWidth === 0) return;  // map hidden (simple/mobile) — position mat karo
```

- [ ] **Step 5: JS — lazy boot.** Replace `OFFICE.game = new Phaser.Game({ ... });` (the whole constructor call ~3202–3252) with the SAME config object assigned to `OFFICE.GAME_CONFIG` plus a guarded boot function — i.e. change the first line to `OFFICE.GAME_CONFIG = {` and the closing `});` to `};`, then append:

```js
  // BUGFIX (sabse bada): Simple→Pro pe map BLANK. Root cause: game yahan
  // (script order me) boot hota tha, par simple-mode class neeche lagti thi —
  // 0-width parent pe Scale.FIT 0x0 canvas bake karta jo refresh() se recover
  // nahi hota. Fix: Phaser sirf tab boot karo jab #stageWrap sach me visible ho.
  OFFICE.bootGame = function(){
    if (OFFICE.game) return;
    var wrap = document.getElementById("stageWrap");
    if (!wrap || wrap.clientWidth === 0) return;   // simple mode / mobile — abhi nahi
    OFFICE.game = new Phaser.Game(OFFICE.GAME_CONFIG);
  };
```

(Do NOT call `bootGame()` here — call site moves below the view-mode init, Step 6.)

- [ ] **Step 6: JS — boot after view-mode init + no-game data load.** In `OFFICE.setViewMode`, replace the `if (m === "pro") { setTimeout(...) }` block with:

```js
    if (m === "pro") {
      setTimeout(function(){
        OFFICE.bootGame();   // pehli baar simple me load hua tha to game ab banega
        try { if (OFFICE.game && OFFICE.game.scale) OFFICE.game.scale.refresh(); } catch (e) {}
      }, 60);
    }
```

Then, right AFTER the existing view-mode init lines
```js
  var _vm = "pro";
  try { _vm = localStorage.getItem("officeViewMode") || "pro"; } catch (e) {}
  OFFICE.setViewMode(_vm);
```
add:

```js
  OFFICE.bootGame();   // pro + desktop = turant boot; warna Pro-switch pe hoga
  // Game na bane (simple mode / mobile) to bhi DOM panels ko data chahiye —
  // create() wala initial load nahi chalega, isliye yahan se seed karo.
  if (!OFFICE.game) {
    OFFICE.refreshSnapshot();
    OFFICE.pollEvents();
    OFFICE.renderActivityChart();
  }
```

Note: `create()` already calls `OFFICE.refreshSnapshot()` when the game does boot (including a late boot on Pro-switch), which draws the avatars — no extra wiring needed there.

- [ ] **Step 7: Run tests — all green**

Run: `.venv\Scripts\python -m pytest tests/test_office_map_frontend.py -v`
Expected: 8 passed.

- [ ] **Step 8: Commit**

```bash
git add frontend/office_map.html tests/test_office_map_frontend.py
git commit -m "fix(office-map): lazy Phaser boot kills Simple->Pro blank map; coordinator ticker hidden on mobile/simple"
```

---

### Task 4: Dark mode (system + manual toggle)

**Files:**
- Modify: `frontend/office_map.html` (CSS `:root` area ~14; topbar markup ~355; inline `background:#fff` sweeps; JS near view-mode init)
- Test: `tests/test_office_map_frontend.py`

**Interfaces:**
- Produces: `<html data-theme="dark|light">` attribute, `OFFICE.applyTheme(pref)`, `OFFICE.themePref` ("auto"|"dark"|"light"), `#themeBtn`. The command palette (Task 6) calls `OFFICE.cycleTheme()`.

- [ ] **Step 1: Add failing tests**

```python
def test_dark_mode():
    assert 'data-theme="dark"' in SRC or "data-theme" in SRC
    assert 'id="themeBtn"' in SRC
    assert "prefers-color-scheme" in SRC
    assert "OFFICE.cycleTheme" in SRC
```

- [ ] **Step 2: Run — FAIL.** Expected: 1 failed, 8 passed.

- [ ] **Step 3: CSS variables + surface overrides.** Immediately after the `:root{...}` block, add:

```css
  :root[data-theme="dark"]{
    --brand-soft:#312e58; --ink:#e7e5f4; --muted:#9ca3af; --line:#2b2b40;
    --bg:#12121c; --card:#1c1c2c;
  }
  :root[data-theme="dark"] .topbar{background:var(--card)}
  :root[data-theme="dark"] .war-card, :root[data-theme="dark"] .mode-toggle,
  :root[data-theme="dark"] #agentSearchResults, :root[data-theme="dark"] .panel-card,
  :root[data-theme="dark"] #legendPopover, :root[data-theme="dark"] .map-btn,
  :root[data-theme="dark"] .ia-btn, :root[data-theme="dark"] #schedList .sched-btn,
  :root[data-theme="dark"] .qn-chip{background:var(--card);color:var(--ink)}
  :root[data-theme="dark"] .priority-item:hover, :root[data-theme="dark"] .feature-tile:hover{background:#262640}
  :root[data-theme="dark"] .lb-name{color:var(--ink)}
  :root[data-theme="dark"] #agentSearch, :root[data-theme="dark"] .stage-search{background:var(--card);color:var(--ink)}
```

- [ ] **Step 4: Sweep inline card-whites to var(--card).** These exact replacements in the HTML/JS (CSS vars resolve in inline styles too):
  - Topbar buttons `viewModeBtn`, `briefingBtn`, `manualRefreshBtn` inline styles: `background:#fff` → `background:var(--card)` (3×).
  - `#legendPopover` inline `background:#fff` → `background:var(--card)`; `#legendClose` inline `background:#fff` → `background:var(--card)`.
  - Briefing modal inner div inline `background:#fff` → `background:var(--card)`; `briefingClose` + `briefingPlay` inline `background:#fff` → `background:var(--card)`.
  - `bossReviewBtn`, `dlqSweepBtn` inline `background:#fff` → `background:var(--card)`.
  - CSS rules: `.mode-toggle{...background:#fff...}`, `.war-card{...background:#fff}`, `#agentSearchResults{...background:#fff...}`, `.map-btn{...background:#fff...}`, `.panel-card{...background:#fff...}`, `.ia-btn{...background:#fff...}`, `#schedList .sched-btn{...background:#fff...}`, `.topbar{...background:#fff...}` → all `background:var(--card)`.
  - JS `btnStyle` strings (DLQ drawer + hot-queue drawer, 2 places): `background:#fff` → `background:var(--card)`, and append `;color:var(--ink)`.
  - `councilTopic` textarea + `kaamGoal` textarea (JS string) inline style: append `;background:var(--card);color:var(--ink)`.
  - Coordinator ticker box inline `background:#fff` → `background:var(--card)`.
  - Keep red banner, colored CTA buttons, feed-card (already dark), and the Phaser canvas untouched.

- [ ] **Step 5: Topbar button + JS.** In the topbar, before `viewModeBtn`, add:

```html
    <button id="themeBtn" style="border:1px solid var(--line);background:var(--card);border-radius:7px;
      padding:4px 10px;font-size:11.5px;font-weight:700;cursor:pointer"
      title="Theme: Auto (system) → Dark → Light">🌗 Auto</button>
```

In the JS, right before the view-mode init block, add:

```js
  // ---- Dark mode: system (auto) + manual toggle, localStorage me yaad -------
  OFFICE.themePref = "auto";
  OFFICE.applyTheme = function(pref){
    OFFICE.themePref = pref;
    var dark = pref === "dark" || (pref === "auto" && window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    var btn = document.getElementById("themeBtn");
    if (btn) btn.textContent = pref === "auto" ? "🌗 Auto" : (dark ? "🌙 Dark" : "☀️ Light");
    try { localStorage.setItem("officeTheme", pref); } catch (e) {}
  };
  OFFICE.cycleTheme = function(){
    var next = { auto: "dark", dark: "light", light: "auto" }[OFFICE.themePref] || "auto";
    OFFICE.applyTheme(next);
  };
  try { OFFICE.applyTheme(localStorage.getItem("officeTheme") || "auto"); }
  catch (e) { OFFICE.applyTheme("auto"); }
  document.getElementById("themeBtn").onclick = OFFICE.cycleTheme;
  if (window.matchMedia) {
    try {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function(){
        if (OFFICE.themePref === "auto") OFFICE.applyTheme("auto");
      });
    } catch (e) {}
  }
```

- [ ] **Step 6: Run — all green.** Expected: 9 passed.

- [ ] **Step 7: Commit**

```bash
git add frontend/office_map.html tests/test_office_map_frontend.py
git commit -m "feat(office-map): dark mode — system-aware + manual cycle toggle, all card surfaces on CSS vars"
```

---

### Task 5: Six labelled sections + scroll-spy nav + card polish

**Files:**
- Modify: `frontend/office_map.html` (markup inside `#page`; theatre-order CSS ~100; simple-mode CSS; new CSS; scroll-spy JS after quick-nav wiring ~2967)
- Test: `tests/test_office_map_frontend.py`

**Interfaces:**
- Produces: `<section class="hq-sec" id="secCommand|secMap|secActivity|secPipeline|secApprovals|secReliability">`, chip class `qn-active`.

- [ ] **Step 1: Add failing tests**

```python
def test_six_labelled_sections():
    for sec in ("secCommand", "secMap", "secActivity", "secPipeline", "secApprovals", "secReliability"):
        assert f'id="{sec}"' in SRC, sec
    assert "hq-sec-label" in SRC


def test_scrollspy():
    assert "IntersectionObserver" in SRC
    assert "qn-active" in SRC
```

- [ ] **Step 2: Run — 2 new FAIL.** Expected: 2 failed, 9 passed.

- [ ] **Step 3: Wrap panels into sections.** Inside `#page` (keep `quickNav` + `statusSummary` as-is at top), wrap the existing elements — do not move anything across groups, only insert wrappers:

```html
<section class="hq-sec" id="secCommand"><div class="hq-sec-label">🎯 Command Center</div>
  <!-- warRoom, councilPanel, capabilitiesPanel (unchanged) -->
</section>
<section class="hq-sec" id="secMap"><div class="hq-sec-label">🗺️ Live Office</div>
  <!-- mapToolbar, modeToggle, stageWrap, roomListCompact, replayPanel -->
</section>
<section class="hq-sec" id="secActivity"><div class="hq-sec-label">📡 Team Activity</div>
  <!-- feedCard, two-col (leaderboardPanel + activityPanel) -->
</section>
<section class="hq-sec" id="secPipeline"><div class="hq-sec-label">📈 Pipeline & Schedule</div>
  <!-- pipelineBoard, schedulePanel, systemMapCard -->
</section>
<section class="hq-sec" id="secApprovals"><div class="hq-sec-label">🗂️ Approvals & Coordination</div>
  <!-- workflowRunsCard, activeCoordCard, two-col (approvalsPanel + systemHealthPanel) -->
</section>
<section class="hq-sec" id="secReliability"><div class="hq-sec-label">🚨 Reliability & Queues</div>
  <!-- schedulerPanel, failureConsoleCard, dlqRepairCard, hotQueueCard -->
</section>
```

- [ ] **Step 4: CSS.** Add:

```css
  .hq-sec{display:flex;flex-direction:column;gap:16px}
  .hq-sec-label{font-size:11px;font-weight:900;letter-spacing:.08em;text-transform:uppercase;
    color:var(--muted);border-bottom:1px solid var(--line);padding-bottom:4px;margin-top:6px}
  body.simple-mode #secMap, body.simple-mode #secActivity{display:none !important}
  .qn-chip.qn-active{background:var(--brand-2);color:#fff;border-color:var(--brand-2)}
  /* card polish */
  .panel-box, .kpi, #enterpriseCard, #pipelineBoard, .rc-card{
    box-shadow:0 1px 2px rgba(24,16,55,.05);transition:box-shadow .18s ease}
  .panel-box:hover, .rc-card:hover{box-shadow:0 4px 14px rgba(24,16,55,.10)}
  .panel-box{position:relative;overflow:hidden}
  .panel-box::before{content:"";position:absolute;top:0;left:0;right:0;height:2.5px;
    background:linear-gradient(90deg,var(--brand),var(--brand-2),transparent);opacity:.45}
```

And REPLACE the theatre-order rules (`body.office-theatre #warRoom{order:2}` etc., 4 lines) with section-level ordering:

```css
  body.office-theatre #secMap{order:-1}
```

(#page is already a column flexbox; sections are its direct children, so `order` now works at section level — theatre still shows the map first.)

- [ ] **Step 5: Scroll-spy JS.** After the existing quick-nav chip wiring (`.qn-chip` onclick block), add:

```js
  // ---- Scroll-spy: viewport me jo section hai uska nav-chip highlight -------
  (function(){
    if (!("IntersectionObserver" in window)) return;
    var chips = document.querySelectorAll(".qn-chip");
    var vis = {};
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(en){ vis[en.target.id] = en.isIntersecting; });
      var current = null;
      Array.prototype.some.call(chips, function(c){
        var id = c.getAttribute("data-jump");
        if (vis[id]) { current = id; return true; }
        return false;
      });
      Array.prototype.forEach.call(chips, function(c){
        c.classList.toggle("qn-active", c.getAttribute("data-jump") === current);
      });
    }, { rootMargin: "-60px 0px -55% 0px" });
    Array.prototype.forEach.call(chips, function(c){
      var el = document.getElementById(c.getAttribute("data-jump"));
      if (el) io.observe(el);
    });
  })();
```

- [ ] **Step 6: Run — all green.** Expected: 11 passed.

- [ ] **Step 7: Commit**

```bash
git add frontend/office_map.html tests/test_office_map_frontend.py
git commit -m "feat(office-map): 6 labelled sections, scroll-spy nav chips, card polish (gradient accents + hover shadows)"
```

---

### Task 6: Ctrl+K command palette

**Files:**
- Modify: `frontend/office_map.html` (markup before `#roomTooltip`; CSS; JS after scroll-spy block)
- Test: `tests/test_office_map_frontend.py`

**Interfaces:**
- Consumes: `OFFICE.jumpToCta`, `OFFICE.focusAgent`, `OFFICE.openAgentPanel`, `OFFICE.agentByKey`, `OFFICE.cycleTheme`, `OFFICE.setViewMode`, `OFFICE.openBriefing`.
- Produces: `#cmdPalette`, `OFFICE.openPalette()`, `OFFICE.closePalette()`.

- [ ] **Step 1: Add failing tests**

```python
def test_command_palette():
    assert 'id="cmdPalette"' in SRC
    assert "OFFICE.openPalette" in SRC
    assert '(e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")' in SRC
```

- [ ] **Step 2: Run — FAIL.** Expected: 1 failed, 11 passed.

- [ ] **Step 3: Markup** (insert right before `<div id="roomTooltip">`):

```html
  <div id="cmdPalette" style="display:none;position:fixed;inset:0;z-index:80;background:rgba(15,17,35,.45)">
    <div class="cp-box">
      <input id="cpInput" placeholder="⌨️ Kahin bhi jump karo / action chalao… (Esc = band)" autocomplete="off" />
      <div id="cpResults"></div>
    </div>
  </div>
```

- [ ] **Step 4: CSS**

```css
  .cp-box{width:min(560px,92vw);margin:80px auto 0;background:var(--card);border:1px solid var(--line);
    border-radius:12px;box-shadow:0 24px 60px rgba(0,0,0,.35);overflow:hidden}
  #cpInput{width:100%;border:none;outline:none;padding:14px 16px;font-size:14px;background:transparent;
    color:var(--ink);box-sizing:border-box;border-bottom:1px solid var(--line)}
  #cpResults{max-height:320px;overflow-y:auto}
  .cp-row{padding:9px 14px;font-size:13px;cursor:pointer;display:flex;gap:8px;align-items:center;color:var(--ink)}
  .cp-row.cp-sel{background:var(--brand-soft)}
  .cp-kind{margin-left:auto;font-size:10px;color:var(--muted);font-weight:800;text-transform:uppercase}
```

- [ ] **Step 5: JS** (after the scroll-spy IIFE):

```js
  // ---- Ctrl+K command palette: sections + agents + quick actions ------------
  OFFICE.paletteStatic = [
    { label: "War Room / Command Center", kind: "section", run: function(){ OFFICE.jumpToCta("warRoom"); } },
    { label: "Priorities (action stack)", kind: "section", run: function(){ OFFICE.jumpToCta("priorityActionStack"); } },
    { label: "Office Map", kind: "section", run: function(){ OFFICE.jumpToCta("stageWrap"); } },
    { label: "Replay", kind: "section", run: function(){ OFFICE.jumpToCta("replayPanel"); } },
    { label: "Live feed", kind: "section", run: function(){ OFFICE.jumpToCta("feedCard"); } },
    { label: "Pipeline board", kind: "section", run: function(){ OFFICE.jumpToCta("pipelineBoard"); } },
    { label: "Aaj ka Schedule", kind: "section", run: function(){ OFFICE.jumpToCta("schedulePanel"); } },
    { label: "Approvals", kind: "section", run: function(){ OFFICE.jumpToCta("approvalsPanel"); } },
    { label: "Team Improvement Council", kind: "section", run: function(){ OFFICE.jumpToCta("councilPanel"); } },
    { label: "System health", kind: "section", run: function(){ OFFICE.jumpToCta("systemHealthPanel"); } },
    { label: "Agent Scheduler", kind: "section", run: function(){ OFFICE.jumpToCta("schedulerPanel"); } },
    { label: "Reliability Console", kind: "section", run: function(){ OFFICE.jumpToCta("failureConsoleCard"); } },
    { label: "DLQ Repair Desk", kind: "section", run: function(){ OFFICE.openDlqRepairDrawer(); } },
    { label: "Hot Queue", kind: "section", run: function(){ OFFICE.openHotQueueDrawer(); } },
    { label: "Refresh now", kind: "action", run: function(){ document.getElementById("manualRefreshBtn").click(); } },
    { label: "Subah ki Briefing", kind: "action", run: function(){ OFFICE.openBriefing(false); } },
    { label: "Theme badlo (auto/dark/light)", kind: "action", run: function(){ OFFICE.cycleTheme(); } },
    { label: "Simple/Pro view toggle", kind: "action", run: function(){
        OFFICE.setViewMode(document.body.classList.contains("simple-mode") ? "pro" : "simple"); } },
    { label: "Inbox kholo", kind: "action", run: function(){ window.open("/app/inbox", "_blank"); } },
    { label: "Automation / Schedule tab", kind: "action", run: function(){ window.open("/app/automation#schedule", "_blank"); } }
  ];
  OFFICE.paletteItems = function(){
    var items = OFFICE.paletteStatic.slice();
    Object.keys(OFFICE.agentByKey).forEach(function(k){
      var a = OFFICE.agentByKey[k];
      items.push({ label: (a.emoji || "🤖") + " " + (a.name || k) + " — " + (a.title || ""), kind: "agent",
        run: function(){ OFFICE.focusAgent(k); OFFICE.openAgentPanel(k); } });
    });
    return items;
  };
  // Subsequence fuzzy score: har query-char order me mile to match; consecutive
  // hits ko bonus. 0 = no match.
  OFFICE.fuzzyScore = function(q, s){
    q = q.toLowerCase(); s = s.toLowerCase();
    var si = 0, score = 0, streak = 0;
    for (var qi = 0; qi < q.length; qi++) {
      var idx = s.indexOf(q[qi], si);
      if (idx < 0) return 0;
      streak = (idx === si) ? streak + 1 : 1;
      score += 1 + streak;
      si = idx + 1;
    }
    return score + Math.max(0, 20 - s.length / 4);
  };
  OFFICE._cpSel = 0;
  OFFICE._cpMatches = [];
  OFFICE.renderPalette = function(){
    var q = document.getElementById("cpInput").value.trim();
    var items = OFFICE.paletteItems();
    var matches = !q ? items.slice(0, 12) :
      items.map(function(it){ return { it: it, sc: OFFICE.fuzzyScore(q, it.label) }; })
        .filter(function(x){ return x.sc > 0; })
        .sort(function(a, b){ return b.sc - a.sc; })
        .slice(0, 12).map(function(x){ return x.it; });
    OFFICE._cpMatches = matches;
    OFFICE._cpSel = Math.min(OFFICE._cpSel, Math.max(0, matches.length - 1));
    document.getElementById("cpResults").innerHTML = matches.map(function(it, i){
      return '<div class="cp-row' + (i === OFFICE._cpSel ? " cp-sel" : "") + '" data-i="' + i + '">' +
        esc(it.label) + '<span class="cp-kind">' + esc(it.kind) + '</span></div>';
    }).join("") || '<div class="cp-row">Kuch nahi mila.</div>';
    Array.prototype.forEach.call(document.querySelectorAll("#cpResults .cp-row[data-i]"), function(row){
      row.onclick = function(){ OFFICE.runPaletteItem(parseInt(row.getAttribute("data-i"), 10)); };
      row.onmouseenter = function(){ OFFICE._cpSel = parseInt(row.getAttribute("data-i"), 10); OFFICE.renderPalette(); };
    });
  };
  OFFICE.runPaletteItem = function(i){
    var it = OFFICE._cpMatches[i];
    OFFICE.closePalette();
    if (it && it.run) it.run();
  };
  OFFICE.openPalette = function(){
    document.getElementById("cmdPalette").style.display = "block";
    var inp = document.getElementById("cpInput");
    inp.value = ""; OFFICE._cpSel = 0;
    OFFICE.renderPalette();
    inp.focus();
  };
  OFFICE.closePalette = function(){ document.getElementById("cmdPalette").style.display = "none"; };
  document.getElementById("cmdPalette").addEventListener("click", function(e){
    if (e.target === this) OFFICE.closePalette();
  });
  document.getElementById("cpInput").addEventListener("input", function(){ OFFICE._cpSel = 0; OFFICE.renderPalette(); });
  document.getElementById("cpInput").addEventListener("keydown", function(e){
    if (e.key === "Escape") { OFFICE.closePalette(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); OFFICE._cpSel = Math.min(OFFICE._cpSel + 1, OFFICE._cpMatches.length - 1); OFFICE.renderPalette(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); OFFICE._cpSel = Math.max(OFFICE._cpSel - 1, 0); OFFICE.renderPalette(); }
    else if (e.key === "Enter") { OFFICE.runPaletteItem(OFFICE._cpSel); }
  });
  document.addEventListener("keydown", function(e){
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      var open = document.getElementById("cmdPalette").style.display !== "none";
      if (open) OFFICE.closePalette(); else OFFICE.openPalette();
    }
  });
```

- [ ] **Step 6: Run — all green.** Expected: 12 passed.

- [ ] **Step 7: Commit**

```bash
git add frontend/office_map.html tests/test_office_map_frontend.py
git commit -m "feat(office-map): Ctrl+K command palette — fuzzy jump to sections/agents + quick actions"
```

---

### Task 7: Toast alerts + honest session-expiry messaging

**Files:**
- Modify: `frontend/office_map.html` (markup near `#toastStack`; CSS; JS: `fetchSnapshot` ~705, `refreshSnapshot` ~2905, `renderScheduler` 401 branch ~3359)
- Test: `tests/test_office_map_frontend.py`

**Interfaces:**
- Produces: `OFFICE.toast(msg, kind, jump)`, `OFFICE.checkAlerts(data)`, `OFFICE.markSessionExpired()`.

- [ ] **Step 1: Add failing tests**

```python
def test_toast_alerts():
    assert 'id="toastStack"' in SRC
    assert "OFFICE.checkAlerts" in SRC


def test_session_expiry_honesty():
    assert "OFFICE.markSessionExpired" in SRC
    # scheduler 401 must not silently freeze anymore
    assert SRC.count("Session expire") >= 2
```

- [ ] **Step 2: Run — 2 new FAIL.** Expected: 2 failed, 12 passed.

- [ ] **Step 3: Markup** (right after the `#cmdPalette` div): `<div id="toastStack"></div>`

- [ ] **Step 4: CSS**

```css
  #toastStack{position:fixed;right:14px;bottom:14px;z-index:90;display:flex;flex-direction:column;
    gap:8px;max-width:340px}
  .toast{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--info);
    border-radius:10px;padding:10px 12px;font-size:12.5px;color:var(--ink);
    box-shadow:0 8px 24px rgba(0,0,0,.18);animation:toastIn .25s ease-out;cursor:pointer}
  .toast.t-err{border-left-color:var(--err)} .toast.t-warn{border-left-color:var(--warn)}
  @keyframes toastIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
```

- [ ] **Step 5: JS — toast + diff-watch.** Add before `OFFICE.refreshSnapshot`:

```js
  // ---- Toast alerts: naya failed job / overdue / approval aate hi corner me --
  OFFICE.toast = function(msg, kind, jump){
    var stack = document.getElementById("toastStack");
    if (!stack) return;
    while (stack.children.length >= 4) stack.removeChild(stack.firstChild);
    var t = document.createElement("div");
    t.className = "toast" + (kind ? " " + kind : "");
    t.textContent = msg;
    t.onclick = function(){ if (jump) OFFICE.jumpToCta(jump); t.remove(); };
    stack.appendChild(t);
    setTimeout(function(){ try { t.remove(); } catch (e) {} }, 7000);
  };
  OFFICE._prevAlerts = null;
  OFFICE.checkAlerts = function(data){
    var m = (data && data.metrics) || {};
    var cur = {
      failed: m.failed_automations || 0,
      approvals: m.approvals_needed || 0,
      overdue: ((((data || {}).system_health || {}).overdue) || []).length
    };
    var prev = OFFICE._prevAlerts;
    if (prev) {
      if (cur.failed > prev.failed)
        OFFICE.toast("🚨 " + (cur.failed - prev.failed) + " naya failed automation — Reliability Console dekho", "t-err", "failureConsoleCard");
      if (cur.overdue > prev.overdue)
        OFFICE.toast("⏰ Job overdue ho gaya — System health dekho", "t-warn", "systemHealthPanel");
      if (cur.approvals > prev.approvals)
        OFFICE.toast("🗂️ Nayi approval pending aayi — decide karo", "t-warn", "approvalsPanel");
    }
    OFFICE._prevAlerts = cur;
  };
```

In `OFFICE.refreshSnapshot`, after `OFFICE.renderCommandCenter(data);` add: `OFFICE.checkAlerts(data);`

- [ ] **Step 6: JS — session-expiry honesty.** Add before `OFFICE.fetchSnapshot`:

```js
  // Session expire pe har data-panel me honest note — pehle 3+ panels chupchaap
  // stale "Loading…"/purane data pe freeze ho jate the.
  OFFICE.markSessionExpired = function(){
    var note = '<div class="empty-note">🔒 Session expire — <a href="/app/admin-login">dobara login karo</a>, phir 🔄 Refresh now.</div>';
    ["tickerList", "approvalsList", "healthList", "leaderboardList", "scheduleList",
     "failureConsoleList", "schedList", "replayList", "boardRow", "kpiRow",
     "priorityActionStack", "bossBriefBody", "dlqRepairSummary", "hotQueueSummary",
     "activityMeta"].forEach(function(id){
      var el = document.getElementById(id);
      if (el) el.innerHTML = note;
    });
  };
```

In `OFFICE.fetchSnapshot`'s 401/403 branch, change to:

```js
      if (r.status === 401 || r.status === 403) {
        var was = OFFICE.authExpired;
        OFFICE.authExpired = true;
        showBanner('🔒 Session expire ho gaya — <a href="/app/admin-login" ' +
          'style="color:#991b1b;font-weight:800;text-decoration:underline">dobara login karo</a>', true);
        if (!was) OFFICE.markSessionExpired();
        return null;
      }
```

In `OFFICE.renderScheduler`, replace the silent `if (r.status === 401 || r.status === 403) return;` with:

```js
      if (r.status === 401 || r.status === 403) {
        list.innerHTML = '<div class="empty-note">🔒 Session expire — <a href="/app/admin-login">dobara login karo</a>.</div>';
        return;
      }
```

- [ ] **Step 7: Run — all green.** Expected: 14 passed.

- [ ] **Step 8: Commit**

```bash
git add frontend/office_map.html tests/test_office_map_frontend.py
git commit -m "feat(office-map): toast alerts on new failures/overdue/approvals + honest session-expiry note in every panel"
```

---

### Task 8: Background-tab polling pause + full verification

**Files:**
- Modify: `frontend/office_map.html` (the `setInterval` calls ~3254–3256, ~3200, ~3416)
- Test: `tests/test_office_map_frontend.py`

- [ ] **Step 1: Add failing test**

```python
def test_battery_friendly_polling():
    assert SRC.count("document.hidden") >= 4
    assert "visibilitychange" in SRC
```

- [ ] **Step 2: Run — FAIL.** Expected: 1 failed, 14 passed.

- [ ] **Step 3: Guard every poll.** Update these exact lines:
  - `setInterval(function(){ if (!OFFICE.authExpired) OFFICE.refreshSnapshot(); }, 15000);` → `setInterval(function(){ if (!OFFICE.authExpired && !document.hidden) OFFICE.refreshSnapshot(); }, 15000);`
  - `setInterval(function(){ if (!OFFICE.authExpired) OFFICE.pollEvents(); }, 8000);` → `setInterval(function(){ if (!OFFICE.authExpired && !document.hidden) OFFICE.pollEvents(); }, 8000);`
  - `setInterval(function(){ OFFICE.applyDayNight(); }, 60000);` → `setInterval(function(){ if (!document.hidden) OFFICE.applyDayNight(); }, 60000);`
  - `setInterval(function(){ OFFICE.renderActivityChart(); }, 60000);` → `setInterval(function(){ if (!document.hidden) OFFICE.renderActivityChart(); }, 60000);`
  - (renderScheduler interval already checks `document.hidden` — leave.)

  Then after those intervals add:

```js
  // Background tab = battery-friendly: polling paused; wapas aate hi fresh data.
  document.addEventListener("visibilitychange", function(){
    if (!document.hidden && !OFFICE.authExpired) {
      OFFICE.refreshSnapshot();
      OFFICE.pollEvents();
    }
  });
```

- [ ] **Step 4: Run full test file — all green.** Expected: 15 passed.

- [ ] **Step 5: Run neighboring office tests (regression):**

Run: `.venv\Scripts\python -m pytest tests/test_office_hq.py tests/test_admin_office.py -q`
Expected: all pass (no backend was touched).

- [ ] **Step 6: Live browser verification (preview mode).** Serve the frontend statically so absolute `/design-system/...` URLs resolve:

```bash
cd C:/Users/Ratanshila/Documents/leadgenrationaiagent/frontend && python -m http.server 8123
```

Open `http://localhost:8123/office_map.html` with claude-in-chrome and verify (APIs will 404 → page runs in error/preview path, which is fine for UI checks):
1. Map boots with demo roster; every avatar has a distinct tint; no console errors.
2. Ctrl+K opens palette; typing filters; Enter jumps; Esc closes.
3. 🌗 theme button cycles Auto→Dark→Light; dark surfaces readable.
4. Simple↔Pro toggle 4× — map NEVER blank after returning to Pro (also test the hard case: set `localStorage.officeViewMode="simple"`, reload, then switch to Pro — map must render).
5. Resize to 380px width — no floating "Coordinator log" box; layout single-column.
6. Scroll page — nav chips highlight follows.

- [ ] **Step 7: Commit**

```bash
git add frontend/office_map.html tests/test_office_map_frontend.py
git commit -m "feat(office-map): pause polling in background tabs, instant refresh on return"
```

---

## Self-Review (done at plan time)

- **Spec coverage:** 6 bugs → Tasks 2–3; dark mode/sections/scroll-spy/polish → Tasks 4–5; palette/toasts/session/battery → Tasks 6–8. Verification → Task 8. ✅
- **Placeholder scan:** every code step has full code; no TBDs. ✅
- **Type consistency:** `layoutSlots` new return shape `{slots, scale}` updated at BOTH call sites (Task 2 Step 7); `drawAvatar(m, slot, room, sizeScale)` matches all callers; `OFFICE.cycleTheme` defined in Task 4, consumed in Task 6; `OFFICE.jumpToCta`/`openDlqRepairDrawer`/`openHotQueueDrawer` all pre-exist. ✅
- **Known trade-off (documented):** theatre-mode reorder becomes section-level (map section first) instead of element-level — visually equivalent intent, noted in Task 5 Step 4.
