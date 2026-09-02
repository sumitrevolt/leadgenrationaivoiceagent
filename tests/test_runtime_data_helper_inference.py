"""Helper inference must be derived from the AST body, never from the name.

Three Tier 0 compliance authorities (WhatsApp suppression, consent ledger,
voice suppression) are only visible because of this inference. Authority
decisions are about to be made on those findings, so a helper called `_append`
that appends to a LIST must not become a filesystem writer, and a helper whose
first argument is content must not have that content read as a path.
"""

from __future__ import annotations

import ast
import pathlib
import textwrap

from app.platform import runtime_data_scan as s

_REPO = pathlib.Path(__file__).resolve().parents[1]


def _helpers(src: str) -> dict:
    return s._path_taking_writers(ast.parse(textwrap.dedent(src)))


def _scan(src: str):
    return s.scan_python("app/x.py", textwrap.dedent(src))


def _ops(findings):
    return {f["operation"] for f in findings}


# --------------------------------------- local path-return helper provenance


def _helpers_of(src: str) -> dict:
    return s._path_return_helpers(ast.parse(textwrap.dedent(src)), {})


def test_env_root_with_static_fallback_is_a_bounded_pattern() -> None:
    h = _helpers_of(
        """
        def root():
            return os.getenv("STORE_DIR", "data/store")
        """
    )
    assert h["root"] == s.PROVEN_DYNAMIC_PATH_PATTERN


def test_nested_path_return_helper_resolves() -> None:
    src = """
        def root():
            return os.getenv("STORE_DIR", "data/store")
        def item_path(item_id):
            return os.path.join(root(), f"{item_id}.json")
    """
    h = _helpers_of(src)
    assert "item_path" in h
    tree = ast.parse(textwrap.dedent(src))
    pat = s._helper_patterns(tree, h)["item_path"]
    assert "STORE_DIR" in pat and "data/store" in pat
    # The interpolated id is STRUCTURE only — never a runtime value.
    assert "item_id" not in pat


def test_conflicting_returns_prove_nothing() -> None:
    """One path branch and one unknown branch is not a path."""
    assert (
        _helpers_of(
            """
            def maybe_path(flag):
                if flag:
                    return Path("data/store")
                return build_prompt()
            """
        )
        == {}
    )


def test_unknown_call_supplying_the_root_proves_nothing() -> None:
    assert _helpers_of("def root():\n    return fetch_root()\n") == {}


def test_mutually_recursive_helpers_terminate_without_proof() -> None:
    assert _helpers_of("def a(): return b()\ndef b(): return a()\n") == {}


def test_helper_name_is_not_evidence() -> None:
    """`_root` returning an upper-cased string is not a path."""
    assert (
        _helpers_of(
            """
            def _root(x):
                '''Returns the storage root.'''
                return x.upper()
            """
        )
        == {}
    )


def test_env_read_without_a_default_is_unbounded() -> None:
    """No fallback means nothing bounds the value, so it is not proven."""
    assert _helpers_of('def root():\n    return os.getenv("STORE_DIR")\n') == {}


def test_helper_pattern_never_leaks_environment_values(monkeypatch) -> None:
    monkeypatch.setenv("STORE_DIR", "/secret/real/location")
    src = 'def root():\n    return os.getenv("STORE_DIR", "data/store")\n'
    tree = ast.parse(src)
    pat = s._helper_patterns(tree, s._path_return_helpers(tree, {}))["root"]
    assert "/secret/real/location" not in pat
    assert "STORE_DIR" in pat


# ------------------------------------------ conditional path provenance (v1)


def test_conditional_path_expression_is_proven_when_both_branches_are() -> None:
    """`x = f() if cond else g()` where BOTH branches are proven paths.

    `runtime_data.store_dir` is written exactly this way. Provenance had no
    `ast.IfExp` arm, so the ternary fell through to UNSUPPORTED_EXPRESSION,
    `path` never entered the table, and the canonical `path.mkdir()` — the one
    call that proves the canonical resolver is used — was never recorded.
    """
    src = """
        def store_dir(*segments):
            path = store_path(*segments) if segments else runtime_root()
            path.mkdir(parents=True, exist_ok=True)
            return path
    """
    tree = ast.parse(textwrap.dedent(src))
    assert "path" in s._provenance_table(tree)
    hits = [f for f in _scan(src) if f.get("symbol") == "path"]
    assert hits, "canonical store_dir mkdir not detected"
    assert {f["operation"] for f in hits} == {s.CREATE}
    assert len(hits) == 1, f"duplicate emission: {hits}"
    assert s.CANONICAL_RUNTIME_PATH in {s.classify(f, {}) for f in hits}


