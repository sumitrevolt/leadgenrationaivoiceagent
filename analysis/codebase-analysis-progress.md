# LeadGen AI — Persistent Execution Ledger

> Updated: 2026-07-19 ~20:40 IST. No secrets. Evidence-backed production closure.

## Project coordinates

| Item | Value |
|---|---|
| Local repository | `C:\Users\Ratanshila\Documents\leadgenrationaiagent` |
| Git remote | `https://github.com/sumitrevolt/leadgenrationaivoiceagent.git` |
| Primary branch | `main` |
| Production domain | `https://leadsgenai.in` |
| VPS app dir | `/opt/leadgen` |
| Compose file | `docker-compose.vps.yml` |
| Real customer | Jiya Makeover Studio · `jiya-makeover` · Starter ₹1,999 |
| Billing/login alias | `d79d690f61b3` (in `billing_client_ids`) |

## Current verified baseline

| Check | Result |
|---|---|
| Local / origin `main` tip (this write) | `716bed8` — includes portal + recurrence commits |
| Portal identity commit | **`dbc4c86`** `fix(portal): canonicalize billing and marketing client identity` |
| Recurrence-prevention commit | **`e845243`** `fix(identity): auto-link billing aliases on plan activation` |
| Previous production SHA (session start) | `5e2ccb9c` → later `670f5793` → `ca98ece4` → **`dbc4c864`** (our deploy) → now **`716bed84`** |
| Current production `/health` | `healthy`, version **`716bed84`**, environment=`production` |
| Working tree | Local verification-only data still dirty (`data/marketing_clients.jsonl`, `data/delivery_ledger/jiya-makeover.jsonl`) — **never committed**. Unrelated WIP may exist in other files — leave alone. |
| `platform_dial` | `enabled: false` (HARD-OFF preserved) |
| Queues (post `dbc4c864` deploy) | celery=0, dlq:failed=0, dlq:dead=0 |

## Files included in portal commit `dbc4c86`

- `app/api/billing.py`
- `app/api/customer_dashboard.py`
- `app/api/customer_dashboard_builders.py`
- `app/api/customer_marketing_studio.py`
- `tests/test_billing_alias_resolution.py`
- `tests/test_client_identity_canonicalization_2026.py`
- `analysis/*` (overview, architecture, technical-issues, this ledger)

## Files explicitly excluded

- `data/marketing_clients.jsonl`
- `data/delivery_ledger/jiya-makeover.jsonl`
- `.env*`, credentials, runtime artifacts, probe scripts

## Files included in recurrence commit `e845243`

- `app/marketing/clients_store.py` (`link_billing_alias`)
- `app/marketing/delivery_ledger.py` (`identity_alias_linked` event)
- `app/billing/usage.py` (`activate_plan` resolve + link)
- `app/api/admin_ops.py` (`billing_client_id` on UPI activate)
- `tests/test_link_billing_alias_2026.py`
- `scripts/report_billing_alias_gaps.py` (read-only dry-run)

## Tests and release gates (pre-commit `dbc4c86`)

- Identity + billing alias + delivery + plan-delivery: **43 passed**
- Tenant isolation (`test_customer_tenant_isolation_authenticated` + `test_phase3_billing_tenant`): **26 passed**
- `scripts/check_secrets.py`: **OK**
- `scripts/prod_check.py`: **ALL CHECKS PASSED** (1155 routes)
- `py_compile` on changed files: **OK**
- Recurrence suite `test_link_billing_alias_2026.py`: **8 passed**

## Deployment

| Step | Evidence |
|---|---|
| Command | `cd /opt/leadgen && setsid nohup bash scripts/deploy_vps.sh dbc4c86 > /tmp/dep_dbc4c86.log` |
| Result | `=== DEPLOYED dbc4c864 OK ===` |
| Rollback target at deploy time | `ca98ece4` (prior live image) |
| All 5 app-image services | `APP_VERSION=dbc4c864` (app/worker/scheduler/worker_heavy/worker_video) — no skew |
| Smoke | `/health` `/api/voice/niches` `/api/billing/plans` `/api/public/pay-info` → 200 |
| Later tip | Production advanced to **`716bed84`** (poster-pack deploy) which **contains** `dbc4c86` + `e845243` |

## Production functional verification (Jiya)

### Portal parity (both identities) — `PARITY_OK` on live app container

