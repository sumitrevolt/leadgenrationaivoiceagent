# 11 — Queue System

## Objective

Create reliable background processing for slow, repeated, provider-dependent and customer-impacting work.

## Queue Types

- lead-import
- lead-enrichment
- voice-call
- transcript-analysis
- whatsapp-send
- email-send
- content-generation
- poster-generation
- billing
- invoice
- reporting
- agent-evaluation
- dead-letter

## Queue Contract

Every queue must define:

- Queue name
- Producer
- Consumer
- Message schema
- Idempotency key
- Retry count
- Backoff policy
- Dead-letter queue
- Visibility timeout
- Concurrency
- Rate limit
- Metrics
- Alert thresholds
- Replay process

## Message Rules

- Messages must be small.
- Store large payloads in database/storage and reference IDs in queue.
- Include correlation ID and trace ID.
- Include customer ID where applicable.
- Include workflow execution ID.
- Include attempt count.
- Include created timestamp.
- Include expiry where needed.

## Queue Failure Handling

- Transient provider error: retry with backoff.
- Permanent validation error: fail and record.
- Unknown error: retry limited times then DLQ.
- Duplicate job: mark skipped, not failed.
- Poison message: isolate and alert.
- Queue backlog: pause upstream producers or scale workers.


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
