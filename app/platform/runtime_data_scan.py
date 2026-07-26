"""Structural scanner for mutable filesystem dependencies.

Production mutable state still lives inside the Git checkout. Before any of it
can be migrated, every place that reads or writes it has to be *visible* -- and
visible in a way that cannot rot, because a hand-maintained list of "files that
touch data/" was wrong four times in a row earlier in this workstream.

Two layers, deliberately separated:

  * RAW DISCOVERY finds candidates. It is allowed to over-match.
  * SEMANTIC CLASSIFICATION decides what a candidate actually is. Only this
    layer, combined with the controlled allowlist, is authoritative.

The separation exists because substring matching has already produced false
findings twice here -- once reading a guard's own docstring ("no `|| true`") as
a violation, once reading a comment that explained a fix as though it were the
bug. Comments, docstrings and echoed instructions are therefore excluded with
proof rather than by hope.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

# ------------------------------------------------------------ classifications
CANONICAL_RUNTIME_PATH = "CANONICAL_RUNTIME_PATH"
DECLARED_LEGACY_READ = "DECLARED_LEGACY_READ"
DECLARED_LEGACY_WRITE = "DECLARED_LEGACY_WRITE"
FIXTURE_ONLY = "FIXTURE_ONLY"
STATIC_ASSET = "STATIC_ASSET"
GENERATED_ARTIFACT = "GENERATED_ARTIFACT"
REBUILDABLE_CACHE = "REBUILDABLE_CACHE"
DOCUMENTATION_EXAMPLE = "DOCUMENTATION_EXAMPLE"
UNDECLARED_MUTABLE_PATH = "UNDECLARED_MUTABLE_PATH"
AMBIGUOUS_REQUIRES_REVIEW = "AMBIGUOUS_REQUIRES_REVIEW"

CLASSIFICATIONS = (
    CANONICAL_RUNTIME_PATH,
    DECLARED_LEGACY_READ,
    DECLARED_LEGACY_WRITE,
    FIXTURE_ONLY,
    STATIC_ASSET,
    GENERATED_ARTIFACT,
    REBUILDABLE_CACHE,
    DOCUMENTATION_EXAMPLE,
    UNDECLARED_MUTABLE_PATH,
    AMBIGUOUS_REQUIRES_REVIEW,
)

# ------------------------------------------------------------------ operations
READ = "READ"
APPEND = "APPEND"
REWRITE = "REWRITE"
CREATE = "CREATE"
DELETE = "DELETE"
REPLACE = "REPLACE"
LOCK = "LOCK"
SQLITE = "SQLITE"
CACHE_WRITE = "CACHE_WRITE"
ARTIFACT_WRITE = "ARTIFACT_WRITE"
UNKNOWN = "UNKNOWN"

MUTATING_OPERATIONS = frozenset(
    {APPEND, REWRITE, CREATE, DELETE, REPLACE, LOCK, SQLITE, CACHE_WRITE, ARTIFACT_WRITE}
)

# Directories that hold checkout-backed mutable state.
_MUTABLE_ROOT_RE = re.compile(
    r"(?:^|[\"'/\\(])(?:\./)?(?:/opt/leadgen/)?(data|var/runtime-data|runtime-data)[/\\]"
)

# Canonical resolver surface. Paths built through these are already correct.
_CANONICAL_MODULE = "runtime_data"
_CANONICAL_FUNCS = frozenset({"store_path", "store_dir", "lock_path", "runtime_data_path"})

# Directories excluded from scanning entirely (not source of production truth).
_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "graphify-out",
        "unity",
        "htmlcov",
        "site-packages",
    }
)

_PY_EXT = frozenset({".py"})
_SHELL_EXT = frozenset({".sh", ".bash"})
_YAML_EXT = frozenset({".yml", ".yaml"})


def _finding(**kw: Any) -> dict[str, Any]:
    kw.setdefault("symbol", None)
    kw.setdefault("store_id", None)
    kw.setdefault("canonical_resolver_used", False)
    kw.setdefault("production_relevant", True)
    kw.setdefault("confidence", "high")
    kw.setdefault("evidence", "")
    kw["finding_id"] = "{}:{}:{}".format(kw["file"], kw["line"], kw["operation"])
    return kw


# ============================================================ python AST layer

# call target -> operation, for calls whose FIRST positional arg is a path
_CALL_OPERATIONS: dict[str, str] = {
    "write_text": REWRITE,
    "write_bytes": REWRITE,
    "unlink": DELETE,
    "remove": DELETE,
    "rmtree": DELETE,
    "replace": REPLACE,
    "rename": REPLACE,
    "truncate": REWRITE,
    "mkdir": CREATE,
    "makedirs": CREATE,
    "touch": CREATE,
    "copy": REWRITE,
    "copy2": REWRITE,
    "copyfile": REWRITE,
    "connect": SQLITE,
    "read_text": READ,
    "read_bytes": READ,
    "open": UNKNOWN,  # resolved from the mode argument
}


def _mode_to_operation(mode: str) -> str:
    if "a" in mode:
        return APPEND
    if "w" in mode or "x" in mode or "+" in mode:
        return REWRITE
    return READ


def _literal_strings(node: ast.AST) -> list[str]:
    """String literals reachable in a path expression, including os.path.join
    and f-string prefixes. Used to decide whether a path is mutable."""
    out: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return out


def _expr_source(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return "<unparseable>"


def _uses_canonical_resolver(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name in _CANONICAL_FUNCS:
                return True
            if isinstance(fn, ast.Attribute) and getattr(fn.value, "id", None) == _CANONICAL_MODULE:
                return True
    return False


def _looks_mutable(strings: list[str], expr: str) -> str | None:
    """Return the matched mutable-root pattern, or None."""
    for s in strings:
        m = _MUTABLE_ROOT_RE.search(s)
        if m:
            return m.group(1)
        if s in {"data", "runtime-data"}:
            return s
    # DATA_DIR / RUNTIME_DATA_DIR style symbols in the expression itself.
    if re.search(r"\bDATA_DIR\b|\bDATA_PATH\b|\bSTORE_DIR\b", expr):
        return "DATA_DIR"
    return None


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """Line numbers of docstring constants, so prose is never a finding."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                first = body[0].value
                for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                    lines.add(ln)
    return lines


