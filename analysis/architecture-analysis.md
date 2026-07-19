# LeadGen AI — Architecture Analysis

> 2026-07-19 · focused on identity + delivery boundaries

## Component map

- **Customer portal:** JWT `role=customer`, `sub=client_id` → dashboard, content, approvals, profile, timeline, invoices
- **Admin / Operating HQ:** `/app/office` (authoritative ops surface) + legacy/overlapping admin routes
- **API:** FastAPI routers in `app/api/`
- **Workers:** Celery + Redis queues (celery / heavy / video + DLQ)
- **Marketing domain:** `clients_store`, `auto_content`, `content_approval`, `brand_kit`, `delivery_ledger`
- **Billing / DB domain:** Subscription, Invoice, UsageRecord, Lead, CallLog
- **Voice:** Swara path; `platform_dial` HARD-OFF

## Critical identity boundary (ADR-095 / ADR-106 / 2026-07-19)

| Domain | Authoritative id | Examples |
|---|---|---|
| Marketing | Marketing client id (`jiya-makeover`) | content queue, approvals, brand, ledger, slug |
| Billing / DB | Billing id (`d79d690f61b3`) | invoices, subscriptions, often CallLog/Lead |
| Auth JWT `sub` | Either, depending on login provisioning | Must canonicalize **per domain** |

**Rules:**
- Marketing reads/writes: `clients_store.canonical_client_id(cid)` / `resolve_client(cid)`
- Billing reads: `_billing_client_ids(cid)` (marketing → billing aliases) — ADR-106
- Never mix: do not canonicalize invoice ownership onto marketing id

## Request / event flows (customer delivery)

```
plan entitlement → onboarding → scheduler/worker content gen
  → auto_content queue (marketing id)
  → content_approval.submit (marketing id)
  → customer portal pending/decide (MUST canonicalize login→marketing)
  → publish / ledger event
  → customer_delivery_status / timeline
```

## Known architectural conflicts

1. **Dual id for one customer** — fixed at read/write boundaries for portal; provisioning of `billing_client_ids` must remain reliable.
2. **Multiple admin surfaces** (`/app/admin`, `/office`, `/owner`, `/control-center`, …) — Operating HQ `/app/office` is the intended authority; consolidation is P2 after delivery truth on prod.
3. **OmniRoute installed but VPS-inert** without reachable gateway — intentional fail-open.
4. **Local vs prod data drift** — local `marketing_clients.jsonl` can miss aliases present in production.

## Auth boundaries

- Admin: `require_admin`
- Customer: `require_customer` (JWT role + Redis logout blacklist)
- Object-level: approvals use `_by_id_for_client`; invoices filter by `client_id`; dashboard builders scope inquiries/content by client record
