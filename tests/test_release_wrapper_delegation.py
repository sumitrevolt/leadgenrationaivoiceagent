"""Behavioural proof that the consolidated release wrappers really delegate.

Each of these scripts used to carry its own copy of the release chain --
`cd /opt/leadgen`, `git pull --ff-only`, `compose build`, `compose up -d` --
with a pinned historical SHA. None of them touched the runtime-data guard, so
running any one of them deployed straight over the live ledgers inside the
checkout.

They now delegate to `deploy_vps.sh`. The claim being tested is NOT "the file
contains the word delegate": it is that when the parent denies, the wrapper
exits 90 and nothing mutates, and when the parent is unavailable it exits 91
and nothing mutates.

A textual test cannot establish that -- the Parent A fail-open proved it, where
the guard line was present, correctly ordered, and did nothing.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import textwrap

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO / "scripts"
_PARENT = "deploy_vps.sh"
_DELEGATE = "_deploy_parent_delegate.sh"

WRAPPERS = [
    "deploy_adr095.sh",
    "deploy_adr096.sh",
    "deploy_adr097.sh",
    "deploy_all.sh",
    "vps_flywheel_deploy.sh",
]

# Anything that changes the checkout or the running stack.
_MUTATING_RE = re.compile(
    r"^(git\s+(pull|reset|clean|checkout|stash)|docker\s+(compose|run|rm|stop|restart))"
)


def _bash() -> str | None:
    for cand in (
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
        "/bin/bash",
        shutil.which("bash"),
    ):
        if not cand:
            continue
        p = pathlib.Path(cand)
        # System32 bash.exe is the WSL launcher, which mangles Windows paths.
        if p.exists() and p.parent.name.lower() != "system32":
            return str(p)
    return None


_BASH = _bash()
requires_bash = pytest.mark.skipif(_BASH is None, reason="bash unavailable")


def _record_stub(path: pathlib.Path, log: pathlib.Path, exit_code: int = 0) -> None:
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


def _sandbox(tmp_path: pathlib.Path, wrapper: str, *, parent_rc: int | None):
    """Copy wrapper + delegate into a sandbox with a FAKE parent.

    `parent_rc=None` means the parent is absent entirely (tests the 91 path).
    The fake parent stands in for the real one deliberately: Parent A's own
    behaviour is proven in test_deploy_parent_behaviour.py, and re-testing it
    here would confuse "the wrapper propagates" with "the guard works".
    """
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True)
    log = tmp_path / "commands.log"
    log.write_text("", encoding="utf-8")

    shutil.copy2(_SCRIPTS / wrapper, scripts / wrapper)
    shutil.copy2(_SCRIPTS / _DELEGATE, scripts / _DELEGATE)
    if parent_rc is not None:
        _record_stub(scripts / _PARENT, log, exit_code=parent_rc)

    binmock = tmp_path / "bin"
    binmock.mkdir()
    for name in ("git", "docker", "curl", "sleep", "chmod"):
        _record_stub(binmock / name, log)

    return scripts / wrapper, log


def _run(script: pathlib.Path, tmp_path: pathlib.Path, **extra: str):
    env = dict(os.environ)
    env.update(extra)
    env["PATH"] = f"{(tmp_path / 'bin').as_posix()}:/usr/bin:/bin"
    return subprocess.run(
        [str(_BASH), str(script)],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        cwd=str(tmp_path),
    )


def _mutations(log: pathlib.Path) -> list[str]:
    return [
        ln.strip()
        for ln in log.read_text(encoding="utf-8").splitlines()
        if _MUTATING_RE.match(ln.strip())
    ]


def _assert_ran(proc, wrapper: str) -> None:
    """126/127 is a broken harness, not a passing security control."""
    assert proc.returncode not in (126, 127), (
        f"HARNESS BROKEN for {wrapper} (not a guard result): "
        f"rc={proc.returncode}\nSTDERR:\n{proc.stderr}"
    )


# --------------------------------------------------------------- propagation


@requires_bash
@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_parent_denial_propagates_as_90_with_no_mutation(
    wrapper: str, tmp_path: pathlib.Path
) -> None:
    script, log = _sandbox(tmp_path, wrapper, parent_rc=90)
    proc = _run(script, tmp_path)
    _assert_ran(proc, wrapper)

    assert proc.returncode == 90, (
        f"{wrapper} swallowed a guard denial (rc={proc.returncode}).\nSTDOUT:\n{proc.stdout}"
    )
    assert _mutations(log) == [], f"{wrapper} mutated after denial: {_mutations(log)}"


@requires_bash
@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_parent_unavailable_propagates_as_91_with_no_mutation(
    wrapper: str, tmp_path: pathlib.Path
) -> None:
    script, log = _sandbox(tmp_path, wrapper, parent_rc=None)
    proc = _run(script, tmp_path)
    _assert_ran(proc, wrapper)

    assert proc.returncode == 91, (
        f"{wrapper} continued with the parent ABSENT (rc={proc.returncode}).\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert _mutations(log) == [], f"{wrapper} mutated with no parent: {_mutations(log)}"


@requires_bash
@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_nothing_mutates_before_the_parent_is_invoked(wrapper: str, tmp_path: pathlib.Path) -> None:
    """Ordering by execution: the parent must be the FIRST recorded command."""
    script, log = _sandbox(tmp_path, wrapper, parent_rc=0)
    proc = _run(script, tmp_path)
    _assert_ran(proc, wrapper)

    lines = [ln.strip() for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines, f"{wrapper} recorded nothing at all"

    parent_idx = next((i for i, ln in enumerate(lines) if ln.startswith(_PARENT)), None)
    assert parent_idx is not None, f"{wrapper} never invoked the parent:\n{lines}"

    before = [ln for ln in lines[:parent_idx] if _MUTATING_RE.match(ln)]
    assert before == [], f"{wrapper} mutated BEFORE the guarded parent: {before}"


# --------------------------------------------------------------- anti-vacuity


@requires_bash
@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_permitted_path_actually_invokes_the_parent(wrapper: str, tmp_path: pathlib.Path) -> None:
    """Control: without this, the denial tests could pass on a script that
    exits early for some unrelated reason and never reaches anything."""
    script, log = _sandbox(tmp_path, wrapper, parent_rc=0)
    _run(script, tmp_path)

    recorded = log.read_text(encoding="utf-8")
    assert _PARENT in recorded, (
        f"{wrapper} never called the parent on the permitted path — the denial "
        f"tests may be vacuous. recorded:\n{recorded}"
    )


# ------------------------------------------------- legacy chain must be gone


@requires_bash
@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_no_independent_release_chain_remains(wrapper: str, tmp_path: pathlib.Path) -> None:
    """The old chain must be REMOVED, not merely bypassed.

    A wrapper that still contained `git pull` + `compose build` would remain an
    independent production mutation path regardless of what it does first, and
    would keep its own entry in the guard denominator.
    """
    text = (_SCRIPTS / wrapper).read_text(encoding="utf-8")
    executable = [
        ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")
    ]
    banned = [
        ln
        for ln in executable
        if re.search(r"\bgit\s+(pull|reset|clean|stash)\b", ln)
        or re.search(r"\bdocker\s+compose\b.*\bbuild\b", ln)
    ]
    assert banned == [], f"{wrapper} still owns a release chain: {banned}"


@requires_bash
@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_no_fallback_after_denial(wrapper: str, tmp_path: pathlib.Path) -> None:
    """Denial must be terminal.

    Proven behaviourally rather than by grepping for `||`: run with a denying
    parent and assert the wrapper produced no mutation at all, whatever
    control flow it uses internally.
    """
    script, log = _sandbox(tmp_path, wrapper, parent_rc=90)
    _run(script, tmp_path)
    lines = [ln.strip() for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    after_parent = lines[1:] if lines else []
    assert [ln for ln in after_parent if _MUTATING_RE.match(ln)] == [], (
        f"{wrapper} ran a fallback chain after denial: {after_parent}"
    )


@requires_bash
@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_no_environment_bypass(wrapper: str, tmp_path: pathlib.Path) -> None:
    script, log = _sandbox(tmp_path, wrapper, parent_rc=90)
    proc = _run(
        script,
        tmp_path,
        SKIP_PREFLIGHT="1",
        FORCE="1",
        RUNTIME_DATA_CUTOVER_ENABLED="1",
        RUNTIME_DATA_GUARD_BYPASS="1",
    )
    _assert_ran(proc, wrapper)
    assert proc.returncode == 90
    assert _mutations(log) == []


def test_delegate_helper_is_not_a_second_guard() -> None:
    """Enforcement must stay in ONE place.

    If the helper grew its own preflight call, there would be two places to
    keep correct and two places to weaken. It is allowed to check that the
    parent exists; it is not allowed to decide whether a deploy may proceed.
    """
    text = (_SCRIPTS / _DELEGATE).read_text(encoding="utf-8")
    executable = [
        ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")
    ]
    for ln in executable:
        assert "runtime_data_preflight" not in ln, f"helper duplicated the guard: {ln}"
        assert "_runtime_data_guard" not in ln, f"helper duplicated the guard: {ln}"
