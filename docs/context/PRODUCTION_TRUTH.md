# PRODUCTION_TRUTH — live-proven only

## Production SHA
`d32a4934` — verified 2026-07-20 via `GET https://leadsgenai.in/health`
`environment=production` · `status=healthy`

## Container versions
App-image services tagged `:d32a4934` (app, worker, scheduler, worker-heavy, worker-video) — PRODUCTION-PROVEN via compose ps after deploy.
Note: recreate used hashed container names; deploy script skew check false-failed while health+tags correct.

## Health endpoints
| Endpoint | Result | Label |
|---|---|---|
| `/health` | healthy, version `d32a4934` | PRODUCTION-PROVEN |
| `/api/admin/delivery-assurance` | 401 unauthenticated | PRODUCTION-PROVEN |
| `/api/admin/delivery-cockpit` | 401 unauthenticated | PRODUCTION-PROVEN |

## Enabled high-risk flags (ops memory — re-verify before acting)
| Flag | Claimed state | Label |
|---|---|---|
| `AGENT_RUNTIME` | `1` canary | PRODUCTION-PROVEN historically |
| `PLATFORM_DIAL_DAILY` | HARD OFF | PRODUCTION-PROVEN mandate |
| `WHATSAPP_AUTO_SEND` | `0` | PRODUCTION-PROVEN ops fact |

## Known live customer
Jiya Makeover · `jiya-makeover`

## Live workflow evidence
- In-container `delivery_assurance.missed_deliverables_summary()` → checked=1, missed=0, at_risk=1, error=None — PRODUCTION-PROVEN
- Routes include `/api/admin/delivery-assurance` once — PRODUCTION-PROVEN
- `product_one_health` in scheduler source (count 5) + prior heartbeat ok=True @ 2026-07-20T03:50Z — PRODUCTION-PROVEN registration; post-deploy hourly tick may not have fired yet

## Known production defects
- Deploy script APP_VERSION skew check false-negative on hashed container names (ops tooling debt)
- CI remote `prod_check + pytest` job fails many pre-existing tests (not WS-1 unique)

## Last deployment evidence
2026-07-20 deploy wave landed `d32a4934` (includes squash merge #59 `d625e48` + domain-assurance agents). Concurrent deploy noise; end state healthy.

## Rollback reference
`bash scripts/deploy_vps.sh 208fcf48` (pre-WS-1-merge tip) or `69c4c8d2` (earlier) — only if health/auth regresses. Current: no rollback needed.

## Agent-harness production shadow (canonical harness)
- `dag_engine` production **shadow** canary passed 2026-07-22 on prod SHA `878c13973ce496c05979571e136c0138e95e4256`, registry manifest `1d3b83331cf303e2` — record-only, enforcement never enabled, all `AGENT_HARNESS*` flags restored OFF. PRODUCTION-PROVEN. Evidence: `docs/agent_runtime/DAG_SHADOW_PRODUCTION_CANARY_PROOF.md`.
- `batch_harness` production **shadow** canary passed 2026-07-22 (same SHA/manifest) — `agent=nikhil`, `tenant=__system__`, `batch.internal.safe_calculation@1.0.0`, deterministic value 321; registry-bound executor invoked **0** times (`enforce._SAFE_CALLS` delta 0); record-only, flags restored OFF. PRODUCTION-PROVEN. Evidence: `docs/agent_runtime/BATCH_SHADOW_PRODUCTION_CANARY_PROOF.md`.
- Production-shadow-proven families: **2 / 5** (`dag_engine`, `batch_harness`). Production-enforced: **0 / 5**.
- Harness audit baseline: **2** shadow records at `/app/data/harness_runs.jsonl` — dag=1, batch=1, enforce=0 (SHA-256 `660fdb599092bed637773887a096d758509c41f86ad09d88e3a15e6bf4f5999e`). The original DAG record stayed byte-identical (`85f2b52de060de5355faa0f74dbc3c9d8971f77e60c6143250438972b12c9f0b`). Future reviews compare against this baseline.
- `CODE_EXEC=0`, canonical harness OFF, `AGENT_HARNESS_ENFORCE` empty — re-verified in-container 2026-07-22. PRODUCTION-PROVEN.
- `BATCH_HARNESS=1` is an **info-flag only** (batch runner capability; sole call site is an admin endpoint; no `data/batch_runs/` usage in prod). It is separate from the `AGENT_HARNESS*` canonical-harness flags and does not enable shadow, enforcement, or code execution.
