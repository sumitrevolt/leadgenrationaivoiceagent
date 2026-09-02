# Customer Delivery Ledger — Design Spec (Sub-project 1 of "Customer Delivery OS")

- **Date:** 2026-07-06
- **Status:** Draft — pending user review
- **Scope:** Sub-project 1 of a 6-part decomposition (see §1). This spec covers ONLY the delivery ledger + minimal admin/customer surfacing. Later sub-projects get their own spec/plan cycle.

## 0. Source

Full mission brief given by the user: turn the fragmented LeadGen AI platform (45+ pages, 4 admin cockpits, 1 real paying customer receiving no visible value) into a "Customer Delivery OS" — 6 phases (audit, new IA, ₹1,999 Day-1 delivery packet, backend delivery ledger, UX rules, implementation rules). Audited via 5 parallel research agents + direct verification (see §2). Full mission text preserved in conversation history, not duplicated here.

## 1. Program decomposition

The full mission is too large for one spec/plan/implementation cycle. Decomposed into 6 sub-projects, each with its own design → plan → build → test cycle:

| # | Sub-project | Depends on | Status |
|---|---|---|---|
| 1 | **Delivery ledger** (this spec) — event log + core wiring + admin "Deliver Now" + minimal customer surfacing | none | drafting now |
| 2 | Marketing Calendar view (draft/approved/published/failed states, platform badges) | 1 | not started |
| 3 | Admin Command Center (new front door: total/paying/stuck/receiving-value/failed-automation/approvals) + Customer 360 | 1 | not started |
| 4 | Interactive Setup Wizard (business profile/social/WhatsApp/brand-tone/approval prefs) | none (parallel-safe) | not started |
| 5 | Leads Inbox + Reports view | 1 | not started |
| 6 | Old→new page mapping, hidden/merged nav cleanup, full test suite, proof-of-journey deliverable | 1–5 | not started |

**Why ledger first:** every later sub-project reads from it (customer timeline, admin Customer 360, Reports "what AI did"). Building IA/nav first would ship prettier pages that are still honestly empty. This sub-project is additive-only — no existing page, nav item, or flag changes — so it carries zero risk to the live product and needs no user permission to proceed on its own.

## 2. Audit findings this spec relies on (verified, not from the one agent that hallucinated)

