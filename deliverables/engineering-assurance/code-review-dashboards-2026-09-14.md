# Code Review — Admin & Customer Dashboards (Enterprise-Grade Gap Audit + Implementation Spec)

**Reviewer:** Cody (科迪) · Code Reviewer, Engineering Assurance Team
**Date:** 2026-09-14
**Repo HEAD:** `20e4180bc5f148f7b5e75596b1783a2a86ea946d` (matches Graphify build — graph is FRESH)
**Brief:** *"Admin dashboard aur customer dashboard dono enterprise-grade nahi hain — user-friendly banao aur missing features add karo."*
**Scope:** audit + mechanical implementation spec. No source edited this turn. **No commit / push / deploy.**

**Evidence labels used:** `PRODUCTION-PROVEN` · `CODE-PRESENT` · `TEST-PROVEN` · `LOCAL-ONLY` · `PARTIAL` · `STALE` · `UNKNOWN`
Every finding carries a `file:line`. Where a claim is source-only and not runtime-verified, it is labelled `CODE-PRESENT` (not PRODUCTION-PROVEN).

---

## 0. Method & Graphify verdict

- **Graphify IS usable for this task (backend navigation).** Graph is fresh (`GRAPH_REPORT.md` "Built from commit: `20e4180b`" == `git rev-parse HEAD`). `graphify query "customer dashboard routes and tenant scoping"` returned the correct canonical files with line numbers in one call: `customer_dashboard.py` (community 8, 90 nodes), `customer_dashboard_builders.py`, `product_consoles.py` (community 33), `admin_dashboard.py` (community 46), `owner_os.py`, `control_center.py`, `dashboard_assessment.py`. God-node list (`User` 338 edges, `Lead` 120, `get_db_session()` 99) confirms the auth/data core.
- **Graphify limit (as documented):** graph is `app/`-scoped; the **dashboards are HTML in `frontend/`**, which the graph does NOT cover. All frontend claims below come from `grep`/`Read` of `frontend/*.html`, not the graph. `frontend/` page count = **66** (verified `ls frontend/*.html | wc -l` — matches the brief).
- **Route inventory caveat:** importing `app.main:app` locally mounts only **111 routes** because most API routers are env-flag-gated `try/except` mounts (e.g. `COMBO_PRODUCT` unset). The ~700+ production route count could not be reproduced locally → **`LOCAL-ONLY` / `UNKNOWN` for the exact production route total.** Admin/customer router inventory below is therefore built from **source-level** prefix+decorator resolution, which is reliable for the files listed.

---

## 1. Severity-ranked findings

