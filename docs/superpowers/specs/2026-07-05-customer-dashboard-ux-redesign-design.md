# Customer Dashboard UX Redesign — Design Spec

- **Date:** 2026-07-05
- **Status:** Approved (approach decided via LLM Council)
- **Branch:** `feat/dashboard-ux-redesign`
- **Owner decision method:** LLM Council (2 code-grounded experts + growth lens → peer review → chairman verdict)

## 1. Problem

Owner feedback: the customer dashboard is "not user-friendly at all" — confirmed across **all four** axes: (1) cluttered/confusing, (2) hard to navigate, (3) bad on mobile, (4) dated/unprofessional look.

Root cause is **information architecture, not skin**. `frontend/customer_dashboard.html` (~2339 lines, vanilla HTML/CSS/JS + linked `/design-system/styles.css` + Chart.js) is **one long-scroll "Home" page**. The sidebar and the mobile bottom nav *look* like navigation but every link just calls `scrollToId()` — no real view switching. The top of the page stacks **five competing "hero" blocks** before any real work appears:

`.status-strip` → `.owner-hero` → `.ai-command` (AI Command Center) → `#teamCard` (`.team-office`, animated AI agents) → `.hero-leads`

A business owner on a phone thumb-scrolls through 4–5 "dashboards about the dashboard" before reaching a single actionable lead.

### Current card inventory (DOM order in `customer_dashboard.html`)

| Element | Purpose | Fork gating |
|---|---|---|
| `.status-strip`, `.owner-hero`, `.ai-command`, `.hero-leads` | Top hero blocks | mixed |
| `#teamCard` (`.team-office`) | Animated AI-team decoration | all |
| `#contentCard` | Aaj ka Post (social content) | marketing |
| `#approvalCard` | Post approvals | marketing |
| `#webToolsCard` | Website / mini-site tools | marketing |
| `#routingCard` | Sales team lead routing | voice |
| `#leadsCard` | Naye Leads list | all |
| `.grid-2` / `.grid-3` / `.kpis` + `#summaryBox` | 3 Chart.js charts + KPI grid (daily calls, hot/cold, city-wise) | mostly voice/combo |
| `#callsCard` | Calls ka Hisaab | voice |
| `#billingCard` | Bill / Plan / old bills | all |
| `#webhookCard`, `#secCard` (`.advanced-area`) | Webhooks, Security / 2FA | all |

### Fork gating mechanism (must be preserved)

`document.body` carries `prod-marketing` / `prod-voice` / (no class = `combo`). CSS at lines ~137–141 and ~395–410 hides the wrong product's cards, navlinks, and action-cards via `display:none !important` keyed on the card IDs above. `pageProduct` JS var (line ~420) mirrors this. **Three separate fork files exist and are maintained together:** `customer_dashboard.html` (combo, default route), `customer_marketing.html`, `customer_voice.html`.

## 2. Decision — Approach B: Information Architecture restructure

