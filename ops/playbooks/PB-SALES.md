# PB-SALES — Sales Execution Playbook (P0)

- **Purpose**: Close verified revenue. Every action must move a lead toward
  owner_confirmed_upi with evidence at each step.
- **Trigger**: lead enters pipeline / hot lead surfaces / revenue sprint active.
- **Scope**: prospecting -> qualification -> outreach -> follow-up -> close.
- **Prereqs**: lead eligible (no opt-out, no DND, deduped), channel approved.

## Strategy
1. Hot Queue first: `/app/inbox` + daily 09:00 IST owner pack (CSV+MD+ntfy).
2. Qualification by niche/ICP fit — only qualified leads enter outreach.
3. Outreach via approved channels (WA 1-click human default; email ≤25/day; calling LIVE under gates).
4. Follow-up cadence until reply or 3-touch stop (consent-aware).
5. Close: manual UPI (canonical) -> owner confirms bank credit -> ledger + invoice.

## Decision tree
```
Lead surfaces
├─ opted out / DND?  -> SUPPRESS instantly (RB-SALES-005), no contact
├─ duplicate?        -> dedupe/merge (RB-SALES-004)
├─ high intent?      -> Hot Queue for OWNER 1-click close (RB-SALES-007)
├─ cold but in ICP?  -> nurture (email ≤25/day / call within window)
└─ not in ICP?       -> park (do NOT burn outreach budget)
```

## Allowed actions
- Query Hot Queue, dedupe, suppress opt-outs, log every message, record outcome.
- Email/WA/call via approved, rate-limited, consent-aware rails only.

## Prohibited actions
- Cold/bulk WhatsApp auto-send (ban risk) — 1-click human default.
- Claiming revenue without owner_confirmed_upi + ledger id.
- Contacting opted-out / DND numbers (compliance).

## Escalation
- Hot lead stuck >24h -> owner via Hot Queue pack.
- Conversion blocked by product/pricing -> raise to owner (WS-3 ACV decision).

## KPIs
- Verified collected revenue/day (only confirmed payments).
- Hot Queue close rate; reply rate; qualified lead cost.

## Guardrails
- Rate limits (email 25/day; calls in TRAI window 10-19 IST; concurrency=1 for dialer).
- All automation owner-armed; manual recovery path always available.

## Linked runbooks
RB-SALES-001..007 (WA send / auth / email / dedupe / opt-out / payment / hot lead).

## Evidence requirements
- Every outreach: message id, channel, timestamp, lead id.
- Every close: ledger entry + invoice id + owner confirmation.

## Owner approval conditions
- Revenue counted only after owner confirms bank credit.
- Any new paid acquisition channel.
