# 18 — Deployment Playbook

## Objective

Ship changes safely with validation, rollback and production smoke tests.

## Deployment Pipeline

1. Lint.
2. Type check.
3. Unit tests.
4. Integration tests.
5. Contract tests.
6. Build.
7. Migration dry-run.
8. Security scan.
9. Staging deploy.
10. E2E tests.
11. Smoke tests.
12. Production deploy.
13. Production smoke tests.
14. Monitor.

## Pre-Deploy Checklist

- No critical tests failing.
- No secrets committed.
- Migration has rollback.
- Feature flag exists for risky changes.
- External provider sandbox tested.
- Runbook updated.
- Monitoring exists.
- Rollback owner assigned.

## Rollback Strategy

- Code rollback.
- Feature flag disable.
- Migration rollback or forward repair.
- Queue pause.
- Scheduler pause.
- Provider disable.
- Customer communication if needed.

## Production Smoke Tests

- /health
- /ready
- auth login
- customer dashboard load
- admin dashboard load
- queue worker heartbeat
- scheduler heartbeat
- sample workflow dry run
- billing read path
- CRM read path


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
