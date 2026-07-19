# LeadGen AI — Technical Issues Ledger

> 2026-07-19 · post production closure

| Priority | Area | Problem | Evidence | Root Cause | Required Fix | Status |
|---|---|---|---|---|---|---|
| P1 | Customer deliverability / identity | Billing-alias login saw orphan marketing view; could not approve; profile 404; timeline blank | Local + prod parity; approve ownership proofs | ADR-095 split; portal used raw JWT for marketing stores | Canonicalize via `resolve_client` / `canonical_client_id` | **FIXED + DEPLOYED** (`dbc4c86` in prod `716bed84`) |
| P1 | Billing helper direction | `_billing_client_ids` used `get_client` — billing JWT missed aliases | Contract test + prod `billing_ids` both directions | Assumed JWT always marketing id | `resolve_client` + include canon | **FIXED + DEPLOYED** (in `dbc4c86`) |
| P1 | Identity provisioning | `billing_client_ids` manual-only | Repo grep pre-fix | No activation hook | `link_billing_alias` + `activate_plan` + UPI `billing_client_id` + dry-run report | **FIXED + DEPLOYED** (`e845243` in prod `716bed84`); bulk backfill not run |
| P1 | Deploy lag | Identity fix not on prod | Was `5e2ccb9c` | Deploy pending | `deploy_vps.sh dbc4c86` | **RESOLVED** — prod now `716bed84` |
| P1 | Voice quality gate | Swara live canary not proven | SESSION_HANDOFF | User/telecom gated | Controlled INBOUND canary | OPEN (blocked) |
| P1 | Admin/customer UAT | Browser acceptance needs credentials | SESSION_HANDOFF | Credential gated | Operator login checks | OPEN (blocked) |
| P2 | Admin surfaces | Multiple overlapping command centers | Routes under `/app/*` | Organic growth | Consolidate after delivery truth | BACKLOG |
| P2 | OmniRoute on VPS | Agent path inert in production | ADR-108 | Gateway not reachable | Infra then flip gate | BACKLOG |
| — | Billing invoices | INV/0001 active for Jiya | Prod isolation check | Ops plan C | Do not reopen | **VERIFIED** (only INV/0001) |
