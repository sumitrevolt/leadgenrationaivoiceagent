# Customer Delivery OS — Reality Audit + Consolidation Plan

> Goal: 45 scattered pages → ek simple **Customer Delivery OS** jahan har paid customer ko visible value dikhe aur har automation ka proof ho. Stop adding random features; consolidate + prove.
> Date: 2026-07-06 · Owner: product-delivery overhaul · Status: Phase 1 (audit) DONE, Phase 2 (IA) proposed, Phase 3-6 pending build.

---

## PHASE 1 — REALITY AUDIT (evidence-based, from parallel code audit)

### 1A. Page inventory (57 real frontend pages; 4 vendor artifacts ignored)

All page routes live in `app/main.py` as `@app.get(tags=["Frontend"])` → `FileResponse`. **No route collisions** — duplication is at the UI/data-fetch level, not the route table. So consolidation = pick canonical page + redirect/hide others; no route-conflict surgery needed.

**Classification legend:** KEEP · MERGE · HIDE-NAV (route stays, drop from primary nav) · ADMIN-ONLY · CUSTOMER-ONLY · DELETE-LATER (after verify)

#### Public funnel (money path) — KEEP ALL
| Page | Route | Verdict |
|---|---|---|
| website/index.html | `/` | KEEP |
| website/demo, audit, site-audit, geo-check | `/demo` `/audit` `/site-audit` `/geo-check` | KEEP (lead magnets) |
| website/voice-agent.html | `/voice-agent` | KEEP (Product-2 landing) |
| website/compare.html | `/compare` | KEEP |
| pricing.html | `/pricing` `/start` | KEEP |
| website/privacy, terms, refund | legal | KEEP (compliance) |
| blog / for/{slug} / b/{slug} mini-sites | SEO | KEEP (compounding assets) |
| status.html | `/status` | KEEP |

#### Customer app (target: 6 areas) — currently 3 forks + scattered
| Page | Route | Verdict → new home |
|---|---|---|
| customer_marketing.html (7 nav) | `/app/customer/marketing` | KEEP → primary ₹1,999 shell → **Customer Home** |
| customer_dashboard.html (Combo, 4 nav) | `/app/customer` | KEEP (product-adaptive shell) |
| customer_voice.html (6 nav) | `/app/customer/voice` | KEEP (separate Voice product) |
| onboard.html | `/app/onboard` | KEEP → **Setup Wizard** |
| customer_pipeline.html | `/app/customer/pipeline` | KEEP → **Leads Inbox** (simplify) |
| calendar.html | `/app/calendar` | MERGE → **Marketing Calendar** |
| customer_flows.html ("My Automations") | `/app/customer/flows` | HIDE-NAV (too complex for shop owner; surface as read-only status in Home) |

#### Admin app — **38 nav items today** (the core confusion) → target 6
| Page | Route | Verdict |
|---|---|---|
| admin_dashboard.html (38 nav, 5 groups) | `/app/admin` | KEEP → slim to **Admin Command Center** |
| command_center.html (title collision) | `/app/command-center` | MERGE → into Admin Command Center |
| ops.html | `/app/ops` | MERGE → Automation Monitor · HIDE-NAV |
| automation.html (33 tabs) | `/app/automation` | KEEP → **Automation Monitor** (human-readable subset) |
| control_center.html + _graph | `/app/control-center` | ADMIN-ONLY advanced → **Internal Office**, HIDE from primary nav |
| agent_tools.html (14 tabs) | `/app/agent-tools` | ADMIN-ONLY advanced (dev tooling) → Internal Office, HIDE-NAV |
| office_map.html (10 sections) | `/app/office` | ADMIN-ONLY → **Internal Office** (advanced agent map) |
| explorer.html | `/app/explorer` | ADMIN-ONLY advanced, HIDE-NAV |
| agents.html · team_dashboard.html | `/app/agents` `/app/team` | MERGE → Internal Office (overlap w/ office_map) |
| marketing.html (28-tab internal suite) | `/app/marketing` | ADMIN-ONLY internal tool, HIDE from customer |
| studio.html | `/app/studio` | MERGE → customer Content/Studio (overlap) |
| inbox.html + conversations.html | `/app/inbox` `/app/conversations` | MERGE → single admin inbox |
| deals.html · journeys.html | `/app/deals` `/app/journeys` | ADMIN CRM → secondary tools menu |
| assistant.html + brain.html | `/app/assistant` `/app/brain` | MERGE → one AI-query surface |
| segments, dialer, outreach, whatsapp, minisite-builder, clients, analytics, dashboards | various | KEEP but demote to secondary "Tools" menu (not primary nav) |
| battlecard, reseller | sales | secondary |
| admin_db, impersonate, team-access, voice-keys, test-call | gated | ADMIN-ONLY (super-admin), keep gated |

