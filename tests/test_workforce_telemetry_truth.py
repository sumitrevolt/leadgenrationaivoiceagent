"""The autonomous-workforce status file must never report FABRICATED telemetry.

WHY THIS TEST EXISTS
====================
`scripts/autonomous_workforce_orchestrator.py` used to generate fake telemetry:
it reported 31 agents as "LOCAL_ACTIVE" and inflated `actions_today` by
`cycle_num * 31` every 15 seconds (reaching ~277,528 actions) while NOTHING was
actually executing. That data was rendered on the Owner Command Center as if it
were real worker activity.

The loop was disabled (2026-09-11) and `main()` now writes an honest, INERT
payload. But that regression was UNPINNED: nothing stopped a future edit from
re-enabling the fake loop, hard-coding a large action count, or reintroducing
the synthetic "LOCAL_ACTIVE" worker status.

This file pins BOTH:
  1. the runtime OUTPUT of `main()` is inert (status/actions/workers all zero), and
  2. the SOURCE cannot hard-code fabricated telemetry (no `LOCAL_ACTIVE` status
     outside a docstring, no non-zero `actions_today`, `run_continuous_batch`
     stays inert).

THESE TESTS ARE A COMPLIANCE GATE. If any fail, do NOT "fix" them by loosening
an assertion — the fabricated-telemetry bug would be back.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import scripts.autonomous_workforce_orchestrator as orch

_SCRIPT = Path(orch.__file__).resolve()


# ----------------------------------------------------------- runtime output


def test_orchestrator_main_is_inert(monkeypatch, tmp_path, capsys) -> None:
    """`main()` must write an honest NOT_INSTRUMENTED payload — no fake activity."""
    from app.platform import runtime_data

    out = tmp_path / "workforce_live_status.json"
    monkeypatch.setattr(runtime_data, "store_path", lambda *_a, **_k: out)

    orch.main()
    capsys.readouterr()  # discard the console banner

    assert out.is_file(), "main() wrote no status file"
    status = json.loads(out.read_text(encoding="utf-8"))

    assert status["status"] == "NOT_INSTRUMENTED", status.get("status")
    assert status["active_workers"] == 0, status.get("active_workers")
    assert status["actions_today"] == 0, status.get("actions_today")
    assert status["evidence_kind"] == "inference_probe_only", status.get("evidence_kind")
    assert status["task_execution_verified"] is False
    assert status["agents"] == []
    assert status["recent_rescues"] == []


def test_orchestrator_main_prints_no_activity_claims(monkeypatch, tmp_path, capsys) -> None:
    from app.platform import runtime_data

    monkeypatch.setattr(
        runtime_data, "store_path", lambda *_a, **_k: tmp_path / "s.json"
    )
    orch.main()
    printed = capsys.readouterr().out.upper()
    assert "LOCAL_ACTIVE" not in printed
    assert "INERT" in printed


# ----------------------------------------------------------- source guards


def _tree() -> ast.Module:
    return ast.parse(_SCRIPT.read_text(encoding="utf-8"))


def _docstring_constant_ids(tree: ast.Module) -> set[int]:
    """id() of every ast.Constant that is a module/class/function docstring."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(body, list)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            ids.add(id(body[0].value))
    return ids


def _is_docstring_expr(stmt: ast.stmt) -> bool:
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(
        stmt.value.value, str
    )


def test_no_local_active_status_outside_docstrings() -> None:
    """`LOCAL_ACTIVE` may only appear in prose (docstring), never as a code string."""
    tree = _tree()
    docstrings = _docstring_constant_ids(tree)
    offenders = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and "LOCAL_ACTIVE" in n.value
        and id(n) not in docstrings
    ]
    assert not offenders, (
        "LOCAL_ACTIVE is used as a real code string — the synthetic worker-status "
        "bug is back (offending lines: "
        f"{[n.lineno for n in offenders]})"
    )


def test_no_actions_today_inflation() -> None:
    """No augmented assignment to `actions_today` (the `+= cycle_num * 31` bug)."""
    tree = _tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.AugAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == "actions_today":
                raise AssertionError(
                    f"actions_today is inflated at line {node.lineno} — fake telemetry is back"
                )


def test_actions_today_literals_are_zero() -> None:
    """Any literal written to the `actions_today` key must be exactly 0."""
    tree = _tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "actions_today"
                ):
                    assert (
                        isinstance(value, ast.Constant) and value.value == 0
                    ), f"actions_today literal at line {key.lineno} is not 0"


def test_run_continuous_batch_is_inert() -> None:
    """The fake-telemetry generator must stay a no-op (docstring + pass only)."""
    tree = _tree()
    fn = next(
        (
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "run_continuous_batch"
        ),
        None,
    )
    assert fn is not None, "run_continuous_batch was removed; contract changed"
    body = [s for s in fn.body if not _is_docstring_expr(s)]
    assert body, "run_continuous_batch body is empty"
    assert all(isinstance(s, ast.Pass) for s in body), (
        "run_continuous_batch is no longer inert — it contains "
        f"{[type(s).__name__ for s in body]}"
    )