# Names that, as an attribute call, take the path as the RECEIVER.
_RECEIVER_PATH_CALLS = frozenset(
    {
        "write_text",
        "write_bytes",
        "read_text",
        "read_bytes",
        "unlink",
        "mkdir",
        "touch",
        "truncate",
        "replace",
        "rename",
    }
)

# Module names that make an attribute call function-style instead.
#
# `path` is NOT in this list. Including it (thinking of `os.path`) discarded the
# receiver of every `path.mkdir()` / `path.write_text()` in the repo, because
# `path` is overwhelmingly a variable name for an actual path rather than a
# module alias. That single word was why canonical findings read 0.
_PATH_MODULES = frozenset({"os", "shutil", "sqlite3", "shelve", "dbm"})


def _path_argument(node: ast.Call, name: str) -> ast.AST | None:
    """Return the sub-expression that is actually the PATH."""
    fn = node.func
    if isinstance(fn, ast.Attribute) and name in _RECEIVER_PATH_CALLS:
        base = getattr(fn.value, "id", None)
        if base not in _PATH_MODULES:
            return fn.value  # p.write_text(data) -> p
    return node.args[0] if node.args else None


def _path_taking_writers(tree: ast.Module) -> dict[str, str]:
    """Module-local helpers that write to a path passed IN as a parameter.

    This closes the scanner's worst blind spot. `consent_ledger.py` and
    `wa_campaign_runner.py` -- the two most compliance-critical suppression
    stores in the repo -- produced ZERO findings, because every write goes
    through local helpers:

        _append(LEDGER_FILE, rec)
        _write_all(SUPPRESSION_FILE, keep)

    The scanner only recognised a fixed set of stdlib call names, so the
    authority looked clean when it was merely invisible. Reporting "0 findings"
    for a Tier 0 compliance store because of that would be exactly the false
    comfort this whole workstream keeps correcting.

    Returns {function_name: operation}.
    """
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        params = {a.arg for a in node.args.args}
        if not params:
            continue
        op: str | None = None
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            nm = getattr(sub.func, "attr", None) or getattr(sub.func, "id", None)
            if nm not in _CALL_OPERATIONS:
                continue
            target = _path_argument(sub, nm)
            if target is None:
                continue
            # Does the write act on one of this function's parameters?
            names = {getattr(x, "id", None) for x in ast.walk(target) if isinstance(x, ast.Name)}
            if not (names & params):
                continue
            cand = _CALL_OPERATIONS[nm]
            if nm == "open":
                mode = "r"
                if len(sub.args) > 1 and isinstance(sub.args[1], ast.Constant):
                    mode = str(sub.args[1].value)
                for kw in sub.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = str(kw.value.value)
                cand = _mode_to_operation(mode)
            # Prefer the most destructive operation the helper performs.
            if op is None or _OP_SEVERITY.get(cand, 0) > _OP_SEVERITY.get(op, 0):
                op = cand
        if op:
            out[node.name] = op
    return out


