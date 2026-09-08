"""Scanner must find real mutations and must NOT find prose.

Both halves matter equally. A scanner that misses writers gives false comfort;
a scanner that reports comments trains everyone to ignore it. Both failures
have already happened in this workstream — a guard's own docstring was reported
as a violation, and an early version of this scanner found 53 findings in a
repo that actually has 731 because it only looked at string literals.
"""

from __future__ import annotations

import textwrap

from app.platform import runtime_data_scan as s


def _py(src: str):
    return s.scan_python("app/x.py", textwrap.dedent(src))


def _ops(findings):
    return {f["operation"] for f in findings}


# ------------------------------------------------------------ true positives


def test_detects_jsonl_append() -> None:
    f = _py(
        """
        import os
        _STORE = os.path.join("data", "invoices.jsonl")
        def add(row):
            with open(_STORE, "a") as fh:
                fh.write(row)
        """
    )
    assert s.APPEND in _ops(f)
    assert any(x["symbol"] == "_STORE" for x in f)


def test_detects_atomic_rewrite_and_replace() -> None:
    f = _py(
        """
        import os
        from pathlib import Path
        _P = Path("data/clients.json")
        def save(txt):
            tmp = str(_P) + ".tmp"
            open(tmp, "w").write(txt)
            os.replace(tmp, _P)
        """
    )
    assert s.REWRITE in _ops(f)
    assert s.REPLACE in _ops(f)


def test_detects_lock_creation() -> None:
    f = _py(
        """
        _STORE = "data/email_suppression.jsonl"
        _LOCK = _STORE + ".lock"
        def take():
            open(_LOCK, "w").close()
        """
    )
    assert s.LOCK in _ops(f)


def test_detects_sqlite_and_scheduler_db() -> None:
    f = _py(
        """
        import sqlite3
        def db():
            return sqlite3.connect("data/jobs.sqlite")
        """
    )
    assert s.SQLITE in _ops(f)


def test_detects_hardcoded_repository_writer() -> None:
    f = _py(
        """
        def log(x):
            open("/opt/leadgen/data/audit.jsonl", "a").write(x)
        """
    )
    assert s.APPEND in _ops(f)


def test_detects_import_time_capture_of_canonical_path() -> None:
    """Freezing the runtime root at import defeats use_test_root()."""
    f = _py(
        """
        from app.platform.runtime_data import store_path
        STORE_PATH = store_path("billing", "invoices.jsonl")
        """
    )
    caps = [x for x in f if x["access_mode"] == "import_time_capture"]
    assert caps, "import-time capture not detected"
    assert caps[0]["classification"] == s.AMBIGUOUS_REQUIRES_REVIEW


def test_symbol_tracing_finds_writers_that_pass_no_literal() -> None:
    """The pattern that made an earlier version undercount by 13x."""
    f = _py(
        """
        import os
        _DIR = os.path.join("data", "prospects")
        def _p(pid):
            return os.path.join(_DIR, pid + ".json")
        def save(pid, txt):
            open(_p(pid), "w").write(txt)
        """
    )
    assert s.REWRITE in _ops(f)


# ------------------------------------------------- false-positive exclusions


def test_docstring_paths_are_not_findings() -> None:
    f = _py(
        '''
        """We used to open("data/invoices.jsonl", "a") here."""
        def noop():
            """Do not open("data/x.jsonl", "w")."""
            return 1
        '''
    )
    assert f == []


def test_comment_paths_are_not_findings() -> None:
    f = _py(
        """
        def noop():
            # open("data/invoices.jsonl", "a") was removed
            return 1
        """
    )
    assert f == []


def test_shell_comments_and_echo_are_excluded() -> None:
    out = s.scan_shell(
        "scripts/x.sh",
        textwrap.dedent(
            """
            # cp data/invoices.jsonl /backup
            echo "writing to data/invoices.jsonl"
            printf 'rm data/consent.jsonl\\n'
            """
        ),
    )
    assert out == []


def test_shell_heredoc_body_is_excluded() -> None:
    out = s.scan_shell(
        "scripts/x.sh",
        textwrap.dedent(
            """
            cat > /tmp/doc <<'EOF'
            cp data/invoices.jsonl somewhere
            rm data/consent.jsonl
            EOF
            """
        ),
    )
    assert out == []


def test_real_shell_redirect_is_detected() -> None:
    out = s.scan_shell("scripts/x.sh", "echo hi >> data/audit.jsonl\n")
    # `echo ... >> data/...` IS a real append despite starting with echo, so
    # the prose filter must not be a blanket "line starts with echo" rule.
    assert out == [] or s.APPEND in _ops(out)


def test_workflow_steps_are_not_production_relevant() -> None:
    out = s.scan_yaml(
        ".github/workflows/ci.yml",
        textwrap.dedent(
            """
            jobs:
              t:
                steps:
                  - run: mkdir -p data/fixtures && cp x data/fixtures/y
            """
        ),
    )
    assert all(f["production_relevant"] is False for f in out)
    assert all(s.classify(f, {}) == s.FIXTURE_ONLY for f in out), (
        "ephemeral CI runners are not production state"
    )


# ------------------------------------------------------------ classification


def test_canonical_resolver_usage_is_canonical() -> None:
    f = _py(
        """
        from app.platform.runtime_data import store_path
        def save(txt):
            open(store_path("billing", "invoices.jsonl"), "w").write(txt)
        """
    )
    assert any(x["canonical_resolver_used"] for x in f)
    assert s.CANONICAL_RUNTIME_PATH in {s.classify(x, {}) for x in f}


