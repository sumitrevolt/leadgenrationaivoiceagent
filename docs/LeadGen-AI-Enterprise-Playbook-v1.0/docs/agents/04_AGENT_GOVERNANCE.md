# 04 — Agent Governance

## Objective

Standardize every AI agent so it has identity, authority, limits, memory rules, inputs, outputs, health checks and evaluation.

## Every Agent Must Define

- Name and role.
- Business owner.
- Technical owner.
- Inputs and outputs.
- Allowed tools.
- Forbidden actions.
- Memory scope.
- Knowledge sources.
- Retry policy.
- Fallback model.
- Timeout.
- Health check.
- Success metrics.
- Failure modes.
- Escalation path.

## Agent Runtime Rules

- Every agent action must include correlation ID and trace ID.
- Agent outputs must be validated before triggering external side effects.
- Agents must not directly mutate production state unless the workflow grants permission.
- Agents must record task history and confidence score.

## Agent Evaluation

- Evaluate accuracy, latency, cost, task success, escalation rate and customer impact.
- Run regression tests on prompts before promoting agent versions.
- Keep prompt versions and rollback path.

## Memory Rules

- Store durable business facts only when useful and permitted.
- Do not let experimental learning corrupt production policy memory.
- Separate customer-specific memory from global system memory.
- Expire stale operational assumptions.


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