def test_conditional_path_expression_requires_both_branches_proven() -> None:
    """One unproven branch means the value is not proven to be a path.

    Accepting a half-proven ternary would re-open arbitrary-receiver writes,
    which is the failure the provenance authority exists to prevent.
    """
    src = """
        def pick(flag, blob):
            path = store_path("a") if flag else blob
            path.mkdir(parents=True, exist_ok=True)
    """
    tree = ast.parse(textwrap.dedent(src))
    assert "path" not in s._provenance_table(tree)
    assert [f for f in _scan(src) if f.get("symbol") == "path"] == []


def test_real_repo_store_dir_canonical_mkdir_is_detected() -> None:
    """The real canonical authority in runtime_data.py, not a synthetic stand-in."""
    rel = "app/platform/runtime_data.py"
    f = s.scan_python(rel, (_REPO / rel).read_text(encoding="utf-8"))
    assert s.CANONICAL_RUNTIME_PATH in {s.classify(x, {}) for x in f}, sorted(
        {s.classify(x, {}) for x in f}
    )
    assert [x for x in f if x.get("symbol") == "path"], "store_dir mkdir missing"
    # The two pre-existing runtime_root() findings must survive the fix.
    assert len([x for x in f if x.get("symbol") == "root"]) == 2


# ------------------------------------------------- scope + receiver (Stage A)


def test_bound_method_call_is_not_a_local_helper() -> None:
    """`aq.queue_task(action, ...)` must not resolve to a class method.

    `self_improve.py` has a module helper `_append(path, rec)` and an unrelated
    `AutoQueue.queue_task(self, task_name, reason, cost_estimate)`. Resolving
    the attribute call through the flat helper registry marked the plain string
    `action` as a REWRITE of a runtime store.
    """
    src = """
        def _append(path, rec):
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(rec)

        class AutoQueue:
            def queue_task(self, task_name, reason):
                _append("data/queue.jsonl", reason)

        def run(action):
            aq = AutoQueue()
            aq.queue_task(action, "why")
    """
    assert "queue_task" not in _helpers(src)
    hits = [f for f in _scan(src) if f.get("symbol") == "action"]
    assert hits == [], hits


def test_static_method_keeps_every_parameter() -> None:
    """A @staticmethod has no implicit receiver, so arg0 stays a candidate."""
    h = _helpers(
        """
        class Store:
            @staticmethod
            def dump(path, rows):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(rows)
        """
    )
    # Not registered (methods are unreachable by a bare name) ...
    assert "dump" not in h


def test_instance_method_receiver_is_never_the_path() -> None:
    """`self` must not be inferred as the path parameter of a method."""
    h = _helpers(
        """
        class Store:
            def save(self, rows):
                with open(self, "w", encoding="utf-8") as fh:
                    fh.write(rows)
        """
    )
    assert "save" not in h


def test_bare_local_helper_still_resolves() -> None:
    """The scope fix must not suppress the real module-level helper."""
    src = """
        LEDGER = "data/consent_ledger.jsonl"

        def _append(path, rec):
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(rec)

        def record(rec):
            _append(LEDGER, rec)
    """
    assert _helpers(src)["_append"]["operation"] == "APPEND"
    assert "APPEND" in _ops(_scan(src))


def test_nested_helper_does_not_escape_its_scope() -> None:
    """A closure is invisible outside its parent and must not claim call sites."""
    src = """
        def outer():
            def _write(path, rec):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(rec)
            _write("data/inner.json", "x")

        def unrelated(payload):
            _write(payload, "y")
    """
    assert "_write" not in _helpers(src)
    assert [f for f in _scan(src) if f.get("symbol") == "payload"] == []


# ------------------------------------------------------------------ positive


def test_direct_append_helper() -> None:
    h = _helpers(
        """
        def _append(path, record):
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(record)
        """
    )
    assert h["_append"]["operation"] == s.APPEND
    assert h["_append"]["path_param"] == "path"


def test_path_parameter_is_not_first() -> None:
    """`_write_all(records, destination)` — position 1 is the path."""
    h = _helpers(
        """
        def _write_all(records, destination):
            with open(destination, "w", encoding="utf-8") as fh:
                fh.write(records)
        """
    )
    assert h["_write_all"]["operation"] == s.REWRITE
    assert h["_write_all"]["path_param"] == "destination"
    assert h["_write_all"]["path_index"] == 1


def test_keyword_call_site_resolves_the_path() -> None:
    f = _scan(
        """
        import os
        SUPPRESSION_FILE = os.path.join("data", "wa_suppression.jsonl")
        def _write_all(records, destination):
            with open(destination, "w", encoding="utf-8") as fh:
                fh.write(records)
        def save(items):
            _write_all(records=items, destination=SUPPRESSION_FILE)
        """
    )
    assert s.REWRITE in _ops(f)
    assert any(x.get("symbol") == "SUPPRESSION_FILE" for x in f), [
        (x.get("symbol"), x["operation"]) for x in f
    ]


