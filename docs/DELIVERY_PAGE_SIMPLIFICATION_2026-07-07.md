# Delivery Page Simplification - 2026-07-07

Goal: Product One customers should feel "AI mere liye kaam kar raha hai" without
opening 20 different screens. Keep the selling/approval/proof loop simple; move
internal machinery behind admin-only delivery views.

## Admin Navigation

Keep as primary:

- `/app/admin` - command home and KPI front door.
- `/app/delivery-command-center` - Product One Delivery Cockpit: pipeline,
  setup status, deliverables, approvals, failures, manual fallback, reports.
- `/app/clients` - customer workspace and 360 view.
- `/app/studio` - content creation/review workspace.
- `/app/automation` - internal automation monitor.
- Billing/settings pages - payments, plan truth, team/security settings.

Merge or demote:

- `/app/control-center`, `/app/office`, `/app/agent-tools`, internal ops
  dashboards - keep URL-reachable, but demote under System/Internal unless they
  create direct customer value.
- Separate approval/log/report admin pages - surface the default flow inside
  Delivery Cockpit first; keep advanced pages for debug/super-admin.

Remove from primary nav:

- Duplicate command-center style pages that show the same health/customer
  numbers without a delivery action.
- Any page whose main output is "automation exists" instead of "customer got
  this deliverable".

## Customer Portal

Keep as customer-facing:

- Home - current plan, next action, support.
- Setup Wizard - business profile, brand, social links, approval preference.
- Approvals - content waiting for yes/no.
- Content Calendar - what is planned/scheduled.
- Delivery Proof - completed deliverables, proof notes, published/scheduled
  counts, monthly plan.
- Report - monthly value recap.
- Support - help/update request.

Hide from customer:

- Raw automation logs, cron names, worker failures, API/provider errors.
- Internal retry details. Show "manual delivery in progress" instead.

## Current Implementation Status

- Delivery Cockpit is implemented on `/app/delivery-command-center` and backed
  by `/api/admin/delivery-cockpit`, `/api/admin/delivery-logs`, and
  `/api/admin/clients/{client_id}/delivery-action`.
- Customer Delivery Proof is implemented in Reports via
  `/api/customer/delivery-proof`.
- Workflow catalog is represented in `app/marketing/product_one_delivery.py`
  as Product One workflow IDs. Auto-send remains off; reminder workflows create
  admin/manual tasks until WAHA QR and ban-safe test-send are explicitly cleared.
