"""Keep required CI lanes active for every commit pushed to main."""

import re
from pathlib import Path

CI = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
REQUIRED_JOBS = ("prod-check", "pip-audit", "pytest-job", "harness-redis-integration")


def _job_block(source: str, job: str) -> str:
    match = re.search(rf"^  {re.escape(job)}:\n(.*?)(?=^  [a-z][\w-]*:|\Z)", source, re.M | re.S)
    assert match, f"CI job missing: {job}"
    return match.group(1)


def test_main_push_runs_every_required_lane() -> None:
    source = CI.read_text(encoding="utf-8")
    trigger = source.split("on:\n", 1)[1].split("\nconcurrency:", 1)[0]
    push = trigger.split("  push:\n", 1)[1].split("\n  pull_request:", 1)[0]
    assert "branches: [main]" in push
    assert "paths-ignore:" not in push
    for job in REQUIRED_JOBS + ("tests",):
        assert "github.event_name == 'push'" in _job_block(source, job)


def test_aggregate_still_blocks_failed_lanes() -> None:
    source = CI.read_text(encoding="utf-8")
    aggregate = _job_block(source, "tests")
    assert "name: prod_check + pytest" in aggregate
    for job in REQUIRED_JOBS + ("quality",):
        assert f"needs['{job}'].result" in aggregate
    assert aggregate.count('= "success"') == len(REQUIRED_JOBS) + 1
