# ACTIVE_WORK - max 3 workstreams

Fact tags: **GIT_VERIFIED** · **DIRECT_HOST_VERIFIED** · **LOCAL_ARTIFACT** · **ASSUMED**

---

## WS-1 PR #188 rate-limit 429 — DONE (deployed + UAT)
- **ID:** WS-1
- **Business outcome:** False dashboard `Rate limit exceeded` fixed without weakening auth/abuse.
- **Current state:** MERGED `#188` → `58a3b70c7cd9431d0c70d4bc0744df1ae4753984`. **DIRECT_HOST_VERIFIED** 2026-07-30T13:12Z: `/health.version=58a3b70c`, 5/5 app-image services `:58a3b70c` healthy, smoke 200, celery/DLQ=0. Live UAT: 120 asset hits → 0×429 then 30 API OK (asset bucket isolated); anon API burn still 429 with structured detail + Retry-After (plan-tier 60 rpm). Claude review PASS @ `e5970f8a` ([Review](52cef277-be4f-456c-8629-0349edd2103d)).
- **Next exact action:** None for this lane. Optional P2 follow-up: Redis TTL-based Retry-After on primary path.
- **Out of scope:** flag flips · dial · WA auto.

---

## WS-2 Automation Max matrix + blueprint drift repair — ACTIVE
- **ID:** WS-2
- **Business outcome:** Honest capability matrix + Master Blueprint represents on-disk inert engines.
- **Current state:** Matrix at `docs/context/AUTOMATION_MAX_READINESS_MATRIX.md`. Code repair: L1 nodes `detail_sales_autopilot`, `detail_creative_os`, `detail_owner_email_canary` added → counts **L0=48 / L1=8 / L2=1 = 57** (validate_graph ok). Branch `codex/blueprint-missing-nodes`.
- **Next exact action:** Open/merge PR for blueprint nodes + matrix after CI green; do NOT enable inert flags.
- **Out of scope:** PLATFORM_DIAL / WA auto / REPLY_AUTO_SEND / UPI_AUTO_ACTIVATE / sales-autopilot live channels.

---

## WS-3 Revenue canary — OWNER ACTION
- **ID:** WS-3
- **Business outcome:** 2nd Marketing paid customer; first safe sales action.
- **Current state:** Owner-email-canary routes LIVE on prod (`/api/admin/owner-email-canary/preflight` → 401 without token = auth gate OK). Activation summary `ready_for_first_paid_customer=true`. Estique 1-click send + Jiya video review login still owner-owned.
- **Next exact action:** Owner: (1) admin login → owner-email-canary preflight/send one inbox canary, (2) Estique Hot Queue human send decision. Keep bulk/auto OFF.
- **Out of scope:** cold auto-calls · bulk WA · platform_dial.

---

## Open / recent PRs
- **#188** — MERGED + DEPLOYED `58a3b70c` (DIRECT_HOST_VERIFIED).
- **#187** — Owner Email Canary ancestry under prod tip.
