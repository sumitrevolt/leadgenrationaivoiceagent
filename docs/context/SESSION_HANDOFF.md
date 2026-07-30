# SESSION_HANDOFF - overwrite every session end

## Session objective
PR #187 owner-inbox email canary — release-blocking safety remediation + commit/push only. No merge/deploy/email/flag changes.

## Branch
`feat/owner-inbox-email-canary` (this worktree only)

## Outcome
Canary path hardened:
- one-shot transport (Resend|Brevo|SMTP pick-one) — never `EmailSender` cascade
- ambiguity/timeout/error → `UNKNOWN_REQUIRES_REVIEW`, no fallback/retry
- `ProviderNotCalledError` for definite pre-network failures → `FAILED`, `provider_called=false`, daily cap not consumed
- `AttemptLedgerError` / `SuppressionLedgerError` block before provider I/O (canary-local; `email_unsub` globals unchanged)
- claim under OS file-lock; lock released before network
- `GET /last` exposes failed preflight/authority truth (`ok: false`)

## Files
- `app/platform/owner_email_canary.py`
- `app/api/owner_email_canary.py`
- `tests/test_owner_email_canary.py`
- `docs/context/SESSION_HANDOFF.md`

## Evidence (independent local, this exact worktree, post-edit)
- `tests/test_owner_email_canary.py` — **35 passed**
- A1–A9 ratchets + `runtime_data_path_allowlist` — **152 passed**
- `scripts/prod_check.py` — **PASS** (1216 routes, 0 wiring gaps, 88/88 engines, 0 orphans)
- `scripts/check_secrets.py` — clean
- ruff on the 3 code/test files — clean before final narrow exception edits; rerun required at commit time

## Safety
No deploy. No email sent. No protected flags changed. Marketing default email fallback semantics unchanged. `_recovery/` not staged.

## Next
After push: re-request cloud review on new head. Do not merge until re-green.