| Metric | Billing id `d79d690f61b3` | Marketing id `jiya-makeover` |
|---|---|---|
| `canonical_client_id` | `jiya-makeover` | `jiya-makeover` |
| `_client_record().id` / plan | `jiya-makeover` / starter | same |
| Content posts | 26 (later recheck; was 24 on `dbc4c864`) | 26 |
| Approval banner count | 7 | 7 |
| Delivery % / generated / waiting | 90 / 26 / 7 | 90 / 26 / 7 |
| `_billing_client_ids` set | `{d79d…, jiya-makeover}` | same set |

Invariant: **equality across identities** (counts may grow with real activity).

### Approval workflow

- Raw billing id `decide_for_client` → `ok=False` (`approval nahi mila`) — ownership gate intact
- Unrelated tenant → `ok=False`
- `_by_id_for_client(marketing)` True; raw billing False; canon(billing) True
- **Mutation skipped** — approving a real draft can enqueue publish; not performed. Reason recorded.

### Billing isolation

- Jiya invoice set via alias resolution: **1 active**, **0 voided payable**
- Active number: **`INV/2026-27/0001`** only
- Billing id sets equal for both JWT directions

### Negative tenant isolation

- Unknown tenant `_client_record` → None
- Other-tenant pending does not include Jiya
- Cross-tenant decide refused

## Recurrence prevention

| Field | Detail |
|---|---|
| Root cause | `billing_client_ids` was ops-manual only (ADR-080 repair). Recreation/activation could diverge marketing vs invoice owner again. |
| Implemented | `link_billing_alias` (idempotent, conflict-safe, audit event). `activate_plan` resolves marketing id + links activation id. UPI activate optional `billing_client_id`. Dry-run `scripts/report_billing_alias_gaps.py` (email-unique suggestions only; no bulk mutate). |
| Status | **Committed `e845243`, present on prod `716bed84`** (`def link_billing_alias` verified in container). |
| Bulk backfill | **Not executed** (requires explicit dry-run review + execution flag per policy). |

## HTTP-layer UAT (2026-07-19, prod container, read-only)

Method: short-lived customer JWT minted in-container for billing alias `d79d690f61b3`
(same shape as real login; token never persisted/exposed), real FastAPI endpoints hit
on `localhost:8080`. Script removed from VPS + container after run.

| Endpoint | Status | Evidence |
|---|---|---|
| `GET /api/customer/auth/me` | 200 | `business='Jiya Makeover Studio'` |
| `GET /api/customer/auth/portal/content` | 200 | 10 items, business/niche/summary present |
| `GET /api/customer/auth/portal/invoices` | 200 | exactly 1: `INV/2026-27/0001` |
| `GET /api/customer/dashboard` | 200 | approval_banner/branding/kpis/leads present |
| `GET /api/customer/approvals/pending` | 200 | **7 pending** (matches container proof) |
| `GET /api/customer/timeline` | 200 | 27 events |
| `GET /api/customer/delivery-proof` | 200 | deliverables + completion pct present |
| `GET /api/customer/profile` | 200 | `business='Jiya Makeover Studio'`, approval_preference present |
| `GET /api/customer/office` | 200 | next_best_action/tasks present |

**Verdict: PASS 9/9** — billing-alias JWT sees full canonical marketing view over real HTTP.

### Approve-one-draft: intentionally NOT executed

`content_approval.approve → auto_content.enqueue_approved → social_engine.enqueue_publish`
and prod has `SOCIAL_ENGINE=1` + `data/social_engine.json {"enabled": true, "dry_run": false}`.
Approving = real external publish enqueue. This is a customer-visible business action;
left for Jiya/admin to perform deliberately. (Ownership gates already contract-tested.)

### Alias-gaps dry-run (prod): `orphan_billing_ids=0` — no unlinked invoice owners exist.

## Active work

- None for identity deliverability — **production-closed + HTTP-layer UAT passed**.

## Backlog

### P1 (remaining, external-gated)
1. Swara controlled **inbound** canary (telecom/user) — `platform_dial` stays OFF
2. Jiya portal **visual/browser** UAT (needs real credentials/OTP; API layer already verified)
3. First real draft approval — deliberate business action (social_engine live, will publish)

### P2
- Unified admin command surface consolidation
- OmniRoute VPS gateway

## Architecture map (unchanged essence)

Marketing domain must use `canonical_client_id` / `resolve_client`. Billing domain uses `_billing_client_ids` / raw invoice owner ids. Never mix invoice ownership onto marketing id.
