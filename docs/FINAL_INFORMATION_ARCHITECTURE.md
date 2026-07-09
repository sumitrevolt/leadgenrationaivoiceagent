# Final Information Architecture — Phase 2
Date: 2026-07-09 | Lead Principal Engineer

---

## Final Page List — Simplified Three-Surface Architecture

### SURFACE 1: Admin (operator/staff view)

| # | Route | File | Priority | Status |
|---|-------|------|----------|--------|
| 1 | `/app/admin` | `admin_dashboard.html` | **Keep** | Main admin cockpit (clients, agents, campaigns, revenue, health) |
| 2 | `/app/delivery-command-center` | `delivery_command_center.html` | **PRIMARY** | Product One Delivery Cockpit — THE page for customer deliverability |
| 3 | `/app/clients` | `clients.html` | **Keep** | Client store + per-client content engine |
| 4 | `/app/onboard` | `onboard.html` | **Keep** | 4-step admin client onboarding wizard |
| 5 | `/app/marketing` | `marketing.html` | **Keep** | 28-tab AI Marketing Suite (Isha) |
| 6 | `/app/studio` | `studio.html` | **Keep** | AI Studio — photo→poster, AI image |
| 7 | `/app/calendar` | `calendar.html` | **Keep** | Content calendar |
| 8 | `/app/automation` | `automation.html` | **Keep** | Automation Mission Control |
| 9 | `/app/office` | `office_map.html` | **Keep** | Virtual Office HQ |
| 10 | `/app/team` | `team_dashboard.html` | **Keep** | AI Staff roster |
| 11 | `/app/team-access` | `team_access.html` | **Keep** | Team access management (sub-admins + module grants) |
| 12 | `/app/settings` | *None yet* | **NEW** | Settings & Integrations (env flags, API keys, providers) |
| 13 | `/app/control-center` | `control_center.html` | **Keep (dev)** | Enterprise L1 cockpit — rename title, keep for power users |

#### Pages to HIDE from main nav (keep routes alive for deep-links):

| Route | Reason | Where It Merges |
|-------|--------|-----------------|
| `/app/ops` | Overlaps with delivery command center + automation | Deep-link only — ops diagnostics |
| `/app/dashboards` | 17-api endpoint page — too technical for daily use | Deep-link only — admin `/system` area |
| `/app/explorer` | Graph visualization — power user tool | Link from automation.html |
| `/app/conversations` | Threaded reply inbox | Link from clients.html per-client |
| `/app/inbox` | Action inbox (hot leads, triage) | Link from admin_dashboard.html |
| `/app/outreach` | Rohan's outreach queue | Link from automation.html |
| `/app/deals` | Sales pipeline Kanban | Link from admin_dashboard.html |
| `/app/dialer` | Human telecaller dialer | Link from office_map.html |
| `/app/whatsapp` | WhatsApp panel | Link from settings page |
| `/app/minisite-builder` | Mini-site builder | Link from clients.html |
| `/app/agents` | Multi-agent coordination | Deep-link only — dev tool |
| `/app/agent-tools` | Agent Tools cockpit | Deep-link only — dev tool |
| `/app/brain` | Second Brain | Deep-link only — dev tool |
| `/app/assistant` | NL CRM command bar | Deep-link only |
| `/app/growth-tools` | Growth Tools admin | Deep-link only |
| `/app/analytics` | Analytics dashboard | Link from admin_dashboard.html |
| `/app/battlecard` | Static competitive intel | Deep-link only |
| `/app/segments` | Segment builder | Link from automation.html |
| `/app/journeys` | Journey rule engine | Link from automation.html |
| `/app/impersonate` | Super-admin impersonation | Deep-link only (gated) |
| `/app/voice-keys` | Gemini key manager | Link from settings page |
| `/app/test-call` | Web test call | Link from office_map.html |
| `/app/admin/db` | DB explorer | Link from settings page (super-admin gated) |
| `/app/admin-login` | Admin login | Standalone — no nav |

---

### SURFACE 2: Customer (buyer/end-user view)

