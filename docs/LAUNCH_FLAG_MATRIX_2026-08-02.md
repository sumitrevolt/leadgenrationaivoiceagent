# Launch Flag-Matrix Snapshot — 2026-08-02 (session-limiter build)

> Artifact for the controlled Vobiz cold-calling go-live. Code-truth column = local build (`48f0577` + session-limiter changes); prod-truth must be re-probed post-deploy (never carry forward).
> Evidence labels: CODE-PRESENT (source) | DIRECT_HOST_VERIFIED (live prod probe) | UNVERIFIED.

## Controlled-launch spine flags (single source: `app/api/automation_flags.py` + `app/telephony/voice_launch.py`)

| Flag | Default / clamp | Safe range | Now (code) | Out-of-range? | Meaning |
|---|---|---|---|---|---|
| `VOICE_LAUNCH_CAMPAIGN` | `0` | `{0,1}` | `0` | NO | Master gate for controlled cold-call spine. INERT when off |
| `VOICE_LAUNCH_KILL` | `0` | `{0,1}` | `0` | NO | Global admin kill — `1` = ALL outbound ineligible (fail-safe; `data/voice_launch_kill.json` fallback) |
| `VOICE_DAILY_CALL_CAP` | `100` | 1…100 (hard-clamped ≤100) | `100` | NO | Attempts/IST-day aggregate ceiling; every provider-accepted attempt counts; wins when below session cap |
| `VOICE_CALLS_PER_SESSION` | `30` | 1…200 (hard-clamped `_SESSION_CAP_CEILING=200`) | `30` | NO | **NEW** — attempts per launch session; Redis-backed; reset ONLY via session lifecycle (worker restart NO); 31st blocked pre-provider |
| `VOICE_TEST_DAILY_CAP` | `25` | 1…cap | `25` | NO | Internal allowlist test-call quota (separate from campaign cap) |
| `VOICE_CALL_CONCURRENCY` | `1` | ≥1 | `1` | NO | Simultaneous outbound calls; launch starts at 1 |
| `VOICE_TRAIN_BATCH` | `30` | ≥1 | `30` | NO | Calls-per-batch before training pause |
| `VOICE_CIRCUIT_FAIL_THRESHOLD` | `5` | ≥1 | `5` | NO | Consecutive provider failures before circuit breaker trips |
| `VOICE_RECORDING_REQUIRED` | `0` | `{0,1}` | `0` | NO | `1` = recording MANDATORY; unhealthy recordings dir blocks new dials (fail-closed) |

## Related gates (must remain as-is)

| Flag | Now (code/prod) | Gate |
|---|---|---|
| `DLT_APPROVED` | `1` (prod, user-confirmed 2026-07-14) | Legal basis for cold outbound |
| `COMPLIANCE_ENABLED` | prod-env | DND scrub fail-CLOSED |
| `DND_FAIL_OPEN` | `0` (prod 2026-08-01) | TRAI fail-closed |
| `PLATFORM_DIAL_DAILY` | `10` (owner test-mode 2026-07-31, allowlist + bot/IVR detection) | platform_dial TEST-MODE |
| `WHATSAPP_AUTO_SEND` | `0` | ban-safety preserved |
| `UPI_AUTO_ACTIVATE` | `1` (allowlist `81bd0bbe501d`) | fail-closed |

## Credential/readiness (checked post-deploy via `scripts/vobiz_go_live.py` inside container)

- `TELEPHONY_PROVIDER`=vobiz · `VOBIZ_AUTH_ID`/`VOBIZ_AUTH_TOKEN`/`VOBIZ_CALLER_ID`/`VOBIZ_TRUNK_ID` SET
- `GROQ_API_KEY` SET (voice STT)
- Vobiz balance > 0 · readiness score ≥ 80 → `GO_LIVE_READY: YES`
- Runtime probes read-only (balance + compliance sample only — no live call)

## Session-limiter invariants (proven by `tests/test_voice_session.py`, green)

- Cap+1 (31st) blocked BEFORE any provider request — reserve is `INCR` then fail-closed rollback, pinned at cap
- Redis down → `counter_unavailable` (block); no active session → `no_session` (block)
- Worker/scheduler restart does NOT reset counter (`create_voice_session` is the only reset)
- Concurrent `asyncio.gather` dispatch → at most `cap` provider calls
- Emergency `session_stop()` blocks new reservations immediately
- Per-session idempotency claim → at-most-once even after crash/restart; retries counted `retried_blocked`, not attempts
- Compliance/daily-cap gates still compose ABOVE session limiter (daily cap wins when lower)

## Out-of-range flag check

None. All launch-spine flags at documented defaults/safe values in code. Prod re-verify required after deploy (owner-gated).

## Verification record (2026-08-02 local)

| Gate | Result |
|---|---|
| `pytest tests/test_voice_session.py tests/test_voice_launch.py` | 49 passed |
| `pytest tests/test_voice_launch_kill_preflight.py tests/test_voice_launch_kill_failclosed.py` | passed |
| `pytest tests/test_campaign_launch.py tests/test_cross_path_telephony.py tests/test_outbound_webhook_emit.py tests/test_billing_webhook_emit.py` | 32 passed |
| `ruff check` (changed files) | clean (pre-existing `fire_calls.py:59` I001 only, CI non-blocking) |
| `scripts/prod_check.py` | PASS — 1222 routes, imports OK, wiring 0 gaps |
| `scripts/check_secrets.py` | clean (11 changed files scanned) |
| Duplicate-route grep `voice-launch/session` | 3 unique routes (GET/POST/stop) — no shadow |
