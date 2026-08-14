# Runbook Billing Incident

## Scenario

Billing, invoice, payment or subscription state becomes inconsistent.

## Immediate Response

1. Declare incident if customer impact exists.
2. Assign incident commander.
3. Freeze affected automation.
4. Preserve logs and evidence.
5. Identify blast radius.
6. Stop further damage.
7. Communicate internally.

## Diagnosis

Check:
- Recent deployments.
- Queue depth.
- Scheduler history.
- Provider status.
- Error logs.
- Database state.
- Workflow execution history.
- Audit logs.
- Customer impact count.

## Recovery

1. Apply safe rollback or pause.
2. Restore service gradually.
3. Run smoke tests.
4. Reconcile data.
5. Re-enable automation in controlled batches.
6. Monitor for recurrence.

## Post-Incident

- Create RCA.
- Add regression tests.
- Update runbook.
- Add alert if missing.
- Create ADR if architecture changed.
- Update production scorecard.

## Communication Template

Current status:
Impact:
Actions taken:
Expected next update:
Owner:


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