| # | View | Route | Priority |
|---|------|-------|----------|
| 1 | Home / This Month | `/app/customer` → `data-active-view="home"` | **Keep — enhance** |
| 2 | My Delivery | `/app/customer` → `data-active-view="delivery"` | **PRIMARY — build out** |
| 3 | Setup Wizard | `/app/customer` → `data-active-view="setup"` | **PRIMARY — enhance** |
| 4 | Content & Approvals | `/app/customer` → `data-active-view="calendar"` | **Enhance** |
| 5 | Leads Inbox | `/app/customer` → `data-active-view="leads"` | Voice-only, keep |
| 6 | Reports | `/app/customer` → `data-active-view="reports"` | **Enhance** |
| 7 | Billing | `/app/customer` → `data-active-view="billing"` | Keep |
| 8 | Support | `/app/customer` → `data-active-view="support"` | Keep |
| — | `/app/customer/pipeline` | `customer_pipeline.html` | Keep (separate route for deep-link) |
| — | `/app/customer/flows` | `customer_flows.html` | Keep (Phase 7, separate route) |
| — | `/app/login` | `login.html` | Keep (auth) |

**Already consolidated:** `customer_marketing.html` + `customer_voice.html` DELETED (ADR-039). All 3 tiers use `customer_dashboard.html`.

---

### SURFACE 3: Public (SEO + lead magnets + legal)

| # | Route | File | Purpose |
|---|-------|------|---------|
| 1 | `/` | `website/index.html` | Marketing homepage |
| 2 | `/pricing`, `/start` | `pricing.html` | Self-serve checkout |
| 3 | `/audit` | `website/audit.html` | Free GBP audit |
| 4 | `/site-audit` | `website/site-audit.html` | Free website audit |
| 5 | `/demo` | `website/demo.html` | 30-sec demo |
| 6 | `/voice-agent` | `website/voice-agent.html` | Product 2 landing |
| 7 | `/compare` | `website/compare.html` | Competitor comparison |
| 8 | `/privacy` | `website/privacy.html` | Legal |
| 9 | `/terms` | `website/terms.html` | Legal |
| 10 | `/refund` | `website/refund.html` | Legal |
| 11 | `/status` | `status.html` | Public status page |
| 12 | `/reseller` | `reseller.html` | Agency apply |
| 13 | `/blog` + `/blog/{slug}` | Server-rendered | Programmatic SEO |
| 14 | `/for/{niche}-in-{city}` | Server-rendered | SEO landing pages |
| 15 | `/b/{slug}` + subpages | Server-rendered | Per-client mini-sites |

---

## Merges & Removals

### Already Done (ADR-039)
- ❌ `customer_marketing.html` — DELETED (~4700 lines)
- ❌ `customer_voice.html` — DELETED (~2300 lines)
- ✅ All merged into `customer_dashboard.html` with JS product-gating
- ❌ `command_center.html` — DELETED, `/app/command-center` → 307 redirect → `/app/control-center`

### Recommended (this phase)
- No more deletions needed. The admin pages serve distinct purposes.
- Focus on **nav simplification**: hide secondary pages from sidebar, keep them reachable via deep-links
- Fix 3 title collisions (`admin_dashboard.html`, `control_center.html`, `delivery_command_center.html` all have "Command Center" title)

---

## New Navigation Structure

### Admin Sidebar (primary pages only)

```
🏠  Admin Home          → /app/admin
📦  Delivery Cockpit    → /app/delivery-command-center    ← PRIMARY
👥  Clients             → /app/clients
➕  New Client          → /app/onboard
📱  Marketing Tools     → /app/marketing
🎨  AI Studio           → /app/studio
📅  Calendar            → /app/calendar
⚙️  Automation          → /app/automation
🏢  AI Office           → /app/office
👤  Team                → /app/team
🔧  Settings            → /app/settings                    ← NEW PAGE
---
📊  Control Center      → /app/control-center             ← Advanced
```

### Customer Sidebar (already clean, 8 views)

```
🏠  Home / This Month   → #home
📦  My Delivery         → #delivery                       ← PRIMARY
🧙  Setup Wizard        → #setup                          ← PRIMARY
📅  Content & Approvals → #calendar
🔥  Leads Inbox         → #leads          (voice-only)
📊  Reports             → #reports
💳  Billing             → #billing
💬  Support             → #support
```

---

## Exact Route Mapping

