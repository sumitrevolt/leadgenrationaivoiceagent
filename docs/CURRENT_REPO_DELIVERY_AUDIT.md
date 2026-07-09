# Current Repo Delivery Audit — Phase 1
Date: 2026-07-09 | Lead Principal Engineer Audit

---

## 1. What Is Working ✅

### Backend Routes
- **94 router files**, ~1046 total routes registered
- **Delivery cockpit API**: `GET /api/admin/delivery-cockpit`, `GET /api/admin/delivery-logs`, `POST /api/admin/clients/{id}/delivery-action`, `GET /api/admin/automation-logs` — all wired
- **Customer delivery API**: `GET /api/customer/delivery-proof`, `GET/POST /api/customer/social-config`, `GET/POST /api/customer/profile`
- **Auth**: Customer JWT (`/api/customer/auth/login`), admin JWT (`/api/admin/auth/login`), impersonation gated
- **Billing**: UPI manual payments, Stripe webhooks, subscriptions, GST, plan sync from `packages.py`
- **Tenant isolation**: Customer isolation via `client_id` context; IDOR-guarded on all customer routes

### Product One Delivery Engine
- **Core orchestration**: `product_one_delivery.py` (1901 lines) — computes delivery state from 5+ data sources
- **Deliverable tracking**: `customer_deliverables` DB table + model — per-client, per-billing-cycle rows
- **Content generation**: `auto_content.py` — daily content engine (Mon=tip, Tue=offer, Wed=poster, etc.) + seed content for new clients
- **Approval workflow**: `content_approval.py` — submit/approve/reject with token-based links, WhatsApp integration
- **Delivery ledger**: `delivery_ledger.py` — append-only JSONL timeline with customer/admin dual views
- **Social config**: `social_engine/client_config.py` — per-client prefs (channels, cadence, approval mode)
- **Monthly reports**: `monthly_report.py` + `client_report.py` — HTML report generation with brand colors
- **Customer delivery**: `customer_delivery.py` — WhatsApp delivery, weekly digest, monthly receipt, testimonial sweep

### Automation
- **Celery Beat**: 24 active `staff-*` jobs + 15 dormant legacy jobs
- **In-process scheduler**: `team_scheduler.py` — 60s tick loop with file lock, fallback path
- **DLQ**: Redis-based dead letter queue with auto-retry sweep (gated `DLQ_AUTO_RETRY`)
- **Idempotency**: `@idempotent_task` decorator, Redis SETNX keys, state-machine transitions
- **Automation logs**: `automation_log_service.py` — DB-backed (`automation_logs` table) with JSONL fallback
- **Integration health**: `integration_readiness()` — maps infra failures to affected customers

### Frontend
- **Delivery Command Center**: `delivery_command_center.html` (29.6 KB) — admin cockpit with KPIs, pipeline stages, customer cards, automation runs panel
- **Customer dashboard**: `customer_dashboard.html` (191.6 KB) — unified customer portal with view engine (home/delivery/setup/calendar/leads/reports/billing/support)
- **Admin dashboard**: `admin_dashboard.html` (262 KB) — broad admin cockpit
- **Onboarding wizard**: `onboard.html` (23.5 KB) — 4-step admin client onboarding
- **Marketing suite**: `marketing.html` — 28-tab marketing tools
- **Office HQ**: `office_map.html` — virtual office with 41 API calls

### Security
- **Sentry**: Armed in production, no PII sent (`send_default_pii=False`)
- **Secrets**: `.env` only, `check_secrets.py` gate, no hardcoded secrets in code
- **TRAI compliance**: DND scrub, calling window 9am-7pm, AI disclosure, consent ledger
- **DPDP**: 90-day recording retention, purge API, grievance officer, purpose limitation

---

## 2. What Is Broken / Disconnected ❌

### Critical Gaps
| Issue | Impact | Fix |
|-------|--------|-----|
| **SOCIAL_ENGINE flag OFF** in prod | No real social posting. Content sits in queue forever. | User must connect Postiz/Meta tokens + flip flag. Document "pending integration" in UI. |
| **SOCIAL_PREFS_HONOR=0** | Social setup wizard prefs stored but NOT consumed by content pipeline. Cadence/approval-mode settings ignored. | Flip to 1 after verifying pipeline respects prefs. |
| **SOCIAL_AUTOPOST=0** | Meta Graph publishing is MOCK even if tokens exist. | Flip after Meta app review + token setup. |
| **POSTIZ_API_KEY unset** | Postiz auto-publishing path is inert. | User must obtain + set key. |
| **WHATSAPP_AUTO_SEND=0** | No auto WhatsApp sending (ban-safe, correct). 1-click human send only. | Documented limitation. |
| **No safe_ai_payload utility** | External LLM calls may send raw customer PII to Mistral/Groq/Cerebras/Gemini/etc. | Build masking layer — CRITICAL before enabling any LLM-heavy automation. |

