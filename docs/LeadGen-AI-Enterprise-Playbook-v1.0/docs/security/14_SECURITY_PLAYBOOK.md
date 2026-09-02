# 14 — Security Playbook

## Objective

Protect customer data, business data, credentials, communications, billing, voice records and operational systems.

## Security Controls

- Authentication for customer portal and admin dashboard.
- Role-based access control.
- Least privilege service accounts.
- Secure secrets storage.
- No secrets committed to repository.
- Input validation on every API boundary.
- Output encoding on UI.
- Rate limiting on public routes.
- Webhook signature verification.
- Audit logs for sensitive actions.
- Encryption for sensitive data.
- Secure file upload validation.
- Dependency scanning.
- Error messages must not leak secrets.
- Admin actions require audit trail.

## Sensitive Actions

Require additional logging and possibly approval:
- Customer deletion.
- Subscription modification.
- Invoice correction.
- API key rotation.
- Telephony campaign start.
- WhatsApp bulk send.
- Database migration.
- Provider credential update.
- Role permission changes.

## Consent and Compliance

- Track opt-out.
- Track do-not-call.
- Respect WhatsApp template and opt-in rules.
- Respect email unsubscribe.
- Store call recording notice status where required.
- Prevent outreach to restricted leads.

## Security Testing

- Auth bypass tests.
- RBAC tests.
- Injection tests.
- File upload tests.
- Webhook spoofing tests.
- Rate limit tests.
- Secrets scan.
- Dependency vulnerability scan.


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
