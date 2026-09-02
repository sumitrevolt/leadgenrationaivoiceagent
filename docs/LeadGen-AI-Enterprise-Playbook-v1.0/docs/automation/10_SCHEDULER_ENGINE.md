# 10 — Scheduler Engine

## Objective

Make all scheduled tasks reliable, idempotent, monitored and recoverable.

## Scheduler Contract

Every scheduled task must include:

- Task name
- Owner
- Frequency
- Timezone
- Trigger source
- Distributed lock
- Max runtime
- Retry policy
- Missed-run behavior
- Catch-up behavior
- Input query
- Output actions
- Idempotency key
- Success metric
- Failure metric
- Alert condition
- Runbook

## Required Scheduled Tasks

- Daily content generation around 7 AM customer local time.
- Lead scraping/import.
- Lead enrichment.
- Voice call queue preparation.
- Follow-up sequences.
- Invoice generation.
- Renewal reminders.
- Failed payment reminders.
- Agent health check.
- Queue depth check.
- Workflow stuck-state scanner.
- Daily executive report.
- Weekly production readiness score.
- Backup verification.
- Knowledge freshness scan.

## Scheduler Safety Rules

- No overlapping execution unless explicitly allowed.
- No customer-impacting scheduled job without idempotency.
- No billing job without reconciliation.
- No outreach job without consent and opt-out check.
- No scheduled job without execution history.
- No scheduled job without alerting.

## Missed Run Handling

Options:
- Skip safely.
- Catch up once.
- Catch up in bounded batches.
- Human approval required.
- Freeze and alert.

Default: bounded catch-up with idempotency.


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
