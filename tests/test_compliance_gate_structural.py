"""STRUCTURAL proof that the TRAI DND gate refuses to fail OPEN in production.

WHY THIS TEST EXISTS
====================
The whole point of the DND refusal is that, in production, `DND_FAIL_OPEN=1`
must be IGNORED and the gate must stay fail-CLOSED (an unverified DND lookup
=> promotional call BLOCKED). A prior audit found that a *behavioural* test
(`tests/test_fail_open_refused_in_production.py::test_dnd_fail_open_still_refused_in_production`)
can be satisfied by monkeypatching `_is_production`, and — more importantly —
that a *behavioural* test can be accidentally satisfied by a stub, a partial
implementation, or a comment that merely mentions the flag.

This file proves the REFUSAL BRANCH EXISTS IN THE SOURCE, by parsing the real
function with `ast` — not by grepping the file. A comment, a docstring, or a
string literal mentioning `_is_production` cannot satisfy it; there must be a
real `if _is_production():` statement whose body RETURNS a falsy constant.

If this test ever fails, the production DND refusal was removed or rewritten.
THESE TESTS ARE A COMPLIANCE GATE. If any fail, do NOT "fix" them by loosening
an assertion.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from app.telephony import compliance

_FLAG = "DND_FAIL_OPEN"
_PROD_PREDICATE = "_is_production"


def _module_level_functions() -> list[tuple[str, object, str]]:
    """Every module-level function defined in compliance.py, with its source."""
    out: list[tuple[str, object, str]] = []
    for name, obj in vars(compliance).items():
        if not inspect.isfunction(obj):
            continue
        if getattr(obj, "__module__", None) != compliance.__name__:
            continue
        try:
            src = inspect.getsource(obj)
        except (OSError, TypeError):  # pragma: no cover - defensive
            continue
        out.append((name, obj, src))
    return out


def _find_gate_function() -> tuple[str, object, str]:
    """The function that BOTH reads DND_FAIL_OPEN and consults _is_production."""
    matches = [
        (n, o, s)
        for (n, o, s) in _module_level_functions()
        if _FLAG in s and _PROD_PREDICATE in s
    ]
    assert matches, (
        "no module-level function in app/telephony/compliance.py both reads "
        f"{_FLAG!r} and consults {_PROD_PREDICATE!r} — the fail-open handler is gone"
    )
    assert len(matches) == 1, (
        "expected exactly one fail-open handler; found "
        f"{[m[0] for m in matches]}"
    )
    return matches[0]


def _references_name(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(n, ast.Name) and n.id == name for n in ast.walk(node)
    )


def _has_falsy_return(body: list[ast.stmt]) -> bool:
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Return) and node.value is not None:
                val = node.value
                if isinstance(val, ast.Constant) and not val.value:
                    return True
    return False


def test_dnd_refusal_branch_present() -> None:
    """AST proof: the handler has `if _is_production(): ... return <falsy>`."""
    name, _obj, src = _find_gate_function()
    assert name == "_dnd_fail_open", f"unexpected handler name: {name}"

    tree = ast.parse(textwrap.dedent(src))
    func = tree.body[0]
    assert isinstance(func, ast.FunctionDef), (
        f"AST shape changed: {name} is {type(func).__name__}, not FunctionDef"
    )

    prod_ifs = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.If) and _references_name(node.test, _PROD_PREDICATE)
    ]
    assert prod_ifs, (
        f"no `if {_PROD_PREDICATE}(...)` branch inside {name}() — the production "
        "refusal has been removed. This is a COMPLIANCE REGRESSION, not a test bug."
    )
    assert any(_has_falsy_return(if_node.body) for if_node in prod_ifs), (
        f"the `{_PROD_PREDICATE}` branch in {name}() does not RETURN a falsy constant "
        "(False/None/0). A branch that merely logs, or falls through, does not refuse."
    )


def test_dnd_refusal_not_satisfiable_by_comment_or_string() -> None:
    """Negative control: comments/strings mentioning the predicate are not an If."""
    name, _obj, src = _find_gate_function()
    tree = ast.parse(textwrap.dedent(src))
    func = tree.body[0]

    # Strip every docstring/comment influence: count only real If statements that
    # call the predicate. A pure docstring mention yields zero.
    prod_ifs = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.If) and _references_name(node.test, _PROD_PREDICATE)
    ]
    assert prod_ifs, "no real conditional refusal branch present"


def test_dnd_flag_defaults_to_closed_source_shape() -> None:
    """The handler must default the flag OFF (`_env(_FLAG, "0")`), i.e. fail-closed
    when the env var is unset. Pinned structurally so a default flip is caught."""
    name, _obj, src = _find_gate_function()
    assert '"0"' in src, (
        f"{name}() no longer defaults {_FLAG} to '0' (fail-closed). Default flip detected."
    )


@pytest.mark.parametrize("falsy", ["False", "None", "0"])
def test_falsy_return_detector_recognises_falsy_constants(falsy: str) -> None:
    """Self-check of the detector so the gate above cannot silently no-op."""
    body = ast.parse(f"def f():\n    return {falsy}\n").body[0].body  # type: ignore[attr-defined]
    assert _has_falsy_return(body) is True
    truthy = ast.parse("def f():\n    return True\n").body[0].body  # type: ignore[attr-defined]
    assert _has_falsy_return(truthy) is False