_OP_SEVERITY = {READ: 0, CREATE: 1, LOCK: 2, APPEND: 3, REWRITE: 4, REPLACE: 4, DELETE: 5}


def _mutable_symbols(tree: ast.Module) -> dict[str, str]:
    """Names bound to a mutable-looking path, plus functions returning one.

    Two passes so that a symbol assigned from another symbol
    (`_LOCK = _STORE.with_suffix(".lock")`) still resolves.
    """
    syms: dict[str, str] = {}
    for _ in range(2):
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                value, targets = node.value, node.targets
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                value, targets = node.value, [node.target]
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                # A helper whose body returns a mutable path counts as a symbol
                # under its own name, so `open(store_path(), "a")` resolves.
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Return) and sub.value is not None:
                        expr = _expr_source(sub.value)
                        if _looks_mutable(_literal_strings(sub.value), expr) or _refs(
                            sub.value, syms
                        ):
                            syms.setdefault(node.name, expr[:120])
                continue
            else:
                continue

            expr = _expr_source(value)
            # Canonical assignments count as mutable-path symbols too. Without
            # this, `path = store_path(...)` never enters the symbol table, so
            # the `path.mkdir()` on the next line is invisible — which is why
            # canonical findings read 0 even for runtime_data.py itself.
            if (
                _looks_mutable(_literal_strings(value), expr)
                or _refs(value, syms)
                or _uses_canonical_resolver(value)
            ):
                for t in targets:
                    tname = getattr(t, "id", None) or getattr(t, "attr", None)
                    if tname:
                        syms.setdefault(tname, expr[:120])
    return syms


def _refs(node: ast.AST, syms: dict[str, str]) -> bool:
    """Does this expression reference an already-known mutable symbol?"""
    if not syms:
        return False
    for sub in ast.walk(node):
        name = getattr(sub, "id", None) or getattr(sub, "attr", None)
        if name and name in syms:
            return True
    return False


