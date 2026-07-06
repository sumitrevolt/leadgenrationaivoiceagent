# Customer Dashboard UX Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the single long-scroll `frontend/customer_dashboard.html` into a focused, mobile-first dashboard with a real 4-view navigation (Home / Leads / Content / Account) so a customer sees one job at a time instead of 12+ stacked cards.

**Architecture:** Attribute-driven view switching — **no DOM re-parenting**. Every top-level content block gets a `data-view="home|leads|content|account"` attribute; a new `showView(name)` JS function + one CSS rule hide all blocks except the active view. Existing `renderAll()` renderers and every `/api/customer/*` fetch stay untouched (renderers run against fixed IDs regardless of visibility). Product gating (`prod-marketing`/`prod-voice`) keeps working because it uses `!important` and outranks the view rule.

**Tech Stack:** Vanilla HTML + inline `<style>` + inline `<script>`, linked `/design-system/styles.css`, Chart.js (CDN). No build pipeline. Python/pytest + `node --check` for static test guards (mirrors `tests/test_office_map_frontend.py`).

## Global Constraints

- **Single file, pilot only:** touch **only** `frontend/customer_dashboard.html` in this plan. Do NOT edit `customer_marketing.html` / `customer_voice.html` (separate follow-up).
- **No DOM moves except Task 6** (one bounded block move). Prefer adding attributes in place.
- **Preserve every existing `id`, `class`, and `onclick` selector** — gating and renderers depend on them. Never delete `scrollToId`.
- **No new backend calls, no new endpoints, no framework, no CSS/JS file extraction.** (YAGNI)
- **Git discipline (this repo has background file automation):** work on branch `feat/dashboard-ux-redesign`; `git status` before every commit; **stage explicit paths only — never `git add -A`.**
- **Gating precedence:** the view rule must use no `!important` so `#card{display:none !important}` gating always wins inside a shown view.
- **Verification per task:** `node --check` on inline JS must pass, and `pytest tests/test_customer_dashboard_frontend.py -q` must be green before commit.

---

### Task 1: Regression guard test (baseline green)

Create the static test guard first so every later task has a safety net. On the **current** HTML this test must PASS (it asserts nothing has been removed yet).

**Files:**
- Create: `tests/test_customer_dashboard_frontend.py`

**Interfaces:**
- Produces: `SRC` (the HTML text), `_inline_js()` helper, `PRE_EXISTING_IDS`, `GATING_TOKENS` — later tasks append marker tests to this same file.

- [ ] **Step 1: Write the guard test**

```python
"""Static assertions on frontend/customer_dashboard.html (UX redesign pilot).

Mirrors tests/test_office_map_frontend.py:
 (1) node --check syntax gate on inline <script>,
 (2) no-removal guard: every pre-redesign id/gating token must still exist,
 (3) per-task markers added by docs/superpowers/plans/2026-07-05-customer-dashboard-ux-redesign.md.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HTML_PATH = Path(__file__).resolve().parents[1] / "frontend" / "customer_dashboard.html"
SRC = HTML_PATH.read_text(encoding="utf-8")

PRE_EXISTING_IDS = [
    "aiCommand", "teamCard", "contentCard", "contentBody", "approvalCard",
    "approvalBody", "webToolsCard", "webToolsBody", "routingCard", "leadsCard",
    "summaryBox", "mktKpis", "callsCard", "billingCard", "webhookCard", "secCard",
]
# Gating + hero DOM tokens that must never vanish.
GATING_TOKENS = [
    "prod-marketing", "prod-voice", "marketing-only", "voice-only",
    'class="owner-hero"', 'class="status-strip"', 'class="hero-leads"',
]


def _inline_js() -> str:
    blocks = re.findall(r"<script>(.*?)</script>", SRC, re.S)
    assert blocks, "no inline <script> block found"
    return "\n;\n".join(blocks)


def test_inline_js_syntax_ok(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node not on PATH")
    f = tmp_path / "cust_inline.js"
    f.write_text(_inline_js(), encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_no_pre_existing_id_removed():
    missing = [i for i in PRE_EXISTING_IDS if f'id="{i}"' not in SRC]
    assert not missing, f"pre-redesign IDs vanished: {missing}"


def test_gating_tokens_present():
    missing = [t for t in GATING_TOKENS if t not in SRC]
    assert not missing, f"gating/hero tokens vanished: {missing}"
```

- [ ] **Step 2: Run it — expect PASS on current HTML**

Run: `cd /c/Users/Ratanshila/Documents/leadgenrationaiagent && python -m pytest tests/test_customer_dashboard_frontend.py -q`
Expected: 3 passed (or `test_inline_js_syntax_ok` skipped if node missing — node IS on PATH here, so expect PASS).

