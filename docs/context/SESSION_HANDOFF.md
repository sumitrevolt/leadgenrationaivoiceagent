# SESSION_HANDOFF — 2026-08-14 (Cursor: WS-DSH full migration complete LOCAL-ONLY)

## Status
**DeepSeek Harness Full Migration implementation is CODE-READY/INERT and LOCAL-ONLY.**
Hardened source build, governance/execution rewire, tests, and blocked shadow gate are present.
No commit, push, deploy, flag arm, canary promotion, legacy deletion, or `.env` touch.
Voice/Swara remains FROZEN.

## Active streams
- `WS-DSH` ACTIVE — implementation complete / production rollout blocked
- `WS-GTM1` ACTIVE — owner Hot Queue execution remains the business blocker
- `WS-SEC` ACTIVE — compliance/watch-only; no gate weakening

## Facts
- Upstream pin: `https://github.com/deepseek-ai/deepseek-harness.git` @ `47f943859bef60e4160492346772ded9b24f765a`
- Tree `f904efab9ef435201d6ba4da88a34d6366568272` · archive SHA-256 `c2d8d1e9ec24f0500da431288d2c0c80cf3f502d4dbda2026bd87ac099f3e2e6`
- Executable SHA-256 (bit-identical across two no-cache builds): `4d2f75728797d7c932c20a09be1ff5042f3758111cde81ec8b7455ce52dfdfc6`
- Cordis path: `/usr/local/bin/cordis.yml` (pkg-visible; `/etc/dsh` rejected by existsSync)
- Child allowlist: `DSH_RUN_TOKEN`, `DSH_MCP_URL`, `DSH_LLM_BASE_URL`, `DSH_CORDIS_CONFIG`, `HOME`
- Internal MCP mount uses exact `include_operations=MCP_OPERATION_IDS`
- Sole workforce dispatch path: `agent_runtime.submit` → `workforce_runtime.dispatch`
- Flags remain OFF: `DSH_RUNTIME_ENABLED=0`, `DSH_SHADOW_ENABLED=0`, allowlist empty
- Shadow promotion gate: `promotion_allowed=false` (`LOCAL_ONLY_NOT_SOAKED`)
- Canonical image smoke: fake model+MCP passed; shutdown 0.485s; cancel 2.672s
- SBOM: CycloneDX, 1,275 components via pinned Syft digest

## Evidence paths
- `docs/evidence/DSH_LINUX_CI_EVIDENCE_20260814.json`
- `docs/evidence/DSH_SUPPLY_CHAIN_STATIC_20260814.json`
- `docs/evidence/DSH_MIGRATION_CONTRACT_20260814.json`
- `docs/evidence/DSH_TESTS_AND_SHADOW_20260814.md`
- `deploy/dsh/evidence/shadow_promotion_gate.json`
- `tests/fixtures/dsh_shadow_golden_set.json`
- Raw binaries / full SBOM stay local/CI artifacts; SHA-256 bound in summary JSON

## Verification (this session)
- smoke `leadgen-dsh:smoke-a` then canonical `leadgen-dsh:final-local` → exit 0
- `assemble_dsh_ci_evidence.py` → `DSH_LINUX_CI_EVIDENCE_OK`
- focused DSH pytest → 40 passed
- affected agent/API/scheduler pytest → 157 passed
- Ruff changed Python → exit 0
- `git diff --check` → exit 0
- `scripts/prod_check.py` → `[OK] ALL CHECKS PASSED` exit 0
- `scripts/check_secrets.py` → `[OK] no secrets detected` exit 0
- voice/telephony dirty diff → empty

## USER-ACTION gates still pending
1. **AUTH-DEPLOY** — code/image only; not flag arm
2. **Shadow arm** — only after deploy evidence + separate authorization
3. **Canary waves + soak** — 120 golden cases, 2,000 turns / 14 days, then each wave separately
4. **Legacy deletion** — only after 30 green days + game-day + caller scan + `/health` + separate auth

## Branch / worktree
- Worktree: `C:\Users\Ratanshila\Documents\leadgen-wt-cursor-dsh-20260814`
- Branch: `cursor/deepseek-harness-migration-20260814` @ `330f837a` + uncommitted implementation fixes
- No commit/push/deploy performed