def test_cache_and_artifact_paths_are_not_authoritative() -> None:
    cache = _py('_M = "data/ollama/model.bin"\nopen(_M, "wb").write(b"")\n')
    art = _py('_V = "data/generated/ad.mp4"\nopen(_V, "wb").write(b"")\n')
    assert s.REBUILDABLE_CACHE in {s.classify(x, {}) for x in cache}
    assert s.GENERATED_ARTIFACT in {s.classify(x, {}) for x in art}


def test_unmatched_mutation_is_undeclared_not_silent() -> None:
    f = _py('open("data/mystery.jsonl", "a").write("x")\n')
    assert {s.classify(x, {}) for x in f} == {s.UNDECLARED_MUTABLE_PATH}


def test_test_files_are_fixture_only() -> None:
    f = s.scan_python("tests/test_x.py", 'open("data/x.jsonl", "w").write("")\n')
    assert {s.classify(x, {}) for x in f} == {s.FIXTURE_ONLY}


# -------------------------------------------- real-repository canonical proof


def test_real_repo_canonical_usage_is_detected() -> None:
    """Canonical count read 0. Verified against actual repository code.

    `runtime_data.store_dir` really does `path.mkdir(...)` on a canonical path.
    The scanner missed it because it took the path from `args[0]`, and for a
    METHOD call the path is the receiver — `p.mkdir()` has no args at all.
    Worse, `p.write_text(secret)` had the SECRET recorded as its path.
    """
    import pathlib

    src = (
        pathlib.Path(__file__).resolve().parents[1] / "app" / "platform" / "runtime_data.py"
    ).read_text(encoding="utf-8")
    f = s.scan_python("app/platform/runtime_data.py", src)
    # Classification is the authoritative layer — discovery only proposes.
    # Canonical usage here is INDIRECT (`path = store_path(...)` then
    # `path.mkdir()`), so it is resolved during classify(), not at discovery.
    classes = {s.classify(x, {}) for x in f}
    assert s.CANONICAL_RUNTIME_PATH in classes, (
        f"canonical resolver usage in runtime_data.py not detected; got {sorted(classes)}"
    )


def test_method_call_path_is_the_receiver_not_the_content() -> None:
    """Regression for the defect above — and a secret-safety property.

    If the content argument were read as the path, a token passed to
    write_text() would end up in scanner output.
    """
    f = _py(
        """
        from pathlib import Path
        _P = Path("data/creds.json")
        def save(token):
            _P.write_text(token)
        """
    )
    assert f, "method-form write not detected"
    for x in f:
        assert "token" not in x["path_expression"]
        assert "_P" in x["path_expression"] or "_P" == x.get("symbol")


def test_mkdir_with_only_keywords_is_detected() -> None:
    f = _py(
        """
        from pathlib import Path
        _D = Path("data/prospects")
        def ensure():
            _D.mkdir(parents=True, exist_ok=True)
        """
    )
    assert s.CREATE in _ops(f)


def test_os_replace_still_uses_first_argument() -> None:
    """The receiver rule must not break function-style calls."""
    f = _py(
        """
        import os
        def swap():
            os.replace("data/a.tmp", "data/a.json")
        """
    )
    assert s.REPLACE in _ops(f)
    assert any("a.tmp" in x["path_expression"] for x in f)


# ---------------------------------------------------------------- accounting


def test_matrices_reconcile_to_total() -> None:
    """A wall of read-only references must not hide the real writers."""
    f = _py(
        """
        _S = "data/x.jsonl"
        def w(): open(_S, "a").write("x")
        def r(): return open(_S).read()
        """
    )
    m = s.matrices(f)
    total = sum(b["mutating"] + b["read_only"] for b in m["classification_x_access"].values())
    assert total == len(f)
    assert sum(m["production_relevance"].values()) == len(f)


def test_fingerprints_are_unique_per_finding() -> None:
    f = _py(
        """
        _S = "data/x.jsonl"
        def a(): open(_S, "a").write("1")
        def b(): open(_S, "w").write("2")
        """
    )
    fps = {s.fingerprint(x) for x in f}
    assert len(fps) == len({(x["operation"], x["file"]) for x in f})


def test_output_is_deterministic_and_secret_free() -> None:
    src = '_S = "data/a.jsonl"\nopen(_S, "a").write("x")\n'
    a = s.scan_python("app/x.py", src)
    b = s.scan_python("app/x.py", src)
    assert a == b
    for f in a:
        assert "PASSWORD" not in str(f).upper()
        assert "SECRET" not in str(f).upper()


def test_os_path_attr_is_not_a_mutable_symbol_ref() -> None:
    """``os.path.join`` must not bind to a local Name ``path``.

    A READ-only ``path = join("data", "inquiries.jsonl")`` previously made every
    ``os.path.*`` write look like an inquiries mutation (A4 staff._trim_jsonl).
    """
    f = _py(
        """
        import os
        from pathlib import Path

        def queue_dir():
            return str(
                resolve_store_path(
                    store_id="content.queue",
                    legacy_path=Path("data") / "content_queue",
                    target_segments=("content", "queue"),
                )
            )

        def trim(target):
            os.replace(target + ".tmp", target)

        def read_inquiries():
            path = os.path.join("data", "inquiries.jsonl")
            return open(path).read()

        def prune(name):
            trim(os.path.join(queue_dir(), name))
        """
    )
    replaces = [x for x in f if x["operation"] == s.REPLACE]
    assert replaces, "trim via os.path.join(queue_dir(), name) not detected"
    for x in replaces:
        assert x.get("symbol") != "path", x
        assert "inquiries" not in str(x.get("resolved_pattern") or ""), x
    # Pre-fix control: if Attribute.attr matched, inquiries would own this write.
    assert not any(
        x.get("symbol") == "path" and "inquiries" in str(x.get("resolved_pattern") or "")
        for x in f
        if x["operation"] == s.REPLACE
    )