### UI Gaps
| Issue | Impact | Fix |
|-------|--------|-----|
| **Customer dashboard is ONE 192KB file** | Works but hard to maintain. View engine (`data-active-view`) handles tab switching well. | Accept for now; refactor only if adding major new views. |
| **Three pages share "Command Center" title** | `admin_dashboard.html`, `control_center.html`, `delivery_command_center.html` all have same `<title>`. Confusing browser tabs. | Fix titles. |
| **Customer sees "Automation" tab in dashboard** | Customer dashboard has 8 views but automation status view is thin — shows "automation running" without real per-deliverable detail. | Fill the "delivery" view with real deliverable checklist. |
| **Admin cockpit has 4 overlapping views** | admin_dashboard, control_center, delivery_command_center, ops — all show health/status/automation info. | See Phase 2 IA simplification. |

### Half-Connected Routes
| Route | Issue |
|-------|-------|
| `battlecard.html` at `/app/battlecard` | Static page with ZERO API calls. No auth gate. |
| `POST /api/admin/clients/{id}/delivery-action` "publish_manual" | Adds proof note but no real publishing unless SOCIAL_ENGINE=1 |
| `POST /api/admin/clients/{id}/delivery-action` "monthly_report" | Generates report HTML file but customer may never see it |
| `POST /api/admin/clients/{id}/delivery-action` "send_reminder" | Creates reminder task in JSONL but not actually sent to customer |

### Automation Health
| Issue | Detail |
|-------|--------|
| DLQ retry is gated (`DLQ_AUTO_RETRY`) | Failed tasks sit in DLQ unless watchdog is armed |
| Legacy beat jobs dormant | 15 scraping/calling/reporting tasks gated behind `ENABLE_LEGACY_BEAT=1` |
| `platform_dial` HARD OFF | 3-layer kill switch — intentional per user mandate |
| `email_outreach` cap 25/day | Working but tight |

---

## 3. What Is Duplicate / Overlapping 📋

### Admin Pages with High Overlap
1. **admin_dashboard.html ⇄ control_center.html** — Both show ops overview, system health, agent status. Different depth levels but overlapping.
2. **ops.html ⇄ control_center.html** — Both show automation health, LLM, telephony, feature flags, DLQ.
3. **office_map.html ⇄ team_dashboard.html** — Both show AI staff roster, activity. office_map is richer spatially.
4. **conversations.html ⇄ inbox.html** — Both are "inbox" concepts. conversations = threaded replies; inbox = triage/action items.

### Customer Page Consolidation (ALREADY DONE)
- `customer_marketing.html` + `customer_voice.html` DELETED (ADR-039, ~7000 lines dead weight)
- All 3 product tiers now use single `customer_dashboard.html` with JS product-gating

### Route Duplication Risk
- `admin_dashboard.py` router at `/api/admin` — OK, distinct from `admin.py` router at `/admin`
- `admin_ops.py` router at `/api/admin` — routes registered on same prefix but different function names → no collision
- `customer_dashboard.py` router at `/api/customer` — same prefix as `customer_flows.py` (`/api/customer`), `customer_pipeline.py` (`/api/customer`) — `customer_marketing_studio.py` uses `/api/customer/studio` — all distinct function names, no FIRST-ROUTE-WINS shadow

---

## 4. What Is Missing 🕳️

### Product One MVP Gaps
| Missing | Priority |
|---------|----------|
| **Customer-facing deliverable checklist UI** | P0 — customer sees "delivery" view but it's mostly proof-notes, not a real checklist |
| **Admin delivery timeline per customer** | P0 — delivery cockpit shows health/status but timeline is thin |
| **Social setup wizard completion scoring** | P1 — wizard saves prefs but no "X% complete" for customer |
| **Missing info detection for customer** | P1 — customer sees what they entered but not what's MISSING |
| **"Manual setup required" labels** | P1 — no clear labeling when WhatsApp/Postiz/GBP integrations missing |
| **Proof-of-work downloads** | P1 — monthly reports generated but no clear download button in customer view |
| **Customer notification on new content** | P2 — WhatsApp delivery sends link but no dashboard notification/email |
| **Automation pause/resume per customer** | P2 — exists via action buttons but no clear toggle UI |

### Security Gaps
| Missing | Priority |
|---------|----------|
| **`safe_ai_payload.py` utility** | P0 — must mask PII before any external LLM call |
| **External API call audit** | P1 — which routes send raw customer data to which providers? |
| **Log PII audit** | P1 — do automation logs contain customer phone/email/name? |

### Automation Monitoring Gaps
| Missing | Priority |
|---------|----------|
| **Per-customer automation status dashboard** | P1 — automation page shows global view, not per-customer |
| **Failed-job alerting for admin** | P1 — DLQ exists but admin must manually check |
| **"Why is automation not running for this customer"** diagnosis | P1 — product_one_health sweep runs but admin can't see per-customer reason |

---

## 5. What Is Mocked / Placeholder 🎭

