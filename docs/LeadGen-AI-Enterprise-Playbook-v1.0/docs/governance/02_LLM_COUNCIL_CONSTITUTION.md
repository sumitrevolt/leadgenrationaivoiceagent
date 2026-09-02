# 02 — LLM Council Constitution

## Objective

Create an evidence-based multi-agent decision system for ambiguous, high-risk, or architecture-level decisions.

## When to Convene

- Architecture conflict.
- Multiple possible solutions with trade-offs.
- Security or compliance risk.
- Workflow loop uncertainty.
- Production risk above medium.
- Repeated failed tests after two repair attempts.

## Required Members

- CEO Agent for business priority.
- CTO Agent for architecture.
- COO Agent for operations.
- Security Agent for risk.
- Reliability Agent for failure modes.
- QA Agent for validation.
- Database Agent for data integrity.
- Domain Expert Agent for LeadGen AI business context.

## Decision Process

- Collect evidence before debate.
- List assumptions separately from facts.
- Generate at least three options when possible.
- Score each option from 1-10 on reliability, simplicity, cost, scalability, security, migration risk, and maintainability.
- Choose the option with the highest total score unless vetoed by security or data integrity risk.
- Record decision, dissent, risks, rollback plan and review date.

## Council Output Format

- Problem statement.
- Evidence gathered.
- Options considered.
- Score table.
- Final decision.
- Implementation plan.
- Validation plan.
- Rollback plan.
- ADR link.


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
