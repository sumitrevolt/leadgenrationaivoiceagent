# 16 — Observability Playbook

## Objective

Make every important system behavior visible, searchable, measurable and alertable.

## Required Telemetry

- Structured logs.
- Metrics.
- Traces.
- Error reports.
- Audit logs.
- Workflow execution history.
- Queue depth.
- Scheduler run history.
- Agent health.
- Provider health.
- Customer-impacting action history.

## Key Dashboards

### Executive Dashboard
Revenue, active customers, churn risk, leads processed, calls made, conversions, costs, incidents.

### Operations Dashboard
Workflow success rate, scheduler health, queue depth, worker status, failed jobs, retries.

### Engineering Dashboard
API latency, error rates, DB latency, deployment status, test status.

### AI Dashboard
Model usage, token cost, agent success rate, confidence, fallback rate, hallucination flags.

### Outreach Dashboard
Calls, WhatsApp messages, emails, delivery rate, response rate, opt-outs.

## Alerts

Alert on:
- Critical workflow failure.
- Scheduler missed run.
- Queue backlog over threshold.
- DLQ increase.
- Provider outage.
- Billing failure.
- Database latency.
- Auth anomaly.
- Cost spike.
- Agent repeated low confidence.
- Production smoke test failure.


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
