# 12 — Event Bus

## Objective

Use events to decouple services, agents, workflows and dashboards.

## Event Naming

Use past-tense business events:

- lead.created
- lead.enriched
- lead.scored
- call.completed
- call.failed
- transcript.analyzed
- crm.stage_changed
- whatsapp.sent
- email.sent
- content.generated
- content.approved
- invoice.generated
- payment.failed
- subscription.renewed
- workflow.failed
- agent.unhealthy

## Event Contract

Every event must include:

- event_id
- event_type
- version
- occurred_at
- producer
- customer_id if applicable
- entity_id
- correlation_id
- trace_id
- payload
- schema_version

## Event Rules

- Events are immutable.
- Events should not contain secrets.
- Consumers must be idempotent.
- Events must be replayable.
- Schema changes must be versioned.
- Event failures must go to DLQ.
- Event subscriptions must be documented.

## Event Replay

Replay only after:
- scope is defined
- idempotency is verified
- affected consumers are listed
- dry-run is performed
- rollback plan exists


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
