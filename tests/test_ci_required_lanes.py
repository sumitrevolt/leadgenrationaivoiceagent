"""Contract: CI lanes keep the Protect-main required check names.

2026-08-15 merge-train bottleneck: `prod_check + pytest` ran four pytest shards
sequentially in one job (~17 min) and then the same suite ran AGAIN on main
after auto-merge. DeepSeek Harness CI (independent lanes + named aggregator +
cancel-in-progress only on non-push) is the layout we steal. Runtime DSH flags
stay OFF — this file only locks the GitHub Actions contract.

Does not run GitHub Actions. Workflow text is the contract under review.

--------------------------------------------------------------------------------
2026-09-14 RE-ANCHOR (Engineering Assurance task #7)
--------------------------------------------------------------------------------
Four tests here had silently rotted: they still referenced a `pytest-shards`
matrix job that was deleted on 2026-09-04 (replaced by a single `pytest-job`
running pytest-xdist), and a stale `pydantic-core==2.46.4` literal. They were
RED inside the required pytest lane, but the aggregator only *echoed* that
lane's result, so the merge went green anyway. The aggregator now ASSERTS the
lane (Rex, task #3) — which EXPOSED the rot.

They are re-anchored, not weakened:
  * lane names are DERIVED from the aggregator's own `needs:` block, so a future
    restructure cannot silently orphan these assertions again;
  * every job referenced in `needs:` must exist in `jobs:` (a rename fails
    loudly instead of KeyError-ing obscurely);
  * the pydantic-core pin is checked against the LOCK's documented pairing, not
    a hardcoded literal;
  * the parallel (not serial) invariant, the `always()` + `= "success"`
    assertions, the torch ban and the PR/dispatch-only gating are all kept.
No assertion was dropped. See deliverables/engineering-assurance/
testing-phase1-regression-2026-09-14.md §5 for the before/after.
"""

from __future__ import annotations

import re
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

# The ONLY lane deliberately allowed to run on a push to main: the fast,
# dependency-light gate. Every other lane is "heavy" and must be gated to
# pull_request / workflow_dispatch. Listing the exception explicitly (rather
# than inferring it from a missing `if:`) is what makes the heavy-lane test
# fail loudly if a heavy lane silently loses its gate.
ALWAYS_ON_LANES = {"quality"}


@pytest.fixture(scope="module")
def ci() -> dict:
    assert CI.is_file(), f"missing {CI}"
    data = yaml.safe_load(CI.read_text(encoding="utf-8"))
    assert data["name"] == "CI"
    return data


def _run_block(job: dict) -> str:
    """All `run:` shell text of a job, concatenated."""
    return "\n".join(str(step.get("run") or "") for step in job.get("steps") or [])


def _aggregator(ci: dict) -> tuple[str, dict]:
    """The single required-check aggregator job — the one with a `needs:` block."""
    candidates = {k: j for k, j in ci["jobs"].items() if j.get("needs")}
    assert len(candidates) == 1, (
        f"expected exactly one aggregator job (one with `needs:`); got {sorted(candidates)}"
    )
    return next(iter(candidates.items()))


def _pytest_lanes(ci: dict, agg: dict) -> list[str]:
    """The aggregator-required lanes that run the FULL network-free suite.

    Keyed on the `-m "not network"` full-suite marker, so single-file lanes such
    as `harness-redis-integration` (legitimately serial) are not misclassified.
    """
    return [
        lane
        for lane in agg["needs"]
        if "pytest" in _run_block(ci["jobs"][lane])
        and "not network" in _run_block(ci["jobs"][lane])
    ]


def test_required_check_names_are_exact(ci: dict) -> None:
    names = {job.get("name") or key for key, job in ci["jobs"].items()}
    missing = [n for n in REQUIRED_JOB_NAMES if n not in names]
    assert not missing, f"renaming a required check blocks every PR: {missing}"