| # | 严重度 | 类别 | 文件:行 | 问题描述 | 建议修复 | 来源 |
|---|--------|------|---------|----------|----------|------|
| F1 | 🔴严重 | 认证/授权 | `app/admin/routes/tasks.py:29` (route fns at `:32,42,48,61,70,79,86,93`) | **Admin task-ledger API had ZERO auth.** `router = APIRouter()` with no `dependencies=` and no per-endpoint `Depends`. All 8 endpoints under `/admin/api/tasks` were callable **unauthenticated**: `GET` list, `GET` kanban, `POST` create, `PUT` update, `DELETE` delete, `POST` auto-assign, `GET` duplicates, `GET` worker/{name}. Mount chain: `app/main.py:1188` → `app/admin/main.py:18` → `tasks.py:29`. The mount is a `try/except` that logs-and-continues (`app/main.py:1187-1191`) — not literally "unconditional", but the import succeeds in practice so impact is unchanged. Siblings `docker.py:40`, `system.py:23`, `workers.py:33` ALL use per-endpoint `Depends(require_admin)` — this file was the outlier. **Zero HTTP callers existed** (verified: only `tests/test_admin_modules.py` hits `/admin/api/tasks`; no HTML/JS/Python consumer). | **✅ FIXED 2026-09-14** — `router = APIRouter(dependencies=[Depends(require_admin)])`. See §4.1 + §9. | CODE-PRESENT → FIXED (TEST-PROVEN) |
| F2 | 🟠高 | 真实性 (fabricated data) | `frontend/archify_customer.html`, `frontend/archify_marketing.html`, `frontend/archify_console_home.html` served at `app/api/product_consoles.py:670,678,686` | **A fabricated-data dashboard surface shipped in prod.** These 3 pages have **0 `fetch()`/XHR/`/api/` calls** (grep verified) — pure static demo backed by `seed-customer.js` (hardcoded `Tata`×5, `Mirae`×3, `Lakme`×4, `CureFit`×3, `containment`×4) + `archify-app.js` localStorage. Were reachable **unauthenticated** at `/app/archify`, `/app/archify/customer`, `/app/archify/marketing`. A customer/stakeholder landing here saw fake enterprise KPIs (CSAT 4.7, ₹14.6L pipeline) as if real. Also **unlinked** (0 refs from any served page) and their internal relative links 404 under `/app/archify/*`. | **✅ GATED 2026-09-14** — all 3 page routes now `Depends(require_admin)`. **Deletion recommended** (pending owner sign-off per `docs/context/FEATURE_PRESERVATION_MATRIX.md:155`). See §4.2 + §9. | CODE-PRESENT → GATED (TEST-PROVEN) |
| F3 | 🟠高 | 分叉漂移 (fork drift) | `frontend/customer_dashboard_v2.html` (served `app/main.py:1826-1839`) vs `frontend/customer_dashboard.html` (served `app/main.py:1795-1823`) | **The v2 fork's docstring is FALSE.** `main.py:1830-1834` claims v2 "binds the SAME authenticated API contract as v1". Verified: v1 calls **~37** endpoints; v2 calls **5** (`/api/customer/auth/me`, `/api/customer/dashboard`, `/api/customer/team`, `/api/billing/subscription`, `/api/billing/usage`). A customer on `/app/dashboard-v2` silently loses: social config/accounts, approvals, videos, delivery-proof, profile, routing, kb-info, 2FA, webhooks, studio, CRM-sync, speed-to-lead, creatives. | Merge v1 features into v2, or make v2 a pure CSS/theme layer over v1's JS. Do not ship two divergent dashboards. See §4.3. | CODE-PRESENT |
| F4 | 🟠高 | 死代码/孤儿 | `frontend/admin_command_center.html`, `frontend/owner_dashboard.html`, `frontend/autonomous_mission_control.html`, `frontend/archify_landing.html` | **4 orphaned templates** — never referenced by any `app/**/*.py` route (grep: 0 hits each). Dead weight; `admin_command_center.html` and `owner_dashboard.html` are superseded by `owner_command_center.html`/`owner_os.html`. | Delete. See duplication map §5. | CODE-PRESENT |
| F5 | 🟡中 | 可维护性/信息架构 | `app/main.py:1842-2198` (admin page routes) | **Admin surface sprawl — 8+ overlapping admin/owner dashboards** served with no single nav: `admin_dashboard.html`(/app/admin), `owner_os.html`(/app/owner), `owner_command_center.html`(/app/owner-command-center), `delivery_command_center.html`(/app/delivery-command-center), `control_center.html`(/app/control-center), `control_center_graph.html`(/app/control-center/graph), `video_command_center.html`(/app/admin/video), `dashboards.html`(/app/dashboards), `admin_db.html`(/app/admin/db). `admin_dashboard.html` nav links only **16** `/app/*` pages — several dashboards are unreachable from any nav. | Define ONE admin shell + nav; demote the rest to tabs/redirects. See §4.5. | CODE-PRESENT |
| F6 | 🟡中 | 重复 | `frontend/voice_console.html` + `frontend/marketing_console.html` (real, API-wired) vs `frontend/archify_customer.html` + `frontend/archify_marketing.html` (demo) | Two competing "console" implementations under near-identical routes (`/app/voice-console` vs `/app/archify/customer`). The real ones (`voice_console.html` calls `/api/social/oauth/*`; `marketing_console.html` 71 KB) are correct; the archify ones are the F2 demo. | Keep the real consoles; delete the archify demo (F2). | CODE-PRESENT |
| F7 | 🟡中 | 一致性 | `app/api/bot_command_center.py:142-145` vs `app/main.py:1842-2165` | **Inconsistent page-route auth.** `bot_command_center_page` gates the HTML shell with `_user=Depends(require_admin)`, but every other page route returns `FileResponse(...)` with **no** server-side auth (client-side token only). Two different security models for the same class of page. | Pick one model. If server-gating the shell is desired, apply it uniformly (admin/owner shells at minimum). See §4.6. | CODE-PRESENT |
| F8 | 🟡中 | 缺失企业特性 | `app/admin/routes/tasks.py:32-39`; `frontend/admin_dashboard.html` (`page=` = 0 occurrences) | **No pagination / bounded queries on admin lists.** `list_tasks()` returns the whole ledger unbounded; the admin HTML has no page control. At scale this is an unbounded read (perf + UX). | Add `limit`/`offset` to `list_tasks` + a page control in the template. See §4.4. | CODE-PRESENT |
| F9 | 🟢低 | 正确性 (misleading) | `frontend/customer_dashboard.html:555,565` (`/api/billing/subscription?client_id=`, `/invoices?client_id=`, `/usage?client_id=`) | Frontend passes `?client_id=` on billing calls. **Not an IDOR today** — `_authed_client_id` (`app/api/billing.py:64-79`) returns the JWT `sub` for `role=customer` and ignores the query param. But it is a footgun: any future refactor to trust the query param becomes an instant IDOR. | Remove the redundant `client_id=` from customer-side calls (it is only needed for the admin-acting-on-behalf path). | CODE-PRESENT |
| F10 | 🟢低 | 多租户 (cosmetic) | `app/middleware/tenant.py:82-90` | Reseller branding middleware is **fail-open** and purely cosmetic (title/logo/colors). It does **not** scope data. A mis-mapped subdomain/custom_domain (`resolve_branding` L38-79) would show one reseller's BRANDING on another's dashboard — cosmetic leak, not data leak. | Acceptable; document. Consider making branding resolution fail-closed only if a future version uses it for scoping. | CODE-PRESENT |
| F11 | 🟢低 | 真实性 (guard) | `data/revenue_attribution.jsonl` (rows carry `"amount_inr": 0`) | `revenue_attribution.jsonl` is **touch/attribution data, not money**. Any tile summing `amount_inr` would report ₹0 or a lie. Real revenue = `data/invoices.jsonl` via `app.billing.gst_invoice`. Current code is correct (see §6) — this is a guard note for future tiles. | Add a code comment / assertion; never sum `revenue_attribution` as revenue. | CODE-PRESENT |

