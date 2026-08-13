# FREEBUFF HOT QUEUE CONNECTOR — PARKED SPEC (2026-08-12)

**Status: PARKED / NOT IMPLEMENTED.** No code exists. No flag, route, engine or dependency added.
Default posture: `NO-GO` until a real attempted funnel step produces **correlated technical defect evidence**
(mission phase-change rule: engineering reopens only on proven defect, never on speculation).

---

## 1. Purpose (one line)

Ek narrow **read-only** bridge: authenticated Hot Queue cards + draft preview + send-readiness to
FreeBuff/Boss for ranking and draft support — **final send stays 100% owner-operated**.

## 2. Grounded truth — capability ALREADY EXISTS (no new engine needed)

Verified on `origin/main @ cd2e3437` (read-only source inspection):

| Need | Existing surface | Location |
|---|---|---|
| Hot Queue read (admin) | `GET /api/growth/reply/hot-queue?limit&scope` → `{ok, count, summary, items}` | `app/api/growth.py:1279` |
| Card fields | `hq_id · intent · channel · draft · phone · wa_link · business_name · niche · city · age_* · sla_state · owner_action` | `app/platform/reply_agent.py:2242` (`hot_queue`) |
| Draft preview + wa.me 1-click | `wa_link` auto-generated (`https://wa.me/…?text=<draft>`) | `reply_agent.py` same fn |
| Done / park / council | `POST /reply/hot-queue/done` · `/park` · `/council-decide` · `/quick-done/{token}` | `growth.py:1319–1365` |
| Daily revenue brief (read-only) | `hot_queue_brief` job — flag `HOT_QUEUE_BRIEF_DAILY` (default OFF), health-gated | `worker.py:53,537` · `automation_flags.py:236` · `automation_health.py:75` |
| Payment-chase cards | `sales_autopilot.pay_truth.unpaid_chase_cards` → `owner_action=chase_payment_upi_proof` | `reply_agent.py` (same fn) + `app/platform/sales_autopilot` |
| Noise/suppression filter | `_is_noise_row` + emailed-prospect join (email enters queue only if we actually emailed them) | `reply_agent.py` |

**Conclusion:** a connector would add NO new read capability the platform lacks. Any un-park must first
prove the existing API/UI is the broken thing — not that "an agent couldn't reach it yet".

## 3. Capability contract (IF ever built)

- **READ only:** list + summary + draft preview + `wa_link` presence. Zero writes from the connector.
- **NO-SEND:** no email / WhatsApp / call / post / payment mutation possible from the connector surface.
  `wa_link` is presented to the owner, never auto-fired.
- **Auth:** `require_admin` (module-limited respect via `rbac`) + existing `rate_limit` deps; token never
  embedded/logged.
- **PII minimisation:** full phone/email NOT transmitted or logged by the connector; masked refs only
  (`hq_id` + `business_name` + `city` + `niche`). Reuse `hot_queue_summary` envelope for counts.

## 4. Gates (apply only at implementation time — mirror `integration-engineering` pattern)

- **Flag:** `FREEBUFF_HQ_READ=0` default OFF, registered in `AUTOMATION_FLAGS` (`app/api/growth.py` /
  `automation_flags.py`) so it is visible at `/api/growth/infra/flags`.
- **Kill-switch:** flag OFF = connector inert (zero surface); container recreate to reload env.
- **Idempotency:** read-only ⇒ no side effects; `done`/`park` remain owner-UI actions only.
- **Suppression/consent:** inherits existing noise filter + emailed-prospect join + DND/suppression
  semantics; connector never bypasses them.
- **Tenant isolation:** single-tenant admin surface; no cross-client path; scope param respected
  (`boss|admin|all`).
- **Compliance:** cold WhatsApp stays OFF (`SALES_AUTOPILOT_WHATSAPP_ENABLED=0`), UPI approval
  owner-only, no §5 gate weakened.
- **Tests:** import-safe · inert-without-flag · read contract (item fields present) · 401 without admin ·
  **no-send assert** (no POST-capable path exists on the connector).
- **Rollback:** flag OFF + recreate; no schema/migration.
- **Observability:** reuses `hot_queue_summary` + `automation_health`; no new heartbeat.

## 5. Explicit non-goals

No new loop, agent, scheduler, process engine, route, flag or module **until defect evidence**; no agent
32; no second Boss/control plane; no auto-send in any form; no paid services; no Voice/Swara touch.

## 6. Decision rule (when this un-parks)

Un-park only when BOTH:
1. Owner-attempted Hot Queue step fails with correlated evidence (e.g., API 500, missing drafts, broken
   `wa_link`, auth broken for legit admin) — reproduced, not assumed; **and**
2. No existing surface (`/app/inbox`, `/reply/hot-queue`, `hot_queue_brief`) fixes it.

Otherwise this spec stays parked and the owner sprint continues on `/app/inbox` — no code required.

## 7. Owner actions (unchanged, NOT blocked by this spec)

Login → `/app/inbox` → top cards → manual draft/send (TRAI 9–19 IST) → log outcome → UPI bank-credit
confirmation (owner-only) → revenue `PROVEN` only on owner-confirmed credit.

---

_Not implemented — documentation only. No code, flag, route or engine._
