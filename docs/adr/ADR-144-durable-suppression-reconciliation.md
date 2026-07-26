# ADR-144 — Durable, restart-recoverable suppression reconciliation

- **Date:** 2026-07-25
- **Status:** ACCEPTED (deferred implementation)
- **Blocks:** `BLOCKS_PRODUCTION_DEPLOYMENT` · `BLOCKS_LIVE_EMAIL_AUTOMATION` · `BLOCKS_LIVE_WHATSAPP_AUTOMATION_WHERE_UNIFIED_SUPPRESSION_APPLIES`
- **Does NOT block:** merging PR #144 to `main`

## Context

PR #144 made the canonical suppression authority real: opt-outs, bounces and
complaints now write `data/email_suppression.jsonl`, and both the scheduler-time
eligibility check and the pre-provider recheck read it fail-closed.

Suppression is written as **two** operations:

1. append the canonical ledger row (load-bearing — blocks sending), then
2. write durable cancellation metadata (terminal prospect status).

A failure between (1) and (2) is reported explicitly as
`SUPPRESSED_NEEDS_RECONCILIATION` rather than as success, and `reconcile_suppressions()`
can repair it. But that repair works by **re-scanning the ledger**, and the
in-process `_last_result` carrier does not survive a restart. There is therefore
no durable record of "this suppression has an incomplete side effect".

## Why deferred rather than built now

The marker store would live in `data/` — the exact directory the runtime-data
separation work is about to relocate outside the Git checkout. Building it now
means building it twice, and the second build would be a migration rather than
an implementation.

## Why this is safe to defer past merge

The safety-critical property is already proven by test:

- the ledger write happens **before** cancellation metadata;
- suppression remains readable after a partial failure;
- both eligibility and the pre-provider recheck consult the authority;
- provider sending stays blocked after the partial failure;
- the partial outcome is surfaced, not swallowed;
- live automated outreach is disabled (`AUTO_EMAIL_OUTREACH=0`,
  `WHATSAPP_AUTO_SEND=0`, `SALES_AUTOPILOT_ENABLED` unset);
- PR #144 is not deployed under this authorization.

The gap affects **operational repair and state consistency**, not the send gate.

## Required implementation (on the new runtime-data root)

```
suppression ledger
  -> durable incomplete-side-effect marker
  -> bounded reconciliation worker
  -> prospect / follow-up / audit repair
  -> COMPLETE or MANUAL_REVIEW
```

Each marker must persist:

| Field | Purpose |
|---|---|
| `event_id` | namespace-safe idempotency key |
| `destination` | normalized email / phone |
| `tenant`, `prospect_id` | identity context |
| `suppression_state` | permanent / quarantine |
| `required_side_effects` | what must happen |
| `completed_side_effects` | what did happen |
| `last_error` | why it stalled |
| `attempt_count` | retry accounting |
| `next_retry_at` | bounded backoff |
| `terminal_status` | complete / manual review |
| `created_at`, `updated_at` | timestamps |

### Required behaviour

- process-restart recovery (the whole point);
- idempotent repair;
- bounded retry with backoff;
- **never sends outreach**;
- poison items move to explicit manual review after the retry cap;
- concurrent-worker safe (shared inter-process lock on the runtime root);
- a broader existing suppression is **never** downgraded by repair.

## Consequences

Until this exists:

- production deployment is blocked;
- live email automation is blocked;
- live WhatsApp automation is blocked wherever unified suppression applies;
- operators must rely on `reconcile_suppressions()` being invoked manually to
  repair a partial failure.

## Related

- PR #144 — unified suppression scopes, quarantine, partial-write result model
- Runtime-data separation (next batch) — provides the external root this depends on
- Brevo outcome ingestion (`MISSING_PROVIDER_INGESTION`) — separate blocker for
  live email activation
