# 13 — Self-Healing Architecture

## Objective

Detect common failures automatically and recover where safe without causing duplicate customer actions.

## Detect

- Dead workers
- Queue backlog
- Scheduler missed run
- API provider outage
- Redis outage
- Database latency
- Failed webhooks
- Failed voice calls
- WhatsApp send failures
- SMTP disabled account
- Token/cost spike
- Memory leak
- CPU spike
- Repeated agent hallucination or low confidence
- Stuck workflow state

## Recover

- Restart worker.
- Pause upstream producer.
- Switch provider if configured.
- Retry with backoff.
- Open circuit breaker.
- Replay from checkpoint.
- Move poison messages to DLQ.
- Alert admin.
- Create incident.
- Create regression test after fix.

## Self-Healing Safety

Self-healing must not:
- Send duplicate messages.
- Create duplicate invoices.
- Call opted-out leads.
- Overwrite CRM state with stale data.
- Delete customer data.
- Change production config without approval.

## Human Approval Required

- Billing corrections.
- Mass retries.
- Provider migration.
- Production database repair.
- Workflow replay affecting more than configured threshold.
- Customer communication after incident.


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