- **Customer-side nav is not the problem.** `frontend/customer_dashboard.html` (+ `customer_marketing.html`, `customer_voice.html`) got a 4-view IA redesign merged yesterday (`docs/superpowers/specs/2026-07-05-customer-dashboard-ux-redesign-design.md`, branch `feat/dashboard-ux-redesign`, merged in `a44a3ab`): Home / Leads-Calls / Content / Account, one job above the fold, LLM-Council-approved. This spec must fit inside that IA, not fight it.
- **Admin-side is genuine sprawl:** 17 nav items + 4 cockpits (Office/Automation/Agent-Tools/Control-Center, ~90 tabs combined) — all correctly admin-gated (verified: zero customer exposure). Deferred to sub-project 3.
- **Root cause of "no visible value":** `app/marketing/auto_content.py` generates draft content daily (real, runs). Delivery to the customer is gated behind `AUTO_DELIVER_VALUE` (default OFF). `app/marketing/customer_delivery.py:174` (`deliver_client_value`) and its hourly caller `run_delivery_sweep()` (`onboarding.py:455`) already exist — when the flag is off, the sweep only appends to a local `_STUCK_LOG` file nobody surfaces. `app/api/admin_ops.py:807-810` comment confirms this code path was already patched once for the jiya-makeover incident, but the customer still never received anything because nobody has visibility into the stuck-log and the flag stays off (correctly — see §5).
- **No delivery/timeline ledger exists anywhere today** — confirmed by direct grep across the repo (zero matches for `delivery_ledger`, zero matches for the mission's event-type strings outside one coincidental substring hit). This is genuinely greenfield.
- **Reusable hook found:** `/api/admin/clients/{id}/timeline` (`app/api/admin_dashboard.py:315`, built by `_build_client_timeline` at line 236) already renders a per-client timeline from `AgentEvent` + inquiries + audit log. Extend this endpoint to also merge in delivery-ledger events rather than building a separate Customer 360 page now.
- **Existing event-log pattern to mirror:** `app/models/agent_event.py` (`AgentEvent` — id, member, action, detail, status, meta_json, created_at, indexed on `(member, created_at)` and `(created_at)`), written via `app/platform/team.py:log_event()` (sync, never raises). Deliberately NOT reusing this table directly — it's staff-internal ("kaun kya kar raha hai") and mixing customer-facing business events into it would couple two different consumers/audiences and leak internal noise to a customer-visible read path. Following the same *pattern*, new table.
- **Entitlements (`app/marketing/packages.py`):** Main ₹1,999 plan lists 75+ features; only ~10 auto-fire with zero admin action on signup (minisite, content-queue seed, KB seed, chatbot widget). Everything else is either draft-only (needs a human click) or gated behind `AUTO_DELIVER_VALUE`/`WHATSAPP_AUTO_SEND` (both default OFF, correctly — see §5).

## 3. Goals / Non-goals

**Goals**
- Single source-of-truth append-only ledger per customer, covering a first core subset of the mission's 14 event types (full list in §4.2; remaining 6 wire in during sub-projects 2/5, listed explicitly so nothing is silently dropped).
- Admin can see, for any one customer, what actually happened and manually unstick delivery with one click — no flag flip, no auto-send.
- Customer can see a plain-language "what AI did for you" trail somewhere in the existing (just-redesigned) IA, without competing with the one-job-above-the-fold Home rule.
- Ships the concrete fix for the one real paying customer (jiya makeover) via a human-clicked action, not an autonomous send.

**Non-goals (this sub-project)**
- No nav/page restructuring, no merge/hide/delete of any existing page (sub-project 3/6).
- No flipping `AUTO_DELIVER_VALUE` or `WHATSAPP_AUTO_SEND` globally — that stays the user's call (ban-risk, prior explicit council decision to keep WhatsApp auto-send off in prod).
- No Marketing Calendar / Setup Wizard / Reports view build-out (sub-projects 2/4/5).
- No fix for the duplicate-aggregator findings from the audit (automation-health/today-overview/team-status computed 3x, 3 separate approval-decide code paths) — real, logged to `memory/backlog.md`, not in scope here (mission says stop adding unrequested refactors).
- No deploy to VPS — build + test locally only, per CLAUDE.md and Phase 6 rule 5.

## 4. Design

### 4.1 New model — `app/models/delivery_event.py`

Mirrors `AgentEvent`'s shape and conventions:

```
class DeliveryEvent(Base):
    __tablename__ = "delivery_events"
    __table_args__ = (
        Index("ix_delivery_events_client_time", "client_id", "created_at"),
        Index("ix_delivery_events_time", "created_at"),
    )
    id = Column(String(36), primary_key=True)
    client_id = Column(String(40), nullable=False)
    event_type = Column(String(40), nullable=False)   # one of EVENT_TYPES
    detail = Column(String(500), default="")            # short technical/log line
    status = Column(String(10), default="ok")            # ok | warn | error
    meta_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
```

New Alembic migration, additive only (new table, touches nothing existing). Flag for a quick `database-architect` sanity pass during implementation, not now.

DPDP note: only `client_id` (already the join key used everywhere else) + short strings — no phone/email/raw PII duplicated into this table.

### 4.2 Module — `app/platform/delivery_ledger.py`

Mirrors `team.py`'s style (sync, defensive, never raises):

- `EVENT_TYPES` — the mission's 14 types. `EVENT_LABELS` dict per type: `{"customer_hi": "...", "admin": "...", "icon": "..."}` so one row renders two ways (customer-friendly Hinglish vs admin-technical) without duplicating storage.
- `log_event(client_id, event_type, detail="", status="ok", meta=None) -> None` — validates `event_type` is known (unknown types still logged, just unlabeled, never raises).
- `get_timeline(client_id, limit=50, audience="customer"|"admin") -> list[dict]` — reads rows, renders via `EVENT_LABELS` for the given audience.

**Core event subset wired in THIS sub-project** (8 of 14 — chosen to prove the ledger end-to-end and cover the urgent unblock):
`customer_created`, `plan_activated`, `onboarding_started`, `onboarding_completed`, `marketing_calendar_generated`, `post_draft_created` (batched per run, not per item — avoids timeline spam), `automation_failed` (fed from the existing `_record_stuck` path in `customer_delivery.py` — reuses a signal that already exists, just wasn't visible), `admin_manual_action` (fed from the new "Deliver Now" button, §4.3).

**Deferred to sub-project 2/5** (explicitly, so nothing is silently dropped): `post_approved`, `post_published`, `post_failed`, `lead_captured`, `followup_sent`, `weekly_report_generated` — each wires in naturally when its owning view (Marketing Calendar / Leads Inbox / Reports) is built, touching that view's real call sites rather than guessing at them now.

### 4.3 Admin surface

- Extend `_build_client_timeline()` (`admin_dashboard.py:236`) to merge `delivery_ledger.get_timeline(client_id, audience="admin")` alongside the existing `AgentEvent`/inquiries/audit sources — one combined technical+business timeline per the mission's Phase 4 ask, no new page.
- New endpoint `POST /api/admin/clients/{id}/deliver-now` → calls existing `customer_delivery.deliver_client_value(client, force=True)` (already built, already the correct one-customer bypass — no flag flip) → logs `admin_manual_action` to the ledger either way (success or failure reason, so admin sees why it's still stuck if it fails, e.g. `no_phone`).

### 4.4 Customer surface

Must fit the just-shipped 4-view IA, not compete with Home's one-job rule. Recommendation: a small "AI ne aapke liye kya kiya" collapsed section inside the **Account** view (next to Billing/Plan — low-traffic, detail-oriented view, matches where the redesign already parks secondary information) rather than a new Home card. Reads `delivery_ledger.get_timeline(client_id, audience="customer")`. No new nav item, no new page — one section inside an existing view.

### 4.5 Wiring the core 8 events into existing call sites

| Event | Call site |
|---|---|
| `customer_created` | `customer_onboard.py` (admin onboard) + UPI activation path when client record is new |
| `plan_activated` | `upi_payments.py:_try_activate`, `upi_payments.py` decide(), `admin_ops.py:upi_activate` |
| `onboarding_started` | `onboarding.py` auto_onboard() entry |
| `onboarding_completed` | `onboarding.py` setup_done mark (~line 401) |
| `marketing_calendar_generated` | `auto_content.py` seed_client_content() / run_daily_content() completion |
| `post_draft_created` | same, batched count per run |
| `automation_failed` | `customer_delivery.py:_record_stuck()` — add ledger call alongside existing jsonl log |
| `admin_manual_action` | new deliver-now endpoint (§4.3) |

## 5. Compliance / safety

- `AUTO_DELIVER_VALUE` and `WHATSAPP_AUTO_SEND` stay exactly as they are (both OFF). This sub-project never reads or flips them — the "Deliver Now" button calls `deliver_client_value(..., force=True)`, the same single-customer bypass path the code already exposes for operator use, requiring a human admin click every time.
- No new customer-facing writes without human action. No bulk-send. No change to any compliance gate (DND/consent/AI-disclosure untouched — this sub-project doesn't touch telephony).
- All new code follows this repo's fail-open-on-external/fail-closed-on-compliance convention: ledger writes never raise and never block the caller's real work (matches `AgentEvent`/`team.log_event` precedent exactly).

## 6. Testing plan

1. `log_event()` writes a row; unknown event_type doesn't raise.
2. Admin `/clients/{id}/timeline` includes delivery-ledger events merged with existing sources.
3. `POST /clients/{id}/deliver-now` — success path marks delivered + logs `admin_manual_action`; failure path (no phone / send error) still logs the reason, doesn't raise, doesn't require the global flag.
4. Customer-facing timeline renders Hinglish labels, not raw event_type strings; empty state (brand new customer, zero events) shows a useful message, not a blank box.
5. Existing `test_billing_truth_2026.py` and duplicate-route grep stay green (no packages.py or routing changes in this sub-project).

## 7. Rollout

Local build + targeted pytest + `prod_check.py` only. No VPS deploy without explicit user authorization (per CLAUDE.md and Phase 6 rule 5). No git commit of this spec or any resulting code without the user asking.

## 8. Open items carried to memory/backlog.md (not blocking this sub-project)

- Duplicate aggregator logic (automation-health/today-overview/team-status computed independently 3x across `control_center.py`/`admin_dashboard_builders.py`/`growth.py`; 3 separate approval-decide code paths) — real, found during audit, out of scope here.
- `agent_tools.html` (17 dev-only capabilities) has no value for a solo shop-owner admin persona — candidate for HIDE-FROM-DEFAULT-NAV in sub-project 3, not delete.
- 3 customer dashboard fork files share near-identical structure by design (product IA, not accidental duplication) — template-level consolidation is a low-priority backlog item, not a redesign.