| Component | Reality | What Customer Sees |
|-----------|---------|-------------------|
| Social publishing (SOCIAL_ENGINE=0) | Content generated but NEVER posted | Draft content exists in queue |
| Meta Graph publishing (SOCIAL_AUTOPOST=0) | Returns MOCK `{"sent": false, "reason": "SOCIAL_AUTOPOST off"}` | Nothing visible to customer |
| Postiz publishing (POSTIZ_API_KEY unset) | Returns `{"sent": false, "reason": "POSTIZ_API_KEY unset"}` | Nothing |
| WhatsApp auto-send (WHATSAPP_AUTO_SEND=0) | 1-click human send only | Nothing auto-delivered |
| "Auto-post" on social setup wizard | Wizard says "auto-post stays OFF" honestly | Honest framing ✅ |
| Client report stats | `_zero_stats()` for per-client — honest zeros | Report says "tracking setup" |
| Voice agent for Product One | Gated behind voice band purchase, DLT | Not applicable to ₹1999 plan |

### Honesty Assessment
The codebase is **mostly honest** — it doesn't pretend to have posted when it hasn't. The social setup wizard explicitly states "auto-post stays OFF." Content is genuinely generated and stored in the queue. The gap is VISIBILITY — customers don't know what's in the queue or what's blocking publication.

---

## 6. Customer-Visible vs Admin-Visible

### Customer Currently Sees
| View | What's Actually Shown |
|------|----------------------|
| **Home** | KPI cards (content, leads, calls), priority actions, AI command card, quick actions |
| **Delivery** | Proof notes, content count, "what's happening this month" summary |
| **Setup** | Social Networking Setup card, business profile card, brand kit card |
| **Calendar** | Content calendar (if generated) |
| **Leads** | Lead pipeline Kanban |
| **Reports** | Monthly report view |
| **Billing** | Plan, payment history |
| **Support** | Contact/support info |

### Admin Currently Sees
| View | What's Actually Shown |
|------|----------------------|
| **Delivery Command Center** | Total/paying/stuck customers, MRR, pipeline stages, per-customer health cards, automation runs, delivery logs |
| **Admin Dashboard** | Broad admin cockpit — agents, campaigns, revenue, health |
| **Control Center** | Executive L1 view — ops overview, system health, agent status |
| **Office HQ** | Virtual office — AI staff in rooms, live activity stream |
| **Marketing Suite** | 28-tab marketing toolset |
| **Clients** | Client store + per-client content engine |

---

## 7. What Must Be Fixed Before Real Delivery 🔴

### BLOCKERS (Can't deliver to real customer without these)
1. **Customer deliverable checklist** — customer must see a clear list of what's done/pending with status
2. **Admin delivery cockpit clarity** — one page that answers "what was delivered to this customer?"
3. **Automation logs humanization** — plain-language logs, not developer traces
4. **Missing-integration labeling** — when WhatsApp/Postiz/GBP creds missing, show "manual setup required"
5. **`safe_ai_payload.py`** — mask customer PII before any external LLM call
6. **Content approval flow UI** — customer must be able to approve/reject from dashboard
7. **Proof-of-work visible to customer** — downloadable reports/content packs

### HIGH PRIORITY (Should fix before customer complains)
1. **Per-customer "why automation not running" diagnosis in admin cockpit**
2. **Customer notification when new content generated**
3. **Social setup wizard progress percentage**
4. **Admin action button: "request missing info from customer"**
5. **Automation log 3-level views (customer/admin/developer)**

---

## 8. Environment / Config Flags — Current State

| Flag | Value | Effect |
|------|-------|--------|
| `SOCIAL_ENGINE` | `0` (OFF) | No real social publishing |
| `SOCIAL_PREFS_HONOR` | `0` (OFF) | Wizard prefs stored but NOT consumed |
| `SOCIAL_AUTOPOST` | `0` (OFF) | Meta Graph publishing is MOCK |
| `WHATSAPP_AUTO_SEND` | `0` (OFF) | 1-click human send only (ban-safe) |
| `AUTO_DELIVER_VALUE` | `?` | WhatsApp delivery of mini-site link |
| `AUTO_ONBOARD` | `?` | Auto-onboard new clients |
| `CLIENT_REPORTS` | `?` | Monthly HTML report delivery |
| `DLQ_AUTO_RETRY` | `?` | Auto-retry failed DLQ tasks |
| `RUN_IN_PROCESS_SCHEDULER` | `1` (default) | In-process scheduler active; prod uses Celery |
| `ENABLE_LEGACY_BEAT` | `0` | Legacy scraping/calling jobs dormant |
| `PLATFORM_DIAL_DAILY` | `0` (HARD OFF) | Platform cold-calling killed (user mandate) |
| `IMPERSONATION` | `1` (gated) | Super-admin login-as-customer |

---

## 9. Highest-Priority Next Actions

1. **Create `safe_ai_payload.py`** — mask_customer_data(), validate_no_secrets(), block_if_sensitive()
2. **Build customer deliverable checklist UI** — clear what's done/pending per deliverable
3. **Enhance admin delivery cockpit** — per-customer timeline + "why stuck" diagnosis
4. **Humanize automation logs** — 3-level views (customer/admin/developer)
5. **Social setup wizard completion scoring** — progress % + missing items detection
6. **"Manual setup required" labeling** — honest UI when integrations missing
7. **Content approval flow in customer dashboard** — approve/reject from delivery view
8. **Proof-of-work download** — monthly report accessible from customer dashboard