### 1B. Duplicate-function map (same data rendered N ways)

The 4 cockpits + admin dashboard are **~70% the same data**:

| Function / API | Surfaced in | # places |
|---|---|---|
| Today overview (`/api/growth/overview/today`) | automation, control-center, command-center, admin | 4 |
| Automation health (`/api/growth/infra/automation-health`) | control-center, ops, command-center, admin | 4 |
| Process runs (`/api/growth/process/runs`) | automation, control-center, office, admin | 4 |
| Team scheduler/roster (`/api/platform/team*`) | automation, office, team, command-center, admin | 5 |
| Events stream | automation, office, control-center, team | 4 |
| DLQ (`/api/growth/infra/dlq`) | automation, office, control-center, ops, admin | 5 |
| Approvals (3 parallel systems) | automation, office, admin | 3 |
| Agent roster/metrics | automation, office, agents, control-center, admin | 5 |

**3 different "office" aggregators** (naming hazard, different scopes, no route collision): `/api/platform/office/*` (staff HQ) · `/api/admin/office` (admin pending-actions) · `/api/customer/office` (customer portal).

`/app/agent-tools` is the only *distinct* cockpit (dev tooling) — cleanest to keep standalone under Internal Office.

### 1C. What ₹1,999 (starter) ACTUALLY does — honest verdict

**Runs automatically today (real):**
- Day-1 auto-onboard on signup — `public_site.py:691` `onboard_client.delay` (`SIGNUP_AUTO_ONBOARD` default-ON) → `onboarding.auto_onboard()`: website→KB seed, first content pack, seeds customer content queue, niche mini-site, `setup_done`. (`onboarding.py:365-450`)
- Daily content generation — **NO flag gate**, real: `auto_content.run_daily_content()` per active client → post/poster/reel + festival as `draft` into `data/content_queue/<id>.jsonl` (`team_scheduler.py:484`, paying clients prioritized).
- Daily SEO blog (`seo_blog.run_daily_blog`).
- ~40 on-demand AI Studio tools (`customer_marketing_studio.py:1907+`) — genuinely work.
- Lead capture widget → dashboard inbox.

**Built but DORMANT (default-OFF flags):** all 20 "Hands-Free Automations" (cadence, reminders, newsletter, win-back...), `SOCIAL_ENGINE` (auto-posting), `AUTO_DELIVER_VALUE` (proactive delivery), `VIDEO_AD_CYCLE`, `SOCIAL_AUTOPOST`.

**Claimed but NOT delivering:** "1-click publish to your channels / WhatsApp auto-send" (`packages.py:60`) — content is **generated but never posted** (no per-customer social OAuth; vault only has admin `_global`; `SOCIAL_ENGINE` off; WhatsApp auto-send hard-OFF by ban-safety). Customer must copy-paste manually.

**Accurate positioning:** ₹1,999 = **"done-with-you daily content + lead-capture studio"**, NOT "done-for-you autopilot." Day-1 packet must lead with what actually fires; auto-posting/hands-free = opt-in flags per customer.

### 1D. ROOT-CAUSE — why the paid customer sees no visible value (ranked)

1. **Payment activation never triggers delivery.** `upi_payments._try_activate` (`:153-206`) sets the plan but does NOT set `delivery_state` and never calls `deliver_client_value`. Stripe handlers same.
2. **`AUTO_DELIVER_VALUE` default-OFF** → `deliver_client_value` (`customer_delivery.py:174`) never fires; sweep just logs customer as "stuck" in `data/delivery_stuck.jsonl`. Customer is **never told** anything happened.
3. **No persistent, customer-facing "what AI did for you" timeline.** Only `_office_activity()` (`customer_dashboard_builders.py:811`) — derived on-the-fly, not persisted, must log in to see. Real event table `agent_events` is **staff-scoped** (cross-customer leak risk — do NOT reuse).
4. **Content generated but never surfaces out / never publishes** (see 1C).
5. **No-website customers depend on a fragile WhatsApp interview thread** (`awaiting_kb_interview`) — the historical silent-swallow bug ghosted the real paying customer.
6. **Admin has no per-customer 360 view** — 38 scattered nav items, none answers "is THIS customer getting value / what's stuck / which button to press."

### 1E. Reusable assets (extend, don't rebuild)
- Customer store: `data/marketing_clients.jsonl` (`clients_store.py`) — has `delivery_state ∈ {paid, assets_built, delivered, acknowledged}`, `delivered_at`, `acknowledged_at` (coarse, single-state — closest thing to a ledger).
- `data/content_queue/<cid>.jsonl` (content sub-timeline, draft/approved/posted)
- `data/autopilot_*.jsonl` (hands-free drafts, customer-facing via `customer_autopilot.drafts_for_client`)
- `data/inquiries.jsonl` (leads per client)
- `data/site_views.jsonl`, `delivery_stuck.jsonl`
- `_office_activity()` shape (reuse for ledger view) · `GET /api/customer/office` (customer feed) · `GET /api/admin/office` (admin pending)

