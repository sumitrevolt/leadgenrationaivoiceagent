# Product One Delivery Cockpit Plan

Date: 2026-07-07

## Goal
Make Product One delivery visible, actionable, and proof-backed for both admin and customer without adding another disconnected page.

Approach: reuse the existing customer portal, admin delivery command center, delivery ledger, content approvals, client store, and automation health. Add a small jsonl-first delivery helper that derives the Product One deliverable checklist, pipeline stage, next action, risk, proof, and admin-friendly automation events from current stores. Wire it into existing APIs/UI.

## Audit Gaps
- Customer setup wizard and social setup exist, but the Product One monthly deliverables are not shown as one clear checklist/proof object.
- Admin Command Center shows high-level value/failure counts, but not the requested pipeline stage, next action, owner, due date, and ready/blocked filters per customer.
- Automation logs are technical job heartbeats; customer-delivery events exist in the ledger but need an admin-friendly filtered view tied to customers and next actions.
- Existing pages are already partially simplified: `/app/command-center` redirects to `/app/control-center`, `/app/delivery-command-center` exists, and customer marketing/voice templates were consolidated. We should upgrade these, not create more pages.

## Change Risk
Standard. Touches automation/delivery visibility but no billing truth, telephony sending, migrations, secrets, or deploy. Rollback: remove new helper/endpoints/UI blocks; existing ledger and dashboards keep working.

## File Map
- `app/marketing/product_one_delivery.py`: new jsonl/derived delivery state helper.
- `app/api/admin_dashboard_builders.py`: enrich `_build_command_center()` with delivery pipeline and automation filters.
- `app/api/admin_dashboard.py`: add admin delivery cockpit/action/log endpoints.
- `app/api/customer_dashboard.py`: add customer delivery proof endpoint.
- `frontend/delivery_command_center.html`: upgrade existing page to Delivery Cockpit cards/table/log filters.
- `frontend/customer_dashboard.html`: add customer-friendly proof/report block in Reports.
- `tests/test_product_one_delivery.py`: helper/API acceptance tests.
- `tests/test_admin_command_center.py`: adjust/add command-center assertions if needed.
- `progress.md`: append loop evidence.

## Tasks
1. Build `product_one_delivery.py`.
   - Derive required deliverables: profile, brand kit, 4 posters, 12 captions/posts, festival/local ideas, GBP suggestions, WhatsApp pack, review replies, monthly report, proof.
   - Use client profile, brand/social fields, content queue, approvals, delivery ledger, and optional `data/product_one_delivery/<cid>.jsonl` manual action events.
   - Expose `customer_delivery_status(cid)`, `admin_customer_card(client)`, `automation_events(cid/filter)`, and `record_manual_action(cid, action, status, note)`.
   - No raise; all text customer/admin friendly.

2. Wire APIs.
   - Admin: `GET /api/admin/delivery-cockpit`, `GET /api/admin/delivery-logs`, `POST /api/admin/clients/{id}/delivery-action`.
   - Customer: `GET /api/customer/delivery-proof`.
   - Existing `/api/admin/command-center` also gets richer `per_customer` fields for current UI reuse.

3. Upgrade UI.
   - `/app/delivery-command-center`: show pipeline summary, customer cards/table, actionable filters, log list, and per-customer actions.
   - Customer dashboard Reports: show monthly deliverables + proof with plain wording.

4. Tests.
   - New paid starter customer appears at Payment Received/Onboarding Pending and gets pending deliverables.
   - Completed wizard/setup changes progress/stage and next action.
   - Pending approval and published proof move deliverables/stage.
   - Failed automation event appears in admin logs with retry/manual action.
   - Customer delivery proof is non-technical and includes completed/pending items.

5. Verify.
   - Run focused tests: `tests/test_product_one_delivery.py`, `tests/test_admin_command_center.py`, `tests/test_customer_delivery_os.py`.
   - Run `scripts/prod_check.py`.
   - Run `scripts/check_secrets.py`.