**Severity counts:** 🔴严重 **1** · 🟠高 **3** · 🟡中 **4** · 🟢低 **3** = **11 findings**.

---

## 2. Tenant-isolation findings (dedicated section)

> **Verdict: NO confirmed cross-tenant DATA leak found in the dashboard surface.** (Stated explicitly, per brief.)

What was checked and what holds:

| Surface | Mechanism | Verdict | Evidence |
|---|---|---|---|
| Customer dashboard API (`/api/customer/*`) | Every data endpoint resolves `client_id` from `Depends(require_customer)` = JWT `sub` (`app/api/customer_auth.py:285-330`), never from user input. Verified 39/40 routes in `app/api/customer_dashboard.py`; the 1 without is `/health` (L2896). | ✅ SAFE | CODE-PRESENT |
| Customer consoles API (`/api/consoles/*`) | All 14 API routes `Depends(require_customer)` (`app/api/product_consoles.py:731-1432`). The 12 unguarded routes are static CSS/JS/HTML page serves only. | ✅ SAFE | CODE-PRESENT |
| Customer marketing studio (`/api/customer/studio/*`) | 91/91 routes gated (`app/api/customer_marketing_studio.py`). | ✅ SAFE | CODE-PRESENT |
| Billing (`/api/billing/*`) | `_authed_client_id` (`billing.py:64-79`): customer → JWT `sub` (query param ignored); admin → query `client_id` required. Customer cannot read another tenant's invoices/subscription. | ✅ SAFE | CODE-PRESENT |
| Admin API | `require_admin` on 28/28 `admin_dashboard.py`, 31/31 `admin_ops.py`, 37/37 `owner_os.py`, 9/9 docker, 5/5 workers, 3/3 system. | ✅ SAFE | CODE-PRESENT |
| **Admin task ledger** | **`app/admin/routes/tasks.py` — 0/8 gated** (F1). | ⚠️ **EXPOSED** | CODE-PRESENT |

