# LeadGen M020: P0 webhook fail-closed + 09:00–20:00 IST daily window

## Summary

This PR delivers the LeadGen-only end-to-end setup the owner authorized:
the P0 webhook authentication fail-closed fix and the operational
09:00–20:00 IST daily calling window with 5-channel concurrent
allocation, bounded retries, and self-heal.

## Changes

### `app/telephony/smartflo_webhooks.py` — P0 fail-closed

Previously the webhook receiver accepted requests WITHOUT authentication
when ``SMARTFLO_WEBHOOK_SECRET`` was unset, regardless of environment. This
let any third party spoof CDR events, trigger fraudulent billing metering,
and poison lead status.

After this change:
- production (default) + secret unset → 503 + critical log
- production + secret set + missing/wrong ``X-Smartflo-Secret`` header → 401
- production + secret set + correct header → 200 + CDR append
- non-production (dev|test) + secret unset + ``ALLOW_UNAUTH_WEBHOOK=true`` → 200 + warning log
- non-production + secret unset + flag unset → 503
- production + ``ALLOW_UNAUTH_WEBHOOK=true`` → still 503 (flag ignored in prod)

### `app/platform/leadgen_daily_window.py` — new module

Operational window (09:00–20:00 IST, 1h tighter than TRAI's 09:00–21:00):
- ``evaluate_window(now)`` → ``WindowDecision(in_window, pre_window_ready, post_window_hard_stop, ...)``
- pre-window readiness (5min lead)
- post-window hard stop (no new outbound dials after 20:00 IST)
- ``ChannelAvailabilityLedger`` — file-backed lease ledger with 5-channel concurrent cap, TTL-based stale-lease cleanup, same-lead refresh, cross-lead blocking
- ``RetryLedger`` — per-(lead, channel, day) bounded retry budget (3/day by default), per-channel isolation
- ``preflight(...)`` → ``CallPathCheck.can_dial`` with structured ``reasons_to_block``
- ``ack(...)`` — release channel lease after attempt completion
- ``safe_self_heal(...)`` — drop stale leases on worker restart

Unlimited FUP per Tata partner dashboard does NOT remove:
- per-call throttle (per-second, per-minute)
- per-lead retry budget (3/day)
- per-day per-DID anti-abuse
- DND / opt-out / consent check (DPDP Act 2023 + TRAI TCCCPR)

### Tests (31/31 pass, 5.1s)

| File | Cases | Coverage |
|---|---:|---|
| `tests/test_smartflo_webhook_fail_closed.py` | 9 | prod unset → 503, staging unset → 503, dev+flag unset → 503, dev+flag set → 200, prod+flag set → still 503, secret set + missing header → 401, secret set + wrong header → 401, secret set + correct header → 200, test env + flag → 200 |
| `tests/test_leadgen_daily_window.py` | 22 | window inside/outside/pre-window/post-window, channel ledger start-with-5, acquire/release, 5-channel concurrent cap, double-hold refusal, same-lead refresh, retry ledger 3-then-block, separate-days isolation, separate-channels isolation, preflight pass/block per gate, safe_self_heal stale-lease release |

```
$ python -m pytest tests/test_smartflo_webhook_fail_closed.py tests/test_leadgen_daily_window.py -v
============================= 31 passed in 5.11s ==============================
```

### P0 spec (delivered earlier this session)

`docs/security/P0_SMARTFLO_WEBHOOK_SECRET.md` — owner-action checklist for setting
``SMARTFLO_WEBHOOK_SECRET`` in VPS ``.env`` and adding ``X-Smartflo-Secret`` header
in the Tata CloudPhone portal Webhook "Headers" section.

## Out of scope (gated on owner-action)

- Live CDR / webhook test event → requires VPS-side ``SMARTFLO_WEBHOOK_SECRET`` to be set first.
- Consented canary call → requires C2C api_key + DID binding + agent config (Do Big Cloud Hub partner dashboard or VPS pre-config).
- 5-channel concurrent live proof → requires all of the above + at least 1 consented test target.
- VPS shell access for deployed SHA + Telegram sole-poller + SmartFlo runtime readback → owner hPanel Web Console (Cloudflare-blocked from this PC).

## Verification

- CI: not yet run on this PR head; branch is `fix/M020-clean-20260923` (no remote push yet).
- Local tests: 31/31 pass on this PC.
- Owner pre-merge gate: confirm ``SMARTFLO_WEBHOOK_SECRET`` value in VPS ``.env`` matches the value added to the Tata portal Webhook "Headers" section.
