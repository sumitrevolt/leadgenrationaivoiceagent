"""Targeted guard for the ISSUE-237 CI diagnostic slice.

Scope is deliberately tiny: prove the diagnostic is (a) parseable YAML,
(b) ordered correctly relative to the resolving install and the gates it must not
disturb, (c) incapable of failing the build, and (d) capturing every artefact the
owner asked for. It asserts nothing about #237's cause — that stays open until
fresh CI evidence lands.

Also pins the two things this slice must NOT do: change a dependency pin, or
alter existing workflow behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "tests.yml"
DIAGNOSTIC_STEP = "ISSUE-237 dependency drift diagnostic (never fails)"
RESOLVING_INSTALL = "pip install pytest-github-actions-annotate-failures"


def _job() -> dict:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = data["jobs"]
    assert len(jobs) == 1, "tests.yml is expected to hold exactly one job"
    return next(iter(jobs.values()))


def _step_names() -> list[str]:
    return [s.get("name") or s.get("uses") or "" for s in _job()["steps"]]


def _step(name: str) -> dict:
    for step in _job()["steps"]:
        if (step.get("name") or "") == name:
            return step
    raise AssertionError(f"step not found: {name}")


def test_workflow_is_valid_yaml_and_job_shape_is_intact():
    job = _job()
    assert job["runs-on"] == "ubuntu-latest"
    assert job["timeout-minutes"] == 25
    names = _step_names()
    assert names.count(DIAGNOSTIC_STEP) == 1, "diagnostic must appear exactly once"


def test_step_order_diagnostic_sits_between_install_and_prod_check():
    names = _step_names()
    install = next(i for i, n in enumerate(names) if n.startswith("Install deps"))
    diag = names.index(DIAGNOSTIC_STEP)
    prod_check = next(i for i, n in enumerate(names) if n.startswith("prod_check"))
    tests = next(i for i, n in enumerate(names) if n.startswith("Targeted test suites"))

    assert install < diag < prod_check < tests, (
        "diagnostic must run after the resolving install (so 'after' is real) and "
        f"before the gates it must not disturb; got order {names}"
    )


def test_diagnostic_can_never_fail_the_build():
    """Every command is either tolerated with `|| true` or a plain echo. A gate
    that can turn CI red is not a diagnostic."""
    run = _step(DIAGNOSTIC_STEP)["run"]
    for line in run.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("echo "):
            continue
        assert stripped.endswith("|| true"), f"diagnostic command may fail the build: {stripped!r}"


def test_diagnostic_captures_every_required_artefact():
    """Owner-specified capture list: pydantic, pydantic-core, the annotate
    package version, and pip check."""
    run = _step(DIAGNOSTIC_STEP)["run"]
    for needle in ("pydantic", "pydantic-core", "pytest-github-actions-annotate-failures"):
        assert needle in run, f"diagnostic must capture {needle}"
    assert "pip check" in run, "diagnostic must capture pip check output"
    assert "pip freeze" in run, "version capture must come from pip freeze"


def test_before_snapshot_exists_and_precedes_the_resolving_install():
    """A before/after comparison needs the 'before' taken *before* the install."""
    install_step = next(
        s for s in _job()["steps"] if (s.get("name") or "").startswith("Install deps")
    )
    run = install_step["run"]
    assert "ISSUE-237 BEFORE" in run, "missing the before-snapshot"
    assert run.index("ISSUE-237 BEFORE") < run.index(RESOLVING_INSTALL), (
        "the before-snapshot must be taken before the resolving install"
    )
    assert "pip freeze" in run.split(RESOLVING_INSTALL)[0]


def test_slice_changes_no_dependency_pin():
    """This slice is diagnostics-only. The install lines must be byte-identical to
    the pinned discipline they had before: lock install stays --no-deps, and the
    only pinned test-tool install keeps its pin."""
    install_step = next(
        s for s in _job()["steps"] if (s.get("name") or "").startswith("Install deps")
    )
    run = install_step["run"]
    assert "pip install --no-deps -r requirements.lock.txt" in run
    assert 'pip install --no-deps "pytest-timeout==2.4.0"' in run
    # The suspect install is deliberately left UNPINNED and dependency-resolving —
    # pinning it would be the fix, and the fix is not part of this slice.
    assert RESOLVING_INSTALL in run
    assert f"{RESOLVING_INSTALL}==" not in run, "no pin change belongs in this slice"


def test_lock_pairing_is_internally_consistent():
    """The bad-lock-pin hypothesis, kept falsified in code rather than prose:
    pydantic and pydantic-core ship as an exactly-pinned pair, and the lock must
    agree with what pydantic itself declares."""
    lock = (REPO / "requirements.lock.txt").read_text(encoding="utf-8")
    pins = dict(
        line.split("==", 1)
        for line in (raw.strip() for raw in lock.splitlines())
        if "==" in line and not line.startswith("#")
    )
    assert pins.get("pydantic") == "2.13.4", f"unexpected pydantic pin: {pins.get('pydantic')}"
    assert pins.get("pydantic_core") == "2.46.4", (
        f"unexpected pydantic_core pin: {pins.get('pydantic_core')}"
    )