**F1 is isolation-adjacent (not a classic tenant leak, but flagged here):** the unauthenticated task-ledger API exposes a **global admin artifact** (worker task titles, owners, statuses) to anyone. Task titles may embed client/business names → a public reader could enumerate client work. This is the single highest-severity finding and the one that most resembles a cross-tenant exposure. **Fix F1 first.**

`?client_id=` (F9) and tenant branding (F10) were specifically probed for IDOR — both are **not** exploitable as written; F9 is a latent footgun only.

---

## 3. Enterprise-grade feature gap matrix

Legend: ✅ present · 🟡 partial · ❌ missing. "Where" = file the fix belongs in.

| Capability | Admin | Customer v1 | Where the fix belongs |
|---|---|---|---|
| **Audit trail of actions** | ✅ `record_admin_action` used on all 15 mutating admin routes (`admin_dashboard.py:605-1480`); `GET /api/admin/audit-logs` (`admin.py:1129`, super-admin) | 🟡 delivery ledger + approvals, no user-action audit | admin: keep. customer: add `customer_audit` writes on profile/social/approval mutations |
| **RBAC / roles** | ✅ `require_admin` + module grants (`app/platform/rbac.py:16-95`, `require_admin` `auth_deps.py:109-122`) | n/a (single tenant) | admin: expose RBAC editor UI (module grants exist; UI for `team_access.html`) |
| **Bulk operations** | 🟡 `POST /clients/bulk-email` (`admin_dashboard.py:1247`), `POST /clients/dedupe` (L1203) | ❌ | admin: add bulk delete/pause/export; customer: bulk lead actions |
| **Export** | 🟡 DB explorer CSV (`admin_db_explorer.py`), per-client timeline | ❌ | add `/api/admin/export/{dataset}.csv`; customer: leads/report CSV |
| **Search / filter / pagination** | 🟡 filters on some (`/clients/{id}/timeline?limit`), **no pagination** (`page=`=0 in HTML) | 🟡 `limit` only | add `limit/offset` + UI pager (see F8) |
| **Empty / error / loading states** | 🟡 HTML has `error`×146, `empty`×11, `loading`×7 — present but ad-hoc, no shared component | 🟡 same | extract a shared `state()` renderer in `frontend/archify_console.js` or a new `frontend/lib/states.js` |
| **Confirmation on destructive actions** | 🟡 `confirm(`×28 in `admin_dashboard.html` — but `DELETE /admin/api/tasks/{id}` (F1) and other task ops have none | ❌ | add confirm to task-ledger UI; standardise a modal |
| **Observability surface** | ✅ `/api/admin/system-health-detail`, `/ops-snapshot`, `/sync-health`, `/mcp/health` | ❌ | admin: consolidate into one health tile; customer: "system status" banner |
| **Data-freshness indicators** | 🟡 `is_sample_data` flag + `evidence_kind`/`task_execution_verified` truth gate (`admin_dashboard.py:1518-1532`) | 🟡 `is_sample_data` in payload | surface an explicit "as of <ts>" on every tile |
| **Bounded queries / indexes** | ❌ task ledger unbounded (F8) | 🟡 | see F8 |

**Already good (do not rebuild):** invoice-backed revenue (`_has_paid_evidence` `admin_dashboard_builders.py:104`), the workforce truth gate, admin idempotency (`admin_idempotency`), `admin_audit` redaction (`app/platform/admin_audit.py:51-163`).

---

## 4. Implementation spec (ordered so the work is mechanical)

> All edits are source-only. **Do not deploy.** Each fix ships with its acceptance test.

