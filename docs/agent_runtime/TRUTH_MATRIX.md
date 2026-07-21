# 31-Agent Truth Matrix (Wave-B read-only canary scope)

Source: `team.STAFF` · `agent_registry` · `agent_runtime.PILOT_AGENTS` · `agent_runtime_workforce`.

## Counts

| Bucket | Count | Rollout state |
|---|---|---|
| **pranav** (SRE) | **1** | `canary_proven` — **LOCAL only**; not `production_canary_proven` |
| Other Wave-A/B read-only pilots | **11** | `canary_ready` |
| GREEN mutate + AMBER/voice-adjacent hold | **17** | `rollout_hold` |
| Swara + Ananya | **2** | `intentionally_disabled` |
| **Total STAFF** | **31** | Boss=`manager` counted once |

## Production canary — BLOCKED (owner auth)

| Fact | Evidence |
|---|---|
| Drift class | `SAFE_BEHIND_DOCS_ONLY` (`7ce4d979` → `10a3996a` = docs/memory only) |
| Running image | `7ce4d979` (pre-PR#72 — no workforce factory / Wave-B pilots) |
| PR #72 | draft CI green @ `676c51a` — **not merged, not deployed** |
| Effective flags on **old** image | `AGENT_RUNTIME=1`, `SRE_AGENT=1` (arms **legacy 3 pilots only**) |
| OpenClaw / calling | unset / HARD OFF |
| Redis | celery=0, dlq:failed=0, dlq:dead=7 |
| Alembic | `022_add_request_depth` |

Production Pranav `run_owned_workflow` path does **not** exist on the running image.
Do not mark `production_canary_proven` until merge → deploy reviewed main SHA → disabled-state proof → Redis-backed canary → rollback.

## Pilot allowlist (post-PR#72 code only)

`kavya, isha, zara, hermes, pranav, vidya, arnav, kabir, diya, aryan, arya, nikhil`

## Local proof

`docs/agent_runtime/CANARY_LOCAL_PROOF.md` — real `run_sre`, idempotency (memory fallback), cancel, RED refuse.
