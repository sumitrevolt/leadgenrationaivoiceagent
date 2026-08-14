# SESSION_HANDOFF — 2026-08-14 (Cursor: WS-DSH canary/retirement prep)

## Status
**DeepSeek Harness is CODE-READY/INERT and LOCAL-ONLY in this isolated worktree.** Canary/retirement prep scaffolding is documented, but no deploy, commit, push, flag arm, canary promotion, legacy deletion, or `.env` touch occurred. Voice/Swara remains FROZEN.

## Active streams
- `WS-DSH` ACTIVE — ADR-181 contract + ADR-182 evidence-gated rollout/retirement policy + rollback/retirement runbook; all DSH flags OFF
- `WS-GTM1` ACTIVE — owner Hot Queue execution remains the business blocker
- `WS-SEC` ACTIVE — compliance/watch-only; no gate weakening
- `WS-UPI304` PARKED — external wait for first live proof

## Facts
- ADR-179 still rejects stock wheel, direct embedding, default tools, and direct provider access
- ADR-181 conditionally allows only the hardened source-built Linux path, and only for planning/turn/tool loop replacement inside existing governance
- ADR-182 fixes the non-automatic wave order: shadow → Kavya read-only → Isha draft → GREEN read-only → GREEN internal mutators → Zara approved-social handoff → AMBER final-approval-gated
- Current runtime posture is `DSH_RUNTIME_ENABLED=0`, `DSH_SHADOW_ENABLED=0`, allowlist empty; direct executor remains authoritative
- Runtime rollback is `DSH_RUNTIME_ENABLED=0` → direct executor. Image rollback is last known-good exact `APP_VERSION` via `scripts/deploy_vps.sh`, with direct cache-busted `/health` and skew/smoke evidence
- Legacy `agent_runtime`/harness deletion is blocked until 30 consecutive green production days, a recorded flag+image rollback game-day, full caller/import scan, green tests/gates, direct `/health` evidence, and separate owner deletion authorization
- Canonical controls remain: Celery, Python domain engines, `agent_registry`, Owner OS approvals, tenant/compliance/billing controls
- Workforce posture stays 31 identities preserved / 29 migratable / `swara` + `ananya` frozen RED/HARD_OFF and out of DSH
- Contract artifacts are local paths only: `docs/evidence/DSH_MIGRATION_CONTRACT_20260814.json` and `tests/fixtures/dsh_migration_contract.json`

## Prep completed in this slice
- `memory/decisions.md`: ADR-182 rollout/rollback/retirement policy
- `memory/playbooks.md`: operator rollback drill and legacy retirement checklist
- `docs/context/ACTIVE_WORK.md`: CODE-READY/INERT status and owner gates
- `CLAUDE.md` / `AGENTS.md`: minimal current-state sync; SHA-256 comparison proved byte-identical

## Verification evidence
- `git diff --check` on the six owned documentation files: exit 0
- `CLAUDE.md` / `AGENTS.md` SHA-256 equality check: `CLAUDE_AGENTS_BYTE_IDENTICAL`, exit 0
- `scripts/prod_check.py`: `[OK] ALL CHECKS PASSED`, exit 0 (1280 routes, 0 wiring gaps)
- `scripts/check_secrets.py`: `[OK] no secrets detected`, exit 0
- Targeted DSH suite: **25 passed, 3 failed**, exit 1. Existing migration-contract fixture/API baseline and supply-chain evidence hashes are stale against concurrent runtime/source changes; no test/evidence artifact was modified in this documentation-owned slice. These failures block shadow/AUTH-DEPLOY readiness until the owning lanes regenerate/review evidence and return the suite to green.

## USER-ACTION gates still pending
1. **AUTH-DEPLOY:** separately authorize code/image deployment; this is not authorization to arm a flag
2. **Flag arm:** after deployed evidence, separately authorize shadow; later authority requires a separate `DSH_RUNTIME_ENABLED` arm decision
3. **Canary promotion + soak:** separately authorize every wave promotion after its evidence/soak package; shadow minimum is 120 golden cases + 2,000 turns / 14 days
4. **Legacy deletion:** only after the 30-green-day retirement checklist and a separate reviewed deletion authorization

## Do not
- Edit `C:\Users\Ratanshila\.cursor\plans\deepseek_harness_migration_25be8ac3.plan.md`
- Deploy, commit, push, create PR, arm any DSH/harness flag, promote a wave, or delete legacy runtime without explicit owner authorization
- Vendor `deepseek-ai/deepseek-harness` or introduce a second runtime
- Edit Voice/Swara modules or move any voice path into DSH
- Touch `.env` or print secrets/config values

## Next
1. Coordinator may mark `canary-and-retirement` prep complete only; owner-blocked deploy/arm/promotion/soak/deletion remain open
2. Owning contract/supply-chain lanes must resolve the 3 targeted DSH evidence failures before presenting AUTH-DEPLOY evidence
3. Keep production state unchanged until the owner chooses the next gate