---

## PHASE 2 — NEW SIMPLE INFORMATION ARCHITECTURE

### Customer side (≤6 nav) — for the non-technical shop owner
1. **Home** — plan status · setup % · today's marketing work · content ready to approve · posts published · leads received · WhatsApp/follow-up status · this week's report · **"AI ne aapke liye kya kiya" timeline** (from ledger)
2. **Setup** — business profile · services · target area · social accounts · WhatsApp · brand tone · approval prefs (← onboard.html + checklist)
3. **Calendar** — generated posts, draft/approved/published/failed, platform badges (IG/FB/GBP/WA) (← calendar + content_queue)
4. **Leads** — new leads · follow-up status · source · next action (← customer_pipeline)
5. **Reports** — weekly benefit summary · posts created/published · leads · follow-ups · pending setup issues
6. **Billing/Plan**

### Admin side (≤6 nav)
1. **Command Center** — total/paying customers · stuck-in-setup · receiving-value · failed-automation · pending approvals · revenue/plan (← admin dashboard + command_center merged)
2. **Customer 360** — one customer = full timeline: plan · setup · automations enabled · last successful job · failed jobs · content pipeline · social state · leads · **manual fix buttons** (NEW — biggest gap)
3. **Delivery Queue** — what must ship today · who's blocked · which automation failed · retry buttons (← delivery_stuck.jsonl + ledger)
4. **Automation Monitor** — human-readable job names · last/next run · success/fail · error reason · customer affected (← automation.html subset, humanized)
5. **Approvals** — posts/campaigns waiting (unify the 3 approval systems)
6. **Internal Office** — advanced agent map + system view (office_map + agent_tools + control_center + explorer), ADMIN-ONLY, kept OUT of customer-facing surfaces

---

## PHASE 3-6 — BUILD SEQUENCE (recommended)

**Constraint-first:** the bottleneck = "customer sees no value + admin can't tell." Keystone = the **Delivery Ledger**, because Customer Home, Reports, Admin Command Center, Customer 360, Delivery Queue ALL read from it. Build order:

1. **[Phase 4] Delivery Ledger spine** — new `app/marketing/delivery_ledger.py`, append-only `data/delivery_ledger/<cid>.jsonl`, canonical event types (customer_created, plan_activated, onboarding_started/completed, marketing_calendar_generated, post_draft_created, post_approved, post_published, post_failed, lead_captured, followup_sent, weekly_report_generated, automation_failed, admin_manual_action). Ledger append = always-on, additive, never-raise. Helper to backfill from existing sources (content_queue/inquiries/delivery_state) so existing customers aren't blank. TESTS.
2. **Wire triggers** to append ledger events: `onboard_client`, `upi_payments._try_activate` (+ set delivery_state), Stripe handlers, `auto_content` (draft created / calendar generated), approval endpoints, lead capture, weekly digest. High-risk (billing) — fail-open, additive, contract test.
3. **[Phase 3] Day-1 packet** — `ensure_day1_packet(client)`: profile checklist + 7-day calendar draft + ≥3 post drafts + 1 WhatsApp promo draft + 1 offer/campaign + approval queue; logs ledger events; idempotent. Most already runs (auto_onboard) — make explicit + measured + surfaced. Blocked states (no social / WAHA / Postiz fail) → customer sees simple "Connect X", admin sees technical error.
4. **Customer surface** — Home "What AI did for you" timeline + delivery-packet cards reading ledger (extend `/api/customer/office` or new `/api/customer/delivery`).
5. **Admin surface** — Customer 360 + Delivery Queue + Command Center rollups reading ledger + delivery_stuck.
6. **[Phase 5] Nav cleanup** — flag-gated new-nav (`DELIVERY_OS_NAV`), collapse admin 38→6 + customer to 6; hide/merge per 1A (routes stay, drop from nav); redirects for merged pages.
7. **[Phase 6] Tests + evidence** — paid customer sees dashboard · ₹1,999 creates packet · admin sees delivery status · failed social shows blocked state · nav collapsed · ledger records events. Old→new mapping + route proof + test results + remaining blockers.

**Gates honored throughout:** pricing source-of-truth (`packages.py`/`voice_packages.py`) untouched · Marketing vs Voice kept separate · compliance gates intact · no VPS deploy without explicit auth · additive + flag-gated + never-raise.
