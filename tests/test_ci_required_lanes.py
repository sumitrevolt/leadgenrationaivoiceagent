"""Contract: CI lanes keep the Protect-main required check names.

2026-08-15 merge-train bottleneck: `prod_check + pytest` ran four pytest shards
sequentially in one job (~17 min) and then the same suite ran AGAIN on main
after auto-merge. DeepSeek Harness CI (independent lanes + named aggregator +
cancel-in-progress only on non-push) is the layout we steal. Runtime DSH flags
stay OFF — this file only locks the GitHub Actions contract.

Does not run GitHub Actions. Workflow text is the contract under review.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parents[1]
CI = REPO / ".github" / "workflows" / "ci.yml"
TESTS = REPO / ".github" / "workflows" / "tests.yml"
DEPLOY = REPO / ".github" / "workflows" / "deploy-vps.yml"
SETUP = REPO / ".github" / "actions" / "setup-python-lock" / "action.yml"

REQUIRED_JOB_NAMES = (
    "Lint + syntax + secrets",
    "prod_check + pytest",
    "harness real-redis integration",
)


@pytest.fixture(scope="module")
def ci() -> dict:
    assert CI.is_file(), f"missing {CI}"
    data = yaml.safe_load(CI.read_text(encoding="utf-8"))
    assert data["name"] == "CI"
    return data


def test_required_check_names_are_exact(ci: dict) -> None:
    names = {job.get("name") or key for key, job in ci["jobs"].items()}
    missing = [n for n in REQUIRED_JOB_NAMES if n not in names]
    assert not missing, f"renaming a required check blocks every PR: {missing}"


def test_pytest_is_a_parallel_matrix_not_a_serial_loop(ci: dict) -> None:
    shards = ci["jobs"]["pytest-shards"]
    matrix = (shards.get("strategy") or {}).get("matrix") or {}
    assert matrix.get("group") == [1, 2, 3, 4]
    run_blocks = "\n".join(str(step.get("run") or "") for step in shards.get("steps") or [])
    assert "for group in 1 2 3 4" not in run_blocks
    aggregator = ci["jobs"]["tests"]
    assert aggregator["name"] == "prod_check + pytest"
    assert "pytest-shards" in aggregator["needs"]
    assert "prod-check" in aggregator["needs"]
    assert "pip-audit" in aggregator["needs"]


def test_aggregator_reports_failure_not_skip(ci: dict) -> None:
    """Skipped required contexts look like a missing check. always() + result
    tests keep the named job red when a lane fails."""
    tests = ci["jobs"]["tests"]
    assert "always()" in str(tests.get("if") or "")
    run = "\n".join(str(s.get("run") or "") for s in tests["steps"])
    assert "needs['pytest-shards'].result" in run
    assert '= "success"' in run or "= 'success'" in run


def test_cancel_in_progress_spares_main_push(ci: dict) -> None:
    conc = ci["concurrency"]
    assert "github.event_name != 'push'" in str(conc.get("cancel-in-progress"))


def test_heavy_lanes_are_pr_or_dispatch_only(ci: dict) -> None:
    for key in ("prod-check", "pytest-shards", "pip-audit", "harness-redis-integration"):
        job_if = str(ci["jobs"][key].get("if") or "")
        assert "pull_request" in job_if, key
        assert "workflow_dispatch" in job_if, key


def test_lock_install_does_not_pull_torch() -> None:
    text = CI.read_text(encoding="utf-8") + SETUP.read_text(encoding="utf-8")
    assert "torch torchaudio" not in text
    assert "download.pytorch.org" not in text
    assert SETUP.is_file()
    assert "pydantic-core==2.46.4" in SETUP.read_text(encoding="utf-8")


def test_tests_yml_does_not_duplicate_pr_pytest() -> None:
    header = TESTS.read_text(encoding="utf-8").split("jobs:", 1)[0]
    assert "\n  pull_request:" not in header
    assert "\npull_request:" not in header


def test_deploy_vps_does_not_block_release_on_retest_shards() -> None:
    data = yaml.safe_load(DEPLOY.read_text(encoding="utf-8"))
    shards = data["jobs"]["pytest-shards"]
    assert "DEPLOY_RETEST" in str(shards.get("if") or "")
    release = data["jobs"]["release-gate"]
    assert release["needs"] == ["gate"]
    assert "pytest-shards" not in release["needs"]
