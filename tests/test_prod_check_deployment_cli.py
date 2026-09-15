"""`prod_check.py --deployment` — the canonical deployment preflight.

Two modes, one checker:

    python scripts/prod_check.py               general repository readiness
    python scripts/prod_check.py --deployment  actual pre-deploy gate

REWRITTEN 2026-09-15 — what this file no longer tests, and why
--------------------------------------------------------------
This module used to be dominated by a ``VOICE_LAUNCH_KILL`` ENV preflight harness
(``_main`` plus a spy on ``check_voice_launch_kill_env``). That preflight was a
SELF-BLOCKING control: it passed only on a TRUE token, i.e. it refused to ship
unless the kill switch was ENGAGED — while ``VOICE_LAUNCH_KILL=0`` is the normal,
documented state of a live calling campaign (prod-verified 2026-09-15). Wired
correctly it would have blocked every healthy release, and its invocation had
already been lost in commit db5b1ceb, so four assertions here were RED against a
gate that ran nowhere. The preflight is deleted; see the NOTE in
``scripts/prod_check.py`` for the full reasoning and why it must not return.

Four fence-specific tests were removed with it (two here, the classification and
blocker-policy suite in the now-deleted ``test_voice_launch_kill_preflight.py``).
No assertion about RELEASE SAFETY was dropped: the tests below are the ones that
actually protect a deploy, and they were never about the voice kill switch at all.

WHAT REMAINS IS THE REAL CONTRACT
---------------------------------
  * ``--deployment`` exists on the published CLI, and an unrecognised flag does
    not silently degrade to general mode (a typo must fail, not skip the gate);
  * ``deploy_vps.sh`` invokes the canonical preflight EXACTLY once, inside the
    candidate image;
  * that preflight runs BEFORE every operation that mutates production;
  * the runtime-data guard runs before the build, the gate, and the pull.

Does not run GitHub Actions or a real deploy. Script text is the contract.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "prod_check.py"


# ------------------------------------------------------------ published CLI


def test_real_cli_accepts_the_deployment_flag():
    """The published interface must exist on the actual script, not just main()."""
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=180,
    )
    assert "--deployment" in (r.stdout + r.stderr)


def test_unknown_argument_is_rejected():
    """An unrecognised flag must never silently degrade to general mode.

    A typo that falls through to general mode runs a weaker checker while
    reporting success — the exact shape of a gate that is bypassed by accident.
    """
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--deploymnet"],  # typo on purpose
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=180,
    )
    assert r.returncode != 0, r.stdout + r.stderr


# --------------------------------------------- deploy_vps.sh ordering proof


def _deploy_lines():
    """Executable lines only — a commented mention must not count as a gate."""
    raw = (REPO / "scripts" / "deploy_vps.sh").read_text(encoding="utf-8").splitlines()
    return [
        (i + 1, ln) for i, ln in enumerate(raw) if ln.strip() and not ln.strip().startswith("#")
    ]


def _preflight_invocations():
    """Real invocations only — an `echo` that merely names the command is not a gate."""
    return [
        (n, ln)
        for n, ln in _deploy_lines()
        if "scripts/prod_check.py --deployment" in ln and not ln.strip().startswith("echo")
    ]


def test_deploy_invokes_the_canonical_preflight_exactly_once():
    hits = _preflight_invocations()
    assert len(hits) == 1, hits
    # Since 2026-07-28 the gate runs inside the CANDIDATE image rather than on
    # the host, because the host has never had fastapi/pydantic and the gate
    # could therefore only ever fail closed. The invocation is a container
    # runner, and `python` is the interpreter it hands the script to.
    assert "gate_run_image" in hits[0][1], hits[0][1]
    runner = (REPO / "scripts" / "_deploy_gate_container.sh").read_text(encoding="utf-8")
    assert "docker run --rm" in runner and "python " in runner


def test_preflight_precedes_every_destructive_operation():
    """The gate must precede everything that MUTATES production.

    `git fetch` (object database), the candidate worktree and the candidate
    image build are deliberately excluded: none of them moves the live checkout
    or replaces a container, and requiring the gate before them would mean
    gating code that has not been fetched yet — which is how the gate ended up
    unable to run at all.
    """
    lines = _deploy_lines()
    gate = _preflight_invocations()[0][0]
    mutators = [
        (n, ln)
        for n, ln in lines
        for pat in (
            "git pull",
            "git reset",
            "git clean",
            "docker compose up",
            "_compose_up",
            "docker push",
            "ssh ",
            "scp ",
            "rsync ",
        )
        if pat in ln
    ]
    assert mutators, "no mutating operations found — parser is wrong"
    first = min(n for n, _ in mutators)
    assert gate < first, f"preflight at {gate} runs after mutation at {first}"


def test_runtime_data_guard_precedes_the_deployment_gate_and_the_build():
    """Ordering the isolated-candidate flow depends on.

    The runtime-data guard is the FIRST decision: it is what stands between the
    release and the ledgers that still live inside the checkout. Building an
    image before it has spoken would be wasteful; pulling before it has spoken
    would be the incident this whole workstream exists to prevent.
    """
    lines = _deploy_lines()
    guard = next(
        n for n, ln in lines if "_runtime_data_guard.sh" in ln and ln.strip().startswith(".")
    )
    build = next(n for n, ln in lines if "BUILD candidate" in ln)
    gate = _preflight_invocations()[0][0]
    pull = next(
        n for n, ln in lines if "git pull --ff-only" in ln and not ln.strip().startswith("echo")
    )
    assert guard < build < gate < pull, (guard, build, gate, pull)


@pytest.mark.parametrize("flag", ["--deployment"])
def test_deployment_flag_help_text_mentions_pre_deploy_gates(flag):
    """The flag must describe itself as the pre-deploy gate, not a variant."""
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=180,
    )
    assert flag in r.stdout
    assert "pre-deploy" in r.stdout or "before an actual production deploy" in r.stdout