### 4.1 — F1 🔴 Gate the admin task-ledger API — ✅ DONE (2026-09-14)
**File:** `app/admin/routes/tasks.py`
**Change:** add the import + router-level dependency (router-level = one line, covers all 8 endpoints):
```python
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.auth_deps import require_admin
...
router = APIRouter(dependencies=[Depends(require_admin)])
```
**Acceptance test** (`tests/test_admin_task_ledger_auth.py`, new):
```python
def test_tasks_require_admin(client):
    for method, path in [("get","/admin/api/tasks"),("get","/admin/api/tasks/kanban"),
                         ("post","/admin/api/tasks"),("post","/admin/api/tasks/auto-assign"),
                         ("get","/admin/api/tasks/duplicates?title=x")]:
        r = getattr(client, method)(path, json={}) if method=="post" else getattr(client, method)(path)
        assert r.status_code in (401, 403), f"{method} {path} not gated"
```
**Also add a repo guard test** asserting every router in `app/admin/routes/*.py` declares `require_admin` (prevents regression).

### 4.2 — F2 🟠 Kill (or wire) the fabricated archify surface — ✅ GATED (2026-09-14); deletion pending sign-off
**File:** `app/api/product_consoles.py:670-696` (routes; **note: `app/api/`, not `app/platform/`**) + `frontend/archify_customer.html`, `frontend/archify_marketing.html`, `frontend/archify_console_home.html`, `frontend/seed-customer.js`, `frontend/seed-marketing.js`
**Change applied (safe, non-destructive):** all three `@router.get("/app/archify*")` handlers now carry `_user=Depends(require_admin)` (import added `from app.api.auth_deps import require_admin`). Anonymous + customer access to the fabricated pages is closed. **Deletion of the routes + 5 files remains the recommended final fix but needs owner sign-off** (`docs/context/FEATURE_PRESERVATION_MATRIX.md:155` → "Owner must explicitly bless deletion"). Alternative: repoint to the real `voice_console.html`/`marketing_console.html`.
**Acceptance test:** `tests/test_admin_routes_auth.py::test_archify_demo_pages_are_admin_gated` — unauthenticated `GET /app/archify*` → 401/403. ✅ passing.

### 4.3 — F3 🟠 Resolve the v2 fork drift
**File:** `frontend/customer_dashboard_v2.html` (or retire it)
**Change:** pick ONE of:
- **(a) Retire:** delete `main.py:1826-1839` route + `customer_dashboard_v2.html`; redirect `/app/dashboard-v2` → `/app/customer`.
- **(b) Converge:** make v2 load v1's JS module (extract v1's `loadX()` functions into `frontend/lib/customer_dashboard.js`) and keep v2 as CSS-only.
**Acceptance test:** a parity test that asserts the set of `/api/...` endpoints referenced by v2 ⊇ the required feature set (social, approvals, videos, delivery-proof, profile, routing, kb-info, 2fa, webhooks, studio, crm).

### 4.4 — F8 🟡 Bound the task-ledger query
**File:** `app/admin/services/task_ledger.py` (`list_tasks`), `app/admin/routes/tasks.py:32-39`
**Change:** add `limit: int = Query(50, ge=1, le=500)`, `offset: int = Query(0, ge=0)`; pass through to `list_tasks`; add a pager to the tasks UI.
**Acceptance test:** `GET /admin/api/tasks?limit=10&offset=0` returns ≤10 rows and a `total` count.

### 4.5 — F5 🟡 One admin shell + nav
**File:** `frontend/admin_dashboard.html` (nav), `app/main.py:1842-2198`
**Change:** add every admin dashboard to `admin_dashboard.html`'s nav (currently 16 links); convert `/app/command-center` (already a 307 → owner-command-center, `main.py:2054-2058`) into the canonical entry; make `control_center_graph.html`, `dashboards.html`, `video_command_center.html` reachable or remove.
**Acceptance test:** nav-coverage test — every `/app/<admin-page>` route appears in ≥1 nav.

