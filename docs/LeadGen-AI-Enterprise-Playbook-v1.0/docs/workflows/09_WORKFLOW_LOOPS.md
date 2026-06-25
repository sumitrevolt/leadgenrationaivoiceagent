# 09 — Workflow Loops Hardening

## Objective

Ensure all repeating loops are safe, bounded, observable, recoverable and never duplicate work.

## Loop Types

- Lead scraping loop
- Deduplication loop
- Enrichment loop
- Scoring loop
- Voice calling loop
- Transcript analysis loop
- Follow-up loop
- CRM sync loop
- Content generation loop
- Approval loop
- Billing loop
- Invoice loop
- Reporting loop
- Learning loop
- Health-check loop

## Loop Contract

Every loop must define:

- Loop owner
- Loop purpose
- Trigger
- Frequency
- Input source
- Output target
- Locking strategy
- Cursor/checkpoint
- Max batch size
- Max retry
- Backoff
- Stop condition
- Failure condition
- Recovery method
- Metrics
- Alerts

## Mandatory Controls

### Duplicate Prevention
Use idempotency keys, unique indexes, external provider request IDs, and workflow execution IDs.

### Checkpointing
Every batch loop must store cursor state so it can resume safely after crash.

### Backpressure
If downstream queue is full or provider is rate-limited, slow down or pause.

### Circuit Breaker
Stop calling failing providers after repeated errors.

### Graceful Shutdown
Worker must finish current item or safely checkpoint before exit.

### Missed Run Recovery
If a scheduled loop misses execution, run catch-up only if safe and bounded.

## Loop Failure Modes

- Infinite loop due to missing terminal state.
- Duplicate lead creation.
- Duplicate WhatsApp or email message.
- Duplicate invoice.
- Retried call to same lead too quickly.
- Stale CRM status overwritten.
- Learning loop corrupts production prompt.
- Queue backlog grows forever.
- Scheduler overlaps previous execution.

## Recovery Steps

1. Freeze affected loop.
2. Inspect execution history.
3. Identify last successful checkpoint.
4. Reconcile downstream state.
5. Repair data if required.
6. Add regression test.
7. Restart in dry-run mode.
8. Promote to production only after validation.


---

## Mandatory Acceptance Criteria

This document is complete only when the related implementation has:

- A named owner.
- Clear inputs and outputs.
- Logged execution.
- Observable metrics.
- Automated tests.
- Error handling.
- Retry and recovery behavior.
- Production-safe defaults.
- Documented rollback.
- Evidence recorded in an ADR or execution report.

## Definition of Done

A module following this document is Done only when it is implemented, tested, monitored, documented, secured, recoverable, and validated through at least one end-to-end scenario.

## Continuous Improvement Rule

After every change, re-run discovery, dependency mapping, regression tests, security checks, workflow validation, scheduler validation, queue validation, and production simulation for impacted areas.
