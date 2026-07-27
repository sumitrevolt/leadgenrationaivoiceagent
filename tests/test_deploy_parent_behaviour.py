"""Behavioural harness for the canonical release parent (`scripts/deploy_vps.sh`).

Eight wrapper scripts are about to be consolidated under this parent, and the
whole safety argument for that consolidation is "the parent's guard covers
them". Every other test of this surface is TEXTUAL — it reads the file and
checks that the guard line appears before the `git pull` line. That proves
ordering in the source, not behaviour at runtime.

The distinction is not academic. Two things already went wrong in this exact
shape:

  * `vps_selfheal.sh` was classified from a grep of its comments and the
    classification was wrong in both directions.
  * A canary test asserted a provider was never called, and passed only
    because execution stopped at step one — the assertion was vacuous.

So this harness EXECUTES the parent against stub `git`/`docker` binaries and
asserts what actually happened:

  1. preflight DENIES  -> exit 90, and zero mutating commands were invoked
  2. preflight PERMITS -> `git pull` IS invoked

Scenario 2 is the anti-vacuity control. Without it, scenario 1 would pass even
if the script were broken in some unrelated way and never reached any command.

The script is copied to a sandbox with `REPO=/opt/leadgen` rewritten, because
the real value makes the script exit at `cd "$REPO"` on any non-production
host — safe, but untestable. The test asserts that this is the ONLY difference,
so the thing under test cannot silently drift from the thing that ships.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import textwrap

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]
_DEPLOY = _REPO / "scripts" / "deploy_vps.sh"
_GUARD = _REPO / "scripts" / "_runtime_data_guard.sh"

# Commands that mutate the checkout or the running stack. If any of these is
# recorded after a denial, containment failed.
_MUTATING = ("git pull", "git reset", "git clean", "git checkout", "docker")


def _bash() -> str | None:
    """Prefer Git-for-Windows bash; never WSL.

    `shutil.which("bash")` on this machine returns C:\\Windows\\System32\\bash.exe,
    which is the WSL launcher: it takes Windows paths and hands them to a Linux
    filesystem, so every path silently loses its separators and the script is
    'not found' with exit 127. Ordering matters more than existence here.
    """
    candidates = [
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
        "/bin/bash",
        shutil.which("bash"),
    ]
    for cand in candidates:
        if not cand:
            continue
        p = pathlib.Path(cand)
        if not p.exists():
            continue
        if p.parent.name.lower() == "system32":  # WSL launcher, not a POSIX shell
            continue
        return str(p)
    return None


_BASH = _bash()
requires_bash = pytest.mark.skipif(_BASH is None, reason="bash unavailable")


def _stub(path: pathlib.Path, log: pathlib.Path, exit_code: int = 0) -> None:
    """A fake binary that records its argv and exits with `exit_code`."""
    path.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            echo "$(basename "$0") $*" >> {log.as_posix()!r}
            exit {exit_code}
            """
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _sandbox(tmp_path: pathlib.Path, *, preflight_exit: int) -> tuple[pathlib.Path, pathlib.Path]:
    """Build an isolated copy of the parent plus stub tooling.

    Returns (script_path, command_log).
    """
    scripts = tmp_path / "repo" / "scripts"
    scripts.mkdir(parents=True)
    log = tmp_path / "commands.log"
    log.write_text("", encoding="utf-8")

    original = _DEPLOY.read_text(encoding="utf-8")
    patched = original.replace("REPO=/opt/leadgen", f"REPO={(tmp_path / 'repo').as_posix()}", 1)
    # Honesty check: exactly one line may differ from what ships.
    diff = [
        (a, b) for a, b in zip(original.splitlines(), patched.splitlines(), strict=True) if a != b
    ]
    assert len(diff) == 1, f"sandbox rewrote more than the REPO line: {diff}"
    assert diff[0][0].strip() == "REPO=/opt/leadgen"

    (scripts / "deploy_vps.sh").write_text(patched, encoding="utf-8")
    shutil.copy2(_GUARD, scripts / "_runtime_data_guard.sh")

    # Stub tooling on PATH. `git`/`docker` succeed if called at all — we are
    # measuring WHETHER they are called, not how they behave.
    binmock = tmp_path / "bin"
    binmock.mkdir()
    for name in ("git", "docker", "curl"):
        _stub(binmock / name, log)

    # The parent also runs `python3 scripts/prod_check.py --deployment` before
    # any mutating step. It is a hardcoded `python3` (deliberately NOT
    # PYTHON_BIN, which drives the preflight), and the sandbox repo holds only
    # the two scripts under test — so without a stub the gate fails, the parent
    # exits 1, and every assertion past it becomes vacuous. Stubbing it records
    # WHETHER it ran and in what order, which is what this harness measures.
    _stub(binmock / "python3", log)

    # The guard runs `${PYTHON_BIN:-python3} runtime_data_preflight.py check-deploy`.
    # Driving the verdict through this stub lets us test both branches without
    # touching real production state or the real preflight's blockers.
    _stub(binmock / "preflight_python", log, exit_code=preflight_exit)

    return scripts / "deploy_vps.sh", log