### 4.6 — F7 🟡 Unify page-route auth
**File:** `app/main.py:1842-2165`
**Change:** decide the model. Recommended: add a shared `Depends(require_admin)` to admin/owner **shells** (`/app/admin`, `/app/owner`, `/app/owner-command-center`, `/app/delivery-command-center`, `/app/admin/video`, `/app/admin/db`) to match `bot_command_center_page` (`bot_command_center.py:142-145`). Customer shells stay client-token (public marketing landing).
**Acceptance test:** unauthenticated `GET /app/admin` → 401/403 (or 302 to login).

### 4.7 — F9 🟢 Remove redundant `client_id=`
**File:** `frontend/customer_dashboard.html:4193,4195,4197,4332-4336` (billing fetches)
**Change:** drop `?client_id=` on customer-side calls.
**Acceptance test:** billing calls still 200 for a customer JWT with no query param.

### 4.8 — F4 🟢 Delete orphan templates
**Files:** `frontend/admin_command_center.html`, `frontend/owner_dashboard.html`, `frontend/autonomous_mission_control.html`, `frontend/archify_landing.html`
**Change:** delete (verify no dynamic `FileResponse(f"...{var}...")` references first — grep showed none).
**Acceptance test:** boot smoke test still green; `grep -rn "<name>" app/` = 0.

---

## 5. Duplication map (what to merge / what to delete)

| Cluster | Files | Action |
|---|---|---|
| **Fabricated "console" demos** | `archify_customer.html`, `archify_marketing.html`, `archify_console_home.html`, `seed-customer.js`, `seed-marketing.js` | **DELETE** (or wire to real `/api/consoles/*`). Real counterparts: `voice_console.html`, `marketing_console.html`. |
| **Orphan templates** | `admin_command_center.html`, `owner_dashboard.html`, `autonomous_mission_control.html`, `archify_landing.html` | **DELETE** — 0 refs in `app/`. |
| **Customer dashboard forks** | `customer_dashboard.html` (v1, ~37 eps), `customer_dashboard_v2.html` (v2, 5 eps) | **MERGE** → single dashboard (F3). |
| **Admin/owner dashboards** | `admin_dashboard.html`, `owner_os.html`, `owner_command_center.html`, `delivery_command_center.html`, `control_center.html`, `control_center_graph.html`, `video_command_center.html`, `dashboards.html`, `admin_db.html` | **CONSOLIDATE** into 1 shell + tabs (F5). Keep `admin_db.html` (distinct tool). |
| **Admin backend modules** | `admin.py` (user mgmt), `admin_dashboard.py` (dashboard), `admin_ops.py` (campaign/system), `admin_dashboard_builders.py`, `admin_dashboard_models.py` | **KEEP** — clean split, not duplication. |
| **Admin Command Center mount** | `app/admin/main.py` | **KEEP** — already de-duplicated (the double-mount was removed; see note `main.py:1280-1286`). |

**Total deletable files after fixes: ~9 templates + 2 seed scripts.**

---

## 6. Fabricated-metric verdict (section C — the truth problem)

**Verdict: the previously-fabricated workforce telemetry has been correctly neutralised — BUT a fabricated-data surface still ships (F2).**

| Claim (from brief) | Verified reality | Evidence |
|---|---|---|
| `data/workforce_live_status.json` claims untrustworthy until `task_execution_verified=true` | **Correct & now inert.** File reads `status:"NOT_INSTRUMENTED"`, `task_execution_verified:false`, `evidence_kind:"inference_probe_only"`, with a self-documenting `note` that the old orchestrator "generated FAKE telemetry". | `data/workforce_live_status.json` (read) |
| Dashboard must not surface it as live | **Truth gate present.** `admin_dashboard.py:1514-1533` forces `NOT_INSTRUMENTED`/zeros when `evidence_kind=="inference_probe_only"`; identical gate in `owner_command_center.py:90-105`; `POST /workforce-trigger` now returns `ok:false` ("synthetic orchestrator is inert", `admin_dashboard.py:1539-1551`). | CODE-PRESENT |
| `revenue_attribution.jsonl` is NOT money | **Correct.** Rows are `event/amount_inr:0` touches. Real revenue path = `gst_invoice` (`growth_revenue.py:109-157`). Command-center MRR is **invoice-backed** via `_has_paid_evidence` (`admin_dashboard_builders.py:104`, comment L389-392: "A selected plan is not a payment"). | CODE-PRESENT |
| Old orchestrator emitted 277,528 actions / 31× LOCAL_ACTIVE | **Correct & neutralised** — no live tile reads it as truth (truth gates above). `app/models/dev_worker.py:9` bans the file. | CODE-PRESENT |
| **New risk** | **`/app/archify/*` serves hardcoded fake customer KPIs with zero API wiring, unauthenticated** → **F2**. This is the one live fabricated-metric surface. | CODE-PRESENT |