def test_atomic_rewrite_helper_reports_replace() -> None:
    h = _helpers(
        """
        import os
        def _replace_all(destination, records):
            tmp = destination + ".tmp"
            open(tmp, "w").write(records)
            os.replace(tmp, destination)
        """
    )
    assert h["_replace_all"]["operation"] == s.REPLACE
    assert h["_replace_all"]["path_param"] == "destination"


def test_nested_local_helper_inherits_semantics() -> None:
    h = _helpers(
        """
        def _write_all(records, destination):
            with open(destination, "w") as fh:
                fh.write(records)
        def _save(path, data):
            _write_all(data, destination=path)
        """
    )
    assert h["_save"]["operation"] == s.REWRITE
    assert h["_save"]["path_param"] == "path"


def test_directory_preparation_does_not_replace_the_real_operation() -> None:
    """`mkdir` before an append is preparation, not the store authority."""
    h = _helpers(
        """
        def _append(path, record):
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a") as fh:
                fh.write(record)
        """
    )
    assert h["_append"]["operation"] == s.APPEND


def test_read_only_helper_is_read() -> None:
    h = _helpers(
        """
        def _load(path):
            return path.read_text()
        """
    )
    assert h["_load"]["operation"] == s.READ


# ------------------------------------------------------------------ negative


def test_in_memory_append_is_not_a_filesystem_writer() -> None:
    """The name is `_append`. The body appends to a LIST."""
    h = _helpers(
        """
        def _append(items, value):
            items.append(value)
        """
    )
    assert "_append" not in h


def test_stream_writer_is_not_a_path_writer() -> None:
    h = _helpers(
        """
        def write_message(content, stream):
            stream.write(content)
        """
    )
    assert "write_message" not in h


def test_console_helper_is_not_a_writer() -> None:
    h = _helpers(
        """
        def _emit(value):
            print(value)
        """
    )
    assert "_emit" not in h


def test_content_first_helper_never_treats_content_as_the_path() -> None:
    """The dangerous case: content in position 0, path in position 1."""
    h = _helpers(
        """
        def write_text(content, destination):
            destination.write_text(content)
        """
    )
    assert h["write_text"]["path_param"] == "destination"
    assert h["write_text"]["path_index"] == 1

    f = _scan(
        """
        from pathlib import Path
        STORE = Path("data/creds.jsonl")
        def write_text(content, destination):
            destination.write_text(content)
        def save():
            write_text("TEST_ONLY_CREDENTIAL_PAYLOAD", STORE)
        """
    )
    blob = repr(f)
    assert "TEST_ONLY_CREDENTIAL_PAYLOAD" not in blob
    assert any(x.get("symbol") == "STORE" for x in f)


def test_imported_helper_is_not_inferred_from_its_name() -> None:
    """`persist` sounds like a writer. Its body is not available."""
    f = _scan(
        """
        import os
        from external_module import persist
        STORE = os.path.join("data", "x.jsonl")
        def save(record):
            persist(STORE, record)
        """
    )
    assert all(x["operation"] not in (s.APPEND, s.REWRITE) for x in f), [
        (x["operation"], x["access_mode"]) for x in f
    ]


# --------------------------------------------------------- recursion / cycles


def test_mutually_recursive_helpers_do_not_crash() -> None:
    src = """
        def a(path, data):
            b(path, data)
        def b(path, data):
            a(path, data)
    """
    h = _helpers(src)
    # Neither can be proven to write; the requirement is bounded analysis and
    # no crash, not a confident answer.
    assert "a" not in h or h["a"]["operation"] in (s.UNKNOWN, s.READ)
    assert _scan(src) is not None


def test_self_recursive_helper_is_bounded() -> None:
    h = _helpers(
        """
        def walk(path, depth):
            if depth:
                walk(path, depth - 1)
        """
    )
    assert "walk" not in h


# ------------------------------------------------------------ secret safety


def test_no_secret_shaped_value_reaches_any_output_surface() -> None:
    """Synthetic, unmistakable, test-only markers."""
    src = """
        from pathlib import Path
        TOTP = Path("data/customer_totp.jsonl")
        WEBHOOK = Path("data/customer_webhooks.jsonl")
        def save():
            TOTP.write_text("TEST_ONLY_TOTP_SEED_DO_NOT_USE")
            WEBHOOK.write_text("TEST_ONLY_WEBHOOK_SIGNING_SECRET")
    """
    findings = _scan(src)
    markers = (
        "TEST_ONLY_TOTP_SEED_DO_NOT_USE",
        "TEST_ONLY_WEBHOOK_SIGNING_SECRET",
    )
    import json

    surfaces = [
        repr(findings),
        json.dumps(findings, default=str),
        json.dumps([s.fingerprint(f) for f in findings]),
        json.dumps(s.matrices(findings), default=str),
        json.dumps([s.normalized_path(f) for f in findings]),
    ]
    for surface in surfaces:
        for marker in markers:
            assert marker not in surface, f"leaked {marker}"
    assert findings, "the writes must still be detected"


