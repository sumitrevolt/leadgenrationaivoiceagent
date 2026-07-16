---
type: Runbook
title: Customer onboarding
description: Paid customer first-hour setup — content seed, social wizard, isolation.
tags: [onboarding, customer, social]
timestamp: 2026-07-17T00:00:00Z
resource: app/marketing/auto_content.py
---

# Customer onboarding

1. Plan pick → payment evidence (invoice) → delivery eligibility.
2. Social Setup Wizard: handles + cadence + approval_mode (`review` | `draft` | `auto`).
3. Postiz: customer must save **own** integration IDs (`social_config` / client) — corporate `POSTIZ_INTEGRATIONS` does not apply (ADR-117).
4. Prefs honored only when `SOCIAL_PREFS_HONOR=1` (prod LIVE 2026-07-17).
5. Content seed is today-only (+ WA/campaign); approvals for new rows when review/auto-submit.

Related: [Deliverables](../product/deliverables.md), [Tenant isolation](../architecture/tenant-isolation.md).
