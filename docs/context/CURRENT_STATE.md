# CURRENT_STATE — LeadGen AI (operational truth)

> Evidence labels: PRODUCTION-PROVEN · CODE-PRESENT · TEST-PROVEN · LOCAL-ONLY · PARTIAL · STALE · UNKNOWN

## Last verified timestamp
2026-07-20T05:45Z (UEOS committed; WS-2 inventory LOCAL+TEST; prod health probed)

## Local HEAD
Branch `chore/ueos-adr-129` @ `4966cfe` (+ uncommitted WS-2 inventory surface)
Label: CODE-PRESENT

## Origin/main
`ef5e8b4` (approval remediation) — cherry-picked onto branch as `4966cfe`
Label: CODE-PRESENT

## Production SHA
`22fa97ca` — PRODUCTION-PROVEN (`/health`)
Label: PRODUCTION-PROVEN

## Repository cleanliness
DIRTY: WS-2 inventory files uncommitted · `data/delivery_ledger/jiya-makeover.jsonl` (exclude) · UEOS+cherry-pick committed on feature branch (not pushed)

## Production status
healthy · production · delivery-assurance 401 · new approval-remediation routes 404 until deploy

## Paying customers
1 — Jiya Makeover · `jiya-makeover` · billing alias `d79d690f61b3` (local store missing billing_client_ids)

## Working customer workflows
- Identity canonicalize — PRODUCTION-PROVEN (prod); LOCAL clients store alias link MISSING
- Delivery assurance API — PRODUCTION-PROVEN
- Approval remediation plan/inventory — TEST-PROVEN + LOCAL-ONLY baseline; NOT on prod yet

## Broken / incomplete customer workflows
- Jiya `proof` — 9 local pending approvals + Meta not connected → recovery approve_and/or_meta_connect (EXTERNAL/human)

## Top 3 next actions
1. Commit+PR WS-2 inventory slice on `chore/ueos-adr-129` (user ask)
2. Deploy → authenticated prod GET `/api/admin/approval-remediation/client/jiya-makeover`
3. Human: approve Jiya drafts and/or Meta customer-page connect
