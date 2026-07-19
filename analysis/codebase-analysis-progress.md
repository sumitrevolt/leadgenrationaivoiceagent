# LeadGen AI — Persistent Execution Ledger

> Updated: 2026-07-19 ~19:15 IST. No secrets. Evidence-backed.

## Project coordinates

| Item | Value |
|---|---|
| Local repository | `C:\Users\Ratanshila\Documents\leadgenrationaiagent` |
| Git remote | `https://github.com/sumitrevolt/leadgenrationaivoiceagent.git` |
| Primary branch | `main` |
| Production domain | `https://leadsgenai.in` |
| VPS app dir | `/opt/leadgen` |
| Compose file | `docker-compose.vps.yml` |
| Real customer (read-only / reversible ops) | Jiya Makeover Studio · tenant `jiya-makeover` · plan Starter ₹1,999 |
| Billing/login alias | `d79d690f61b3` (carried in marketing record `billing_client_ids`) |

## Current verified baseline

| Check | Result |
|---|---|
| Local HEAD (pre-session WIP commit) | `670f579` — `fix(delivery/identity): canonicalize billing/login id -> marketing id for customer portal + delivery status` |
| Origin/main relation (session start) | 0 ahead / 0 behind of `origin/main` at discovery; HEAD later advanced locally to `670f579` when WIP was committed mid-session |
| Working tree (this session) | Modified (uncommitted): `app/api/customer_dashboard.py`, `app/api/customer_dashboard_builders.py`, `app/api/customer_marketing_studio.py`, `tests/test_client_identity_canonicalization_2026.py` (extended). Local data only (do **not** commit): `data/marketing_clients.jsonl` (alias seed), `data/delivery_ledger/jiya-makeover.jsonl` (side-effect of delivery_status) |
| Production `/health` | `healthy`, version **`5e2ccb9c`**, uptime ~1h18m (2026-07-19 13:41 UTC). **Does NOT yet include** `670f579` or this session's dashboard/approval canonicalization |
| Known open blockers | (1) Production not on identity-fix SHAs yet. (2) Controlled Swara inbound canary still user-gated (SESSION_HANDOFF). (3) Admin/customer browser UAT needs credentials. (4) `platform_dial` HARD-OFF intact — do not re-enable. |
| Feature flags of note | `platform_dial=false` (HARD-OFF). OmniRoute agent flags OFF on VPS (gateway reachability). |

## Architecture map (concise)

```
Customer JWT (role=customer, sub=client_id)
        │
        ├─ BILLING domain (raw login / billing id)
        │    invoices · subscriptions · CallLog · Lead.assigned_to
        │    → app/api/billing.py already resolves aliases via _billing_client_ids (ADR-106)
        │
        └─ MARKETING domain (canonical marketing id)
             clients_store · auto_content queue · content_approval · brand_kit · delivery_ledger
             → MUST canonicalize via clients_store.canonical_client_id / resolve_client
```

- **Entry points:** FastAPI app routers under `app/api/`; Celery workers + scheduler; customer portal HTML under `frontend/`; admin surfaces under `/app/office` (Operating HQ — authoritative per SESSION_HANDOFF).
- **Identity primitives:** `app/marketing/clients_store.py` → `resolve_client`, `canonical_client_id` (alias via `billing_client_ids`).
- **Customer portal:** `customer_auth.py`, `customer_dashboard.py` + `_builders`, `customer_marketing_studio.py`.
- **Delivery truth:** `product_one_delivery.customer_delivery_status` + `delivery_ledger`.
- **Billing:** GST invoices + subscription tables; alias-aware since ADR-106.
- **Voice:** Swara path; outbound dial HARD-OFF.
- **OmniRoute:** installed; agent traffic double-gated OFF on VPS.

## Completed work (this session)

### P1 — Customer portal identity split (billing login ↔ marketing content)