def test_pytest_lane_runs_parallel_not_serial(ci: dict) -> None:
    """Invariant: the required pytest lane runs in PARALLEL, never as a serial loop.

    Re-anchored 2026-09-14. The old 4-way `pytest-shards` matrix became a single
    `pytest-job` with pytest-xdist. The invariant is unchanged and this is now
    STRONGER: it also asserts `-n auto` and the xdist extra are present.
    """
    _, agg = _aggregator(ci)
    lanes = _pytest_lanes(ci, agg)
    assert lanes, "the aggregator requires no pytest lane"
    for lane in lanes:
        job = ci["jobs"][lane]
        run = _run_block(job)
        assert "-n auto" in run, f"{lane} does not run pytest in parallel (`-n auto` missing)"
        assert "for group in 1 2 3 4" not in run, (
            f"{lane} reverted to the old serial for-loop"
        )
        extras = " ".join(
            str((step.get("with") or {}).get("extras") or "")
            for step in job.get("steps") or []
        )
        assert "pytest-xdist" in extras, f"{lane} does not install pytest-xdist"


def test_aggregator_reports_failure_not_skip(ci: dict) -> None:
    """Skipped required contexts look like a missing check. `always()` plus a real
    `test ... = "success"` assertion for EVERY lane in `needs` keeps the named job
    red when a lane fails.

    Iterating `needs` (instead of a hardcoded name) is the durability fix: a
    future restructure cannot leave a lane required-but-unasserted. Every lane in
    `needs` must also exist in `jobs`, so a renamed job fails loudly here rather
    than KeyError-ing somewhere obscure.
    """
    _, agg = _aggregator(ci)
    assert agg["name"] == "prod_check + pytest"
    assert "always()" in str(agg.get("if") or "")

    assertion_lines = [
        line.strip()
        for line in _run_block(agg).splitlines()
        if line.strip().startswith("test ")
    ]
    assert assertion_lines, "the aggregator run block contains no `test` assertions"

    for lane in agg["needs"]:
        assert lane in ci["jobs"], (
            f"aggregator needs '{lane}' but no such job exists in `jobs` "
            "(renamed/removed job — fails loudly instead of KeyError)"
        )
        matching = [ln for ln in assertion_lines if f"needs['{lane}'].result" in ln]
        assert matching, (
            f"the aggregator does not ASSERT needs['{lane}'].result — a RED {lane} "
            "would not red the merge (echo-only is not a gate)"
        )
        assert any('"success"' in ln or "'success'" in ln for ln in matching), (
            f"the {lane} assertion does not compare to \"success\""
        )


def test_cancel_in_progress_spares_main_push(ci: dict) -> None:
    conc = ci["concurrency"]
    assert "github.event_name != 'push'" in str(conc.get("cancel-in-progress"))


def test_heavy_lanes_are_pr_or_dispatch_only(ci: dict) -> None:
    """Every heavy lane must run only on pull_request / workflow_dispatch, never on
    a push to main.

    Heavy lanes are every job except the aggregator and the explicitly-listed
    always-on fast gate (`ALWAYS_ON_LANES`). Deriving the set this way — instead
    of "jobs that happen to have an `if:`" — is what makes a heavy lane that
    SILENTLY LOSES its gate fail here, rather than quietly dropping out of the
    check. The set is cross-checked against the aggregator's `needs:` so a heavy
    lane can never run un-gated by the required check.
    """
    agg_key, agg = _aggregator(ci)
    for name in ALWAYS_ON_LANES:
        assert name in ci["jobs"], f"always-on lane '{name}' no longer exists (renamed?)"

    heavy = set(ci["jobs"]) - {agg_key} - ALWAYS_ON_LANES
    assert heavy, "no heavy (PR/dispatch-gated) lanes found"
    for key in sorted(heavy):
        job_if = str(ci["jobs"][key].get("if") or "")
        assert "pull_request" in job_if, (
            f"{key} is a heavy lane but is not gated to pull_request (runs on push?)"
        )
        assert "workflow_dispatch" in job_if, (
            f"{key} is a heavy lane but is not gated to workflow_dispatch"
        )
    assert heavy <= set(agg["needs"]), (
        f"heavy lanes not covered by the aggregator: {sorted(heavy - set(agg['needs']))}"
    )


def test_lock_install_does_not_pull_torch() -> None:
    text = CI.read_text(encoding="utf-8") + SETUP.read_text(encoding="utf-8")
    assert "torch torchaudio" not in text
    assert "download.pytorch.org" not in text
    assert SETUP.is_file()


