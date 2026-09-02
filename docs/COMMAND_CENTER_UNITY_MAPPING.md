# COMMAND CENTER ↔ UNITY MAPPING (2026-07-12)

> The existing Command Center (`/app/control-center`, ADR-034 merged from /app/command-center)
> and Delivery Command Center (`/app/delivery-command-center`) REMAIN the operational source of
> truth. Unity rooms map onto their sections and deep-link back; Unity never re-implements their
> tables/forms/logs.

## 1. Department → Unity room → existing surface

| Command-Center area | Unity room (id) | Live state feed (existing) | Deep-link (bridge action → route) | Safe Unity actions (existing endpoints only) |
|---|---|---|---|---|
| Overview / system KPIs | `command_center` (central room) | `/api/control-center/overview`, `snapshot.metrics`, `snapshot.system_health` | `open_command_center` → `/app/control-center` | none (read-only) |
| Customer Operations | `reception` | `snapshot.pipeline` (onboarding stages), `/api/activation/readiness` (admin) | `open_customer_360` → `/app/admin#customer_360` | none |
| Delivery Operations | `delivery` | `product_one_delivery.customer_delivery_status` via admin views; `/api/customer/delivery-proof` (customer) | `open_delivery_proof` → `/app/delivery-command-center` | none |
| Content Operations | `content_studio` | `snapshot.pipeline` content stages | `open_setup`/`open_approval` per item | none |
| Social Operations | `social` | `GET /api/customer/social/accounts` (per tenant), `social_oauth /state` | `open_social_connect` → customer dashboard social view | none — manual/automatic mode shown TRUTHFULLY (auto-publish currently OFF) |
| Approval Operations | `approvals` | `snapshot.approvals` = `office_hq.build_approval_queue()` (fuses approvals_bridge + code_upgrader + self_improve) | `open_approval` → `/app/admin#approvals` | decide via EXISTING per-queue endpoints only |
| Billing / UPI | `billing` | `GET /api/upi/pending` (admin), `/api/billing/*` | `open_billing` → `/app/admin` UPI section (`#sec-upi-selfserve`) | approve/reject via existing `/api/upi/pending/{pid}/approve|reject` — HTML panel, not Unity mesh UI |
| Voice Operations | `voice_team` (exists in ROOM_DEFS) | team status (voice members), `activation` telephony block | `open_agent_details` | pause/resume via `/api/platform/office/agents/{m}/pause|resume` (RUNNABLE_MEMBERS only) — **platform_dial rendered HARD OFF (USER-MANDATE 2026-07-05)** |
| Compliance | `compliance` | `activation._compliance_env()` via `/api/activation/readiness`: DND fail-CLOSED, promo window 09:00–19:00, DLT state, `platform_dial.enabled()` | none (read-only room) | none — display only, gates untouchable |
| Infrastructure | `server_room` | `/api/admin/system-health-detail` (flag `SYS_HEALTH_DETAIL`), `automation_health.health()`, `/metrics` queue depths | `open_command_center` → `/app/ops` | none |
| Support | `support_desk` | no ticket API exists (gap) — show unresolved blockers from snapshot NBAs | `open_support` → customer dashboard support view | none |

Note: `snapshot.*` = `GET /api/platform/office/snapshot` (`app/api/office_hq.py:25`, admin).
Existing `ROOM_DEFS` ids (office_hq.py:42–59): `coordinator, lead_lab, sales_crm, voice_team,
marketing_team, qa_audit, platform_engineering, admin_finance`. Unity's ops rooms above are VIEWS
over these + pipeline stages — Unity must key on ids delivered by the API, adding NO new backend ids.

## 2. Synchronization contract (Phase 19)

Shared selection model (browser JS, single owner — the shell page):
```js
window.LG_OFFICE_SEL = { selectedRoom:null, selectedAgent:null, selectedCustomer:null, activeOfficeMode:"office" };
```
- Unity → shell: `SendMessage`-emitted JSON `{type:"select", kind:"room|agent|customer", id}` via the
  allowlisted bridge (see UNITY_OFFICE_API_CONTRACT.md §4). Shell updates HTML side panel +
  minimap highlight. IDs = opaque ids from the API (room id, agent key, customer display handle).
- Shell → Unity: `unityInstance.SendMessage("Bridge","OnHostEvent", json)` for selection made in the
  HTML panel / Command Center link-in.
- Backend event → both: admin shell subscribes SSE `GET /api/events/stream` (existing, admin-only);
  on event, shell refreshes snapshot (bounded: ≥5s debounce) and forwards a diff to Unity.
  Customer mode: 15s polling (existing office_map pattern) — no tenant SSE exists yet.
- Loop prevention: every selection message carries `origin:"unity"|"host"`; receiver never re-emits
  a message whose origin ≠ itself.

## 3. What stays HTML (never Unity)

Large tables, forms, logs, editors, auth, payments: `/app/admin`, `/app/control-center` inspector,
approval editor, UPI queue table, Customer 360, setup wizard, reports, invoices. Unity room click →
highlight → HTML panel/route. The Command Center remains the place where operational ACTIONS happen.