def _env(tmp_path: pathlib.Path, **extra: str) -> dict[str, str]:
    """Build the child environment with a POSIX PATH.

    Using `os.pathsep` here was wrong: Git-bash parses PATH with ':', so a
    Windows ';'-joined value collapses into one nonsense entry and even
    `dirname` disappears. That is not cosmetic — it is what exposed the
    fail-open, because the guard's `.` source then failed and the script
    carried on regardless.
    """
    binmock = (tmp_path / "bin").as_posix()
    env = dict(os.environ)
    env.update(extra)
    env["PATH"] = f"{binmock}:/usr/bin:/bin"
    env["PYTHON_BIN"] = f"{binmock}/preflight_python"
    env.pop("APP_VERSION", None)
    return env


def _run(
    script: pathlib.Path, tmp_path: pathlib.Path, **extra: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_BASH), str(script)],
        capture_output=True,
        text=True,
        env=_env(tmp_path, **extra),
        timeout=120,
        cwd=str(tmp_path),
    )


def _assert_harness_ran(proc: subprocess.CompletedProcess[str]) -> None:
    """Distinguish 'the harness is broken' from 'the guard failed'.

    Exit 127 means bash never found the script. An earlier version of this file
    reported that as "a bypass env var defeated the guard" — a false alarm
    pointing at the wrong subsystem, which is precisely the failure mode that
    cost time on the /api/voice/niches bug.
    """
    assert proc.returncode != 127, (
        "HARNESS BROKEN (not a guard failure): bash could not execute the "
        f"sandboxed script.\nSTDERR:\n{proc.stderr}"
    )