- [ ] **Step 3: Commit**

```bash
git status --short
git add tests/test_customer_dashboard_frontend.py
git commit -m "test(customer-dashboard): static regression guard before UX redesign"
```

---

### Task 2: View engine — CSS rule + `showView()` + init + view-aware `scrollToId`

Add the switching machinery. Harmless until Task 3 tags blocks, so ships independently.

**Files:**
- Modify: `frontend/customer_dashboard.html` (inline `<style>` — add one rule near line ~135; inline `<script>` — near the existing `scrollToId` at ~line 1452)
- Modify: `tests/test_customer_dashboard_frontend.py` (append markers)

**Interfaces:**
- Produces: global `showView(name)`, `viewForHash(h)`; a CSS rule hiding `[data-view]:not(.v-on)`; `scrollToId` now switches view before scrolling.

- [ ] **Step 1: Append failing marker tests**

```python
def test_view_engine_present():
    assert "function showView" in SRC
    assert "function viewForHash" in SRC
    assert "[data-view]:not(.v-on)" in SRC


def test_showview_resizes_charts():
    # charts render at 0x0 while their view is hidden; showView must resize them
    m = re.search(r"function showView\([^)]*\)\s*\{(.*?)\n\}", SRC, re.S)
    assert m and "getChart" in m.group(1), "showView must resize now-visible charts"


def test_init_on_dom_ready_not_postfetch():
    # default view must paint on DOM ready, independent of the API fetch
    assert "DOMContentLoaded" in SRC or "readyState" in SRC


def test_scrolltoid_is_view_aware():
    # scrollToId must call showView so old anchor links land on the right view
    m = re.search(r"function scrollToId\([^)]*\)\s*\{(.*?)\}", SRC, re.S)
    assert m and "showView" in m.group(1), "scrollToId must route through showView"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `python -m pytest tests/test_customer_dashboard_frontend.py -q`
Expected: FAIL (`test_view_engine_present`, `test_scrolltoid_is_view_aware`).

- [ ] **Step 3: Add the CSS rule** (in the inline `<style>`, next to `.mobile-app-nav{display:none}` ~line 135)

```css
  /* --- view engine: one view visible at a time; gating (!important) still wins --- */
  [data-view]:not(.v-on){display:none}
