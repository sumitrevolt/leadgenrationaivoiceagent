# UNITY OFFICE — API CONTRACT (2026-07-12)

> Phase 11 rule applied: REUSE secure existing APIs first. Audit verdict: the aggregations the
> master spec proposed as `GET /api/office/admin/state` and `GET /api/office/customer/state`
> ALREADY EXIST as `GET /api/platform/office/snapshot` and `GET /api/customer/office`.
> **No new state endpoints are created.** This doc pins the consumed contracts + the JS bridge.

## 1. Admin office state — `GET /api/platform/office/snapshot` (existing)

- File: `app/api/office_hq.py:25`; auth `Depends(require_admin)`; Redis cache TTL 18s.
- Consumed keys (shell → Unity):

```jsonc
{
  "rooms":   [ { "id": "voice_team", "label": "...", ... } ],      // canonical ROOM_DEFS
  "agents":  [ { "key": "...", "name": "...", "room": "...", "status": "...", "task": "...", ... } ],
  "metrics": { },                                                   // KPI strip
  "pipeline":[ { "id": "...", "count": 0, "source": "real|partial|mock", "note": "..." } ],
  "approvals": { "drafts": [], "counts": {}, "queue": [], "recent_decisions": [] },
  "system_health": { },                                             // workers/queues/scheduler
  "next_best_actions": [ ]
}
```

- Honesty guarantee reused: each pipeline stage carries `source`/`note` provenance — Unity must
  surface `partial|mock` provenance visually (muted + "partial data" tag), never dress it as live.
- Drill-down: `GET /api/platform/office/pipeline/{stage_id}` (office_hq.py:54).
- Supplementary admin feeds: `/api/admin/system-health-detail` (flag `SYS_HEALTH_DETAIL`),
  `/api/activation/readiness` (compliance tile incl. DND fail-closed, promo window,
  platform_dial), `/api/control-center/overview`.

## 2. Customer office state — `GET /api/customer/office` (existing)

- File: `app/api/customer_dashboard.py:120` (`_build_office`, flag `CUSTOMER_OFFICE` default ON);
  auth `client_id = Depends(require_customer)` — tenant derived from JWT `sub`. **The customer
  NEVER sends a client_id; any client-supplied tenant hint is ignored by construction.**
- Supplementary (all same auth): `/api/customer/dashboard`, `/delivery-proof` (Delivery Shelf
  truth), `/approvals/pending` + `POST /approvals/{id}/decide`, `/social/accounts` (opaque
  `account_id` = sha1[:16], masked refs, tokens never present), `/timeline`, `/report`.
- Plan/deliverables: derived server-side from `app/marketing/packages.py` through these endpoints —
  Unity/shell hard-codes NOTHING (no plan names, prices, counts).

## 3. Events — existing transports only

- Admin live: SSE `GET /api/events/stream` (app/api/events.py:158, `require_admin`,
  Redis pub/sub `lgai:events`, 20s heartbeat, server-side DB-poll fallback).
- Customer: 15s polling of §2 endpoints (existing office_map cadence; snapshot cache TTLs exceed
  poll interval per CLAUDE.md scheduler rule). Tenant-scoped SSE does not exist; deferred (backlog).
- Client rules: reconnect backoff 2s→60s + jitter; event-id dedup ring; stale >45s → indicator;
  401 → login-required state.

## 4. JS bridge — explicit action allowlist (shell-owned)

Implemented in `frontend/office_blueprint.html` (`LG_BRIDGE`). Unity may ONLY invoke these actions;
anything else is rejected + logged to console (never executed). Payload: `{action, id?, origin}`.
`id` sanitized: `^[a-zA-Z0-9_\-\.]{1,64}$`. Target routes are FIXED here — Unity cannot supply URLs.

| Action | Target (existing route) | Notes |
|---|---|---|
| `open_command_center` | `/app/control-center` | new tab-safe |
| `open_customer_360` | `/app/admin#customer_360` | admin only |
| `open_delivery_proof` | `/app/delivery-command-center` | admin; customer variant → dashboard delivery view |
| `open_approval` | `/app/admin#approvals` | decisioning stays HTML |
| `open_setup` | `/app/customer#setup` | customer |
| `open_reports` | `/app/customer#reports` | customer |
| `open_social_connect` | `/app/customer#social` | existing secure connect flow |
| `open_billing` | `/app/admin` (UPI section) / `/app/customer#billing` | role-dependent |
| `open_support` | `/app/customer#support` | |
| `open_agent_details` | HTML side panel (in-shell) | no navigation |
| `refresh_office_state` | re-fetch state APIs | debounced ≥5s |

Reverse direction: shell → Unity via `unityInstance.SendMessage("Bridge","OnHostEvent", json)`
with `{type:"state"|"select"|"mode", origin:"host", ...}`. Loop guard: origin echo suppression.

## 5. Mutations

All mutations = existing authenticated endpoints, invoked from the HTML panel (not Unity meshes):
agent pause/resume (`/api/platform/office/agents/{m}/pause|resume`), pipeline overrides
(`/assign|next-action|resolve-stuck|move`), approval decisions (existing per-queue endpoints),
UPI approve/reject (`/api/upi/pending/{pid}/*`). Server-side authz unchanged and authoritative.

## 6. Schema stability

These are INTERNAL contracts consumed by first-party frontends; office_hq snapshot has no
`schema_version` today. Shell defends with tolerant parsing (missing key → empty state + stale
badge), and any additive backend change follows the existing additive-only convention (ADR-runbook:
additive over rewrite). If a breaking change ever becomes necessary, add `schema_version` to the
snapshot FIRST and version the shell.

## 7. Forbidden in any office-bound response (test-locked)

Secrets/API keys/tokens (incl. `sk_`, `Bearer`, social vault contents), SIP credentials, webhook
secrets, DB URLs, raw prompts with customer data, other tenants' identifiers in customer responses.
See UNITY_VIRTUAL_OFFICE_SECURITY.md + `tests/test_office_blueprint_shell.py`.