**No P0 fabricated metric was found on the primary admin/customer tiles** (truth gates hold). **F2 is the fabricated-data finding to fix.**

---

## 7. Route / page inventory (appendix)

**Admin page routes** (`app/main.py`): `/app/admin`(1842), `/app/admin/db`(1851), `/app/impersonate`(1858), `/app/owner`(1876), `/app/command-center`→307(2054), `/app/owner-command-center`(2061), `/app/delivery-command-center`(2067), `/app/admin/video`(2073), `/app/dev-control`(2080), `/app/control-center`(2175), `/app/control-center/graph`(2182), `/app/dashboards`(2097), `/app/ops`(1678), `/app/brain`(1691), `/app/team`(1870), `/app/team-access`(1685), `/app/office`(1882), `/app/agent-tools`(2106), `/app/coordination`(2168), `/app/explorer`(2162), `/app/bot-command-center`(`bot_command_center.py:142`, **gated**).

**Customer page routes:** `/app/customer`(1795), `/app/customer/marketing`(1808), `/app/customer/voice`(1820), `/app/dashboard-v2`(1826), `/app/customer/office`(1903), `/app/customer/pipeline`(1723), `/app/customer/flows`(1814), `/app/plugins`(1802), `/app/voice-console`(`product_consoles.py:653`), `/app/marketing-console`(661), `/app/archify*`(669-690).

**Admin API routers & gating (source-resolved):**

| Router file | Routes | Gated | Notes |
|---|---|---|---|
| `app/api/admin_dashboard.py` | 28 | 28 ✅ | `/api/admin/*` |
| `app/api/admin_ops.py` | 31 | 31 ✅ | campaign/system/upi/trust |
| `app/api/owner_os.py` | 37 | 37 ✅ | `/api/admin/owner-os/*` |
| `app/api/admin.py` | 19 | 11 ✅ + 8 self-service | login/2fa/me via `get_current_user` — correct |
| `app/api/clientops.py` | 38 | 36 ✅ + 2 public tokens | `/approve/{token}`, `/p/{token}` — intentional |
| `app/api/customer_dashboard.py` | 40 | 39 ✅ + `/health` | — |
| `app/api/product_consoles.py` | 26 | 14 API ✅ + 12 static | static CSS/JS/HTML |
| **`app/admin/routes/tasks.py`** | **8** | **0 ❌** | **F1** |
| `app/admin/routes/docker.py` | 9 | 9 ✅ | — |
| `app/admin/routes/workers.py` | 5 | 5 ✅ | — |
| `app/admin/routes/system.py` | 3 | 3 ✅ | — |

**Dead wiring:** none confirmed. A representative cross-check of `admin_dashboard.html` refs (`/audit-logs`, `/activity-feed`, `/clients/bulk-email`, `/customers/onboard`, `/mcp/health`, `/system/summary`, `/upi/*`, `/trust/configure-*`, `/flow/seed-templates`, `/bot-command-center`) resolved to real handlers. (Automated full check blocked by include-time prefix composition — `UNKNOWN` beyond the sampled set.)

---

## 8. Conclusion

**Request Changes.** One 🔴 CRITICAL auth gap (F1) must be fixed before any dashboard work; three 🟠 HIGH items (fabricated archify surface F2, v2 fork drift F3, orphan templates F4) are cheap and mechanical. Tenant isolation is **clean** (no confirmed data leak). The truth-gate work already done on workforce/revenue is solid — the remaining fabrication risk is the archify demo pages. The implementation spec (§4) is ordered so F1 → F2 → F3 → F4 can be executed mechanically with the listed acceptance tests.

