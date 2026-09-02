# Distributed Cancellation — Production Proof (PR #77)

**Classification:** `PRODUCTION-PROVEN` for Redis-backed cross-process cancellation (Pranav-only).
**Date:** 2026-07-22
**Deployed SHA:** `d4b248f5` (`d4b248f5b32f5624af70eeaf2a673c23709ed11e`)
**Rollback SHA (unused):** `a7410c2db499f68ec5a81c9eaa26e446ae33bdfa`
**Evidence on VPS:** `/tmp/dist_cancel_prod_proof.jsonl` (no secrets)

Overall 31-agent mission remains **incomplete**. No third agent enabled. Flags restored OFF.

---

## 1. PR and merge

| Item | Value |
|---|---|
| PR | [#77](https://github.com/sumitrevolt/leadgenrationaivoiceagent/pull/77) |
| Final PR head | `4d7c98841c15099677a32a2bae532c6b29d23797` |
| Merged at | 2026-07-22T03:22:55Z |
| Merge commit / `origin/main` | `d4b248f5b32f5624af70eeaf2a673c23709ed11e` |
| CI | Lint/test/Trivy/GitGuardian pass; `prod_check + pytest` red **only** on 2 inherited Jiya caption E2E tests — identical on base `a7410c2d`; **PR-specific regressions = 0** |
| Local gate pre-merge | 185 targeted tests + prod_check + secrets PASS |

## 2. Deploy

| Item | Value |
|---|---|
| Pre-deploy prod | `a7410c2d`, healthy, flags OFF, celery=0 failed=0 dead=7 |
| Deploy | `scripts/deploy_vps.sh d4b248f5b32f5624af70eeaf2a673c23709ed11e` |
| Post-deploy | all 5 app-image containers `APP_VERSION=d4b248f5`, `/health` healthy production |
| Migrations | `022_add_request_depth` (unchanged) |

## 3. Redis backend proof

```yaml
cancellation_backend: redis
fallback_active: false
key_prefix: agentrt:cancel:
default_ttl_s: 3600
```

| Check | Result |
|---|---|
| Structured write | PASS (`schema_version` present) |
| Exact-key GET (no `KEYS *`) | PASS |
| TTL | ~3600s |
| Cross-container visibility | APP write → WORKER `is_requested=true` (`art_xvis001`) |
| Clear by exact run | PASS; other run unaffected |
| Memory fallback | **not** active |

Idempotency (unchanged, not redesigned):

```yaml
idempotency_backend: redis_or_memory_as_observed  # fail_open_on_redis_error: true
idempotency_distributed_durability: not_proven
```

## 4. Disabled-state

With all workforce flags OFF: Pranav submit → `skipped` / `runtime_flag_disabled:AGENT_RUNTIME`. No lease, no engine.

## 5. Pranav-only arm + baseline

```yaml
AGENT_RUNTIME: 1
SRE_AGENT: 1
# all peer pilots + OPENCLAW + PLATFORM_DIAL: 0
```

Preflight: `eligible_agents: [pranav]`, `unexpected_agents: []`, `allowed: true`.

| Field | Value |
|---|---|
| Capability | `run_owned_workflow` → `engineer_agents.run_sre` |
| Task ID | `art_421cee206a6d` |
| Lifecycle | queued → leased → running → succeeded |
| Side effects | none (read-only) |

## 6. Cross-process cancellation (primary)

```text
requester: leadgen_app (Owner OS / cancellation store)
observer:  leadgen_worker
run_id:    art_xproc4693448
command_id: ocmd_cancel_cc8adfa0a3
```

| Field | Value |
|---|---|
| Redis record | visible to worker |
| Checkpoint | policy / pre-lease (`lifecycle: queued → cancelled`) |
| Engine calls | **0** |
| Terminal | `cancelled` / `cancel_requested` |
| Backend | redis, fallback false |

## 7. Race / terminal semantics

| Scenario | Classification |
|---|---|
| Cancel before lease | **production_proven** (`art_b310759c6269`) |
| Cancel after lease / before engine | **integration_proven** (local/CI race tests; not separately timed on prod without artificial sleep) |
| Cooperative in-flight | **integration_proven_not_production_observed** (engine too fast; no permanent delay added) |
| Non-cooperative completion | **production_proven** (`cancel_requested_but_engine_completed` via probe capability) |
| Agent-wide idle | **production_proven** (`no_running_tasks`) |
| Unknown run `runtime_run_not_found` | **unsupported** — request creates TTL’d run-specific record only (no broad cancel); does not invent fake not_found |
| Already-terminal mutate | **not separately production-observed** — contract: do not rewrite history |
| Redis outage fail-closed | **integration_proven** (do not disrupt prod Redis for full outage simulation) |

## 8. Isolation + duplicate

| Check | Result |
|---|---|
| Cancel A only | A cancelled; B succeeded (`art_proofiso_bbb2`) |
| Future C | succeeded (`art_ea078c1cb89f`) |
| Duplicate cancel | first `newly_created`, second `already_requested` |
| Owner OS shape | `command_id`, `targeted_run_ids`, `cancellation_backend=redis`, counts |

## 9. Queues / DLQ / rollback flags

| Phase | celery | failed | dead |
|---|---:|---:|---:|
| Throughout + final | 0 | 0 | **7** (unchanged; not deleted) |

Final flags: **all OFF** in app, worker, scheduler.
`runtime_enabled=false`, preflight eligible `[]`.
OpenClaw OFF, calling HARD OFF, customer state unchanged.
Code left deployed on `d4b248f5` (safety gates passed; no image rollback).

## 10. Updated control-plane

```yaml
shared_runtime_controls:
  pause: production_proven
  drain_new_work: production_proven
  drain_in_flight_finish: partially_proven
  stop_claims: production_proven
  kill_switch: production_proven
  cancellation_same_process: production_proven
  cancellation_cross_process: production_proven
  cancellation_backend: redis
  cancellation_memory_fallback: false
  stable_command_id: production_proven

runtime_durability:
  idempotency_backend: redis_primary_memory_fail_open
  idempotency_distributed_durability: not_proven
```

## 11. Agent counts (unchanged)

| State | Count |
|---|---:|
| production_canary_proven | 2 |
| canary_ready | 10 |
| rollout_hold | 17 |
| intentionally_disabled | 2 |
| **Total** | **31** |

Pranav remains canary-proven for controls; **not** permanently production-enabled (flags OFF).

## 12. Next action

> Implement fail-closed Redis-backed distributed idempotency as a focused PR before authorizing a third production agent.
