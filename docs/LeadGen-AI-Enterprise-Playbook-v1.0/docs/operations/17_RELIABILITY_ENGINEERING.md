# 17 — Reliability Engineering

## Objective

Design the platform to continue operating safely during failures.

## SLO Examples

- API availability: 99.5% initial target.
- Critical workflow success rate: 99%.
- Daily content generation completion: 98%.
- Voice call job processing delay: under defined SLA.
- Invoice generation accuracy: 100%.
- No duplicate invoices: 100%.
- No outreach to opted-out lead: 100%.

## Reliability Patterns

- Idempotency.
- Retry with exponential backoff.
- Circuit breakers.
- Bulkheads.
- Dead-letter queues.
- Checkpointing.
- Graceful degradation.
- Provider fallback.
- Readiness checks.
- Health checks.
- Safe defaults.

## Failure Budget

If failure budget is burned:
- Freeze risky feature releases.
- Prioritize reliability work.
- Run incident review.
- Add regression tests.
- Improve monitoring.


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
