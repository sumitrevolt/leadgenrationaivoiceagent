# DSH canary evidence pack — 2026-08-16

Source: deployed code/runtime checks around prod `26427cde` and local contract tests in the same code line.

## Current runtime posture

- Operational authority: direct executor.
- `DSH_RUNTIME_ENABLED=0`.
- `DSH_SHADOW_ENABLED=0`.
- Rollback string: `DSH_RUNTIME_ENABLED=0`.
- Swara/Ananya are frozen in code: `FROZEN_AGENTS = frozenset({"swara", "ananya"})`.
- DSH allowlist wildcard fails closed: `_allowlist()` returns an empty set when `*` appears.

## Canary matrix

| Canary | Evidence source | Expected result |
|---|---|---|
| Wildcard allowlist refusal | `app/platform/workforce_runtime/dispatch.py` | `DSH_AGENT_ALLOWLIST=*` yields no DSH candidates. |
| Frozen voice identities | `provider_for()` checks `FROZEN_AGENTS` first | `swara` and `ananya` route `direct`, never DSH. |
| Direct fallback | `provider_for()` requires runtime/shadow flags | With both flags off, allowlisted agents still route `direct`. |
| Rollback advertised | `runtime_status()` | Status includes `rollback: DSH_RUNTIME_ENABLED=0`. |
| Cancellation/idempotency substrate | Runtime status / tests | Redis-backed cancellation/idempotency healthy; fallback inactive in verified prod probe. |

## Required before any future DSH promotion

- Owner explicit promotion gate.
- Shadow/golden-case evidence.
- Queue/DLQ and cancellation probe retained.
- Tenant/compliance/billing refusal tests green.
- Rollback drill proves immediate return to direct executor.
- Swara/Ananya frozen assertions remain green.
