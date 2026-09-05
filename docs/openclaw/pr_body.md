## Summary
Replace 4-way pytest sharding matrix with single optimized pytest job using pytest-xdist.

### Changes
- Remove `pytest-shards` matrix job (4-way `--splits 4 --group`)
- Add `pytest-job`: single `pytest -m "not network" -n auto --timeout=60` with pytest-xdist
- Update `tests` aggregator `needs` to reference `pytest-job` instead of `pytest-shards`
- Keep required check name `prod_check + pytest` unchanged for branch protection

### Rationale
- 4 parallel shards added matrix overhead + aggregator bottleneck (ALL 4 must pass)
- Non-deterministic which shard contains failures
- Same test coverage preserved (`-m "not network"`)
- Target: 3-8 min CI wall-clock vs previous 17+ min
- ~81% reduction in pytest runner minutes

### Verification
- All 3 target test suites pass: 38/38 (test_explorer_sync.py, test_issue237_ci_diagnostic.py, test_celery_queue_routing.py)
- YAML syntax validated
- Job dependencies verified: tests needs [prod-check, pytest-job, pip-audit]