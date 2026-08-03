# SESSION_HANDOFF - overwrite every session end

## Session objective
TencentDB Agent Memory → native Workforce Memory Hub (ADR-154) + enterprise gaps → PR → deploy → enable `WORKFORCE_MEMORY=1`.

## Shipped on `feat/workforce-memory-hub`
- Core hub: L0–L3 · chat/skill/wiki/code · bindings · offload/drilldown
- Plus: recall budgets/timeout · hash dedupe · team visibility + equip · L0/L1 prune · agent_runtime `memory_brief` inject + L0 outcome
- Admin `/api/workforce-memory/*` · flag OFF until prod enable
- Tests: `tests/test_workforce_memory_2026_08_03.py` (14)

## Owner / ops
1. Merge PR → `scripts/deploy_vps.sh` with `APP_VERSION=<sha>`
2. Set `WORKFORCE_MEMORY=1` in VPS `.env` (backup first) → recreate app/worker/scheduler at same SHA
3. Verify `GET /api/workforce-memory/stats` enabled:true (admin auth)

## Do not
Vendor Tencent Node stack · flip WA auto-send · touch voice hot-path sync
