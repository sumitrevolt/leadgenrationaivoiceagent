"""Behavioural harness for the canonical release parent (`scripts/deploy_vps.sh`).

Every other test of this surface is TEXTUAL — it reads the file and checks that
the guard line appears before the `git pull` line. That proves ordering in the
source, not behaviour at runtime, and this repo has already been burned twice by
exactly that gap: `vps_selfheal.sh` was classified from a grep of its comments
and the classification was wrong in both directions, and a canary test asserted
a provider was never called yet passed only because execution stopped at step
one — the assertion was vacuous.

So this harness EXECUTES the parent against stub `git`/`docker` binaries and
asserts what actually happened.

THE CONTRACT UNDER TEST (2026-07-28)
------------------------------------
    git fetch (object database only)
        -> isolated candidate worktree at the exact release sha
        -> runtime-data guard, in a PINNED container, against candidate source
           and the LIVE production data (read-only)
        -> candidate image built and tagged with that exact sha
        -> prod_check --deployment, in the CANDIDATE image
        -> live checkout ff-only update
        -> container replacement

The live checkout — the one still holding the invoice, consent and suppression
ledgers and 182 MB of DPDP recordings — must not move until both gates have
passed. That is why "just pull first so the gates can see the new code" is not
an option, and why the candidate lives in its own worktree instead.

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
_SCRIPTS = _REPO / "scripts"
_DEPLOY = _SCRIPTS / "deploy_vps.sh"
_HELPERS = ("_runtime_data_guard.sh", "_deploy_gate_container.sh", "_deploy_candidate.sh")

#: The release sha the sandbox pretends origin/main points at.
FAKE_SHA = "1111111111111111111111111111111111111111"
#: What the live checkout sits on before the deploy.
LIVE_SHA_BEFORE = "0000000000000000000000000000000000000000"

#: Subcommands that move the LIVE checkout. Matched as words rather than as a
#: line prefix, because every recorded call carries an explicit `-C <dir>`.
#: `fetch` is deliberately absent: it updates the object database and touches
#: neither the worktree nor a single data file.
_LIVE_MUTATING = (" pull ", " reset ", " clean ", " checkout ")


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


def _write(path: pathlib.Path, body: str, *, executable: bool = False) -> None:
    path.write_text(textwrap.dedent(body), encoding="utf-8", newline="\n")
    if executable:
        path.chmod(0o755)


def _git_stub(path: pathlib.Path, log: pathlib.Path, state: pathlib.Path) -> None:
    """A git that answers plausibly instead of only recording.

    A stub that printed nothing would make the sha resolution fail for the wrong
    reason, and every ordering assertion below would then be vacuous — the exact
    failure mode this harness exists to catch.
    """
    _write(
        path,
        f"""\
        #!/usr/bin/env bash
        echo "git $*" >> {log.as_posix()!r}
        dir="."
        if [ "${{1:-}}" = "-C" ]; then dir="$2"; shift 2; fi
        cmd="${{1:-}}"; shift || true
        case "$cmd" in
          fetch) exit "${{GIT_FETCH_EXIT:-0}}" ;;
          worktree)
            if [ "${{1:-}}" = "add" ]; then
              for a in "$@"; do case "$a" in /*) mkdir -p "$a" ;; esac; done
              exit "${{GIT_WORKTREE_EXIT:-0}}"
            fi
            exit 0 ;;
          pull)
            rc="${{GIT_PULL_EXIT:-0}}"
            if [ "$rc" = "0" ]; then
              printf '%s' "${{LIVE_AFTER_PULL:-{FAKE_SHA}}}" > {state.as_posix()!r}
            fi
            exit "$rc" ;;
          rev-parse)
            short=0
            for a in "$@"; do [ "$a" = "--short" ] && short=1; done
            case "$dir" in
              *candidates*) sha="${{CANDIDATE_HEAD:-{FAKE_SHA}}}" ;;
              *)
                sha="$(cat {state.as_posix()!r} 2>/dev/null)"
                for a in "$@"; do
                  case "$a" in --verify|--short|HEAD) ;; *) sha="{FAKE_SHA}" ;; esac
                done
                ;;
            esac
            if [ "$short" = "1" ]; then
              printf '%s\\n' "${{sha:0:7}}"
            else
              printf '%s\\n' "$sha"
            fi
            exit "${{GIT_REVPARSE_EXIT:-0}}" ;;
          *) exit 0 ;;
        esac
        """,
        executable=True,
    )


def _docker_stub(path: pathlib.Path, log: pathlib.Path) -> None:
    _write(
        path,
        f"""\
        #!/usr/bin/env bash
        echo "docker $*" >> {log.as_posix()!r}
        all="$*"
        case "$all" in
          *".Config.Image"*) echo "ghcr.io/sumitrevolt/leadgenrationaivoiceagent:dd193a69"; exit 0 ;;
          *".Image"*) echo "sha256:cafebabecafebabe"; exit 0 ;;
          *runtime_data_preflight.py*diagnose*) exit 0 ;;
          *runtime_data_preflight.py*) exit "${{PREFLIGHT_EXIT:-0}}" ;;
          *VOICE_LAUNCH_KILL*) echo "VOICE_LAUNCH_KILL_PRESENT=1"; exit "${{KILLPROOF_EXIT:-0}}" ;;
          *prod_check.py*) exit "${{PRODCHECK_EXIT:-0}}" ;;
          "image inspect"*) exit "${{IMAGE_INSPECT_EXIT:-0}}" ;;
          *build*) exit "${{BUILD_EXIT:-0}}" ;;
          *) exit 0 ;;
        esac
        """,
        executable=True,
    )


def _sandbox(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """Build an isolated copy of the parent plus stub tooling.

    Returns (script_path, command_log, live_head_state).
    """
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    (repo / "data").mkdir()
    (repo / "data" / "invoices.jsonl").write_text("live ledger\n", encoding="utf-8")
    (repo / ".env").write_text("VOICE_LAUNCH_KILL=1\nPLATFORM_DIAL_DAILY=0\n", encoding="utf-8")
    (repo / "docker-compose.vps.yml").write_text("services: {}\n", encoding="utf-8")

    log = tmp_path / "commands.log"
    log.write_text("", encoding="utf-8")
    state = tmp_path / "live_head"
    state.write_text(LIVE_SHA_BEFORE, encoding="utf-8")

    original = _DEPLOY.read_text(encoding="utf-8")
    patched = original.replace("REPO=/opt/leadgen", f"REPO={repo.as_posix()}", 1)
    # Honesty check: exactly one line may differ from what ships.
    diff = [
        (a, b) for a, b in zip(original.splitlines(), patched.splitlines(), strict=True) if a != b
    ]
    assert len(diff) == 1, f"sandbox rewrote more than the REPO line: {diff}"
    assert diff[0][0].strip() == "REPO=/opt/leadgen"

    (scripts / "deploy_vps.sh").write_text(patched, encoding="utf-8", newline="\n")
    for helper in _HELPERS:
        shutil.copy2(_SCRIPTS / helper, scripts / helper)

    binmock = tmp_path / "bin"
    binmock.mkdir()
    _git_stub(binmock / "git", log, state)
    _docker_stub(binmock / "docker", log)
    _write(
        binmock / "curl",
        f"""\
        #!/usr/bin/env bash
        echo "curl $*" >> {log.as_posix()!r}
        echo '{{"status":"healthy","version":"{FAKE_SHA[:7]}","environment":"production"}}'
        exit 0
        """,
        executable=True,
    )
    # The parent waits 22s and then polls /health. This harness measures WHICH
    # commands ran and in what order, not how long a container takes to warm up,
    # and a real sleep here would push every permitted-path test past CI's
    # per-test timeout — a green suite that times out is not a green suite.
    _write(
        binmock / "sleep",
        """\
        #!/usr/bin/env bash
        exit 0
        """,
        executable=True,
    )
    # The disk guard runs `df -P /` and arithmetic on field 5. Real `df` output
    # differs per platform and a non-numeric capacity makes the guard abort
    # under `set -e` — the release would then look "contained" for a reason
    # that has nothing to do with the gates, and every ordering assertion after
    # it would be vacuous.
    _write(
        binmock / "df",
        """\
        #!/usr/bin/env bash
        echo "Filesystem 1024-blocks Used Available Capacity Mounted on"
        echo "/dev/stub  1000000     100000 900000    10% /"
        exit 0
        """,
        executable=True,
    )

    return scripts / "deploy_vps.sh", log, state


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
    env["CANDIDATE_ROOT"] = (tmp_path / "candidates").as_posix()
    env.setdefault("HEALTH_MAX_ATTEMPTS", "1")
    env.setdefault("HEALTH_RETRY_SECONDS", "1")
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
        timeout=180,
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


def _lines(log: pathlib.Path) -> list[str]:
    return [ln.strip() for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _live_mutations(log: pathlib.Path) -> list[str]:
    return [
        ln
        for ln in _lines(log)
        if ln.startswith("git") and any(m in f"{ln} " for m in _LIVE_MUTATING)
    ]


def _container_replacements(log: pathlib.Path) -> list[str]:
    return [ln for ln in _lines(log) if ln.startswith("docker") and " up " in f" {ln} "]


def _index_of(lines: list[str], needle: str) -> int | None:
    return next((i for i, ln in enumerate(lines) if needle in ln), None)


# --------------------------------------------------------------------------- #
# Denial paths — nothing live may move
# --------------------------------------------------------------------------- #
@requires_bash
def test_denied_runtime_data_gate_leaves_live_checkout_and_containers_alone(
    tmp_path: pathlib.Path,
) -> None:
    """The load-bearing claim: denial stops the parent before it touches anything."""
    script, log, state = _sandbox(tmp_path)
    proc = _run(script, tmp_path, PREFLIGHT_EXIT="1")

    _assert_harness_ran(proc)
    assert proc.returncode == 90, (
        f"expected guard exit 90, got {proc.returncode}\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert "DENIED" in proc.stdout, proc.stdout
    assert _live_mutations(log) == [], "the live checkout moved after a denial"
    assert _container_replacements(log) == [], "containers were replaced after a denial"
    assert state.read_text(encoding="utf-8") == LIVE_SHA_BEFORE
    # A fetch IS allowed: it updates the object database, not the worktree.
    assert _index_of(_lines(log), "fetch origin") is not None


@requires_bash
def test_denied_deployment_gate_leaves_live_checkout_alone(tmp_path: pathlib.Path) -> None:
    """prod_check --deployment runs AFTER the candidate build and BEFORE the pull.

    A build creates an image and replaces nothing, so a refusal here must still
    leave the live checkout and every container exactly where they were. This is
    also the case that covers VOICE_LAUNCH_KILL being unset or false: that
    classification belongs to prod_check, and its refusal must contain the
    release rather than merely warn about it.
    """
    script, log, state = _sandbox(tmp_path)
    proc = _run(script, tmp_path, PRODCHECK_EXIT="1")

    _assert_harness_ran(proc)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert _live_mutations(log) == []
    assert _container_replacements(log) == []
    assert state.read_text(encoding="utf-8") == LIVE_SHA_BEFORE


@requires_bash
def test_candidate_build_failure_leaves_production_untouched(tmp_path: pathlib.Path) -> None:
    script, log, state = _sandbox(tmp_path)
    proc = _run(script, tmp_path, BUILD_EXIT="1")

    _assert_harness_ran(proc)
    assert proc.returncode != 0
    assert _live_mutations(log) == []
    assert _container_replacements(log) == []
    assert state.read_text(encoding="utf-8") == LIVE_SHA_BEFORE


@requires_bash
def test_candidate_sha_drift_fails_closed(tmp_path: pathlib.Path) -> None:
    """A candidate worktree that is not at the release sha must abort.

    Gating one tree and shipping another is the entire class of bug the isolated
    candidate exists to remove, so it is asserted rather than assumed.
    """
    script, log, state = _sandbox(tmp_path)
    proc = _run(script, tmp_path, CANDIDATE_HEAD="9" * 40)

    _assert_harness_ran(proc)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert _live_mutations(log) == []
    assert _container_replacements(log) == []
    assert state.read_text(encoding="utf-8") == LIVE_SHA_BEFORE


@requires_bash
def test_live_pull_failure_stops_before_container_replacement(tmp_path: pathlib.Path) -> None:
    script, log, _state = _sandbox(tmp_path)
    proc = _run(script, tmp_path, GIT_PULL_EXIT="1")

    _assert_harness_ran(proc)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert _container_replacements(log) == []


@requires_bash
def test_live_checkout_not_matching_the_gated_sha_fails_closed(tmp_path: pathlib.Path) -> None:
    """The pull succeeded but landed somewhere else — refuse to start containers."""
    script, log, _state = _sandbox(tmp_path)
    proc = _run(script, tmp_path, LIVE_AFTER_PULL="7" * 40)

    _assert_harness_ran(proc)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert _container_replacements(log) == []


# --------------------------------------------------------------------------- #
# Permitted path — ordering, mounts and provenance
# --------------------------------------------------------------------------- #
@requires_bash
def test_permitted_release_runs_both_gates_before_touching_anything_live(
    tmp_path: pathlib.Path,
) -> None:
    """Anti-vacuity control plus the full ordering contract.

    Without a permitted run, every denial test above would still pass if the
    script never reached any command for an unrelated reason — which is exactly
    how an earlier canary test fooled me.
    """
    script, log, _state = _sandbox(tmp_path)
    _run(script, tmp_path)
    lines = _lines(log)

    fetch = _index_of(lines, "fetch origin")
    guard = _index_of(lines, "runtime_data_preflight.py check-deploy")
    build = next(
        (i for i, ln in enumerate(lines) if ln.startswith("docker") and " build " in f"{ln} "),
        None,
    )
    gate = _index_of(lines, "prod_check.py --deployment")
    pull = _index_of(lines, " pull ")

    for name, idx in (("fetch", fetch), ("guard", guard), ("build", build), ("gate", gate)):
        assert idx is not None, f"{name} never ran:\n" + "\n".join(lines)
    assert pull is not None, "the anti-vacuity control never reached the live pull"

    assert fetch < guard, "the runtime-data guard ran before the object database was current"
    assert guard < build, "the candidate image was built before the runtime-data guard decided"
    assert build < gate, "prod_check did not run against the candidate image"
    assert gate < pull, "the live checkout moved before the deployment gate passed"

    replacements = _container_replacements(log)
    if replacements:
        assert pull < lines.index(replacements[0]), (
            "a container was replaced before the live checkout was updated"
        )


@requires_bash
def test_gates_mount_candidate_and_live_data_read_only(tmp_path: pathlib.Path) -> None:
    """The gate must see the CANDIDATE source and the REAL ledgers, both read-only.

    A candidate worktree carries an empty `data/`. Gating against that would
    report a clean, blocker-free system that does not exist — a false green on
    the one question this gate is asked.
    """
    script, log, _state = _sandbox(tmp_path)
    _run(script, tmp_path)

    gate_calls = [ln for ln in _lines(log) if "runtime_data_preflight.py" in ln]
    assert gate_calls, "no gate invocation was recorded"
    live_data = (tmp_path / "repo" / "data").as_posix()
    for call in gate_calls:
        assert "/repo:ro" in call, f"candidate source not mounted read-only: {call}"
        assert f"{live_data}:/repo/data:ro" in call, (
            f"live production data not mounted read-only over the candidate's empty data/: {call}"
        )
        assert "--read-only" in call and "--network none" in call, call
        assert "--env-file" in call, f"the gate ran without production's environment: {call}"


@requires_bash
def test_no_release_step_ever_uses_latest(tmp_path: pathlib.Path) -> None:
    """ADR-097: `:latest` is how production's provenance became unknown."""
    script, log, _state = _sandbox(tmp_path)
    _run(script, tmp_path)
    for line in _lines(log):
        assert ":latest" not in line, f"a release step used :latest -> {line}"


@requires_bash
def test_calling_safety_environment_is_proven_without_printing_values(
    tmp_path: pathlib.Path,
) -> None:
    """VOICE_LAUNCH_KILL must be proven to REACH the gate, as a boolean only."""
    script, log, _state = _sandbox(tmp_path)
    proc = _run(script, tmp_path)

    assert [ln for ln in _lines(log) if "VOICE_LAUNCH_KILL" in ln], (
        "the gate environment was never proven"
    )
    assert "VOICE_LAUNCH_KILL_PRESENT=1" in proc.stdout
    # The token itself must never be echoed by the parent.
    assert "VOICE_LAUNCH_KILL=1" not in proc.stdout


@requires_bash
def test_parent_never_writes_env_or_touches_calling_flags(tmp_path: pathlib.Path) -> None:
    """A release must not be able to turn calling on as a side effect."""
    source = _DEPLOY.read_text(encoding="utf-8")
    for forbidden in ("PLATFORM_DIAL_DAILY=", "WHATSAPP_AUTO_SEND=", "> .env", ">> .env"):
        assert forbidden not in source, f"the release parent writes {forbidden!r}"

    script, _log, _state = _sandbox(tmp_path)
    env_before = (tmp_path / "repo" / ".env").read_text(encoding="utf-8")
    _run(script, tmp_path)
    assert (tmp_path / "repo" / ".env").read_text(encoding="utf-8") == env_before
    assert "PLATFORM_DIAL_DAILY=0" in env_before


# --------------------------------------------------------------------------- #
# The guard itself
# --------------------------------------------------------------------------- #
@requires_bash
def test_missing_helper_fails_closed(tmp_path: pathlib.Path) -> None:
    """A helper that cannot be sourced must stop the release, not be skipped.

    THIS IS THE BUG THE HARNESS FOUND. `deploy_vps.sh` runs under
    `set -uo pipefail` with no `-e`, so a failed `.` source did not abort it:
    with the guard file absent the shell printed "No such file or directory"
    and went straight on to `git pull`. Every textual test passed the whole
    time, because the guard LINE was present and correctly ordered — it just
    did not do anything.
    """
    for helper in _HELPERS:
        base = tmp_path / helper
        script, log, state = _sandbox(base)
        (script.parent / helper).unlink()
        proc = _run(script, base)
        _assert_harness_ran(proc)
        assert proc.returncode == 91, (
            f"missing {helper} must abort with 91, not fall through.\n"
            f"got {proc.returncode}\nSTDOUT:\n{proc.stdout}"
        )
        assert _live_mutations(log) == [], f"deployed with {helper} absent"
        assert state.read_text(encoding="utf-8") == LIVE_SHA_BEFORE


@requires_bash
def test_guard_has_no_bypass_at_runtime(tmp_path: pathlib.Path) -> None:
    """Environment variables must not be able to talk the guard out of a denial.

    Checking behaviour rather than grepping for a bypass name: any future
    bypass, whatever it is called, would have to make a denied preflight
    proceed — and that is what this asserts cannot happen.
    """
    script, log, state = _sandbox(tmp_path)
    env_attempts = {
        "RUNTIME_DATA_CUTOVER_ENABLED": "1",
        "SKIP_PREFLIGHT": "1",
        "FORCE": "1",
        "RUNTIME_DATA_GUARD_BYPASS": "1",
        "CI": "true",
        "PREFLIGHT_EXIT": "1",
    }
    proc = _run(script, tmp_path, **env_attempts)
    _assert_harness_ran(proc)
    assert proc.returncode == 90, f"a bypass env var defeated the guard: {env_attempts}"
    assert _live_mutations(log) == []
    assert state.read_text(encoding="utf-8") == LIVE_SHA_BEFORE


@requires_bash
def test_guard_denial_and_helper_absence_are_distinguishable(tmp_path: pathlib.Path) -> None:
    """90 and 91 must not collapse into one code.

    An operator seeing 90 should look at the blocker list; seeing 91 they should
    look for a missing file. Collapsing them would send them to the wrong runbook.
    """
    denied_script, _, _ = _sandbox(tmp_path / "a")
    denied = _run(denied_script, tmp_path / "a", PREFLIGHT_EXIT="1")

    absent_script, _, _ = _sandbox(tmp_path / "b")
    (absent_script.parent / "_runtime_data_guard.sh").unlink()
    absent = _run(absent_script, tmp_path / "b")

    assert denied.returncode == 90
    assert absent.returncode == 91
    assert denied.returncode != absent.returncode
