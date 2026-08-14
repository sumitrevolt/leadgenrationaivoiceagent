# DSH tests-and-shadow evidence — 2026-08-14

Evidence label: **LOCAL-ONLY / TEST-PROVEN (bounded suites)**.

No commit, push, deploy, flag arm, production write, or Voice/Swara edit was
performed. `DSH_RUNTIME_ENABLED` and `DSH_SHADOW_ENABLED` remain default-OFF.

## Added gate

- `deploy/dsh/evidence/shadow_promotion_gate.json` is deliberately
  `blocked_pending_production_soak` with `promotion_allowed=false`.
- Promotion requires at least 2,000 observed turns, 14 days, zero shadow side
  effects, all golden cases passed, and SHA-256-bound artifacts.
- `tests/fixtures/dsh_shadow_golden_set.json` contains eight pending contract
  stubs. Pending stubs are not represented as executed evidence.
- `tests/test_dsh_shadow_evidence_gate.py` enforces the default-OFF/no-enqueue
  path, proposal-only shadow tools, canonical policy reason parity, single
  workforce dispatch seam, internal-network/no-child-secret contract, frozen
  Voice agents, bounded process termination, and fail-closed cancellation.

## Green local evidence

- `pytest tests/test_dsh_shadow_evidence_gate.py -q` — **10 passed, exit 0**
- `pytest tests/test_dsh_workforce_runtime.py -q` — **21 passed, exit 0**
- agent-runtime governance/idempotency/cancellation group — **87 passed, exit 0**
- harness registry/shadow/session/enforce group — **156 passed, exit 0**
- scheduler routing + parity + Owner OS + agent registry group —
  **54 passed, exit 0**
- Total bounded regression evidence above: **328 passed**
- `ruff check tests/test_dsh_shadow_evidence_gate.py` — **exit 0**
- `git diff --check` — **exit 0**
- frozen diff scan under `app/voice_agent` and `app/telephony` — **0 paths**
- `scripts/prod_check.py` — **exit 0**, 1,280 routes checked, zero wiring gaps
- `scripts/check_secrets.py` — **exit 0**, no secrets detected in changed files

## Exact blockers / deliberately unverified

1. `tests/test_dsh_supply_chain.py`: **3 passed, 1 failed**. The deterministic
   static evidence input hashes no longer match
   `docs/evidence/DSH_SUPPLY_CHAIN_STATIC_20260814.json`. Those build/evidence
   files are sibling-owned; this lane did not rewrite their proof.
2. `tests/test_dsh_migration_contract.py` determinism test exceeded the bounded
   local run while `render_contract_json()` repeated the repository AST scan.
   The 90-second pytest timeout emitted the stack in `_scan_runtime_usage`;
   process completion took about 231 seconds. This lane did not edit the
   sibling-owned generator or committed contract outputs.
3. Linux source build, executable reproducibility, final-image SBOM/licences,
   fake-gateway container smoke, and hard process cancellation in the actual
   Linux image remain CI/build-lane evidence.
4. The 2,000-turn / 14-day shadow soak, production trace hashes, drift metrics,
   and owner promotion authorization are **not done**. Promotion remains
   mechanically represented as blocked.
5. `prod_check.py` passed but reported the generated `API.md` endpoint index as
   out of date; API doc synchronization remains with the implementation lane.
