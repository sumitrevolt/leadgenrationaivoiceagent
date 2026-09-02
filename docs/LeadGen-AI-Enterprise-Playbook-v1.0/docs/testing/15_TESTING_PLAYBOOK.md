# 15 — Testing Playbook

## Objective

Make the platform safe to change by using layered automated testing and production simulation.

## Test Pyramid

### Unit Tests
Business rules, utilities, validators, scoring, state transitions, deduplication.

### Integration Tests
Database, queue, workflow engine, providers in mock mode, auth, billing state.

### Contract Tests
API schemas, webhook schemas, event schemas, queue message schemas.

### End-to-End Tests
Realistic customer journeys across multiple services.

### Load Tests
Queue throughput, scheduler load, API latency, worker concurrency.

### Chaos Tests
Provider outage, Redis down, DB slow, worker crash, duplicate webhook, queue poison message.

## Mandatory E2E Scenarios

1. Customer onboarding.
2. Daily content generation.
3. Content approval.
4. Lead import and dedupe.
5. Lead enrichment.
6. AI voice call simulation.
7. Transcript analysis.
8. CRM update.
9. WhatsApp follow-up.
10. Email follow-up.
11. Invoice generation.
12. Failed payment recovery.
13. Admin retry of failed workflow.
14. Scheduler missed run recovery.
15. Queue DLQ replay.
16. Opt-out protection.
17. Duplicate prevention.
18. Production smoke test.

## Regression Rule

Every production bug must create a regression test that fails before the fix and passes after the fix.

## Test Evidence

Every test run report must include:
- command
- environment
- commit
- pass/fail
- failure logs
- coverage summary
- known skipped tests
- risk statement


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