def test_environment_values_are_not_serialized() -> None:
    f = _scan(
        """
        import os
        _P = os.path.join("data", "x.jsonl")
        def w():
            open(_P, "a").write(os.environ["TEST_ONLY_API_TOKEN"])
        """
    )
    assert "TEST_ONLY_API_TOKEN" not in repr(f)


# ------------------------------------------- real repository helper evidence


def test_real_consent_ledger_helpers_are_inferred() -> None:
    src = (_REPO / "app" / "telephony" / "consent_ledger.py").read_text(encoding="utf-8")
    h = s._path_taking_writers(ast.parse(src))
    assert "_append" in h and h["_append"]["operation"] == s.APPEND
    assert "_write_all" in h and h["_write_all"]["operation"] == s.REWRITE

    findings = s.scan_python("app/telephony/consent_ledger.py", src)
    symbols = {f.get("symbol") for f in findings}
    # A2 replaced the LEDGER_FILE / SUPPRESSION_FILE constants with resolver
    # CALLS. The scanner must keep seeing the writes through that shape too —
    # a detector that only recognised module constants would have gone quiet on
    # the repo's two most compliance-critical stores the moment they migrated,
    # and reported that silence as zero findings.
    assert "ledger_path" in symbols
    assert "suppression_path" in symbols
    # The retention sweep really does rewrite the voice suppression list.
    assert any(
        f.get("symbol") == "suppression_path" and f["operation"] == s.REWRITE for f in findings
    )


def test_real_wa_campaign_runner_helpers_are_inferred() -> None:
    src = (_REPO / "app" / "marketing" / "wa_campaign_runner.py").read_text(encoding="utf-8")
    findings = s.scan_python("app/marketing/wa_campaign_runner.py", src)
    # Resolver call, not a constant, since A2 — see the consent-ledger test above.
    suppression = [f for f in findings if f.get("symbol") == "_suppression_path"]
    assert suppression, "WhatsApp suppression writers not detected"
    assert {f["operation"] for f in suppression} & {s.APPEND, s.REWRITE}


# ============================================================ method dispatch
#
# A method NAME never proves filesystem semantics; the receiver's provenance
# does. Treating the name as proof classified a prompt builder as a REPLACE
# writer and turned a READ into a destructive operation — a regression, not new
# visibility, and one no capability record may launder.


def test_string_replace_is_not_a_filesystem_operation() -> None:
    f = _scan(
        """
        def build(text):
            return text.replace("old", "new")
        """
    )
    assert s.REPLACE not in _ops(f)
    assert "old" not in repr(f) or not f


def test_list_remove_is_not_a_filesystem_delete() -> None:
    f = _scan(
        """
        def prune(items, value):
            items.remove(value)
        """
    )
    assert s.DELETE not in _ops(f)


def test_arbitrary_stream_write_is_not_a_path_writer() -> None:
    """Arbitrary receiver — distinct from the local-helper case above."""
    f = _scan(
        """
        def emit(stream, content):
            stream.write(content)
        """
    )
    assert not (_ops(f) & s.MUTATING_OPERATIONS)
    assert "content" not in "".join(x.get("path_expression", "") for x in f)


def test_arbitrary_object_replace_is_not_a_filesystem_replace() -> None:
    """The real prompt-builder shape from app/ml/agent_brain.py."""
    f = _scan(
        """
        AGENT_KNOWLEDGE_MAP = {}
        def _build_agent_system_prompt(context, a, b):
            agent_config = AGENT_KNOWLEDGE_MAP.get(context.agent_role, {})
            return agent_config.replace(a, b)
        """
    )
    assert s.REPLACE not in _ops(f)


def test_proven_path_replace_is_a_filesystem_operation() -> None:
    """Receiver proven by `Path(...)` assignment — not by being named tmp_path."""
    f = _scan(
        """
        from pathlib import Path
        tmp = Path("data/store.jsonl.tmp")
        destination = Path("data/store.jsonl")
        def commit():
            tmp.replace(destination)
        """
    )
    assert s.REPLACE in _ops(f), [(x["operation"], x["path_expression"]) for x in f]


def test_os_replace_destination_is_the_authority() -> None:
    f = _scan(
        """
        import os
        def commit(tmp, destination):
            os.replace(tmp, destination)
        """
    )
    h = _helpers(
        """
        import os
        def commit(tmp, destination):
            os.replace(tmp, destination)
        """
    )
    assert h["commit"]["path_param"] == "destination"
    assert h["commit"]["operation"] == s.REPLACE
    assert f is not None
