# WAHA recipient preflight

## Goal

Stop WAHA from accepting messages to invalid/unregistered recipients and then failing asynchronously with a misleading HTTP 201 success.

## Risk

High-risk integration change. Default behavior is safe: an explicit `numberExists=false` blocks the send; a provider check outage does not invent a recipient result and preserves the existing graceful provider path. Rollback is code revert plus container recreate; no data migration or flag flip.

## File map

- `app/integrations/whatsapp_selfhost.py` — WAHA contact-check and send-path owner.
- `tests/test_whatsapp_selfhost.py` — fake-provider and blocked-recipient contract owner.

## Contract

1. Before `sendText`, call `GET /api/contacts/check-exists?phone=<digits>&session=<session>`.
2. Explicit `numberExists=false` returns `recipient_not_on_whatsapp`, records a failure, and never calls `sendText`.
3. Explicit `numberExists=true` uses the returned canonical `chatId` when present.
4. Older/fake WAHA responses without `numberExists` remain backward-compatible and continue through the existing send path.
5. HTTP 201 is reported as provider-accepted, not delivery-confirmed; no claim of read/delivered status is added.

## Verification

Run `tests/test_whatsapp_selfhost.py`, the relevant WhatsApp campaign tests, `prod_check.py`, `check_secrets.py`, and `git diff --check`. Do not send a live message as part of automated verification.
