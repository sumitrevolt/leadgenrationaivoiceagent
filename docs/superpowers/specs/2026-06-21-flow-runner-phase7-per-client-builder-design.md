# Flow Runner — Phase 7: Per-client builder (customer portal) — Design Spec

> **Status:** Approved 2026-06-21. Phases 1-6 LIVE on prod. This is the roadmap's "demand-funded product moat" (GoHighLevel-parity), built SAFE MVP.
> **Decision:** Customers build + run their OWN flows from the customer portal, but only with a **draft-only restricted palette** and **hard tenant isolation**. Reuse the entire Phase-1..6 engine; add a tenant-scoped customer API + a restricted compile mode. **Security is the load-bearing design axis** (customers run automations on our infra).

---

## 1. Why
n8n-parity is done for admins (Phases 1-6). The product moat = letting CLIENTS build their own automations in `/app/customer` (GoHighLevel-parity). The risk: customer-authored automations executing on our infra (abuse, SSRF, sending under our identity, cost, tenant leakage). Phase 7 ships this **safely** — restricted palette + strict isolation + double-gated.

## 2. Goal / Non-goals
**Goal:** An authenticated customer (`require_customer` → client_id) can CRUD + run + monitor flows scoped to THEIR client_id, using only **draft-safe** executors, gated double-OFF by default.

**Non-goals (YAGNI):** per-tenant flag granularity (master env flag for MVP); customer cron/event triggers; customer HTTP node; flow sharing between clients; customer-authored side-effecting/sending nodes.

## 3. Security model (the core)
1. **Tenant isolation (hard):** flows carry `owner_client_id`. Customer API derives client_id from `require_customer` (JWT role=customer) — NEVER from the request body. Every read/write/run/status/approve checks `owner_client_id == caller`. Admin flows have `owner_client_id == ""` and are invisible/untouchable to customers. Cross-tenant access → 404 (not 403, to avoid existence leak).
2. **Restricted palette:** `CUSTOMER_SAFE_ACTIONS = {content_pack, social_drafts, seo_blog_draft, brand_pulse, review_scan, client_report_draft}` (+ `breakpoint`/`merge` node kinds). All are draft-generating, no-send, no-cost-scrape, no-SSRF. Compiler `customer_safe=True` mode REJECTS any other action — explicitly bars `http_request` (SSRF), `crm_queue/telegram_draft/whatsapp_draft` (send under our identity), `scrape/harvest` (cost/ToS), `cadence_run/revenue_sweep/optimizer/sales_analysis/rescore` (ops).
3. **Double-gated, default OFF:** `FLOW_RUNNER` (master) AND `FLOW_RUNNER_CUSTOMER` (customer-portal master). Either off → all customer flow routes 503.
4. **Caps:** ≤ `_MAX_CUSTOMER_FLOWS = 20` flows per client (create-time check). Run abuse bounded by existing plan-tier rate-limit middleware.
5. **Reuse + unchanged compliance:** runs go through the SAME `flow_dispatch`/engine — drafts only, breakpoints honored, all server-side TRAI/DLT/send gates intact. Run inputs stamped `_owner_client_id`. Customer sees only runs whose flow they own.

## 4. Components
### 4.1 `flow_store.py` (edit, additive)
- `save_flow(flow, by="admin", owner_client_id="")` — store `owner_client_id` in rec (from caller, not body).
- `list_flows(owner=None)` / `list_flows_full(owner=None)` — when `owner` given, filter to `owner_client_id == owner`. Row exposes `owner`.
- `owned_by(flow_id, client_id) -> bool` — True iff flow exists AND its owner == client_id.
- `count_for_owner(client_id) -> int` — for the cap.

### 4.2 `flow_compiler.py` (edit, additive)
- `compile_flow(flow, customer_safe=False)` — when True, every `task` node action MUST be in `CUSTOMER_SAFE_ACTIONS`, else error `"action 'X' not allowed for customer flows"`. Applies before linear/dag split. Define `CUSTOMER_SAFE_ACTIONS`.

