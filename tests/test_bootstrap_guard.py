"""Bootstrap must be fresh-host only, and must prove it by executing.

`hostinger_hermes_bootstrap.sh` branched on `[ -d "$LOCAL_DIR/.git" ]` and, when
a checkout existed, ran `git reset --hard origin/main` against it. `LOCAL_DIR`
is an environment variable, so `LOCAL_DIR=/opt/leadgen` aimed that reset at the
production checkout holding the live ledgers and the DPDP recordings.

The file's own header says "sandbox". The default IS a sandbox. Neither fact
restricted anything, which is the whole lesson of this workstream: a comment is
not an enforcement mechanism and a default is not a restriction.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import textwrap

import pytest

from app.platform import bootstrap_target as bt

_REPO = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "hostinger_hermes_bootstrap.sh"
_PREFLIGHT = _REPO / "scripts" / "runtime_data_preflight.py"

_MUTATING = ("git", "pip", "docker")


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
        if p.exists() and p.parent.name.lower() != "system32":
            return str(p)
    return None


_BASH = _bash()
requires_bash = pytest.mark.skipif(_BASH is None, reason="bash unavailable")


# =========================================================== classifier layer


def test_empty_directory_is_fresh(tmp_path: pathlib.Path) -> None:
    r = bt.classify(str(tmp_path))
    assert r["classification"] == bt.FRESH_HOST, r["reasons"]
    assert bt.exit_code_for(r) == bt.EXIT_OK


def test_nonexistent_directory_is_fresh(tmp_path: pathlib.Path) -> None:
    r = bt.classify(str(tmp_path / "not-yet"))
    assert r["fresh_host"] is True, r["reasons"]


@pytest.mark.parametrize("marker", [".git", "data", ".env", "docker-compose.vps.yml"])
def test_installation_evidence_refuses(marker: str, tmp_path: pathlib.Path) -> None:
    (
        (tmp_path / marker).mkdir()
        if not marker.startswith(".env")
        else (tmp_path / marker).write_text("X=1", encoding="utf-8")
    )
    r = bt.classify(str(tmp_path))
    assert r["classification"] == bt.EXISTING_HOST
    assert bt.exit_code_for(r) == bt.EXIT_REFUSED
    assert any(x["code"] == "EXISTING_INSTALLATION" for x in r["reasons"])


def test_non_empty_unknown_content_is_not_assumed_fresh(tmp_path: pathlib.Path) -> None:
    """Unrecognised content means 'not proven fresh', not 'probably fine'."""
    (tmp_path / "someones_files.txt").write_text("hello", encoding="utf-8")
    r = bt.classify(str(tmp_path))
    assert r["fresh_host"] is False
    assert any(x["code"] == "TARGET_NOT_EMPTY" for x in r["reasons"])


def test_protected_root_refused_without_authorization() -> None:
    r = bt.classify("/opt/leadgen")
    assert r["fresh_host"] is False
    assert any(x["code"] == "TARGET_IS_PROTECTED_ROOT" for x in r["reasons"])


def test_authorize_flag_is_not_a_force_flag(tmp_path: pathlib.Path) -> None:
    """--authorize-protected-root removes ONE objection, not all of them.

    It must not be usable to bootstrap over a live installation.
    """
    (tmp_path / ".git").mkdir()
    r = bt.classify(str(tmp_path), authorize_protected_root=True)
    assert r["fresh_host"] is False
    assert any(x["code"] == "EXISTING_INSTALLATION" for x in r["reasons"])


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "relative/path", "../escape", "/tmp/../etc/x", "\\\\server\\share", "/tmp/a\x00b"],
)
def test_invalid_targets_refused(bad: str) -> None:
    r = bt.classify(bad)
    assert r["fresh_host"] is False, bad
    assert bt.exit_code_for(r) in (bt.EXIT_INVALID_TARGET, bt.EXIT_REFUSED)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_symlink_into_existing_checkout_refused(tmp_path: pathlib.Path) -> None:
    """The decision must follow the resolved path, not the pretty one.

    An empty-looking symlink that lands inside a real checkout is the exact
    shape that would otherwise sneak past a surface check.
    """
    real = tmp_path / "real"
    real.mkdir()
    (real / ".git").mkdir()
    link = tmp_path / "looks_empty"
    link.symlink_to(real, target_is_directory=True)

    r = bt.classify(str(link))
    assert r["fresh_host"] is False
    assert any(x["code"] == "EXISTING_INSTALLATION" for x in r["reasons"])


def test_runtime_data_root_inside_target_refused(tmp_path: pathlib.Path) -> None:
    """Cloning over a directory that contains the runtime-data root would
    orphan the very state this workstream exists to protect."""
    rd = tmp_path / "runtime"
    rd.mkdir()
    r = bt.classify(str(tmp_path), runtime_data_root=str(rd))
    assert r["fresh_host"] is False
    assert any(x["code"] == "RUNTIME_DATA_ROOT_INSIDE_TARGET" for x in r["reasons"])


# ============================================================ preflight CLI


def _preflight(target: str, *extra: str) -> subprocess.CompletedProcess[str]:
    import sys

    return subprocess.run(  # noqa: S603
        [sys.executable, str(_PREFLIGHT), "check-bootstrap", "--target", target, *extra],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(_REPO),
    )


def test_cli_allows_fresh_target(tmp_path: pathlib.Path) -> None:
    p = _preflight(str(tmp_path))
    assert p.returncode == bt.EXIT_OK, p.stdout + p.stderr


def test_cli_refuses_existing_checkout(tmp_path: pathlib.Path) -> None:
    (tmp_path / ".git").mkdir()
    p = _preflight(str(tmp_path))
    assert p.returncode == bt.EXIT_REFUSED, p.stdout
    assert bt.EXISTING_INSTALL_STATUS in p.stdout


def test_cli_has_no_force_flag() -> None:
    """A bypass must not exist at all, not merely be discouraged."""
    text = _PREFLIGHT.read_text(encoding="utf-8")
    executable = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    joined = "\n".join(executable)
    for banned in ("--force", "--ignore-existing", "--skip-preflight", "--emergency"):
        assert banned not in joined, f"bypass flag present: {banned}"


# ========================================================= behavioural harness


def _stub(path: pathlib.Path, log: pathlib.Path, exit_code: int = 0) -> None:
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


def _sandbox(tmp_path: pathlib.Path, *, with_preflight: bool = True):
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True)
    log = tmp_path / "commands.log"
    log.write_text("", encoding="utf-8")

    shutil.copy2(_SCRIPT, scripts / _SCRIPT.name)
    if with_preflight:
        shutil.copy2(_PREFLIGHT, scripts / _PREFLIGHT.name)

    binmock = tmp_path / "bin"
    binmock.mkdir()
    for name in _MUTATING + ("mkdir", "chmod", "curl"):
        _stub(binmock / name, log)
    return scripts / _SCRIPT.name, log, binmock


def _run(script, tmp_path, target: str, binmock, **extra):
    import sys

    env = dict(os.environ)
    env.update(extra)
    env["PATH"] = f"{binmock.as_posix()}:/usr/bin:/bin"
    env["LOCAL_DIR"] = target
    env["HOME"] = str(tmp_path / "home")
    env["PYTHON_BIN"] = sys.executable
    env["PYTHONPATH"] = str(_REPO)
    return subprocess.run(  # noqa: S603
        [str(_BASH), str(script)],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
        cwd=str(_REPO),
    )


def _mutations(log: pathlib.Path) -> list[str]:
    return [
        ln.strip()
        for ln in log.read_text(encoding="utf-8").splitlines()
        if ln.strip().split(" ")[0] in _MUTATING
    ]


@requires_bash
def test_existing_checkout_denied_with_zero_mutation(tmp_path: pathlib.Path) -> None:
    """The headline case: reset must never be reached on an existing install."""
    target = tmp_path / "install"
    (target / ".git").mkdir(parents=True)
    script, log, binmock = _sandbox(tmp_path)

    proc = _run(script, tmp_path, str(target), binmock)
    assert proc.returncode not in (126, 127), f"HARNESS BROKEN: {proc.stderr}"
    assert proc.returncode == bt.EXIT_REFUSED, proc.stdout + proc.stderr
    assert _mutations(log) == [], f"bootstrap mutated an existing install: {_mutations(log)}"


@requires_bash
def test_existing_data_dir_denied_with_zero_mutation(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "install"
    (target / "data").mkdir(parents=True)
    script, log, binmock = _sandbox(tmp_path)

    proc = _run(script, tmp_path, str(target), binmock)
    assert proc.returncode == bt.EXIT_REFUSED, proc.stdout
    assert _mutations(log) == []


@requires_bash
def test_fresh_target_reaches_the_first_intended_mutation(tmp_path: pathlib.Path) -> None:
    """Anti-vacuity control.

    Without this, every denial test above would still pass on a script that
    exits early for some unrelated reason and never reaches anything at all.
    """
    target = tmp_path / "brand-new"
    script, log, binmock = _sandbox(tmp_path)

    proc = _run(script, tmp_path, str(target), binmock)
    assert proc.returncode not in (126, 127), f"HARNESS BROKEN: {proc.stderr}"
    recorded = log.read_text(encoding="utf-8")
    assert "git clone" in recorded, (
        f"fresh target never reached the clone — denial tests may be vacuous.\n"
        f"rc={proc.returncode}\nSTDOUT:\n{proc.stdout}\nlog:\n{recorded}"
    )


@requires_bash
def test_local_dir_override_cannot_bypass_classification(tmp_path: pathlib.Path) -> None:
    """The original defect, tested directly: LOCAL_DIR pointing at a real
    checkout must be classified on what it RESOLVES to."""
    victim = tmp_path / "opt" / "leadgen"
    (victim / ".git").mkdir(parents=True)
    (victim / "data").mkdir(parents=True)
    script, log, binmock = _sandbox(tmp_path)

    proc = _run(script, tmp_path, str(victim), binmock)
    assert proc.returncode == bt.EXIT_REFUSED
    assert _mutations(log) == [], "LOCAL_DIR override reached a mutation"


@requires_bash
def test_missing_preflight_fails_closed(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "brand-new"
    script, log, binmock = _sandbox(tmp_path, with_preflight=False)

    proc = _run(script, tmp_path, str(target), binmock)
    assert proc.returncode == bt.EXIT_PREFLIGHT_UNAVAILABLE, proc.stdout + proc.stderr
    assert _mutations(log) == [], "bootstrapped with no preflight present"


@requires_bash
def test_no_environment_bypass(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "install"
    (target / ".git").mkdir(parents=True)
    script, log, binmock = _sandbox(tmp_path)

    proc = _run(
        script,
        tmp_path,
        str(target),
        binmock,
        FORCE="1",
        SKIP_PREFLIGHT="1",
        BOOTSTRAP_FORCE="1",
        RUNTIME_DATA_GUARD_BYPASS="1",
    )
    assert proc.returncode == bt.EXIT_REFUSED
    assert _mutations(log) == []


def test_reset_branch_is_gone_from_the_script() -> None:
    """Removed, not merely gated.

    While a `git reset --hard` remained reachable in this file it stayed an
    independent destructive path regardless of what ran before it.
    """
    executable = [
        ln.strip()
        for ln in _SCRIPT.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    offenders = [ln for ln in executable if "reset --hard" in ln or "git clean" in ln]
    assert offenders == [], f"destructive git command still present: {offenders}"
