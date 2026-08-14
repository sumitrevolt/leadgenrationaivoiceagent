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

- Hardened source pin: commit `47f943859bef60e4160492346772ded9b24f765a`,
  tree `f904efab9ef435201d6ba4da88a34d6366568272`, archive SHA-256
  `c2d8d1e9ec24f0500da431288d2c0c80cf3f502d4dbda2026bd87ac099f3e2e6`.
- Two independent no-cache build artifacts are bit-identical: executable
  SHA-256 `4d2f75728797d7c932c20a09be1ff5042f3758111cde81ec8b7455ce52dfdfc6`.
- Canonical image build and smoke: fake MCP/model passed, clean shutdown
  **0.485s**, TERM→KILL cancellation **2.672s**, Docker internal-only network.
- Pinned Syft generated an honest CycloneDX SBOM with **1,275 components**.
- DSH focused suites: supply **5**, workforce **21**, shadow **10**, migration
  contract **4** = **40 passed**, all exit 0.
- Affected agent-runtime/registry group: **85 passed**, exit 0.
- Owner API/scheduler/staff group: **72 passed**, exit 0.
- Frozen diff scan under `app/voice_agent` and `app/telephony`: **0 paths**.
- Runtime summary: `docs/evidence/DSH_LINUX_CI_EVIDENCE_20260814.json`.

## Exact blockers / deliberately unverified

1. The 120-case golden execution, 2,000-turn / 14-day production shadow soak,
   latency/failure/DLQ metrics, and production trace hashes are **not done**.
2. AUTH-DEPLOY, shadow arm, every authority wave, and final legacy deletion
   each require separate owner authorization.
3. Legacy removal remains blocked until 30 consecutive green production days,
   a recorded rollback game-day, caller/import scan, direct `/health` evidence,
   and separate deletion authorization.
