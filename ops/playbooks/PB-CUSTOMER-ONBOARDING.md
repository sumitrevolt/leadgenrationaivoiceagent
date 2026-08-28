# PB-CUSTOMER-ONBOARDING — Customer Onboarding Playbook (P0)

- **Purpose**: First paid customer -> activated, delivered, referenced (jiya makeover = template).
- **Trigger**: payment verified (owner_confirmed_upi) for a new customer.
- **Scope**: welcome -> setup -> first delivery -> feedback -> renewal path.
- **Prereqs**: ledger verified, invoice id, customer record with consent + isolation.

## Strategy
1. Welcome within 24h (brand-consistent, owner-approved copy).
2. Tenant isolation FIRST: customer-scoped KB namespace, no cross-client data access (DPDP).
3. Deliver the promised package (activation + first deliverables) — tracking in delivery ledger.
4. Collect feedback + consent updates (opt-out = instant suppression).
5. Nurture to renewal + reference/upsell (nikhil Revenue Ops).

## Decision tree
```
Payment verified
├─ deliverable package ready? -> activate + deliver + record evidence
├─ blocker (data/branding)    -> owner escalation + RB-VIDEO-004 if asset issue
└─ feedback received          -> store + feed product backlog (memory/backlog.md)
```

## Allowed actions
- Create customer-scoped records, deliver assets, log interactions, schedule follow-ups.

## Prohibited actions
- Cross-tenant data access; contacting after opt-out; promising unagreed deliverables.

## Escalation
- Delivery blocker >24h -> owner; churn-risk signals -> nikhil dunning/nurture.

## KPIs
- Time-to-first-delivery; activation rate; NPS/feedback; renewal likelihood.

## Guardrails
- Customer isolation invariant; consent ledger; 90-day recording retention.

## Linked runbooks
RB-SALES-006 (payment), RB-VIDEO-004 (branding), RUNBOOK_BILLING_INCIDENT.

## Evidence requirements
- Delivery record + customer-facing artifact + feedback log.

## Owner approval conditions
- Custom-package commitments; anything outside the sold plan.