def scan_python(rel: str, text: str) -> list[dict[str, Any]]:
    """AST scan of one Python file. Never raises on bad syntax."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    doc_lines = _docstring_nodes(tree)
    findings: list[dict[str, Any]] = []
    # Helper-relationship tracing. Almost no real writer passes a literal:
    # the pattern is `_STORE = Path("data/x.jsonl")` (or a function returning
    # it) and then `open(_STORE, "a")` somewhere else entirely. Without this
    # pass the scanner sees 53 findings in a repo that has hundreds, which
    # would be a scanner that reports a comfortable number instead of a true
    # one -- the exact failure mode this whole workstream keeps hitting.
    symbols = _mutable_symbols(tree)
    local_writers = _path_taking_writers(tree)

    # --- module-level capture of a runtime path (freezes the root at import).
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not _uses_canonical_resolver(node.value):
            continue
        target = _expr_source(node.targets[0]) if node.targets else "<?>"
        findings.append(
            _finding(
                file=rel,
                line=node.lineno,
                symbol=target,
                language="python",
                operation=UNKNOWN,
                access_mode="import_time_capture",
                path_expression=_expr_source(node.value),
                resolved_pattern="canonical",
                canonical_resolver_used=True,
                classification=AMBIGUOUS_REQUIRES_REVIEW,
                confidence="high",
                evidence=(
                    "canonical resolver called at MODULE level: the runtime root is "
                    "frozen at import, so use_test_root() and any later reconfiguration "
                    "are ignored. Prefer an operation-time accessor."
                ),
            )
        )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = getattr(fn, "attr", None) or getattr(fn, "id", None)
        if name not in _CALL_OPERATIONS and name not in local_writers:
            continue
        if node.lineno in doc_lines:
            continue

        if name in local_writers and name not in _CALL_OPERATIONS:
            # A module-local helper that writes to the path handed to it.
            op = local_writers[name]
            access_mode = f"{name}() [local writer]"
        else:
            op = _CALL_OPERATIONS[name]
            access_mode = name

        if name == "open":
            mode = "r"
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode = str(kw.value.value)
            op = _mode_to_operation(mode)
            access_mode = f"open({mode!r})"

        # WHERE the path lives depends on call shape, and getting this wrong is
        # not a near-miss:
        #   os.replace(src, dst) / open(p) / sqlite3.connect(p)  -> args[0]
        #   p.write_text(data) / p.mkdir() / p.unlink()          -> func.value
        # Reading args[0] for the method form meant `p.write_text(secret)` had
        # the SECRET recorded as its path expression, and `p.mkdir()` (no args)
        # was skipped entirely -- which is why canonical findings read 0 even
        # though runtime_data.store_dir does exactly that.
        if name in local_writers and name not in _CALL_OPERATIONS:
            path_arg = node.args[0] if node.args else None
        else:
            path_arg = _path_argument(node, name)
        if path_arg is None:
            continue

        strings = _literal_strings(path_arg)
        expr = _expr_source(path_arg)
        canonical = _uses_canonical_resolver(path_arg)
        matched = _looks_mutable(strings, expr)
        via_symbol = None
        if not matched and _refs(path_arg, symbols):
            for sub in ast.walk(path_arg):
                nm = getattr(sub, "id", None) or getattr(sub, "attr", None)
                if nm in symbols:
                    via_symbol = nm
                    matched = "symbol"
                    break

        if not matched and not canonical:
            continue

        # `.replace(` on a str is not os.replace. Require path-ish evidence.
        if name == "replace" and not (matched or canonical):
            continue

        if name == "connect" and matched:
            op = SQLITE
        # Lock detection must look at the symbol's DEFINITION too. `open(_LOCK,"w")`
        # carries no ".lock" at the call site, so checking only the call-site
        # expression silently reclassified every lock as a plain REWRITE — and
        # the lock-to-store mapping is exactly what must survive migration
        # (splitting a lock from its data across filesystems breaks atomicity).
        lock_haystack = expr + " ".join(strings) + " " + (symbols.get(via_symbol) or "")
        if matched and re.search(r"\.lock\b|\.lck\b|lock_path", lock_haystack):
            op = LOCK

        findings.append(
            _finding(
                file=rel,
                line=node.lineno,
                language="python",
                operation=op,
                access_mode=access_mode,
                path_expression=expr[:200],
                # For a symbol-resolved finding the call site says `open(_STORE)`,
                # which carries no path information. Classification must use the
                # symbol's DEFINITION or every symbol-resolved cache and artifact
                # write lands in UNDECLARED and the gate becomes noise.
                resolved_pattern=(
                    symbols.get(via_symbol) if via_symbol else (matched or "canonical")
                ),
                canonical_resolver_used=canonical,
                symbol=via_symbol,
                classification="",  # assigned by classify()
                evidence=(
                    f"{name}() on {via_symbol} -> {symbols.get(via_symbol, '')}"
                    if via_symbol
                    else f"{name}() on a {matched or 'canonical'} path"
                ),
            )
        )
    return findings


# ====================================================== shell / workflow layer

_SHELL_OPS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r">>\s*[\"']?[^\s\"'|]*\b(?:data|runtime-data)/"), APPEND),
    (re.compile(r"(?<!>)>\s*[\"']?[^\s\"'|]*\b(?:data|runtime-data)/"), REWRITE),
    (re.compile(r"\btee\b[^|]*\b(?:data|runtime-data)/"), REWRITE),
    (re.compile(r"\b(?:cp|mv|rsync)\b[^|]*\b(?:data|runtime-data)/"), REWRITE),
    (re.compile(r"\btar\b[^|]*-x[^|]*\b(?:data|runtime-data)/"), REWRITE),
    (re.compile(r"\brm\b[^|]*\b(?:data|runtime-data)/"), DELETE),
    (re.compile(r"\bsqlite3\b[^|]*\b(?:data|runtime-data)/"), SQLITE),
    (re.compile(r"\b(?:data|runtime-data)/[^\s\"']*\.lock\b"), LOCK),
)

# Lines that only TALK about a path. Excluded with proof, not by hope: an
# earlier scanner in this workstream reported a guard's own docstring as a
# violation, and a comment explaining a fix as though it were the bug.
_SHELL_PROSE = re.compile(r"^\s*(#|echo\b|printf\b|print\b|:\s*#)")


def _strip_heredocs(lines: list[str]) -> list[str]:
    """Blank out heredoc BODIES (documentation, config templates).

    The delimiter lines stay so line numbers never shift -- a scanner that
    reports the wrong line is worse than one that reports nothing.
    """
    out = list(lines)
    delim: str | None = None
    for i, ln in enumerate(out):
        if delim is None:
            m = re.search(r"<<-?\s*'?\"?([A-Za-z_][A-Za-z0-9_]*)'?\"?", ln)
            if m:
                delim = m.group(1)
            continue
        if ln.strip() == delim:
            delim = None
        out[i] = ""
    return out


def scan_shell(rel: str, text: str) -> list[dict[str, Any]]:
    lines = _strip_heredocs(text.splitlines())
    findings: list[dict[str, Any]] = []
    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or _SHELL_PROSE.match(line):
            continue
        # Inline trailing comment: keep only the executable part.
        code = line.split(" #", 1)[0]
        for pattern, op in _SHELL_OPS:
            if pattern.search(code):
                findings.append(
                    _finding(
                        file=rel,
                        line=idx,
                        language="shell",
                        operation=op,
                        access_mode="shell_redirect_or_command",
                        path_expression=code[:200],
                        resolved_pattern="data",
                        classification="",
                        evidence=f"shell {op.lower()} against a checkout-backed path",
                    )
                )
                break
    return findings


def scan_yaml(rel: str, text: str) -> list[dict[str, Any]]:
    """Workflow/compose files. Only `run:`/`command:` bodies are executable."""
    findings: list[dict[str, Any]] = []
    in_run = False
    run_indent = 0
    for idx, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if re.match(r"-?\s*(run|command|entrypoint):", stripped):
            in_run = True
            run_indent = indent
            body = stripped.split(":", 1)[1].strip()
            if not body or body in {"|", ">", "|-", ">-"}:
                continue
            stripped = body
        elif in_run and indent <= run_indent:
            in_run = False
            continue
        if not in_run:
            continue
        code = stripped.split(" #", 1)[0]
        if _SHELL_PROSE.match(code):
            continue
        for pattern, op in _SHELL_OPS:
            if pattern.search(code):
                findings.append(
                    _finding(
                        file=rel,
                        line=idx,
                        language="yaml",
                        operation=op,
                        access_mode="workflow_run_step",
                        path_expression=code[:200],
                        resolved_pattern="data",
                        classification="",
                        # CI runners are ephemeral: a workflow writing under
                        # data/ is not touching production state.
                        production_relevant=False,
                        evidence="workflow run-step touching a data/ path (ephemeral runner)",
                    )
                )
                break
    return findings


# ========================================================= semantic classifier

_STATIC_ASSET_RE = re.compile(r"data/(legal|compliance|templates|static)/|\.pdf[\"']?$")
_CACHE_RE = re.compile(r"data/(ollama|u2net|models|cache|fastembed|hf)[/\"']")
_ARTIFACT_RE = re.compile(r"data/(generated|media|videos|images|exports|reports)[/\"']")
_FIXTURE_DIRS = ("tests/", "test_", "conftest.py")


def classify(finding: dict[str, Any], allowlist_index: dict[str, dict[str, Any]]) -> str:
    """Assign the authoritative classification for one finding.

    Order matters: canonical first (already correct), then explicit allowlist
    declaration, then category heuristics, then -- only if nothing matched --
    UNDECLARED. Anything mutating that cannot be placed lands in UNDECLARED or
    AMBIGUOUS so it shows up in the gate rather than dissolving.
    """
    if finding["classification"] == AMBIGUOUS_REQUIRES_REVIEW:
        return AMBIGUOUS_REQUIRES_REVIEW  # import-time capture, set at discovery

    if finding.get("canonical_resolver_used"):
        return CANONICAL_RUNTIME_PATH

    # Canonical usage is usually INDIRECT: `path = store_path(...)` on one line
    # and `path.mkdir()` on the next. The call site alone shows only `path`, so
    # checking it kept canonical at 0 even for runtime_data.py itself, which is
    # the most canonical module in the repo.
    resolved = str(finding.get("resolved_pattern") or "")
    if any(fn + "(" in resolved for fn in _CANONICAL_FUNCS) or "runtime_root(" in resolved:
        finding["canonical_resolver_used"] = True
        return CANONICAL_RUNTIME_PATH

    file = finding["file"]
    # Both, because a literal finding carries its path in path_expression while
    # a symbol-resolved one carries it in resolved_pattern.
    expr = f"{finding.get('path_expression', '')} {finding.get('resolved_pattern', '')}"
    op = finding["operation"]

    if any(marker in file for marker in _FIXTURE_DIRS):
        return FIXTURE_ONLY
    if finding.get("production_relevant") is False:
        return FIXTURE_ONLY

    entry = _lookup(finding, allowlist_index)
    if entry is not None:
        finding["store_id"] = entry.get("store_id")
        return DECLARED_LEGACY_WRITE if op in MUTATING_OPERATIONS else DECLARED_LEGACY_READ

    if _STATIC_ASSET_RE.search(expr):
        return STATIC_ASSET
    if _CACHE_RE.search(expr):
        return REBUILDABLE_CACHE
    if _ARTIFACT_RE.search(expr):
        return GENERATED_ARTIFACT
    if op == READ:
        return DECLARED_LEGACY_READ if entry else AMBIGUOUS_REQUIRES_REVIEW
    return UNDECLARED_MUTABLE_PATH


def _key(finding: dict[str, Any]) -> str:
    return f"{finding['file']}:{finding['line']}"


def _lookup(finding: dict[str, Any], index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Match an allowlist entry by exact line OR by symbol.

    Symbol matching is what keeps this from degenerating. One module typically
    has a single `_STORE` path and eight call sites that write through it;
    per-line entries would mean eight declarations of the same fact, drifting
    apart the first time a line number moves. Per-SYMBOL keeps one declaration
    per store-in-module, which is the thing actually being reviewed.
    It is still not a blanket file allowlist: an unrelated write in the same
    file, or a write through a different symbol, stays undeclared.
    """
    hit = index.get(_key(finding))
    if hit is not None:
        return hit
    sym = finding.get("symbol")
    if sym:
        return index.get(f"{finding['file']}:{sym}")
    return None


