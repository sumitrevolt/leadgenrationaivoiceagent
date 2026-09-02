"""Contract tests for scripts/eval_golden.py — new golden-suite behaviour.

Deterministic layer only (no network). Semantic LLM-judge is skip-safe in CI
and covered here via --deterministic-only + fixture helpers.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "scripts" / "eval_golden.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("eval_golden", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # dataclasses + from __future__ annotations needs the module registered first
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def golden():
    return _load_mod()


def test_deterministic_suite_all_pass(golden):
    results = golden.run_deterministic()
    assert len(results) >= 10
    failed = [r for r in results if not r.ok]
    assert failed == [], f"golden deterministic regressions: {failed}"


def test_main_deterministic_only_exits_zero(golden):
    rc = golden.main(["--deterministic-only"])
    assert rc == 0


def test_semantic_skips_without_judge_key(golden, monkeypatch):
    for k in (
        "EVAL_JUDGE_API_KEY",
        "OPENAI_API_KEY",
        "CEREBRAS_API_KEY",
        "GROQ_API_KEY",
        "EVAL_GOLDEN_REQUIRE_JUDGE",
    ):
        monkeypatch.delenv(k, raising=False)
    results = golden.run_semantic()
    assert len(results) == 5
    assert all(r.skipped for r in results)
    assert all(r.ok for r in results)  # skip = not a fail when judge optional


def test_semantic_require_judge_fails_without_key(golden, monkeypatch):
    for k in ("EVAL_JUDGE_API_KEY", "OPENAI_API_KEY", "CEREBRAS_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("EVAL_GOLDEN_REQUIRE_JUDGE", "1")
    results = golden.run_semantic()
    assert all(r.skipped for r in results)
    assert all(not r.ok for r in results)


def test_banned_list_covers_echo_and_no_response(golden):
    low = " ".join(golden._BANNED)
    assert "[echo" in low
    assert "(no response)" in low
