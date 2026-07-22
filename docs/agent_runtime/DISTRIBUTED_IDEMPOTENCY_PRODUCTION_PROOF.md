# Distributed Idempotency — Production Proof (PR #79)

**Classification:** `PRODUCTION-PROVEN` for fail-closed Redis Agent Runtime idempotency (Pranav-only).
**Date:** 2026-07-22
**Deployed SHA:** `3fe74095` (`3fe740958dac14eba2ac27d8ce91104aa7e90389`)
**Rollback SHA (unused):** `d4b248f5b32f5624af70eeaf2a673c23709ed11e`
**Evidence on VPS:** `/tmp/dist_idem_prod_proof.jsonl` (no secrets)

Overall 31-agent mission remains **incomplete**. No third agent enabled. Flags restored OFF.

---

## 1. PR and merge

| Item | Value |
|---|---|
| PR | [#79](https://github.com/sumitrevolt/leadgenrationaivoiceagent/pull/79) |
| Final PR head | `af373a01a00d5eade26f7f487527cb4aeefc48c9` |
| Merged at | 2026-07-22T05:18:06Z |
| Merge commit / `origin/main` | `3fe740958dac14eba2ac27d8ce91104aa7e90389` |
| CI | Lint/test/Trivy/GG pass; full `prod_check+pytest` job: pytest **segfault exit 139** — **identical on base `d4b248f5`**; PR-specific regressions = **0**; local targeted **192** + prod_check PASS |
| Diff | Agent Runtime idempotency only; billing webhook fail-open untouched |

## 2. Deploy

| Item | Value |
|---|---|
| Pre-deploy | `d4b248f5`, healthy, flags OFF, celery=0 failed=0 dead=7 |
| Deploy | `scripts/deploy_vps.sh 3fe740958dac14eba2ac27d8ce91104aa7e90389` |
| Post-deploy | all 5 containers `APP_VERSION=3fe74095`, `/health` healthy production |

## 3. Redis backend proof

```yaml
idempotency_backend: redis
fallback_active: false
fail_open_on_redis_error: false
distributed_visibility: true
key_prefix: agentrt:idem:v1:
default_ttl_s: 1209600  # 14d
cancellation_backend: redis
cancellation_fallback_active: false
```

| Check | Result |
|---|---|
| Atomic claim + exact-key GET | PASS |
| Second claim `duplicate_in_progress` | PASS |
| Cross-container (APP→WORKER) | PASS |
| TTL after terminal | finite (~14d retained) |
| Memory/file fallback | **not** active |

Disabled submit: `runtime_flag_disabled` — no terminal success claim.

## 4. Baseline Pranav

| Field | Value |
|---|---|
| Capability | `run_owned_workflow` |
| Task ID | `art_e8cb44dce370` |
| Lifecycle | queued → leased → running → succeeded |
| Idempotency terminal | `succeeded` |
| Side effects | none (read-only) |

## 5. Concurrent cross-process (mandatory)

```text
IDEM_KEY = pranav-idem-concurrent-3fe74095-v1
Requester A = leadgen_app
Requester B = leadgen_worker
```

| Half | Status | task_id / original |
|---|---|---|
| A | **succeeded** | `art_2079d7e415e2` |
| B | skipped / `duplicate_in_progress` | original=`art_2079d7e415e2` |

```yaml
atomic_claim_winners: 1
runtime_runs_created: 1   # one logical success
engine_call_count: 1      # one succeeded execution
duplicate_responses: 1
```

Hard-fail rule (engine > 1) **not** triggered. No rollback.

## 6. Restart + isolation

| Check | Result |
|---|---|
| App+worker recreate, same key | `duplicate_suppressed` → `art_2079d7e415e2` |
| Capability isolation | PASS |
| Tenant/scope isolation | PASS |

## 7. Terminal semantics

| Scenario | Classification |
|---|---|
| Success + dup after success | **production_proven** |
| Controlled failure + same-key block | **production_proven** |
| Cancel after claim + dup | **production_proven** |
| Pause does not burn key; resume executes once | **production_proven** |
| Redis outage seam (`_redis_factory` fail) | **production_observed** (process seam) → `idempotency_store_unavailable`, engine=0 |
| Terminal-commit uncertainty | **integration_proven** (not separately timed on prod) |
| Stale claim auto-steal | **unsupported** by design — no auto-steal; explicit recovery / new key |

## 8. Queues / flags

| Phase | celery | failed | dead |
|---|---:|---:|---:|
| Throughout + final | 0 | 0 | **7** |

Final: all workforce flags OFF in app/worker/scheduler.
`eligible=[]`, OpenClaw OFF, calling HARD OFF, customer untouched.
Code retained on `3fe74095`.

## 9. Updated control-plane

```yaml
runtime_durability:
  cancellation_backend: redis
  cancellation_cross_process: production_proven
  cancellation_memory_fallback: false
  idempotency_backend: redis
  idempotency_memory_fallback: false
  idempotency_cross_process: production_proven
  idempotency_process_restart_survival: production_proven
  idempotency_exactly_one_engine_execution: production_proven
  idempotency_redis_outage_fail_closed: production_observed  # process seam
```

## 10. Agent counts (unchanged)

| State | Count |
|---|---:|
| production_canary_proven | 2 |
| canary_ready | 10 |
| rollout_hold | 17 |
| intentionally_disabled | 2 |
| **Total** | **31** |

## 11. Next action

> Select the third production canary from the remaining ten canary-ready agents based on the lowest-risk execution pattern, but require a **separate** owner authorization and keep every other agent OFF.