| Field | Detail |
|---|---|
| **Problem** | UPI-activated customer (Jiya) logging in with billing id `d79d690f61b3` saw orphaned / partial marketing views; approvals pending were invisible; **approve/reject mutation failed ownership** (`approval nahi mila`); profile wizard `update_client(alias)` → 404; timeline blank. |
| **Root cause** | ADR-095 identity split: marketing pipeline keys on `jiya-makeover`; login/JWT can carry billing id. Partial fix in `670f579` covered `/me`, `/portal/content`, `customer_delivery_status` only. Dashboard keystone `_client_record` still used `get_client` (no alias). Approval decide/pending/banner/profile/timeline/studio still used raw id. |
| **Expected** | Billing-alias login sees same marketing content, plan, approvals, delivery % as marketing-id login; can approve own posts; profile save works. Billing/invoices stay on raw id. |
| **Actual (before)** | Local proof: content under MKT=9, under BILL=0; `canonical(BILL)` fell back to raw when alias missing; with alias + old `_client_record` → None / 0 posts / banner false. |
| **Files changed (this session, uncommitted)** | `app/api/customer_dashboard_builders.py` (`_client_record` → `resolve_client`; approval banner; brand tone; office approvals). `app/api/customer_dashboard.py` (profile get/set, branded-feed, timeline, delivery-proof, approvals pending/decide, council-decide). `app/api/customer_marketing_studio.py` (NBA + daily brief pending counts). `tests/test_client_identity_canonicalization_2026.py` (7 contract tests). |
| **Already on HEAD `670f579`** | `app/api/customer_auth.py` (`_marketing_cid`), `app/marketing/product_one_delivery.py` (canonicalize at entry), original 3 identity tests. |
| **Tests executed** | `tests/test_client_identity_canonicalization_2026.py` → **7 passed**. Bundle with `test_billing_alias_resolution.py` + `test_customer_delivery_2026_07_05.py` → **33 passed**. |
| **Runtime verification (local, reversible)** | Seeded `billing_client_ids=['d79d690f61b3']` on `jiya-makeover` via `clients_store.update_client` (matches production truth per ADR-106 / commit message). After seed + code: `canonical(BILL)=jiya-makeover`, `content_posts(BILL)=9`, `banner=True count=9`, `delivery(BILL)` name/plan/content_generated/posts_waiting **identical** to `delivery(MKT)` (deliverable_pct=40). Assertion `PARITY OK` printed. |
| **Commit SHA** | Not committed this session (await clean commit of code-only files; do not commit `data/*`). Base WIP: `670f579`. |
| **Deployment status** | **NOT deployed.** Prod still on `5e2ccb9c`. |
| **Remaining risks** | (1) Prod marketing record must retain `billing_client_ids` (ADR-106 said it does). (2) Any remaining customer-facing marketing call site that bypasses `_client_record` / explicit canonicalize. (3) Local auth store still keys Jiya login as `jiya-makeover` (stale vs prod claim of billing-id login) — code is correct for both. (4) Mid-session file reverts observed — verify diffs before commit. |

### P1 — Billing alias helper bidirectional (ADR-106 harden)

| Field | Detail |
|---|---|
| **Problem** | `_billing_client_ids` used `get_client` only — billing-alias JWT never loaded the marketing record's alias list (only `[billing_id]`). |
| **Root cause** | Helper assumed JWT is always marketing id (ADR-106 era). |
| **Fix** | Use `resolve_client`; include canon id + aliases; dedup unchanged. |
| **Files** | `app/api/billing.py`, `tests/test_billing_alias_resolution.py` (+ new `test_billing_alias_jwt_also_resolves_both_ids`) |
| **Tests** | Billing alias suite green inside 38-test bundle |
| **Deploy** | Not deployed |

### Additional portal sites canonicalized (same session)

- `POST /campaigns/generate-first-week` — resolve + seed under marketing id
- `GET /social/config` + readiness checks — resolve marketing socials; social_config/vault try mcid then raw
- Studio mini-site customize — resolve + `update_client(mcid)`

## Active work

- **Current selected task:** Identity canonicalization gap — **DONE locally**; awaiting commit + deploy.
- **Why highest-value:** Real ₹1,999 customer deliverability under billing-alias login.
- **Next concrete step:** Commit **code-only** files (exclude `data/*` and do not commit secrets). Suggested paths:
  - `app/api/customer_dashboard.py`
  - `app/api/customer_dashboard_builders.py`
  - `app/api/customer_marketing_studio.py`
  - `app/api/billing.py`
  - `tests/test_client_identity_canonicalization_2026.py`
  - `tests/test_billing_alias_resolution.py`
  - `analysis/*` (optional docs)
  - Then deploy to VPS; browser-verify Jiya portal.

## Backlog (prioritized)

### P0
- None newly proven this session (prod healthy on `5e2ccb9c`).

### P1
1. **Deploy identity canonicalization** (`670f579` + this session's dashboard/approval/profile/timeline fixes) to production; browser-verify Jiya portal content + approve one draft (tenant-scoped).
2. **Swara controlled inbound canary** on deployed SHA (SESSION_HANDOFF — user/telecom gated; `platform_dial` stays OFF).
3. **Admin HQ browser UAT** — canary call recording/transcript + billing shows only INV/0001.
4. **Audit remaining customer marketing call sites** for raw-id usage (studio deeper paths, any new endpoints).

### P2
- Unified admin command surface consolidation (Priority A) — after customer delivery truth is solid on prod.
- Scheduler/queue last-run observability consistency (Priority C).
- OmniRoute VPS gateway reachability (blocked on infra).

### P3
- Polish / optional Unity virtual-office paths.
- Align `test_voice_gemini_primary_flag` default (non-blocking env artifact).

## Session notes

- Mid-session, uncommitted WIP on `customer_auth.py` + `product_one_delivery.py` was committed externally as `670f579` while this agent was tracing — extended the incomplete fix rather than duplicating.
- Do **not** reopen billing void/active invoice work (SESSION_HANDOFF: DONE).
- Do **not** re-enable `platform_dial` outbound.
