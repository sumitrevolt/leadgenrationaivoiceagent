# LeadGen AI — Technical Issues Ledger

> 2026-07-19

| Priority | Area | Problem | Evidence | Root Cause | Required Fix | Status |
|---|---|---|---|---|---|---|
| P1 | Customer deliverability / identity | Billing-alias login saw orphan marketing view; could not approve content; profile save 404; timeline blank | Commit `670f579` report (7 orphan drafts / 10% vs 20 items / 60%); local runtime: content MKT=9 BILL=0 before alias+fix; after fix PARITY OK | ADR-095 split; portal paths used raw JWT id for marketing stores; `_client_record` used `get_client` only | Canonicalize marketing reads/writes via `canonical_client_id` / `resolve_client` at portal boundary | **FIXED locally** (code uncommitted + `670f579`); **NOT on prod** (`5e2ccb9c`) |
| P1 | Deploy lag | Identity + dashboard canonicalization not in production | Prod `/health` version `5e2ccb9c` ≠ local `670f579`+ | Deploy not run this session | Deploy code-only commit; browser UAT Jiya | OPEN |
| P1 | Identity provisioning | `billing_client_ids` never auto-written by activation/UPI — only manual ops `update_client` | Repo-wide grep: writes only in tests + ops repair (ADR-080) | Recreation/repair path is manual | Keep ops SOP; consider activation hook when marketing id ≠ invoice owner id | OPEN (documented) |
| P1 | Billing helper direction | `_billing_client_ids` used `get_client` — billing-alias JWT missed aliases | Code review + new contract test | Assumed JWT always marketing id | Switched to `resolve_client` + include canon | **FIXED locally** (uncommitted) |
| P1 | Voice quality gate | Swara live canary not proven on current prod SHA | SESSION_HANDOFF: no call on prior deploy SHA; platform_dial HARD-OFF | User/telecom gated | Controlled INBOUND canary to company number | OPEN (blocked) |
| P1 | Admin/customer UAT | Browser acceptance needs credentials | SESSION_HANDOFF §2–3 | Credential gated | Operator login checks | OPEN (blocked) |
| P2 | Admin surfaces | Multiple overlapping command centers | Routes under `/app/admin`, `/office`, `/owner`, `/control-center`, … | Organic growth; HQ intended at `/app/office` | Consolidate nav + shared live-data after delivery truth | BACKLOG |
| P2 | OmniRoute on VPS | Agent OmniRoute path inert in production | ADR-108: gateway not reachable from containers | Infra | Deploy/tunnel OmniRoute then flip double gate | BACKLOG |
| P3 | Test env default | `test_voice_gemini_primary_flag` unset-default mismatch | SESSION_HANDOFF | Env default vs test | Align default or test | BACKLOG |
| — | Billing invoices | Synthetic INV/0002–0013 voided; INV/0001 active | SESSION_HANDOFF | Ops plan C | Do not reopen | DONE (do not touch) |
