"""AST-backed proof that the Python release builders no longer own a chain.

These three scripts EXECUTE (subprocess.run), they do not merely print. All
three ran `git reset --hard origin/main` against /opt/leadgen — the single most
destructive command available against a checkout that still holds the live
invoice, consent and suppression ledgers and 182 MB of DPDP call recordings.

Analysis here is AST-based rather than substring-based on purpose. A grep for
"reset --hard" would be satisfied by this very docstring, and a scanner that
reads prose as evidence has already produced two false findings in this
workstream.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO / "scripts"

BUILDERS = [
    "vps_build_deploy.py",
    "vps_deploy_dashboard.py",
    "vps_deploy_workflow_fix.py",
]

_DESTRUCTIVE = re.compile(r"git\s+(reset\s+--hard|clean|stash)|docker\s+compose[^\"']*\bbuild\b")


def _tree(name: str) -> ast.Module:
    return ast.parse((_SCRIPTS / name).read_text(encoding="utf-8"))


def _string_constants(tree: ast.Module) -> list[str]:
    """Every string literal EXCEPT docstrings.

    Docstrings are prose. Including them is how a scanner ends up reporting the
    comment that explains a fix as though it were the bug.
    """
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            ds = ast.get_docstring(node, clean=False)
            if ds is not None:
                docstrings.add(ds)
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value not in docstrings
    ]


@pytest.mark.parametrize("name", BUILDERS)
def test_no_destructive_git_or_build_command_remains(name: str) -> None:
    tree = _tree(name)
    offenders = [s for s in _string_constants(tree) if _DESTRUCTIVE.search(s)]
    assert offenders == [], f"{name} still carries a destructive chain: {offenders}"


@pytest.mark.parametrize("name", BUILDERS)
def test_invokes_the_canonical_parent(name: str) -> None:
    """Anti-vacuity: removing the chain is only half the job.

    A script that deleted its commands and did nothing would pass the test
    above. It must actually reach deploy_vps.sh.
    """
    tree = _tree(name)
    assert any("deploy_vps.sh" in s for s in _string_constants(tree)), (
        f"{name} removed its chain but never invokes the parent"
    )


@pytest.mark.parametrize("name", BUILDERS)
def test_no_shell_true_execution(name: str) -> None:
    """`shell=True` turns any future string edit into an injection surface.

    vps_build_deploy.py ran every command through `shell=True` in a SEPARATE
    subprocess, which also meant its leading `cd /opt/leadgen` had no effect on
    the commands after it — `git reset --hard` ran against whatever the working
    directory happened to be.
    """
    tree = _tree(name)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value:
                pytest.fail(f"{name} still uses shell=True at line {node.lineno}")


@pytest.mark.parametrize("name", BUILDERS)
def test_no_bash_dash_lc_command_string(name: str) -> None:
    """`bash -lc "<joined string>"` is shell=True wearing a different coat."""
    tree = _tree(name)
    consts = _string_constants(tree)
    assert "-lc" not in consts, f"{name} still executes a joined shell string"


@pytest.mark.parametrize("name", BUILDERS)
def test_parent_exit_status_is_propagated(name: str) -> None:
    """The parent's 90/91 must reach the operator, not be flattened to 1.

    Detected structurally: the module must return a `returncode` somewhere
    rather than only returning literal ints.
    """
    tree = _tree(name)
    returns_returncode = any(
        isinstance(node, ast.Return)
        and any(
            isinstance(sub, ast.Attribute) and sub.attr == "returncode" for sub in ast.walk(node)
        )
        for node in ast.walk(tree)
    )
    assert returns_returncode, f"{name} does not propagate the parent exit status"


@pytest.mark.parametrize("name", BUILDERS)
def test_parent_unavailability_is_handled(name: str) -> None:
    """Missing parent must be an explicit refusal, not an implicit crash.

    The remote/SSH builder is exempt from the local readability check because
    its parent lives on the far side of the connection — for that one the
    remote `set -e` plus verbatim exit propagation is the mechanism.
    """
    text = (_SCRIPTS / name).read_text(encoding="utf-8")
    if "ssh" in text.lower() and "REMOTE" in text:
        assert "REMOTE_EXIT_" in text, f"{name} must surface the remote exit status"
        return
    assert "EXIT_PARENT_UNAVAILABLE" in text, (
        f"{name} has no explicit handling for a missing canonical parent"
    )


@pytest.mark.parametrize("name", BUILDERS)
def test_scripts_still_parse_and_have_a_main(name: str) -> None:
    tree = _tree(name)
    assert any(isinstance(n, ast.FunctionDef) and n.name == "main" for n in ast.walk(tree)), (
        f"{name} lost its main()"
    )