Neither cosmetic polish (A, won't fix clutter) nor a framework rebuild (C, reckless for a live product with no build pipeline and background file automation). Instead: convert the long-scroll into a **focused mobile-first Home (one job above the fold) + real toggle-able sub-views**, on the **same vanilla stack, reusing all existing endpoints and `renderAll()` renderers untouched**.

**Why B (council consensus):**
- The complaint is IA, not skin — reordering/gating fixes it; padding/fonts do not.
- Low risk: the data layer is already decoupled — `renderAll()` fires every renderer against fixed element IDs regardless of visibility, each from independent `/api/customer/*` fetches. View-switching is additive show/hide → **zero backend change**.
- Rebuild is reckless: 3 live forks, Docker+SSH deploy, background automation edits these files.

## 3. Goals / Non-goals

**Goals**
- One clear #1 job visible immediately on open (fork-aware), nothing competing above the fold.
- Real navigation: tapping a nav item switches to a single focused view (not scroll).
- Mobile-first: one screen at a time, working bottom-tab bar, ≥44px targets.
- Modern, consistent look using existing design-system tokens (spacing/type/shadow) — no new framework.

**Non-goals (YAGNI)**
- No framework/build pipeline. No CSS/JS extraction into separate files (keep single-file to avoid risky rewrite). No new backend endpoints. No 3-file consolidation. No new charts.

## 4. Target IA — four views

Nav (sidebar on desktop, bottom-tab on mobile) switches between four `<section data-view>` groups via a new `showView()`:

| View | Contains | Fork north-star (Home hero) |
|---|---|---|
| 🏠 **Home** | ONE fork-aware hero + a compact status strip. Demote `#teamCard` animation + `.ai-command` below fold or into an "AI Team" strip. | **voice/combo:** top 3 hot leads with one-tap Call / WhatsApp. **marketing:** Aaj ka Post (copy-ready) + pending approvals. |
| 🔥 **Leads / Calls** | `#leadsCard`, `#routingCard`, `#callsCard`, and **the 3 charts + `.kpis`** (moved off Home, progressive disclosure behind "Pura hisaab"). | — |
| 📣 **Content** *(marketing)* | `#contentCard`, `#approvalCard`, `#webToolsCard`. | — |
| 👤 **Account** | `#billingCard`, `#webhookCard`, `#secCard` (Plan/Bills/Settings/2FA). | — |

## 5. Behavior design

- **`showView(name)`**: sets `data-view` sections' visibility (a `.view-active` class / attribute toggles `display`), updates the active nav item in both sidebar and `.mobile-app-nav`, and scrolls to top. Default view on load = Home. Deep-link support: honor `location.hash` (`#leadsCard` etc. resolve to their owning view) so existing links keep working.
- **Gating stays authoritative**: `showView` only toggles the *section*; individual card gating (`display:none !important` under `prod-*`) still wins inside a shown view. No card is force-shown. Preserve every `#id`, `.marketing-only`/`.voice-only`, and `onclick*=` hook when re-parenting cards into sections.
- **Hero collapse**: replace the 5-block stack with one hero card driven by `pageProduct`. Existing `.hero-leads` (hot-lead count + CTA) is the voice/combo hero; the marketing hero reuses `#contentCard`'s top. `#teamCard` and `.ai-command` move below the fold.
- **Charts relocation**: move `.grid-2/.grid-3/.kpis` DOM into the Leads view. `renderAll()` still renders them (fixed IDs) — no JS change needed beyond ensuring the canvases exist in the DOM.
- **Mobile bottom-tab**: `.mobile-app-nav` (already a fixed 4-col grid) buttons call `showView()` instead of `scrollToId()`.

## 6. Constraints & risks

- **R1 — 3-fork drift + background automation:** automation edits these HTML files and commits on the current branch. **Mitigation:** work on `feat/dashboard-ux-redesign`, snapshot all 3 fork files before touching, stage explicit paths only (never `git add -A`), re-check `git status` before each commit.
- **R2 — gating hook breakage:** re-parenting cards can leak the wrong product's sections. **Mitigation:** keep all IDs/classes/onclick selectors; after change, verify each `prod-*` mode hides the right cards.
- **R3 — deep links / `scrollToId` callers:** other code and nav use `scrollToId`. **Mitigation:** keep `scrollToId` working (route through `showView` + scroll), don't delete it.
- **R4 — no build pipeline:** all changes must run as plain browser JS/CSS; deploy is Docker rebuild + SSH per `leadgen-ops`.

## 7. Rollout sequence

1. Snapshot the 3 fork files on the feature branch.
2. **Pilot on `customer_dashboard.html` (combo) only** — implement views + hero + chart move + mobile tabs.
3. Verify: views switch, all 3 fork modes (`combo`/`prod-marketing`/`prod-voice`) hide the right cards, mobile tabs work, charts render in Leads, no console errors.
4. Port the pattern to `customer_marketing.html` and `customer_voice.html`, respecting each fork's north-star.

## 8. Success criteria

- On open, exactly one job is visible above the fold on a 390px-wide viewport; no chart/KPI/settings above the fold.
- Each nav item switches to a single view; back-to-top on switch; active state reflects current view on desktop + mobile.
- All three `prod-*` modes show only their own cards (no leakage).
- No new backend calls; `renderAll()` and all `/api/customer/*` fetches unchanged; no JS console errors.
