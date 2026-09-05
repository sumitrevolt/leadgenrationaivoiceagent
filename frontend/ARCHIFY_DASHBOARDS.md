# Archify Enterprise Console

Two enterprise-grade dashboards built from the [Archify](https://github.com/tt-a1i/archify) design language. Dark-first, mono-forward, semantic-color vocabulary, "Evidence Console" creative north star — exactly as the source DESIGN.md prescribes.

## What's here

| File | Role |
|------|------|
| `design-system.css` | Design tokens (canvas / mask / ink / semantic colors), typography (JetBrains Mono), components (chips / panels / tables / forms / toggles / meters) |
| `layout.css` | App shell, side nav, topbar, drawer, modal, toast, stepper, log, chart cards |
| `app.js` | Theme, toast, store (localStorage), formatting helpers, SVG icons |
| `seed-customer.js` | Realistic enterprise seed data — Tata Tele, Mirae Asset, Lakme, CureFit |
| `seed-marketing.js` | Realistic seed data for marketing campaigns, audiences, channels |
| `dashboard-customer.html` | **Dashboard 1** — Customer Configuration & Knowledge Panel |
| `dashboard-marketing.html` | **Dashboard 2** — Marketing Product Launch Panel |
| `index.html` | Landing page with monetization plan |

## Running locally

```bash
cd archify-dashboards
python -m http.server 9876
# open http://localhost:9876/index.html
```

Or just double-click `index.html` — both dashboards and the design system load with relative paths.

## Dashboard 1 — Customer Configuration & Knowledge Panel

**Purpose.** Configure one customer end-to-end: business profile, voice & language, operational hours, customer-specific knowledge, social network logins, and call automation.

### Sections
1. **Customer selector strip** — switch among 4 seeded customers (Tata Tele, Mirae Asset, Lakme, CureFit) or add new ones.
2. **KPI row** — monthly calls, avg duration, CSAT, monthly spend (with deltas).
3. **Business Configuration**
   - Company profile (industry, region, plan, seats, POC, budget)
   - Voice & language (persona, tone, languages, primary channel)
   - Operational hours (business hours, timezone, escalation threshold, auto-recall)
   - Customer-specific preferences (DTMF fallback, real-time transcription, WhatsApp summary, PII redaction, CSAT survey)
4. **Customer Knowledge**
   - Indexed tokens · FAQs · Intents · Scripts · Voice lines · Training status
   - Indexed sources table (PDF / Notion / Web / Markdown / Doc)
   - Answer script library (4 authored samples)
   - Latest training run · retrain now
5. **Social Network Logins** — Facebook, Instagram, X (Twitter), LinkedIn, YouTube, WhatsApp Business. Each shows OAuth scopes, last sync, and Connect / Manage / Disconnect actions.
6. **Call Automation**
   - Active template card with live KPIs (calls/mo, avg duration, containment, CSAT)
   - Visual flow preview (start → greet → identify → branch → RAG → confidence → escalate / reply → end)
   - 6 built-in templates — Inbound, BFSI Verification, Booking & Reminder, Lead Qualification, Outbound, Support Triage
   - **Flow editor modal** — drag-from-palette, 8 block types (Greeting, Intent, Knowledge lookup, Action, Escalate, End, WhatsApp, Webhook)
7. **Audit Log** — full event provenance (integrations, knowledge retrains, template changes, settings updates).

### Interactions wired
- Switch customers → entire dashboard updates
- Connect a social channel → opens OAuth drawer with scope list, persists to localStorage
- Manage an existing integration → view last sync, webhooks, disconnect
- Retrain knowledge → updates tokens, last-trained timestamp, audit log
- Activate a template → switches the active template + audit log entry
- Edit flow → opens the 8-block IVR builder palette + canvas
- Add customer → creates a fresh onboarding-stage record
- Export → downloads full JSON of the current customer

## Dashboard 2 — Marketing Product Launch Panel

**Purpose.** Manage the go-to-market pipeline — plan, build, test, launch, wrap-up — for every product launch and ongoing campaign.

### Sections
1. **Lifecycle stepper** — Plan → Build → Test → Launch → Wrap-up (current step highlighted)
2. **KPI row** — pipeline value, spent (30d), leads / MQL split, live campaigns
3. **Campaign Pipeline**
   - Left rail: lifecycle steps with click-to-filter counts, product / owner / date filters
   - Right: campaign list with stage pill, channel chips, budget, spend meter, leads / MQLs, owner avatar
   - **View toggle** — list or Kanban (drag-style cards, 5 columns)
4. **Performance · Last 30 days** — dual area chart (spend vs leads), 6-stage funnel with meters
5. **Launch Schedule** — September–October 2026 timeline with stage-coloured overlays
6. **Audiences** — 5 segments with overlap Venn diagram
7. **Creative Assets** — 6-asset library with LP / Video / Carousel / Image cards
8. **Marketing Social Logins** — Facebook Ads, Instagram Ads, X Ads, LinkedIn Ads, YouTube Ads, Google Ads. Each shows ad-account scopes, last sync.
9. **Launch Audit** — channel connect, stage change, spend update, A/B variant, audience refresh events

### Interactions wired
- Click lifecycle step → narrows campaigns to that stage
- View toggle → flips between list and Kanban
- Click campaign → opens drawer with KPIs, channels, creative, stage controls
- Move stage (Plan → Build → Test → Launch → Wrap-up) inline
- Connect ad channel → OAuth drawer with ad-account scopes
- + Campaign modal → name / product / stage / budget / owner / dates / audience / channels
- **Start launch (top right)** → moves every Build-stage campaign to Live in one click
- Export → downloads full JSON

## Design system source — tt-a1i/archify

Both dashboards follow the source exactly:

| Source rule | Implementation |
|-------------|----------------|
| Mono-forward typography | JetBrains Mono across the entire UI |
| Semantic color vocabulary | frontend / backend / database / cloud / security / messagebus / external |
| 140–200ms transitions | All hover / focus / state changes |
| Flat-at-rest | Borders and tones, not shadows — shadows only for floating panels and Signal Flow |
| One obvious main path | Sidebar + topbar chrome; main content is the canvas |
| "Evidence Console" north star | Precise, dark-first, vivid only where semantics earn it |
| No dense dashboard shells | Generous spacing, tonal panels, semantic chips |
| Reduced motion respected | `prefers-reduced-motion` collapses all transitions |

## Tech stack

- **HTML / CSS / vanilla JS** — zero build step, zero dependencies. Both dashboards and the design system are static.
- **localStorage** — persistence for customer records, marketing accounts, campaigns, integrations
- **JetBrains Mono** — Google Fonts (with system-monospace fallback)
- **Inline SVG** — all charts, icons, and brand marks

## Monetization plan · ₹5L within 7 days

Both dashboards carry concrete revenue mechanics:

| Lever | Price | Target | Revenue |
|-------|-------|--------|---------|
| Customer tier · Pro | ₹49,999 / mo, 3 mo | 4 customers (Tata Tele, Mirae Asset, Lakme, CureFit-class) | **₹4.5L cash** |
| Knowledge retrain fee | ₹4,999 / retrain | 20 retrains across channels | **₹1.0L** |
| Marketing Launch seats | ₹19,999 / mo, 3 mo | 3 teams × 3 mo upfront | **₹1.8L** |
| Add-on services | ₹9,999 / sprint | Templates, A/B audits, copy | **₹1.0L** |
| Cross-sell · Studio launch | ₹4,99 / campaign | 10 campaigns pre-buy | **₹1.0L** |

**Path to ₹5L within 7 days**: close 3 Pro customers (₹4.5L) + 5 marketing seats (₹1L) + 5 add-on sprints (₹0.5L) = **₹6L buffer**.

## Design decisions, deliberately

1. **Two separate dashboards, not one mega-page.** Customer Configuration is a per-tenant lens. Marketing Launch is a per-pipeline lens. Forcing them together would create the dense shell the Archify design system explicitly forbids.
2. **Customer-specific knowledge, not shared.** Training data and answer scripts are scoped to the active customer — switching the dropdown rebuilds the knowledge view. This is the enterprise pattern (Tata Tele-style per-tenant isolation).
3. **OAuth is in the chrome, not the data path.** The Connect / Manage actions open real-looking drawers with scope lists, redirect URIs, webhook URLs. The actual OAuth handshake is left as the integration step — out of scope for the demo, but the surface is real.
4. **Realistic data, not lorem.** Tata Tele, Mirae Asset, Lakme, CureFit are real enterprise customers of similar product lines. Numbers (CSAT 4.7, containment 78%, ₹14.6L pipeline) match what a working sales-ops dashboard shows.
6. **No fake "AI thinking" overlays.** Per Archify's `don't` list — no decorative glass, no gradient text, no icon-only controls without labels.

## Open hooks for production

- **OAuth** — the Connect button currently persists the connection; replace with `window.location = oauthProvider.authorizeUrl` and handle callback at `/oauth/callback`.
- **IVR runtime** — the flow editor persists block arrangement to localStorage; in production, this is the JSON IR Archify itself takes (`node bin/archify.mjs deliver workflow …`).
- **Backend** — every action that touches a customer (retrain, connect, template activate) is a discrete API call. The seed data shape is the API contract.

## License

MIT — same as upstream Archify.