# ACTIVE_WORK — max 3 workstreams

---

## WS-1 Delivery assurance operator surface — CLOSED (PARTIAL proof)
- **ID:** WS-1
- **Business outcome:** Admin can see missed/at-risk paid customers
- **Owner:** Delivery Ops / nikhil attribution
- **Branch:** merged via PR #59 → `d625e48` on main; live under prod SHA (re-probe)
- **Current state:** MERGED + DEPLOYED historically. Authenticated browser KPI click NOT proven → PARTIAL.
- **Next exact action:** none for WS-1 impl — optional admin UI smoke

---

## WS-2 Jiya delivery assurance proof and operator recovery flow — ACTIVE
- **ID:** WS-2
- **Business outcome:** Paying customer Jiya reaches honest `proof` / recoverable delivery gaps without fake completion
- **Exact observed gap:** Delivery ~90%; `proof` HONEST-blocked (Meta customer-page Advanced Access and/or pending approvals).
- **Owner:** Human operator + content/approval path (Zara gated) + coding agents for inventory/remediation tools
- **Branch:** `chore/ueos-adr-129` (UEOS `439e8b6` + cherry-pick `4966cfe` + uncommitted inventory admin surface)
- **Allowed files:** approval_remediation, content_approval read paths, admin_dashboard approval-remediation routes, automation_flags, tests — no Swara/voice
- **Protected files:** ALL Swara/voice/telephony/STT/TTS/VAD/SIP/WebSocket/call/recording; no ledger forge; no publish
- **Acceptance criteria:**
  - Read-only baseline of Jiya deliverables + assurance item documented ✅ LOCAL (see SESSION_HANDOFF)
  - Chosen recovery path executed with ledger evidence — PENDING (human approve OR Meta connect)
  - `proof` done OR explicit EXTERNAL blocker residual with evidence — EXTERNAL still likely
  - No cross-tenant leakage; no fabricated publish
- **Safe test-data strategy:** Hermetic tests + local read-only inventory; no APPROVAL_REMEDIATION execute on prod without user flag+confirm
- **Dependencies:** Meta Advanced Access for customer pages OR customer approval of `approval_pending`
- **Current state:** ACTIVE — inventory API+helper implemented (uncommitted); local baseline captured
- **Local baseline (2026-07-20, read-only):**
  - `plan_remediation`: total_stuck=104, expire_inactive=86, escalate_active=18
  - `client_inventory(jiya-makeover)`: stuck_count=9 all `pending`, meta_channel.connected=False, recovery=`approve_drafts_and_or_meta_connect`
  - Local `marketing_clients` Jiya record has `billing_client_ids=None` → alias `d79d690f61b3` does NOT resolve locally (prod may differ — verify after deploy)
  - Prod `/health`=`22fa97ca`; new routes 404 until deploy (expected)
- **Next exact action:** Commit WS-2 inventory slice when user asks; deploy after merge; authenticated admin GET client inventory on prod; human choose approve-drafts vs Meta connect
- **Next exact command:** (after deploy) admin GET `/api/admin/approval-remediation/client/jiya-makeover`

---

## WS-3 (empty)
Parked LOCAL-ONLY in stash: automation_health ntfy, coordinator rate-cap test, AGENT_24_7 docs.
