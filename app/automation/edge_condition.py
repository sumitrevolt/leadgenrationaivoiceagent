"""Edge-condition evaluator for the DAG flow runner (Phase 2).

Pure + deterministic — NO code/LLM/attribute-access/arithmetic. Evaluates an
edge's `when` against the SOURCE node's result dict ({ok,count,detail}).
FAIL-CLOSED: any malformed/unevaluable condition returns False, so a branch you
cannot evaluate is NEVER taken (a broken condition can't trigger a side effect).
Import-safe, never raises.
"""

from __future__ import annotations

from typing import Any

OPS = {"==", "!=", ">", ">=", "<", "<=", "in", "not_in", "truthy", "falsy", "exists"}
_REL = {"==", "!=", ">", ">=", "<", "<="}
_MAX_DEPTH = 3


def _cmp(actual: Any, value: Any, op: str) -> bool:
    a, b = actual, value
    try:
        a, b = float(actual), float(value)  # numeric compare if both castable
    except (TypeError, ValueError):
        a, b = str(actual), str(value)  # else string compare
    if op == "==":
        return a == b
    if op == "!=":
        return a != b
    if op == ">":
        return a > b
    if op == ">=":
        return a >= b
    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    return False


def _leaf(cond: dict, src: dict) -> bool:
    field = cond.get("field")
    op = cond.get("op")
    if op not in OPS:
        return False
    present = isinstance(src, dict) and field in src
    actual = src.get(field) if isinstance(src, dict) else None
    if op == "exists":
        return present
    if op == "truthy":
        return bool(actual)
    if op == "falsy":
        return not bool(actual)
    if op == "in":
        try:
            return actual in cond.get("value")
        except TypeError:
            return False
    if op == "not_in":
        try:
            return actual not in cond.get("value")
        except TypeError:
            return False
    if actual is None:  # relational op on missing/None -> fail-closed
        return False
    return _cmp(actual, cond.get("value"), op)


def edge_taken(when: dict | None, source_result: dict) -> bool:
    """True if the edge fires. None/{} -> unconditional True. Never raises."""
    try:
        if not when:
            return True
        if not isinstance(when, dict):
            return False
        src = source_result if isinstance(source_result, dict) else {}
        if "all" in when:
            subs = when.get("all") or []
            return bool(subs) and all(edge_taken(s, src) for s in subs)
        if "any" in when:
            subs = when.get("any") or []
            return any(edge_taken(s, src) for s in subs)
        return _leaf(when, src)
    except Exception:
        return False


def validate(when: dict | None, _depth: int = 0) -> list[str]:
    """Return list of error strings ([] = valid). Caught at SAVE, not run."""
    errs: list[str] = []
    if when is None or when == {}:
        return errs
    if not isinstance(when, dict):
        return ["condition must be an object"]
    if _depth > _MAX_DEPTH:
        return [f"condition nesting too deep (>{_MAX_DEPTH})"]
    if "all" in when or "any" in when:
        key = "all" if "all" in when else "any"
        subs = when.get(key)
        if not isinstance(subs, list) or not subs:
            errs.append(f"'{key}' must be a non-empty list")
        else:
            for s in subs:
                errs += validate(s, _depth + 1)
        return errs
    op = when.get("op")
    if op not in OPS:
        errs.append(f"unknown op '{op}'")
    field = when.get("field")
    if not isinstance(field, str) or not field:
        errs.append("field must be a non-empty string")
    if op in _REL and not isinstance(when.get("value"), (int, float, str, bool)):
        errs.append("value must be a scalar for relational ops")
    return errs


__all__ = ["edge_taken", "validate", "OPS"]