### 4.3 `app/api/customer_flows.py` (NEW) — `APIRouter(prefix="/api/customer")`, mounted in main.py
All routes `Depends(require_customer)` → client_id; gated `FLOW_RUNNER` + `FLOW_RUNNER_CUSTOMER` (503 else):
- `GET /api/customer/flows` → `flow_store.list_flows(owner=cid)`.
- `POST /api/customer/flow` → cap-check (create) → `save_flow(body, owner_client_id=cid)` → `compile_flow(saved, customer_safe=True)` → `{ok, flow, runnable, compile_errors}`.
- `GET /api/customer/flow/{id}` → owner-check (404 if not owned) → flow + customer_safe compile preview.
- `DELETE /api/customer/flow/{id}` → owner-check → delete.
- `POST /api/customer/flow/{id}/run` → owner-check → `flow_dispatch.start("flow:"+id, {"_owner_client_id":cid})` → `process_tick.delay`. (Compile must be customer_safe-clean.)
- `GET /api/customer/flow/run/{run_id}` → resolve run → flow_id from `replay().process` → owner-check → `replay` + `journal`.
- `POST /api/customer/flow/run/{run_id}/approve` + `/reject` → owner-check → `flow_dispatch.approve/reject`.

**Ownership for run-state:** the run's `process` is `flow:<id>`; extract `<id>`, verify `owned_by(id, cid)`. Reject (404) otherwise — a customer can never inspect another tenant's run.

**Run resolver caveat:** `dag_engine.start_run`/`process_library.get_process` resolve `flow:<id>` from flow_store WITHOUT an owner filter (engine is owner-agnostic). Isolation is enforced ENTIRELY at the customer API layer (owner-check before every start/status). Admin flows remain runnable by admin via growth_process; customers can only reach their own via customer_flows. This is acceptable because the customer API never starts/inspects a flow it hasn't owner-checked.

### 4.4 `automation_flags.py` (edit) — add `FLOW_RUNNER_CUSTOMER`.
### 4.5 `main.py` (edit) — `app.include_router(customer_flows_router)` + `GET /app/customer/flows` → `customer_flows.html`.
### 4.6 `frontend/customer_flows.html` (NEW) — minimal builder reusing explorer builder patterns, restricted palette (only CUSTOMER_SAFE_ACTIONS templates), customer endpoints, customer-token auth. List + save + run + status.

## 5. Safety
Hard tenant isolation (API-layer owner-check on every op, 404 on cross-tenant); restricted draft-only palette (compiler-enforced); double-gated default OFF; caps; reuse server-side compliance + breakpoints; never-raise; additive; `process_engine.py` untouched. The engine resolver is owner-agnostic by design — **all isolation is at the customer API boundary** (documented §4.3), which never starts/reads a flow without an owner-check.

## 6. Testing
- `tests/test_flow_store_owner.py` — owner saved; `list_flows(owner)` filters; `owned_by` true/false; cross-owner not listed; `count_for_owner`.
- `tests/test_flow_compiler_customer_safe.py` — safe action compiles; `http_request`/`crm_queue`/`scrape` rejected under customer_safe; allowed under admin (customer_safe=False).
- `tests/test_customer_flows_api.py` — flag-off → 503; create scoped to caller; **cross-tenant get/delete/run → 404** (CRITICAL isolation test); unsafe-action flow → not runnable; cap enforced; run + status owner-checked.
- Regression: all existing flow tests + prod_check + explorer_sync green.

## 7. File touch-list
**New:** `app/api/customer_flows.py` · `frontend/customer_flows.html` · `tests/test_flow_store_owner.py` · `tests/test_flow_compiler_customer_safe.py` · `tests/test_customer_flows_api.py`.
**Edit (additive):** `app/automation/flow_store.py` · `app/automation/flow_compiler.py` (`customer_safe` + `CUSTOMER_SAFE_ACTIONS`) · `app/api/automation_flags.py` (`FLOW_RUNNER_CUSTOMER`) · `app/main.py` (mount router + page route) · explorer `flow_runner` node `files:` (add `customer_flows.py`). **No new dep/DB/worker. `process_engine.py` NOT edited.**

## 8. Rollout
Ship flags OFF → deploy. Enable per-client demand: `FLOW_RUNNER=1` + `FLOW_RUNNER_CUSTOMER=1` → recreate app+worker. Smoke: customer login → build a `brand_pulse → seo_blog_draft → breakpoint` flow → run → drafts only, pause at breakpoint; confirm an `http_request` node is rejected at save; confirm tenant A cannot GET tenant B's flow (404). Rollback = unset `FLOW_RUNNER_CUSTOMER`.
