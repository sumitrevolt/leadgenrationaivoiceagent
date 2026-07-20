# ACTIVE_WORK — max 3 workstreams

---

## WS-1 Delivery assurance operator surface — CLOSED (PARTIAL proof)
- **ID:** WS-1
- **Business outcome:** Admin can see missed/at-risk paid customers
- **Owner:** Delivery Ops / nikhil attribution
- **Branch:** merged via PR #59 → `d625e48` on main; live under `d32a4934`
- **Current state:** MERGED + DEPLOYED. Authenticated browser KPI click NOT proven → treat proof as PARTIAL; API/scan PRODUCTION-PROVEN.
- **Next exact action:** none for WS-1 impl — optional admin UI smoke
- **Next exact command:** (optional) open Delivery Command Center with admin token; confirm At Risk reflects assurance

---

## WS-2 Jiya delivery assurance proof and operator recovery flow
- **ID:** WS-2
- **Business outcome:** Paying customer Jiya reaches honest `proof` / recoverable delivery gaps without fake completion
- **Exact observed gap:** Delivery ~90%; `proof` HONEST-blocked (Meta customer-page Advanced Access and/or pending approvals). Assurance shows at_risk for paid client without mutating records.
- **Owner:** Human operator + content/approval path (Zara gated)
- **Branch or worktree:** TBD when started (new branch from main)
- **Allowed files:** content approval, social publish handoff, delivery ledger read paths, admin recovery actions already exposed — only when workstream activated
- **Protected files:** ALL Swara/voice/telephony/STT/TTS/VAD/SIP/WebSocket/call/recording
- **Acceptance criteria:**
  - Read-only baseline of Jiya deliverables + assurance item documented
  - Chosen recovery path (customer approve drafts OR Meta connect OR admin manual-publish proof) executed with ledger evidence
  - `proof` done OR explicit EXTERNAL blocker residual with evidence
  - No cross-tenant leakage; no fabricated publish
- **Safe test-data strategy:** Prefer real Jiya drafts already in queue; no synthetic paid customers; no ledger forge
- **Dependencies:** Meta Advanced Access for customer pages OR customer approval of `approval_pending`
- **Current state:** DEFINED ONLY — do not implement until WS-1 closed session ends and no open prod fire
- **Next exact action:** Inventory Jiya `approval_pending` + channel connect status (read-only)
- **Next exact command:** `curl.exe -sS https://leadsgenai.in/health` then admin portal approvals for `jiya-makeover` (human)

---

## WS-3 (empty)
Parked LOCAL-ONLY in stash: automation_health ntfy, coordinator rate-cap test, AGENT_24_7 docs.