# ================================================================== repo scan


def _iter_files(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.suffix in _PY_EXT | _SHELL_EXT | _YAML_EXT:
            yield p


def scan_repo(root: Path, allowlist: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Full two-layer scan. Deterministic ordering; no secrets in output."""
    index = {f"{e['file']}:{e['line_or_symbol']}": e for e in (allowlist or [])}
    findings: list[dict[str, Any]] = []

    for path in _iter_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:  # pragma: no cover - defensive
            continue
        if path.suffix in _PY_EXT:
            findings.extend(scan_python(rel, text))
        elif path.suffix in _SHELL_EXT:
            findings.extend(scan_shell(rel, text))
        else:
            findings.extend(scan_yaml(rel, text))

    for f in findings:
        f["classification"] = classify(f, index)

    findings.sort(key=lambda f: (f["file"], f["line"], f["operation"]))
    return findings


_NORMALISE_RE = re.compile(r"\s+")


def normalized_path(finding: dict[str, Any]) -> str:
    """Path identity that survives cosmetic edits.

    Uses the symbol DEFINITION when there is one, because the call site
    (`open(_STORE)`) carries no path. Whitespace collapsed, quotes unified.
    """
    raw = finding.get("resolved_pattern") or finding.get("path_expression") or ""
    return _NORMALISE_RE.sub(" ", str(raw).replace('"', "'")).strip()[:160]


def fingerprint(finding: dict[str, Any]) -> str:
    """Stable identity for ratcheting.

    Line number is DELIBERATELY excluded. A finding that moves because an
    import was added above it is the same finding; treating it as new would
    mean every unrelated edit invents debt, and a ratchet that cries wolf is a
    ratchet people disable.
    """
    parts = [
        finding["file"],
        str(finding.get("symbol") or ""),
        finding["operation"],
        normalized_path(finding),
        finding.get("classification", ""),
        str(finding.get("store_id") or ""),
    ]
    import hashlib

    return "f_" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


def matrices(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Cross-tabs so a pile of read-only references cannot hide real writers.

    "506 mutating" on its own says nothing about WHICH classifications those
    mutations sit in -- undeclared writers and fixture writers are not the
    same risk at all.
    """
    by_class_mut: dict[str, dict[str, int]] = {}
    by_store: dict[str, dict[str, int]] = {}
    for f in findings:
        cls = f["classification"]
        bucket = by_class_mut.setdefault(cls, {"mutating": 0, "read_only": 0})
        key = "mutating" if f["operation"] in MUTATING_OPERATIONS else "read_only"
        bucket[key] += 1
        sid = f.get("store_id")
        if sid:
            by_store.setdefault(sid, {}).setdefault(f["operation"], 0)
            by_store[sid][f["operation"]] += 1

    prod = {"production": 0, "non_production": 0}
    for f in findings:
        prod["production" if f.get("production_relevant") else "non_production"] += 1

    return {
        "classification_x_access": by_class_mut,
        "store_x_operation": by_store,
        "production_relevance": prod,
    }


def summarise(findings: list[dict[str, Any]]) -> dict[str, int]:
    out = {c: 0 for c in CLASSIFICATIONS}
    for f in findings:
        out[f["classification"]] = out.get(f["classification"], 0) + 1
    out["total"] = len(findings)
    out["mutating"] = sum(1 for f in findings if f["operation"] in MUTATING_OPERATIONS)
    return out


__all__ = [
    "CLASSIFICATIONS",
    "MUTATING_OPERATIONS",
    "UNDECLARED_MUTABLE_PATH",
    "AMBIGUOUS_REQUIRES_REVIEW",
    "CANONICAL_RUNTIME_PATH",
    "DECLARED_LEGACY_READ",
    "DECLARED_LEGACY_WRITE",
    "FIXTURE_ONLY",
    "STATIC_ASSET",
    "GENERATED_ARTIFACT",
    "REBUILDABLE_CACHE",
    "scan_python",
    "scan_shell",
    "scan_yaml",
    "scan_repo",
    "classify",
    "summarise",
    "fingerprint",
    "normalized_path",
    "matrices",
]
