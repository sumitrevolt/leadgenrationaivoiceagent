# 08 — Workflow Engine

## Objective

Define production-safe workflow execution for all LeadGen AI business processes.

## Workflow Contract

Every workflow must have:

- Unique workflow ID
- Version
- Owner
- Trigger
- Start state
- Terminal success state
- Terminal failure state
- Allowed transitions
- Inputs
- Outputs
- Validation rules
- Retry policy
- Timeout
- Idempotency strategy
- Events emitted
- Logs
- Metrics
- Alerts
- Runbook
- E2E tests

## State Machine Rules

- No implicit state transitions.
- No direct database state changes outside workflow service.
- Every transition must record actor, timestamp, reason and trace ID.
- Invalid transition must fail loudly.
- Terminal states must be immutable unless reopened through a documented recovery action.
- Long-running actions must checkpoint progress.

## Required Workflow Controls

- Pause
- Resume
- Cancel
- Replay
- Restart
- Rollback
- Manual intervention
- Dry run
- Sandbox run
- Version migration

## Workflow Validation Checklist

Before production:
- Graph has no orphan nodes.
- No unreachable terminal states.
- No infinite loop without max attempts.
- No external side effect without idempotency.
- No retry storm possibility.
- No unhandled failure state.
- Logs include correlation ID.
- Metrics include duration, success rate, failure rate and retries.

## Critical Workflows

1. Customer onboarding.
2. Daily content generation.
3. Lead ingestion.
4. Lead enrichment.
5. AI voice calling.
6. WhatsApp follow-up.
7. Email follow-up.
8. CRM update.
9. Billing and invoice.
10. Admin intervention.
11. Reporting and analytics.


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