**Recommended sequence:** F1 (security, today) → F2 + F4 (delete, low-risk) → F3 (fork convergence) → F5/F7 (IA + auth consistency) → F8/F9 (polish).

---

## 9. Fix status — task #6 (2026-09-14)

### 9.1 F1 — FIXED & PROVEN
**Change:** `app/admin/routes/tasks.py:36` → `router = APIRouter(dependencies=[Depends(require_admin)])` (+ `Depends` import, + `from app.api.auth_deps import require_admin`). Endpoint bodies untouched. 10 insertions / 3 deletions.
**Proof (runtime, not assumed):**
```
tasks routes: 8  deps: ['require_admin']          # router-level dependency resolves to require_admin
GET /admin/api/tasks          (no auth) → 401
GET /admin/api/tasks/kanban   (no auth) → 401
GET /admin/api/tasks/duplicates?title=x (no auth) → 401
GET /admin/api/tasks/worker/pilot (no auth) → 401
```
(The composed `admin_router` is mounted into a real `FastAPI` app; unauthenticated calls are rejected before any handler runs.)

### 9.2 Regression guard — `tests/test_admin_routes_auth.py` (NEW, 325 lines / 13,478 bytes, 9 tests, all passing)
Structural (AST, not grep):
- Every module in `app/admin/routes/*.py` with routes must be auth-bearing (router-level dep **or** per-endpoint dep).
- Every sub-router included by `app/admin/main.py` must be auth-bearing (a future unprotected `include_router(...)` fails the suite).
- Negative controls: the pre-fix shape of `tasks.py` is **rejected**; a comment merely mentioning `require_admin` does **not** satisfy the check (proves the guard has teeth).
- Runtime: the composed Admin Command Center router rejects unauthenticated `/admin/api/tasks*`; the archify demo pages reject unauthenticated access.

### 9.3 Test evidence
```
tests/test_admin_routes_auth.py                                 9 passed in 0.32s      (RC=0)
tests/test_admin_routes_auth.py + test_admin_modules.py
  + test_admin_command_center.py                               77 passed in 154.21s   (RC=0)
```
`tests/test_ci_required_lanes.py` has 4 failures — **unrelated to this change**: that file is already modified in the working tree by another teammate (in-flight CI-harness work), references **0** of my files, and reads only `.github/**` + `action.yml`.

### 9.4 Duplicate verdict — `/admin/api/tasks` vs `/api/dev-tasks/*`
**NOT a duplicate.** They are unrelated domains that merely share the word "task":
| | `/admin/api/tasks` (Task Ledger) | `/api/dev-tasks/*` (Dev Control) |
|---|---|---|
| Purpose | Worker task-assignment board — assign/kanban tasks to 13 Hermes workers | Engineering/deploy control plane — draft-safe, governor reviews, deploy gate, model routing |
| Backing store | `app/admin/services/task_ledger.py` (SQLite) | `app/models/dev_task.DevTask` (DB) + `app.dev_control.*` |
| Auth | `require_admin` (was none — F1) | `require_admin` |
| Live? | HTTP router: **dead** (0 consumers). Service: **live** (read by `app/api/owner_command_center.py:197-200` for the Owner Command Center). | Live (`app/main.py:1437`) |

**Recommendation:** keep the router now that it is authenticated — it is harmless and may be the intended future UI. **Deletion is an owner decision** (a dead-but-authenticated endpoint is not a code-reviewer's call). The genuine duplication the owner asked about is elsewhere: the **8+ overlapping admin/owner dashboards** (F5) and the **archify-demo vs real-console** pair (F6).

### 9.5 Files touched this turn (no commit/push/deploy)
- `app/admin/routes/tasks.py` — F1 fix (10+/3-).
- `app/api/product_consoles.py` — F2 admin-gate on 3 archify routes (+1 import).
- `tests/test_admin_routes_auth.py` — NEW regression guard.
- this deliverable — corrected F1 citations, zero-caller fact, fix status, duplicate verdict.
