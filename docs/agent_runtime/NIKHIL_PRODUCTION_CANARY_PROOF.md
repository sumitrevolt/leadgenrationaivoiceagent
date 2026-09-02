# Nikhil production canary proof (PR #75)

**Status:** PRODUCTION-PROVEN (read-only diagnostic) · flags restored OFF
**Date:** 2026-07-22
**Deployed SHA:** `a7410c2db499f68ec5a81c9eaa26e446ae33bdfa` (`a7410c2d`)
**Rollback image kept:** `3458f8fc` (pre-merge)

## Inherited CI failure comparison (merge gate)

| Test | PR HEAD `296f353` | Base `3458f8fc` |
|---|---|---|
| `test_jiya_makeover_e2e::test_content_generation_for_jiya` | FAIL empty/missing `caption` | FAIL identical |
| `test_jiya_makeover_e2e::test_full_e2e_pipeline_dry_run` | FAIL empty caption | FAIL identical |

PR-specific regressions: **0**. Targeted Nikhil/runtime/registry/status suites: **pass**.
Merge used admin override solely for those two inherited Jiya failures (authorized).

## Merge / deploy

| | |
|---|---|
| PR | [#75](https://github.com/sumitrevolt/leadgenrationaivoiceagent/pull/75) |
| Merge commit | `a7410c2d…` @ 2026-07-22T01:44:23Z |
| Deploy | `scripts/deploy_vps.sh` → all five app-image containers `APP_VERSION=a7410c2d` |
| Health | healthy · `environment=production` |

## Flag isolation

| Metric | Value |
|---|---|
| Staff | 31 · Boss=1 |
| Dispatchable | 12 |
| Gated dispatchable | 12 |
| Ungated | **0** |
| Nikhil flag | `DELIVERY_ASSURANCE_AGENT` (default OFF) |
| Lane | GREEN |

Peer pilots forced OFF before/during canary:
`OPS_WATCHDOG`, `AFTERNOON_CONTENT`, `SOCIAL_ENGINE`, `INFRA_HANDLER`, `SRE_AGENT`, `FINOPS_AGENT`, `SECURITY_AGENT`, `DBRE_AGENT`, `DATA_INTEGRITY_AGENT`, `DEPS_AGENT`, `MCP_ENGINEER`, plus `OPENCLAW_ENABLED=0`, `PLATFORM_DIAL_DAILY=0`.

### Empty eligibility (all flags OFF)

```yaml
agent_runtime_enabled: false
eligible_agents_if_enabled: []
ungated_dispatchable_agents: []
disabled_submit_reason: runtime_flag_disabled:AGENT_RUNTIME
```

### Nikhil-only (DA=1, RUNTIME=0 projected)

```yaml
eligible_agents_if_runtime_enabled: [nikhil]
unexpected_agents: []
allowed: true
```

### Armed (RUNTIME=1 + DA=1)

```yaml
eligible_agents: [nikhil]
unexpected_agents: []
allowed: true
```

## Runtime execution

| Field | Value |
|---|---|
| Owner command_id | `ocmd_6e6a6f2352f6` (top = nested) |
| Correlation | `corr_27976e1a9141` |
| Actor | `admin-nikhil-canary` |
| Run v1 task_id | `art_9bdda593d55e` |
| Capability | `scan_delivery_assurance` |
| Engine | `app.marketing.delivery_assurance.scan_missed_deliverables` |
| Lifecycle | 4 steps (queued → leased → running → succeeded) |
| Duration | ~0.155s |
| Output | `read_only: true`, `customer_contacted: false`, checked=1, missed=0, at_risk=1 (tenant identifiers redacted in evidence) |
| Idempotency v1 | first succeeded; second `duplicate_suppressed` |
| Idempotency v2 | distinct key succeeded (`art_35e81cec0d01`) |

## Policy refusals (armed)

| Agent / action | Result |
|---|---|
| Pranav | `flag_disabled:SRE_AGENT` |
| Kavya | `flag_disabled:OPS_WATCHDOG` |
| Swara | `red_lane_hard_off_mandate_required` |
| Nikhil `repair_deliverables` | `capability_not_registered:repair_deliverables` |

## Control inheritance (Nikhil)

| Control | Result |
|---|---|
| pause | `agent_paused` · no engine |
| resume + one run | succeeded · dup suppressed |
| stop-claims | `agent_claims_stopped` |
| drain new-work | `agent_draining` |
| kill `owner_all_agents` | `kill_switch_engaged:owner_all_agents` · cleared after |
| controlled fail (`limit` non-int) | `failed` / `execution_failed` · not SUCCEEDED |

## Side effects / queues

| | Before | After / final |
|---|---|---|
| celery | 0 | 0 |
| dlq:failed_tasks | 0 | 0 |
| dlq:dead | 7 | **7** (unchanged; not replayed) |
| Unauthorized customer mutations | — | **0** |
| OpenClaw | OFF | OFF |
| Calling | HARD OFF | HARD OFF |

Permitted internal writes: Owner OS command/audit, runtime heartbeats, control records, canary evidence JSON under `data/`.

## Redis notes (honest)

- Lease semantics observed via runtime lifecycle (4-step success includes leased before running).
- Idempotency **behavior** proven (`duplicate_suppressed` same key; distinct key runs).
- Post-run `idem:nikhil*` Redis KEYS empty — likely sync Redis fail-open → in-process memory for that check. Treat **cross-process Redis idem visibility** as PARTIAL; same-process suppression is PRODUCTION-PROVEN.

## Final flags (restored)

All workforce/pilot flags **0** in app/worker/scheduler (and peers).
Post-canary Nikhil control cleared (`manual_pause/scheduled_pause/stop_claims/drain` false).
Eligible set empty. Code left on `a7410c2d`.

## Unresolved limitations

- Cross-process cancellation still unsupported
- In-flight drain finish only partially proven historically
- Live race rechecks mostly integration-proven
- Inherited Jiya E2E caption failures remain on main
- Redis idempotency key visibility PARTIAL (see above)
