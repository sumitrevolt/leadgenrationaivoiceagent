# Branch Protection Ruleset Fix

## Problem
The GitHub branch protection ruleset on `main` requires 4 pytest shard check names that are obsolete after the CI redesign from 4-way sharding to single optimized pytest-job.

## Current Required Contexts (do NOT rename)
1. `Lint + syntax + secrets`
2. `prod_check + pytest` (aggregator over parallel lanes)
3. `harness real-redis integration`

## Obsolete Contexts to Remove
The following 4 check names should be removed from the ruleset as they are from the old 4-way pytest sharding matrix:
- `pytest shard 1/4`
- `pytest shard 2/4`
- `pytest shard 3/4`
- `pytest shard 4/4`

## Rationale
- CI was redesigned (commit 5708b677) from 4-way matrix to single `pytest-job` using `pytest-xdist -n auto`
- Wall-clock reduced from ~17 min to ~5-8 min
- Same test coverage preserved via `-m "not network"` filter
- The `tests: prod_check + pytest` aggregator job now depends on `pytest-job` instead of `pytest-shards`
- Keeping obsolete check names causes PR merges to fail because those contexts never report

## Action Items for Owner
1. Go to GitHub → Settings → Branches → Rulesets
2. Find the ruleset protecting `main` branch
3. Remove the 4 `pytest shard X/4` check names from the "Required checks" section
4. Ensure only these 3 remain:
   - `Lint + syntax + secrets`
   - `prod_check + pytest`
   - `harness real-redis integration`
5. Save the ruleset

## Expected Outcome
- PRs will no longer be permanently blocked due to missing shard check reports
- CI gate will be faster (~60% wall-clock reduction)
- Same regression protection preserved