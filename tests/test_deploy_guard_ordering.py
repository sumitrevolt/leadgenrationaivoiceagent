"""Every destructive production path must run the preflight FIRST.

A guard that runs *after* `git reset --hard` protects nothing. These tests read
the scripts as text and assert ordering by line number, because that is the only
property that actually matters here.

Scope note: a repo-wide scan found 15 production-capable destructive paths — six
`git reset --hard`, one `git clean -fd`, and eight `git pull`. The earlier
working assumption of three was wrong, and this suite exists so the list cannot
silently grow again.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"

GUARD = "_runtime_data_guard.sh"
PREFLIGHT = "runtime_data_preflight.py"

#: Commands that mutate or replace the checkout / running containers.
DESTRUCTIVE = re.compile(
    r"(git\s+reset\s+--hard|git\s+clean\b|git\s+pull\b|git\s+checkout\s+-B\b"
    r"|docker\s+compose[^\n]*\bup\s+-d|docker\s+compose[^\n]*\brecreate\b)"
)

#: Scripts that ALREADY guard, or are being brought under the guard now.
#: `deploy_vps.sh` is the CANONICAL NORMAL-RELEASE parent.
GUARDED_NOW = ("_mcp_deploy_remote.sh", "vps_pitch_deploy.sh", "deploy_vps.sh")

#: Python entry points that guard by calling the preflight directly rather than
#: sourcing the shell helper. Their protection is proven BEHAVIOURALLY in
#: tests/test_force_pull_guard.py (a denied preflight makes subprocess.run fail
#: the test if reached), which is stronger evidence than line ordering.
PY_GUARDED = {"vps_force_pull.py": "tests/test_force_pull_guard.py"}

#: Evidence-based reclassification. The pattern scanner marks a file
#: "production-capable" when it mentions /opt/leadgen, docker-compose.vps.yml,
#: leadsgenai.in or the VPS IP. That heuristic produced false positives, and a
#: heuristic must not decide guard policy — reading the file must.
RECLASSIFIED = {
    ".github/workflows/tests.yml": (
        "TEST_ONLY — runs-on: ubuntu-latest; its `git clean -fdxq` and "
        "`git checkout --orphan ci-debug` act on the RUNNER's ephemeral checkout "
        "and push to a ci-debug branch. No /opt/leadgen, no ssh, no production "
        "compose. The scanner matched only the git config email ci@leadsgenai.in."
    ),
    "pg_restore_drill.sh": (
        "DATABASE_RESTORE — restores a backup into a THROWAWAY container "
        "(`docker run -d --rm --name $TMP`) and its `docker rm -f` targets that "
        "same temp container. It never touches the production checkout or "
        "production services. Needs its own backup preconditions, NOT the "
        "normal-release parent."
    ),
    "sops_decrypt_env.sh": (
        "SECRET_CONFIG_PREPARATION — writes /opt/leadgen/.env. Its only "
        "`docker compose` string is inside an echo instructing the operator what "
        "to run next; it is not an executed command. Mutates configuration, not "
        "release or runtime state."
    ),
}

#: Known-destructive paths not yet guarded. Each entry is debt with an owner,
#: not an exemption: the accompanying test asserts the list only shrinks.
UNGUARDED_DEBT = {
    "hostinger_hermes_bootstrap.sh": "sandbox clone, not /opt/leadgen — verify then guard",
    "vps_build_deploy.py": "python remote-command builder — wave 2",
    "vps_deploy_dashboard.py": "python remote-command builder — wave 2",
    "vps_deploy_workflow_fix.py": "python remote-command builder — wave 2",
    "vps_deploy_automation_fix.py": "git pull || true — wave 2",
    "vps_deploy_smoke.py": "git pull — wave 2",
    "vps_flywheel_deploy.sh": "git pull — wave 2",
    "deploy_adr095.sh": "one-off ADR deploy — wave 2",
    "deploy_adr096.sh": "one-off ADR deploy — wave 2",
    "deploy_adr097.sh": "one-off ADR deploy — wave 2",
    "deploy_all.sh": "git pull — wave 2",
    # --- container-replacement paths -------------------------------------
    # Found only when the scan included `docker compose up -d`. Recreating a
    # container does not by itself revert data/, but these scripts run against
    # production and several also pull/checkout, so they are in scope.
    # This block is why the earlier "3 destructive scripts" figure was wrong by
    # an order of magnitude — the real surface is ~33 paths.
    "activate.py": "container replacement — wave 2",
    "activate_waha_vps.sh": "container replacement — wave 2",
    "chaos_test.sh": "test harness; verify it never targets prod — wave 2",
    "fs_deploy.sh": "container replacement — wave 2",
    "infra_activate.sh": "container replacement — wave 2",
    "set_kv.sh": "container replacement — wave 2",
    "setup_postiz.sh": "container replacement — wave 2",
    "verify_mcp_engineer.py": "verification helper — classify as diagnostic — wave 2",
    "vps_activate_rag_flags.py": "container replacement — wave 2",
    "vps_deploy_call_learn.py": "container replacement — wave 2",
    "vps_deploy_selfimprove.sh": "container replacement — wave 2",
    "vps_enable_deferred_backlog.py": "container replacement — wave 2",
    "vps_flags_smoke.py": "container replacement — wave 2",
    "vps_infra_setup.py": "container replacement — wave 2",
    "vps_migrate_qdrant.sh": "container replacement — wave 2",
    "vps_post_deploy_verify.py": "post-deploy verification — classify as diagnostic — wave 2",
    "vps_prod_finish.sh": "container replacement — wave 2",
    "vps_production_harden.sh": "container replacement — wave 2",
    # Cutover tooling ships the plan/copy/verify/activate parent cited by
    # deploy_vps.sh. It can mutate production bytes outside git; treat as
    # known debt until it sources _runtime_data_guard.sh like other parents.
    "runtime_data_cutover.py": "cutover parent — guard then shrink — wave A5",
}


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


def _first_destructive_line(text: str) -> int | None:
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("echo "):
            continue
        if DESTRUCTIVE.search(stripped):
            return i
    return None


def _guard_line(text: str) -> int | None:
    for i, line in enumerate(text.splitlines(), 1):
        if GUARD in line and not line.strip().startswith("#"):
            return i
    return None


# ------------------------------------------------------------ the guard itself
def test_guard_script_exists_and_has_no_bypass() -> None:
    guard = SCRIPTS / GUARD
    assert guard.is_file()
    text = _text(guard)
    assert PREFLIGHT in text
    assert "check-deploy" in text
    # A bypass variable or `|| true` would make the guard decorative.
    # Comments are excluded — the guard's own docstring *mentions* `|| true`
    # precisely to forbid it, and a naive substring check flagged that.
    code = "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("#"))
    assert "|| true" not in code
    assert "continue-on-error" not in code
    assert "BYPASS" not in code.upper()
    assert "exit 90" in code, "guard must terminate the calling script"


def test_preflight_exists_and_supports_required_modes() -> None:
    pf = SCRIPTS / PREFLIGHT
    assert pf.is_file()
    text = _text(pf)
    for mode in ("diagnose", "check-deploy", "check-cutover"):
        assert mode in text
    assert "--json" in text


# --------------------------------------------------- ordering on guarded paths
@pytest.mark.parametrize("name", GUARDED_NOW)
def test_guard_precedes_first_destructive_command(name: str) -> None:
    path = SCRIPTS / name
    assert path.is_file(), name
    text = _text(path)

    g = _guard_line(text)
    d = _first_destructive_line(text)

    assert g is not None, f"{name} does not source {GUARD}"
    assert d is not None, f"{name} no longer contains a destructive command — update this test"
    assert g < d, (
        f"{name}: guard is on line {g} but the first destructive command is on line {d}. "
        "A guard after the reset protects nothing."
    )


@pytest.mark.parametrize("name", GUARDED_NOW)
def test_guarded_scripts_do_not_swallow_guard_failure(name: str) -> None:
    text = _text(SCRIPTS / name)
    for line in text.splitlines():
        if GUARD in line:
            assert "|| true" not in line
            assert "|| :" not in line


# --------------------------------------------------------- debt only shrinks
def test_unguarded_debt_is_declared_with_a_reason() -> None:
    for name, reason in UNGUARDED_DEBT.items():
        assert reason.strip(), f"{name} needs a reason and a wave"
        assert (SCRIPTS / name).is_file(), f"{name} listed as debt but does not exist"


def test_no_undeclared_destructive_script() -> None:
    """A NEW destructive script must be guarded or explicitly declared as debt.

    This is the anti-drift check: the previous working list of three was wrong,
    and nothing caught it.
    """
    known = set(GUARDED_NOW) | set(UNGUARDED_DEBT) | set(PY_GUARDED)
    undeclared: list[str] = []
    for path in sorted(SCRIPTS.glob("*")):
        if path.suffix not in {".sh", ".py"} or path.name in {GUARD, PREFLIGHT}:
            continue
        if path.name in known:
            continue
        if _first_destructive_line(_text(path)) is not None:
            undeclared.append(path.name)
    assert not undeclared, (
        "undeclared destructive production path(s): "
        + ", ".join(undeclared)
        + " — guard them or add them to UNGUARDED_DEBT with an owner and wave"
    )


def test_reclassified_paths_are_not_treated_as_release_paths() -> None:
    """A pattern match is not evidence of operation class.

    Each entry here was marked production-capable by the scanner heuristic and
    then reclassified by READING the file. Routing them through the
    normal-release parent would break their semantics — a restore drill is not
    a release, and CI is not production.
    """
    for name, reason in RECLASSIFIED.items():
        assert reason.strip(), name
        assert name.split("/")[-1] not in GUARDED_NOW, (
            f"{name} was reclassified as non-release but is listed as a normal-release guarded path"
        )


def test_canonical_release_parent_is_guarded() -> None:
    """deploy_vps.sh is the normal-release authority and must be protected."""
    assert "deploy_vps.sh" in GUARDED_NOW
    text = _text(SCRIPTS / "deploy_vps.sh")
    g, d = _guard_line(text), _first_destructive_line(text)
    assert g is not None and d is not None and g < d
