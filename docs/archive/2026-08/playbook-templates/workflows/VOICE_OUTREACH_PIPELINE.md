# Voice Outreach Pipeline

## Objective

Define the production contract for the Voice Outreach Pipeline.

## Workflow Steps

1. Eligible Lead Selected
2. Consent Checked
3. Call Scheduled
4. Call Executed
5. Transcript Analyzed
6. Crm Updated
7. Follow-Up Scheduled

## Required Controls

- State machine persisted in database.
- Idempotency key for each external side effect.
- Audit trail for each transition.
- Retry policy for transient failures.
- Dead-letter queue for repeated failures.
- Manual recovery path.
- E2E test coverage.
- Metrics and alerts.

## Required Events

- workflow.started
- workflow.step_completed
- workflow.failed
- workflow.retried
- workflow.completed
- workflow.manual_intervention_required

## Validation Rules

- Inputs must be validated before starting.
- Consent and opt-out rules must be checked before outreach.
- Customer subscription status must be checked before paid automations.
- Provider responses must be normalized.
- AI outputs must be schema-validated.

## Test Cases

- Happy path.
- Invalid input.
- Provider failure.
- Retry success.
- Max retry failure.
- Duplicate trigger.
- Manual replay.
- Permission failure.
- Stale state transition.
- End-to-end customer journey.


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
