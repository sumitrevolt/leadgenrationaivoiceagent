# 05 — Engineering Constitution

## Objective

Define non-negotiable engineering behavior for every human or AI contributor.

## Principles

- Simplicity beats cleverness.
- Evidence beats opinion.
- Small reversible changes beat risky rewrites.
- No silent failures.
- No unowned workflows.
- Every production feature must be observable.
- Every customer-impacting action must be auditable.
- Every bug fix gets regression coverage.

## Code Quality Rules

- Keep domain logic separate from transport, UI and infrastructure.
- Avoid duplicated business rules.
- Validate inputs at boundaries.
- Return safe errors to users and rich errors to logs.
- Use typed contracts where possible.
- Protect idempotency for external actions.

## Review Requirements

- Architecture impact reviewed.
- Security impact reviewed.
- Database impact reviewed.
- Workflow impact reviewed.
- Tests included.
- Rollback plan present.

## Production Blockers

- Missing auth on sensitive route.
- No rollback for migration.
- Scheduler can duplicate customer actions.
- Queue can retry external side effect without idempotency.
- Billing state can become inconsistent.
- Voice or WhatsApp flow can contact opted-out lead.


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
