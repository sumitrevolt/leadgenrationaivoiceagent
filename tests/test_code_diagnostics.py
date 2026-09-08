"""Tests for engineering-agent code diagnostics (OpenCode LSP-diagnostics parity).

Covers: enabled() env gate, ast syntax detection, clean-code path, reference-existence
check, summary shaping, never-raise. Offline-clean — ruff is OPTIONAL so we assert only
the stdlib `ast` baseline + path checks (no ruff dependency in assertions).
"""

from app.agents import code_diagnostics


def test_enabled_reads_env(monkeypatch):
    monkeypatch.delenv("CODE_DIAGNOSTICS", raising=False)
    assert code_diagnostics.enabled() is False
    monkeypatch.setenv("CODE_DIAGNOSTICS", "1")
    assert code_diagnostics.enabled() is True


def test_check_code_clean(monkeypatch):
    # disable rull lint so the assertion is stdlib-only / deterministic
    code = "def add(a, b):\n    return a + b\n"
    diags = code_diagnostics.check_code(code, run_lint=False)
    assert diags == []


def test_check_code_syntax_error():
    code = "def broken(:\n    return 1\n"
    diags = code_diagnostics.check_code(code, run_lint=False)
    assert len(diags) == 1
    assert diags[0]["level"] == "error"
    assert diags[0]["code"] == "syntax"
    assert diags[0]["line"] >= 1


def test_check_code_empty_returns_empty():
    assert code_diagnostics.check_code("") == []
    assert code_diagnostics.check_code("   \n  ") == []


def test_check_code_dedents_indented_block():
    # an LLM often returns an indented fragment; dedent should make it parseable
    code = "    x = 1\n    y = x + 2\n"
    assert code_diagnostics.check_code(code, run_lint=False) == []


def test_check_references_flags_missing(tmp_path):
    real = tmp_path / "exists.py"
    real.write_text("x = 1\n")
    diags = code_diagnostics.check_references(
        ["exists.py", "exists.py:10-20", "nope/missing.py:1-3"],
        project_root=str(tmp_path),
    )
    # only the missing one is flagged; the ":line-range" suffix is stripped; dedupe works
    assert len(diags) == 1
    assert diags[0]["code"] == "missing-file"
    assert "nope/missing.py" in diags[0]["message"]


def test_check_references_all_present(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    assert code_diagnostics.check_references(["a.py"], project_root=str(tmp_path)) == []


def test_summary_shapes():
    assert code_diagnostics.summary([]) == "ok — no diagnostics"
    diags = [
        {"level": "error", "code": "syntax", "line": 2, "col": 1, "message": "bad"},
        {"level": "warning", "code": "F821", "line": 5, "col": 1, "message": "undef"},
    ]
    s = code_diagnostics.summary(diags)
    assert "1 error(s), 1 warning(s)" in s
    assert "syntax" in s and "F821" in s


def test_never_raises_on_garbage():
    # non-str / weird inputs must not blow up
    assert code_diagnostics.check_code(None) == []  # type: ignore[arg-type]
    assert code_diagnostics.check_references(None) == []  # type: ignore[arg-type]
    assert code_diagnostics.check_references([None, "", 123]) == []  # type: ignore[list-item]
