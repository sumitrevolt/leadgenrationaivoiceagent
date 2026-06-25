# 20 — Production Certification

## Objective

Define the gates required before LeadGen AI can be considered production-ready.

## Scorecard

Each category receives 0-100:

- Architecture
- Security
- Reliability
- Workflow quality
- Automation safety
- Scheduler safety
- Queue safety
- Database integrity
- API quality
- AI agent governance
- Voice AI readiness
- CRM readiness
- Billing readiness
- Observability
- Testing
- Deployment
- Documentation
- Operations

## Mandatory Zero-Tolerance Gates

Production cannot pass if any are true:

- Security critical issue.
- Billing can duplicate invoices.
- Outreach can contact opted-out leads.
- Scheduler can duplicate customer actions.
- Queue retry can duplicate external side effects.
- Core E2E test fails.
- No rollback path.
- No monitoring for critical workflows.
- Missing backup/restore process.
- Unknown production secrets handling.

## Certification Process

1. Run full audit.
2. Run all test suites.
3. Run E2E journeys.
4. Run load test.
5. Run chaos test.
6. Verify observability.
7. Verify runbooks.
8. Score all categories.
9. Create remediation plan for weak areas.
10. CEO Agent approves only if zero critical blockers remain.


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