def test_pydantic_core_pin_matches_the_lock_pairing() -> None:
    """The setup action's pydantic-core pin must match the LOCK's own pairing.

    Re-anchored 2026-09-14: this used to hardcode `pydantic-core==2.46.4`, which
    went stale the moment the lock moved. It now derives the expected version
    from `requirements.lock.txt` (the pydantic pin) and the pairing `tests.yml`
    documents for that pin, so a lock bump or an action drift fails loudly.
    """
    lock = (REPO / "requirements.lock.txt").read_text(encoding="utf-8")
    lock_m = re.search(r"^pydantic==(\d+\.\d+\.\d+)", lock, re.M)
    assert lock_m, "requirements.lock.txt no longer pins pydantic"
    lock_pydantic = lock_m.group(1)

    doc = TESTS.read_text(encoding="utf-8")
    doc_m = re.search(
        r"pydantic\s+(\d+\.\d+\.\d+)\s+declares\s+pydantic-core==(\d+\.\d+\.\d+)", doc
    )
    assert doc_m, "tests.yml no longer documents the pydantic -> pydantic-core pairing"
    assert doc_m.group(1) == lock_pydantic, (
        f"tests.yml documents pydantic {doc_m.group(1)} but the lock pins {lock_pydantic}"
    )
    expected_core = doc_m.group(2)

    action = SETUP.read_text(encoding="utf-8")
    action_m = re.search(r'pydantic-core==(\d+\.\d+\.\d+)', action)
    assert action_m, "the setup action no longer pins pydantic-core explicitly"
    assert action_m.group(1) == expected_core, (
        f"action.yml pins pydantic-core=={action_m.group(1)} but the lock's pairing "
        f"for pydantic {lock_pydantic} is =={expected_core} — CI install has drifted"
    )


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


# --------------------------------------------------------------- T-1 pin
# The specific 2026-09-14 regression: a RED pytest lane still greened the merge
# because the aggregator echoed `needs['pytest-job'].result` instead of asserting
# it. Kept as a focused structural check in addition to the generic test above.


def test_aggregator_run_block_asserts_pytest_job_result_not_echoes(ci: dict) -> None:
    """The required check must go RED when the pytest lane is RED.

    A real shell assertion line (one that starts with `test`) must reference
    `needs['<pytest-lane>'].result` and compare it to `"success"`. A comment, an
    `echo`, or a mention elsewhere in the file must NOT satisfy it.
    """
    _, agg = _aggregator(ci)
    assert agg["name"] == "prod_check + pytest"
    lanes = _pytest_lanes(ci, agg)
    assert lanes, "the aggregator requires no pytest lane"

    assertion_lines = [
        line.strip()
        for line in _run_block(agg).splitlines()
        if line.strip().startswith("test ")
    ]
    assert assertion_lines, "the aggregator run block contains no `test` assertions"

    for lane in lanes:
        assert any(
            f"needs['{lane}'].result" in line
            and ('"success"' in line or "'success'" in line)
            for line in assertion_lines
        ), (
            f"the required-check aggregator must ASSERT needs['{lane}'].result == "
            "'success' (a real `test` line), not merely echo it — a RED pytest "
            "would otherwise still green the merge"
        )


def test_aggregator_does_not_rely_on_echo_for_any_required_lane(ci: dict) -> None:
    """No lane in the aggregator's `needs` may be reported by an `echo` alone.

    Belt-and-braces: any lane that is echoed must ALSO be `test`-asserted, so a
    future edit that reverts a lane to echo-only fails here.
    """
    _, agg = _aggregator(ci)
    lines = [line.strip() for line in _run_block(agg).splitlines()]
    lanes = set(agg["needs"])

    echoed = {
        lane
        for line in lines
        if line.startswith("echo ")
        for lane in lanes
        if f"needs['{lane}'].result" in line
    }
    asserted = {
        lane
        for line in lines
        if line.startswith("test ")
        for lane in lanes
        if f"needs['{lane}'].result" in line
    }
    assert echoed <= asserted, (
        f"lanes echoed but never asserted (echo is informational only): "
        f"{sorted(echoed - asserted)}"
    )