def _mutations(log: pathlib.Path) -> list[str]:
    lines = [ln.strip() for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [ln for ln in lines if any(ln.startswith(m.split()[0]) for m in _MUTATING)]


@requires_bash
def test_denied_preflight_aborts_before_any_mutation(tmp_path: pathlib.Path) -> None:
    """The load-bearing claim: denial stops the parent before it touches anything."""
    script, log = _sandbox(tmp_path, preflight_exit=1)
    proc = _run(script, tmp_path)

    _assert_harness_ran(proc)
    assert proc.returncode == 90, (
        f"expected guard exit 90, got {proc.returncode}\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert "DENIED" in proc.stdout, proc.stdout

    recorded = _mutations(log)
    assert recorded == [], f"mutating commands ran after denial: {recorded}"


@requires_bash
def test_permitted_preflight_reaches_git_pull(tmp_path: pathlib.Path) -> None:
    """Anti-vacuity control.

    Without this, the denial test would still pass if the script never reached
    any command for an unrelated reason — which is exactly how an earlier
    canary test fooled me.
    """
    script, log = _sandbox(tmp_path, preflight_exit=0)
    _run(script, tmp_path)

    lines = log.read_text(encoding="utf-8")
    assert "git pull" in lines, (
        "permitted preflight did not reach `git pull` — the denial test above "
        f"may be vacuous. recorded:\n{lines}"
    )


@requires_bash
def test_guard_runs_before_the_first_recorded_command(tmp_path: pathlib.Path) -> None:
    """Ordering proven by execution, not by line numbers.

    BOTH release gates are asserted, in the order the parent actually runs them:

        runtime_data_preflight check-deploy   (sourced guard, exit 90 on denial)
            before
        prod_check.py --deployment            (canonical deployment gate)
            before
        the first mutating command

    Asserting only the first gate would let the second one be moved below
    `git pull`, or dropped entirely, with this harness still green — and a gate
    that runs after the checkout has already moved protects nothing.
    """
    script, log = _sandbox(tmp_path, preflight_exit=0)
    _run(script, tmp_path)

    lines = [ln.strip() for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines, "nothing was recorded at all"
    preflight_idx = next(
        (i for i, ln in enumerate(lines) if ln.startswith("preflight_python")), None
    )
    assert preflight_idx is not None, f"preflight never ran:\n{lines}"

    deployment_gate_idx = next(
        (
            i
            for i, ln in enumerate(lines)
            if ln.startswith("python3") and "prod_check.py" in ln and "--deployment" in ln
        ),
        None,
    )
    assert (
        deployment_gate_idx is not None
    ), f"the deployment gate `prod_check.py --deployment` never ran:\n{lines}"

    mutating_idx = [
        i for i, ln in enumerate(lines) if any(ln.startswith(m.split()[0]) for m in _MUTATING)
    ]
    assert mutating_idx, "no mutating command recorded on the permitted path"
    assert preflight_idx < min(
        mutating_idx
    ), f"a mutating command ran BEFORE the preflight:\n{lines}"
    assert deployment_gate_idx < min(
        mutating_idx
    ), f"a mutating command ran BEFORE the deployment gate:\n{lines}"
    assert preflight_idx < deployment_gate_idx, (
        "the runtime-data guard must be the first gate — it is sourced before "
        f"the deployment gate in the parent:\n{lines}"
    )


@requires_bash
def test_guard_has_no_bypass_at_runtime(tmp_path: pathlib.Path) -> None:
    """Environment variables must not be able to talk the guard out of a denial.

    Checking behaviour rather than grepping for a bypass name: any future
    bypass, whatever it is called, would have to make a denied preflight
    proceed — and that is what this asserts cannot happen.
    """
    script, log = _sandbox(tmp_path, preflight_exit=1)

    env_attempts = {
        "RUNTIME_DATA_CUTOVER_ENABLED": "1",
        "SKIP_PREFLIGHT": "1",
        "FORCE": "1",
        "RUNTIME_DATA_GUARD_BYPASS": "1",
        "CI": "true",
    }
    proc = _run(script, tmp_path, **env_attempts)
    _assert_harness_ran(proc)
    assert proc.returncode == 90, f"a bypass env var defeated the guard: {env_attempts}"
    assert _mutations(log) == []


@requires_bash
def test_missing_guard_file_fails_closed(tmp_path: pathlib.Path) -> None:
    """A guard that cannot be sourced must stop the release, not be skipped.

    THIS IS THE BUG THE HARNESS FOUND. `deploy_vps.sh` runs under
    `set -uo pipefail` with no `-e`, so a failed `.` source did not abort it:
    with the guard file absent the shell printed "No such file or directory"
    and went straight on to `git pull`. Every textual test passed the whole
    time, because the guard LINE was present and correctly ordered — it just
    did not do anything.

    That matters more than a normal fail-open: eight wrapper scripts are being
    consolidated under this parent precisely because "the parent's guard covers
    them", so a parent that silently skips its own guard would have voided the
    safety argument for all of them at once.
    """
    script, log = _sandbox(tmp_path, preflight_exit=1)
    (script.parent / "_runtime_data_guard.sh").unlink()

    proc = _run(script, tmp_path)
    _assert_harness_ran(proc)

    assert proc.returncode == 91, (
        "missing guard must abort with 91, not fall through.\n"
        f"got {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    recorded = _mutations(log)
    assert recorded == [], f"deployed with NO guard present: {recorded}"


@requires_bash
def test_guard_denial_and_guard_absence_are_distinguishable(tmp_path: pathlib.Path) -> None:
    """90 and 91 must not collapse into one code.

    An operator seeing 90 should look at the blocker list; seeing 91 they should
    look for a missing file. Collapsing them would send them to the wrong runbook.
    """
    denied_script, _ = _sandbox(tmp_path / "a", preflight_exit=1)
    denied = _run(denied_script, tmp_path / "a")

    absent_script, _ = _sandbox(tmp_path / "b", preflight_exit=1)
    (absent_script.parent / "_runtime_data_guard.sh").unlink()
    absent = _run(absent_script, tmp_path / "b")

    assert denied.returncode == 90
    assert absent.returncode == 91
    assert denied.returncode != absent.returncode
