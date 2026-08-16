# Owner daily checklist

Use this as a 15–30 minute operating loop for LeadsGenAI.

## Daily

1. Open production health: `https://leadsgenai.in/health` and confirm `status=healthy` and expected version.
2. Open Hot Queue: `https://leadsgenai.in/app/inbox`.
3. Review new inquiries and source/UTM labels.
4. Check pending UPI submissions and bind only bank-confirmed payments.
5. Confirm no unexpected queue backlog or DLQ alerts.
6. Review ntfy/phone alerts.
7. For any new lead: call/message manually within compliance rules.

## Weekly

1. Review pricing/start/audit funnel conversion.
2. Review Dependabot/security alerts.
3. Confirm backups and rollback lineage exist.
4. Check API docs drift and run docs sync when needed.
5. Review Automation-Max classifications and only scale proven safe loops.

## Never do

- Do not mark revenue generated without bank credit + client binding + subscription + invoice/ledger proof.
- Do not cold/bulk auto-send WhatsApp.
- Do not disable DND/DLT/consent gates.
- Do not deploy `:latest`; use exact SHA with `scripts/deploy_vps.sh`.
- Do not arm DSH runtime/shadow without explicit promotion evidence and rollback.
