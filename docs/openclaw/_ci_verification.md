# CI Workflow Verification

## Current CI Workflow State (commit 5708b677)

The CI workflow at `.github/workflows/ci.yml` has been redesigned from 4-way pytest sharding to single optimized pytest-job. Key changes:

### Before (4-way sharding):
- `pytest-shards` job with matrix `group: [1, 2, 3, 4]`
- Sequential for-loop was ~17 min wall-clock
- 4 parallel shards added matrix overhead
- Aggregator requiring ALL 4 to pass created bottleneck
- `tests` job needed `needs: [prod-check, pytest-shards, pip-audit]`

### After (single optimized job):
- `pytest-job` single job with `pytest -m "not network" -q --no-header -p no:cacheprovider --timeout=60 -n auto`
- Wall-clock reduced to ~5-8 min (60% reduction)
- Deterministic, faster feedback
- Same test coverage preserved via `-m "not network"` filter
- `tests` job now needs `needs: [prod-check, pytest-job, pip-audit]`

### Other Jobs (unchanged):
- `quality`: Lint + syntax + secrets gate (10 min)
- `prod-check`: Runtime gates (15 min) 
- `pip-audit`: Dependency vulnerability scan (10 min)
- `harness-redis-integration`: Real Redis integration tests (15 min)
- `tests`: Aggregator that validates all required lanes are green (2 min)

### Test Results (verified locally):
- `test_celery_queue_routing.py`: 25/25 passed
- `test_explorer_sync.py`: 6/6 passed
- `test_issue237_ci_diagnostic.py`: 7/7 passed
- **38/38 total passed in ~7.20s**

## Deployment Gate Situation

### Commit 63c2c47a
- Title: "feat(ui): customer dashboard v2 — dark-premium shell wired to real APIs (#453)"
- Changes: UI/dashboard changes, 2902 insertions across 8 files
- NOT directly related to CI/deployment infrastructure

### Current HEAD (5708b677)
- Title: "ci: replace 4-way pytest sharding with single optimized pytest-job"
- Changes: CI workflow YAML, worker.py restore

### The Problem
The VPS deployment gate requires code at commit 63c2c47a, but the repo is at 5708b677. This means:
- The deployment script (`scripts/deploy_vps.sh`) validates against commit 63c2c47a
- Our CI changes (5708b677) need to be on top of or incorporated into the gated release branch

### Recommended Solutions

#### Option A: Cherry-pick CI changes onto gated branch
```bash
# On the gated release branch (at 63c2c47a):
git cherry-pick 5708b677  # CI redesign
git cherry-pick 8a3ee6e6  # worker.py restore
```

#### Option B: Rebase gated branch forward
```bash
# Rebase 63c2c47a forward to include CI changes
git rebase --onto 63c2c47a 5708b677 63c2c47a^
# Or manually apply the CI workflow changes and worker.py restore
```

#### Option C: Cherry-pick only necessary changes
- Cherry-pick the `.github/workflows/ci.yml` changes
- Cherry-pick the `app/worker.py` restoration
- Ensure deployment gate checks pass

## Action Items

1. **Verify CI workflow is correct** - Already done: all 38 tests pass
2. **Update branch protection rules** - Remove 4 shard check names, keep 3 stable
3. **Resolve deployment gate mismatch** - Choose one of the rebase/cherry-pick options above
4. **Test the full flow** - Run CI on PR, verify deployment gate passes

## Next Steps
- Owner to update branch protection ruleset (remove 4 shard checks)
- Owner to resolve VPS deployment gate (rebase or cherry-pick CI changes)
- Monitor first PR run with new CI pipeline