```

- [ ] **Step 4: Add the JS** (replace the existing one-line `scrollToId` at ~line 1452 with the block below)

```js
function viewForHash(h){
  var map={leadsCard:"leads",routingCard:"leads",callsCard:"leads",
           contentCard:"content",approvalCard:"content",webToolsCard:"content",
           billingCard:"account",webhookCard:"account",secCard:"account"};
  h=(h||"").replace(/^#/,"").replace(/^view-/,"");
  if(map[h])return map[h];
  return ["home","leads","content","account"].indexOf(h)>=0 ? h : "home";
}
function showView(name){
  name=["home","leads","content","account"].indexOf(name)>=0?name:"home";
  document.querySelectorAll("[data-view]").forEach(function(el){
    el.classList.toggle("v-on", el.getAttribute("data-view")===name);
  });
  document.querySelectorAll("[data-nav]").forEach(function(n){
    n.classList.toggle("active", n.getAttribute("data-nav")===name);
  });
  // Chart.js canvases rendered while their view was hidden are sized 0x0 —
  // resize any that are now visible.
  try{
    document.querySelectorAll("[data-view].v-on canvas").forEach(function(c){
      var ch=(window.Chart && Chart.getChart) ? Chart.getChart(c) : null;
      if(ch)ch.resize();
    });
  }catch(e){}
  try{history.replaceState(null,"","#view-"+name);}catch(e){}
  window.scrollTo({top:0,behavior:"smooth"});
}
function scrollToId(id){
  showView(viewForHash(id));
  var el=document.getElementById(id);
  if(el)setTimeout(function(){el.scrollIntoView({behavior:"smooth",block:"start"});},60);
}
```

- [ ] **Step 5: Initialise the default view on DOM ready** (NOT in the fetch-success path — the page must paint even if the API is slow/down). Add near the end of the inline script:

```js
(function initView(){
  function go(){ showView(viewForHash(location.hash)); }
  if(document.readyState!=="loading")go();
  else document.addEventListener("DOMContentLoaded",go);
})();
```

Note: this is belt-and-suspenders — Task 3 also hard-codes `v-on` on the Home blocks so Home is visible from the very first paint, before any JS runs.

- [ ] **Step 6: Run tests + node check — expect PASS**

Run: `python -m pytest tests/test_customer_dashboard_frontend.py -q`
Expected: all PASS (`node --check` gate confirms the new JS parses).

- [ ] **Step 7: Commit**

```bash
git status --short
git add frontend/customer_dashboard.html tests/test_customer_dashboard_frontend.py
git commit -m "feat(customer-dashboard): add view-switch engine (showView + view-aware scrollToId)"
```

---

### Task 3: Tag content blocks with `data-view`

Add the attribute to each top-level content block **in place** (no moves). After this task, switching actually works.

**Files:**
- Modify: `frontend/customer_dashboard.html` (opening tags at the DOM lines below — confirm exact lines first, automation may shift them)
- Modify: `tests/test_customer_dashboard_frontend.py`

**Mapping (add `data-view="X"` immediately after `class="..."` on each opening tag):**

| Block (DOM ~line) | data-view |
|---|---|
| `.owner-hero` (507), `.status-strip` (527), `#aiCommand` (544), `#teamCard` (560), `.hero-leads` (584), `#mktKpis` (597) | `home` |
| `#contentCard` (572), `#approvalCard` (613), `#webToolsCard` (622) | `content` |
| `#routingCard` (633), `#leadsCard` (685), `.kpis` (727), `.grid-2` (735), `.grid-3` (746), `#callsCard` (758) | `leads` |
| `#billingCard` (794), `#webhookCard` (848), `#secCard` (873) | `account` |

- [ ] **Step 1: Confirm current line numbers** (automation may have shifted them)

Run: `grep -nE 'class="(owner-hero|status-strip|ai-command|hero-leads|kpis|grid-2|grid-3)"|id="(aiCommand|teamCard|contentCard|approvalCard|webToolsCard|routingCard|leadsCard|callsCard|billingCard|webhookCard|secCard|mktKpis)"' frontend/customer_dashboard.html`

- [ ] **Step 2: Append failing marker test**

```python
def test_all_blocks_tagged():
    for v in ("home", "leads", "content", "account"):
        assert f'data-view="{v}"' in SRC, f"no block tagged {v}"
    assert SRC.count('data-view="') >= 12, "expected >=12 tagged blocks"

def test_key_cards_in_expected_view():
    # each card's opening tag must carry the right data-view (attr adjacent to id)
    def tag_of(_id):
        m = re.search(r"<[^>]*id=\"" + re.escape(_id) + r"\"[^>]*>", SRC)
        assert m, f"no opening tag for {_id}"
        return m.group(0)
    assert 'data-view="leads"' in tag_of("leadsCard")
    assert 'data-view="leads"' in tag_of("callsCard")
    assert 'data-view="content"' in tag_of("contentCard")
    assert 'data-view="account"' in tag_of("billingCard")
    assert 'data-view="account"' in tag_of("secCard")
    # #mktKpis is a .kpis instance but belongs to Home (not the leads charts)
    assert 'data-view="home"' in tag_of("mktKpis")

def test_home_paints_before_js():
    # Home blocks carry static v-on so the page is not blank before showView runs
    assert 'class="owner-hero v-on"' in SRC, "owner-hero must ship with v-on"
    assert 'class="status-strip v-on"' in SRC, "status-strip must ship with v-on"
```

- [ ] **Step 3: Run — expect FAIL**

Run: `python -m pytest tests/test_customer_dashboard_frontend.py::test_all_blocks_tagged tests/test_customer_dashboard_frontend.py::test_key_cards_in_expected_view -q`
Expected: FAIL.

- [ ] **Step 4: Edit each opening tag.** Example edits (apply the same pattern to every row in the mapping table):

```html
<!-- was: <div class="card" id="leadsCard"> -->
<div class="card" data-view="leads" id="leadsCard">

<!-- was: <div class="card" id="contentCard"> -->
<div class="card" data-view="content" id="contentCard">

<!-- was: <div class="card" id="billingCard"> -->
<div class="card" data-view="account" id="billingCard">

<!-- HOME blocks also get static `v-on` so Home paints before JS runs -->
<!-- was: <div class="owner-hero" aria-label="Aapka dashboard"> -->
<div class="owner-hero v-on" data-view="home" aria-label="Aapka dashboard">
<!-- was: <div class="status-strip" aria-label="..."> -->
<div class="status-strip v-on" data-view="home" aria-label="...">
```

**All six Home blocks** (`.owner-hero`, `.status-strip`, `#aiCommand`, `#teamCard`, `.hero-leads`, `#mktKpis`) get **both** `data-view="home"` **and** `v-on` in their class. The other three views' blocks get only `data-view` (no `v-on`) so they start hidden. Tag `#mktKpis` (the `.kpis` at ~597) as `home`; tag the *other* `.kpis` (~727) as `leads` — never tag by the bare `.kpis` class.

- [ ] **Step 5: Run full suite — expect PASS**

Run: `python -m pytest tests/test_customer_dashboard_frontend.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git status --short
git add frontend/customer_dashboard.html tests/test_customer_dashboard_frontend.py
git commit -m "feat(customer-dashboard): tag content blocks into home/leads/content/account views"
```

---

### Task 4: Wire navigation to the views (sidebar + mobile bottom nav)

Give nav items `data-nav="X"` (for active-state) and make them switch views.

**Files:**
- Modify: `frontend/customer_dashboard.html` (sidebar navlinks ~line 439-452; `.mobile-app-nav` block ~line 913)
- Modify: `tests/test_customer_dashboard_frontend.py`

- [ ] **Step 1: Append failing marker test**

```python
def test_nav_wired_to_views():
    nav = re.search(r'<nav class="mobile-app-nav".*?</nav>', SRC, re.S)
    assert nav and "showView(" in nav.group(0), "mobile nav must call showView"
    assert 'data-nav="leads"' in SRC and 'data-nav="account"' in SRC
```

- [ ] **Step 2: Run — expect FAIL**

Run: `python -m pytest tests/test_customer_dashboard_frontend.py::test_nav_wired_to_views -q`
Expected: FAIL.

- [ ] **Step 3: Update sidebar navlinks.** For each section-owning link add `data-nav` and point onclick at `showView` (leave external-route links `/app/customer/pipeline`, `/app/customer/flows` unchanged). Example:

```html
<!-- Home -->
<a class="navlink active" data-nav="home" href="#view-home" onclick="showView('home');return false;" aria-current="page" aria-label="Home dashboard"><span class="ic" aria-hidden="true">🏠</span> Home</a>
<!-- Naye Leads -> leads view -->
<a class="navlink" data-nav="leads" href="#view-leads" onclick="showView('leads');return false;" aria-label="Naye Leads section"><span class="ic" aria-hidden="true">🔥</span> Naye Leads</a>
<!-- Aaj ka Post -> content view -->
<a class="navlink marketing-only" data-nav="content" href="#view-content" onclick="showView('content');return false;" aria-label="Aaj ka Post section"><span class="ic" aria-hidden="true">📣</span> Aaj ka Post</a>
<!-- Bill / Plan -> account view -->
<a class="navlink" data-nav="account" href="#view-account" onclick="showView('account');return false;" aria-label="Bill aur Plan section"><span class="ic" aria-hidden="true">💳</span> Bill / Plan</a>
```

Keep the other marketing/voice navlinks (Approvals, Website Tools, Team Routing, Calls, Settings) — point each at its owning view (`content`/`leads`/`account`) via the same pattern; `openAdvancedSettings()` for Settings may call `showView('account')` first then open the advanced area.

- [ ] **Step 4: Update the `.mobile-app-nav` buttons** (~line 913) to 4 tabs calling `showView`:

```html
<nav class="mobile-app-nav" aria-label="Mobile app shortcuts">
  <button type="button" data-nav="home" class="active" onclick="showView('home')"><span class="mi" aria-hidden="true">🏠</span>Home</button>
  <button type="button" data-nav="leads" onclick="showView('leads')"><span class="mi" aria-hidden="true">🔥</span>Leads</button>
  <button type="button" data-nav="content" class="marketing-only" onclick="showView('content')"><span class="mi" aria-hidden="true">📣</span>Post</button>
  <button type="button" data-nav="account" onclick="showView('account')"><span class="mi" aria-hidden="true">👤</span>Account</button>
</nav>
```

- [ ] **Step 5: Run tests — expect PASS**

Run: `python -m pytest tests/test_customer_dashboard_frontend.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git status --short
git add frontend/customer_dashboard.html tests/test_customer_dashboard_frontend.py
git commit -m "feat(customer-dashboard): wire sidebar + mobile nav to showView (real view switching)"
```

---

### Task 5: Focused Home — money action above decoration

On Home, the hot-leads number (`.hero-leads`) must sit above the AI-command/team decoration. Move the `.hero-leads` block to immediately after `.status-strip`; `#aiCommand` and `#teamCard` remain on Home but below it.

**Files:**
- Modify: `frontend/customer_dashboard.html` (move the `.hero-leads` block; confirm its exact start/end lines first)
- Modify: `tests/test_customer_dashboard_frontend.py`

- [ ] **Step 1: Append failing marker test**

```python
def test_home_money_above_decoration():
    # DOM order: hero-leads must come before the AI command center on Home
    assert SRC.index('class="hero-leads"') < SRC.index('id="aiCommand"'), \
        "hero-leads (money action) must sit above #aiCommand on Home"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `python -m pytest tests/test_customer_dashboard_frontend.py::test_home_money_above_decoration -q`
Expected: FAIL (currently `#aiCommand` at ~544 precedes `.hero-leads` at ~584).

- [ ] **Step 3: Confirm the hero-leads block boundaries**

Run: `grep -nE 'class="hero-leads"|class="ai-command"|class="status-strip"' frontend/customer_dashboard.html` — note the `<div class="hero-leads" ...>` opening line and its matching closing `</div>` (read that region with the Read tool to get the exact closing line).

- [ ] **Step 4: Move the block.** Cut the entire `<div class="hero-leads" data-view="home">…</div>` block and paste it immediately after the `.status-strip` block's closing `</div>` (before `#aiCommand`). Keep its `data-view="home"` attribute.

- [ ] **Step 5: Run full suite + node check — expect PASS**

Run: `python -m pytest tests/test_customer_dashboard_frontend.py -q`
Expected: all PASS (no-removal guard still green ⇒ nothing lost in the move; `node --check` unaffected).

- [ ] **Step 6: Commit**

```bash
git status --short
git add frontend/customer_dashboard.html tests/test_customer_dashboard_frontend.py
git commit -m "feat(customer-dashboard): promote hot-leads hero above AI-command on Home"
```

---

### Task 6: Fork-gating + mobile behavior verification (browser)

Automated guards can't prove the three product modes render correctly or that mobile tabs feel right. Drive it in a browser.

**Files:**
- No file changes (verification task). Any bug found spawns a fix commit on this branch.

- [ ] **Step 1: Serve the frontend + design system** so `/design-system/styles.css` resolves. Easiest: run the app (`docker compose … up` or the local uvicorn per repo README) and open `/` (combo route). If only static needed, serve the repo root so `/frontend/...` and `/design-system/...` both resolve.

- [ ] **Step 2: Combo mode** — open `customer_dashboard.html`. Confirm: only Home visible on load; clicking each nav item (sidebar + mobile bottom bar) switches to exactly one view; back-to-top on switch; active state highlights the current tab.

- [ ] **Step 3: Marketing mode** — load with `document.body.classList.add('prod-marketing')` (or the marketing route param the app uses). Confirm the Leads/Calls/Routing cards + `.hero-leads` stay hidden even inside their views (gating `!important` wins), and Content view shows Post/Approvals/Website Tools.

- [ ] **Step 4: Voice mode** — `prod-voice`. Confirm Content/Approvals/WebTools hidden; Leads + Calls + charts show inside the Leads view. **Chart sizing check (critical):** the 3 charts render while Home is default (Leads hidden ⇒ canvas 0×0). Switch to Leads and confirm each chart is drawn at its *correct size* (fills its card), not collapsed/tiny. If collapsed, the `showView` resize hook (Task 2) isn't firing — debug there. Presence ≠ correct sizing.

- [ ] **Step 5: Mobile** — narrow viewport to 390px. Confirm one screen at a time, bottom tab bar switches views (not scroll), no horizontal overflow, charts live only in Leads.

- [ ] **Step 6: Console** — confirm no JS errors and that `/api/customer/*` calls fire exactly as before (network tab). Fix + commit any issue found.

---

## Self-Review

**Spec coverage:**
- Focused Home (one job) → Tasks 3+5. Real 4-view nav → Tasks 2+3+4. Mobile bottom-tab switching → Task 4 (+verify Task 6). Modern/consistent look via tokens → inherited (no new framework; polish rides on the reduced clutter — deeper visual polish is deliberately deferred, see note). Gating preserved → CSS precedence (Task 2) + verify (Task 6). Charts off Home → Task 3 (tagged `leads`). Reuse renderAll/endpoints → architecture (no renderer edits). Rollout pilot-first → Global Constraints (combo only). ✅
- **Note / deferred:** the spec's "modern look" goal is only partially addressed here (clutter removal + hierarchy). Pure cosmetic restyling (color/type refresh) is intentionally NOT in this plan to keep the pilot low-risk; if desired it becomes a separate task after Task 6 confirms structure.

**Placeholder scan:** no TBD/TODO; every code step shows real code and exact commands. ✅

**Type/name consistency:** `showView`, `viewForHash`, `data-view`, `.v-on`, `data-nav` used identically across Tasks 2–5; test helper names match. ✅