### Admin Primary Routes (always in nav)
| Route | Template | Key API Endpoints Used |
|-------|----------|----------------------|
| `/app/admin` | `admin_dashboard.html` | `/api/admin/live-stats`, `/api/admin/dashboard/*`, `/api/clients/*`, `/api/agents/*` |
| `/app/delivery-command-center` | `delivery_command_center.html` | `GET /api/admin/delivery-cockpit`, `GET /api/admin/delivery-logs`, `GET /api/admin/automation-logs`, `POST /api/admin/clients/{id}/delivery-action` |
| `/app/clients` | `clients.html` | `GET /api/clients`, `GET /api/clients/{id}`, `GET /api/marketing/*`, `GET /api/admin/clients/*` |
| `/app/onboard` | `onboard.html` | `POST /api/clients`, `POST /api/marketing/brand/*`, `POST /api/marketing/complete-post`, `POST /api/campaigns/bulk-voice/*` |
| `/app/marketing` | `marketing.html` | 44 calls to `/api/marketing/*` |
| `/app/studio` | `studio.html` | `/api/marketing/photo-poster`, `/api/marketing/ai-image`, `/api/growth/content/templates` |
| `/app/calendar` | `calendar.html` | `/api/marketing/schedule`, `/api/growth/bookings/*` |
| `/app/automation` | `automation.html` | ~185 calls to `/api/growth/*` |
| `/app/office` | `office_map.html` | 41 calls to `/api/platform/office/*`, `/api/platform/team/*`, `/api/growth/*` |
| `/app/team` | `team_dashboard.html` | `/api/platform/team/*` |
| `/app/team-access` | `team_access.html` | `/api/team-access/*`, `/api/admin/audit-logs` |

### Admin Secondary Routes (deep-link, hidden from nav)
| Route | Template | Access From |
|-------|----------|-------------|
| `/app/ops` | `ops.html` | Deep-link: `/app/ops` |
| `/app/dashboards` | `dashboards.html` | Deep-link: `/app/dashboards` |
| `/app/explorer` | `explorer.html` | Link from automation.html |
| `/app/inbox` | `inbox.html` | Link from admin_dashboard.html |
| `/app/outreach` | `outreach.html` | Link from automation.html |
| `/app/deals` | `deals.html` | Link from admin_dashboard.html |
| `/app/dialer` | `dialer.html` | Link from office_map.html |
| `/app/whatsapp` | `whatsapp.html` | Link from settings |
| `/app/minisite-builder` | `minisite_builder.html` | Link from clients.html |
| `/app/conversations` | `conversations.html` | Link from clients.html per-client |
| `/app/agents` | `agents.html` | Deep-link: dev tool |
| `/app/agent-tools` | `agent_tools.html` | Deep-link: dev tool |
| `/app/brain` | `brain.html` | Deep-link: dev tool |
| `/app/assistant` | `assistant.html` | Deep-link |
| `/app/growth-tools` | `growth_tools.html` | Deep-link |
| `/app/analytics` | `analytics.html` | Link from admin_dashboard.html |
| `/app/segments` | `segments.html` | Link from automation.html |
| `/app/journeys` | `journeys.html` | Link from automation.html |
| `/app/impersonate` | `impersonate.html` | Deep-link (gated `IMPERSONATION=1`) |
| `/app/voice-keys` | `voice_keys.html` | Link from settings |
| `/app/test-call` | `web_call.html` | Link from office_map.html |
| `/app/admin/db` | `admin_db.html` | Link from settings (super-admin) |
| `/app/battlecard` | `battlecard.html` | Deep-link (static, no auth) |

### Customer Routes (single SPA file, view engine)
| Route | Template | Views |
|-------|----------|-------|
| `/app/customer` | `customer_dashboard.html` | home, delivery, setup, calendar, leads, reports, billing, support |
| `/app/customer/marketing` | `customer_dashboard.html` | Same — legacy alias, JS sets marketing-only mode |
| `/app/customer/voice` | `customer_dashboard.html` | Same — legacy alias, JS sets voice-only mode |
| `/app/customer/pipeline` | `customer_pipeline.html` | Separate file — Kanban board |
| `/app/customer/flows` | `customer_flows.html` | Separate file — flow builder (Phase 7) |
| `/app/login` | `login.html` | Auth |

---

## Rules Applied

1. **Every page must answer:** What is happening? What is completed? What is pending? Who must act? What is the next step?
2. **Admin DEFAULT landing**: `/app/delivery-command-center` — this is the business-critical page
3. **Customer sees 8 views** in one SPA — clean, no confusion
4. **No duplicate pages deleted** — all 36 admin pages have distinct purposes; only nav is simplified
5. **Advanced/dev pages** remain behind deep-links, not in sidebar
6. **"Settings & Integrations" is NEW** — consolidates env flags, API keys, provider status, WhatsApp setup, Postiz config
