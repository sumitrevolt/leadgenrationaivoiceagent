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
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

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
# resolve_store_path is the dual-read authority resolver (A1–A4 writers).
# It MUST be listed explicitly: a naive `"store_path(" in text` match would
# also hit inside `resolve_store_path(` and falsely mark unresolved debt as
# CANONICAL (2026-07-28 A4 ratchet incident).
_CANONICAL_FUNCS = frozenset(
    {"store_path", "store_dir", "lock_path", "runtime_data_path", "resolve_store_path"}
)

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
        "_scratch",
        "_agent_fetch",
        ".freebuff",
        ".worktrees",
        ".claude",
        ".agents",
        ".codex",
        ".hermes",
        ".clawhub",
        ".cursor",
        ".memory",
        ".pytest_tmp",
        ".omniroute-cutover",
        ".specify",
        ".workbuddy-ai",
        "_work",
        "backups",
        "artifacts",
        "uat_evidence",
        "_recovery",
        ".vs",
        ".idea",
        "logs",
        "outputs",
        "tmp_deploy",
        "_scratch_ops",
        "openclaw",
        "dsh",
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


# ======================================================== path provenance
#
# `_mutable_symbols` answers roughly "has this name participated in mutable-path
# analysis". That is DISCOVERY. It was wrongly used as receiver PROOF, and the
# difference is not academic: it let `agent_config` (a prompt builder's return
# value), `action = candidates[0]` and `out["path"]` authorise destructive
# filesystem operations on real modules.
#
# Provenance is a separate authority. Transitive resolution is allowed, but only
# along PATH-PRESERVING edges, so the real alias chain
#     path -> _CLIENTS_FILE -> os.path.join("data", "marketing_clients.jsonl")
# still resolves while an unknown call result never does.

PROVEN_STATIC_PATH = "PROVEN_STATIC_PATH"
PROVEN_PATH_ALIAS = "PROVEN_PATH_ALIAS"
PROVEN_DYNAMIC_PATH_PATTERN = "PROVEN_DYNAMIC_PATH_PATTERN"
AMBIGUOUS_PATH = "AMBIGUOUS_PATH"
NOT_PATH = "NOT_PATH"
CYCLE_DETECTED = "CYCLE_DETECTED"
UNSUPPORTED_EXPRESSION = "UNSUPPORTED_EXPRESSION"

_PROVEN = frozenset({PROVEN_STATIC_PATH, PROVEN_PATH_ALIAS, PROVEN_DYNAMIC_PATH_PATTERN})

_PATH_CONSTRUCTORS = frozenset({"Path", "PurePath", "PosixPath", "WindowsPath"})
# `.parent` stays a path; `.name`/`.stem`/`.suffix` are strings and must not.
_PATH_PRESERVING_ATTRS = frozenset({"parent", "absolute", "resolve", "expanduser"})


def _is_path_literal(value: str) -> bool:
    """A string is path evidence only on shape, never on the variable holding it."""
    v = value.replace("\\", "/")
    if v in {"data", "runtime-data"}:
        return True
    return bool(_MUTABLE_ROOT_RE.search(v))


def path_provenance(
    node: ast.AST,
    table: dict[str, ast.AST] | None = None,
    _visited: frozenset[str] = frozenset(),
    _depth: int = 0,
) -> str:
    """Status for one expression. Only PROVEN_* may authorise a filesystem op."""
    table = table or {}
    if _depth > 8:
        return UNSUPPORTED_EXPRESSION

    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            return PROVEN_STATIC_PATH if _is_path_literal(node.value) else NOT_PATH
        return NOT_PATH

    if isinstance(node, ast.Name):
        if node.id in _visited:
            return CYCLE_DETECTED
        src = table.get(node.id)
        if src is None:
            return NOT_PATH
        inner = path_provenance(src, table, _visited | {node.id}, _depth + 1)
        return PROVEN_PATH_ALIAS if inner in _PROVEN else inner

    if isinstance(node, ast.Call):
        fname = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if fname in _PATH_CONSTRUCTORS:
            return PROVEN_STATIC_PATH
        if fname in _CANONICAL_FUNCS or fname == "runtime_root":
            return PROVEN_STATIC_PATH
        # `str(<proven path>)` preserves path-ness (A4 dual-read helpers wrap
        # resolve_store_path in str() for the historical str API).
        if fname == "str" and len(node.args) == 1:
            inner = path_provenance(node.args[0], table, _visited, _depth + 1)
            if inner in _PROVEN:
                return PROVEN_PATH_ALIAS
            return inner if inner != NOT_PATH else UNSUPPORTED_EXPRESSION
        if fname == "join" and isinstance(node.func, ast.Attribute):
            base = getattr(node.func.value, "attr", None) or getattr(node.func.value, "id", None)
            if base == "path":  # os.path.join
                for a in node.args:
                    if path_provenance(a, table, _visited, _depth + 1) in _PROVEN:
                        return PROVEN_STATIC_PATH
                return NOT_PATH
        if _is_env_read(node):
            # `os.getenv("X", "data/store")` — configurable root with a
            # statically bounded default is a path PATTERN, not a fixed path.
            # A default that is not itself a path proves nothing, and an env
            # read with NO default is unbounded, so it stays ENV_READ and only
            # a fallback elsewhere (`... or "data/store"`) can bound it.
            default = node.args[1] if len(node.args) > 1 else None
            if (
                default is not None
                and path_provenance(default, table, _visited, _depth + 1) in _PROVEN
            ):
                return PROVEN_DYNAMIC_PATH_PATTERN
            return _ENV_READ
        if isinstance(node.func, ast.Name):
            # A locally defined path-returning helper. The proof comes from
            # every reachable return in its body, never from its name.
            helper = (table.get(_HELPERS) or {}).get(node.func.id)
            if helper is not None:
                return helper
        # Any other call: an unknown return contract proves nothing.
        return UNSUPPORTED_EXPRESSION

    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        # `os.getenv("X") or DEFAULT` — the value is the first truthy operand,
        # so it is bounded only when the LAST operand is proven. Anything else
        # in the chain must be an env read or itself proven, otherwise an
        # arbitrary object could reach a filesystem call.
        vals = [path_provenance(v, table, _visited, _depth + 1) for v in node.values]
        if vals[-1] not in _PROVEN:
            return NOT_PATH
        if all(v in _PROVEN or v == _ENV_READ for v in vals[:-1]):
            return PROVEN_DYNAMIC_PATH_PATTERN
        return AMBIGUOUS_PATH

    if isinstance(node, ast.BinOp):
        left = path_provenance(node.left, table, _visited, _depth + 1)
        if isinstance(node.op, ast.Div):
            return PROVEN_STATIC_PATH if left in _PROVEN else left
        if isinstance(node.op, ast.Add):  # STORE + ".lock"
            return PROVEN_PATH_ALIAS if left in _PROVEN else NOT_PATH
        return NOT_PATH

    if isinstance(node, ast.JoinedStr):  # f"{STORE}.tmp"
        for part in node.values:
            if isinstance(part, ast.FormattedValue):
                if path_provenance(part.value, table, _visited, _depth + 1) in _PROVEN:
                    return PROVEN_DYNAMIC_PATH_PATTERN
        return NOT_PATH

    if isinstance(node, ast.Attribute):
        if node.attr in _PATH_PRESERVING_ATTRS:
            return path_provenance(node.value, table, _visited, _depth + 1)
        return NOT_PATH  # .name/.stem/.suffix and arbitrary attributes

    if isinstance(node, ast.IfExp):
        # `store_path(*segments) if segments else runtime_root()` — the value is
        # one of two expressions, so it is proven exactly when BOTH are. Half a
        # proof is not a proof: accepting a single proven branch would let an
        # arbitrary receiver through on the other one, which is the failure this
        # authority exists to prevent. With no arm at all the ternary fell to
        # UNSUPPORTED_EXPRESSION and the canonical `store_dir` mkdir vanished.
        body = path_provenance(node.body, table, _visited, _depth + 1)
        orelse = path_provenance(node.orelse, table, _visited, _depth + 1)
        if body in _PROVEN and orelse in _PROVEN:
            return PROVEN_PATH_ALIAS
        if body in _PROVEN or orelse in _PROVEN:
            return AMBIGUOUS_PATH
        return NOT_PATH

    # Subscripts, awaits, comprehensions, dict access: no proof.
    return UNSUPPORTED_EXPRESSION


#: Reserved table key. Not a valid Python identifier, so it can never collide
#: with a symbol name discovered in the module.
_HELPERS = "\x00path_return_helpers"

#: Internal, NOT in _PROVEN: an unbounded environment read. It can only become
#: a path when something else supplies a proven default.
_ENV_READ = "ENV_READ"


def _is_env_read(node: ast.Call) -> bool:
    """`os.getenv(...)` / `os.environ.get(...)` — structural, not by name alone."""
    fn = node.func
    if not isinstance(fn, ast.Attribute):
        return False
    if fn.attr == "getenv":
        return getattr(fn.value, "id", None) == "os"
    if fn.attr == "get":
        base = fn.value
        return getattr(base, "attr", None) == "environ" or (getattr(base, "id", None) == "environ")
    return False


def _path_return_helpers(tree: ast.Module, table: dict[str, Any]) -> dict[str, str]:
    """Module-level functions PROVEN to return a path, by analysing their returns.

    A helper qualifies only when every reachable `return <value>` resolves to a
    PROVEN_* status. One non-path branch makes the whole function AMBIGUOUS_PATH,
    and an unknown call supplying the root leaves it UNSUPPORTED_EXPRESSION —
    the function name, its docstring and its annotation are never evidence.

    Two passes so `def a(): return b()` can see `b`, with the in-progress set
    guarding mutual recursion (`a -> b -> a`) instead of hanging.
    """
    funcs = {f.name: f for f in tree.body if isinstance(f, ast.FunctionDef | ast.AsyncFunctionDef)}
    out: dict[str, str] = {}
    for _ in range(3):
        changed = False
        for name, fn in funcs.items():
            if name in out:
                continue
            returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return) and n.value is not None]
            if not returns:
                continue
            local = dict(table)
            local[_HELPERS] = {k: v for k, v in out.items() if k != name}
            for sub in ast.walk(fn):
                if isinstance(sub, ast.Assign) and len(sub.targets) == 1:
                    tgt = getattr(sub.targets[0], "id", None)
                    if tgt and path_provenance(sub.value, local) in _PROVEN:
                        local[tgt] = sub.value
            statuses = {path_provenance(r.value, local) for r in returns}
            if not statuses <= _PROVEN:
                if statuses & _PROVEN:
                    verdict = AMBIGUOUS_PATH
                elif CYCLE_DETECTED in statuses:
                    verdict = CYCLE_DETECTED
                else:
                    verdict = UNSUPPORTED_EXPRESSION
            elif PROVEN_DYNAMIC_PATH_PATTERN in statuses:
                verdict = PROVEN_DYNAMIC_PATH_PATTERN
            elif statuses == {PROVEN_STATIC_PATH}:
                verdict = PROVEN_STATIC_PATH
            else:
                verdict = PROVEN_PATH_ALIAS
            out[name] = verdict
            changed = True
        if not changed:
            break
    # Only PROVEN verdicts may authorise anything downstream; keeping the
    # negative ones would let AMBIGUOUS leak in as a truthy lookup hit.
    return {k: v for k, v in out.items() if v in _PROVEN}


def _pattern_of(node: ast.AST, helpers: dict[str, str], _depth: int = 0) -> str:
    """Bounded, value-free rendering of a proven path expression.

    Emits STRUCTURE only: env-var NAMES, static fallbacks and `<*>` for anything
    interpolated. Mission ids, payloads and real environment values must never
    reach a finding, a fingerprint or the baseline file.
    """
    if _depth > 6:
        return "<*>"
    if isinstance(node, ast.Constant):
        return str(node.value) if isinstance(node.value, str) else "<*>"
    if isinstance(node, ast.Call):
        if _is_env_read(node):
            var = (
                node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else "?"
            )
            dflt = (
                _pattern_of(node.args[1], helpers, _depth + 1) if len(node.args) > 1 else "<unset>"
            )
            return f"<${var}|{dflt}>"
        fname = getattr(node.func, "id", None)
        fattr = getattr(node.func, "attr", None)
        # `str(<path>)` is a no-op for structure — unwrap so A4 dual-read
        # helpers that wrap resolve_store_path still render the resolver.
        if fname == "str" and len(node.args) == 1:
            return _pattern_of(node.args[0], helpers, _depth + 1)
        if fname in helpers:
            # Expand a nested proven helper so the pattern reaches the env var
            # and its static fallback instead of stopping at `<_root>`.
            return helpers[fname] or f"<{fname}>"
        # Canonical resolvers must render by name so classify / fingerprints
        # can see them. Falling through to `<*>` previously left the pattern
        # as the provenance status string ("PROVEN_STATIC_PATH") — fingerprint
        # poison (2026-07-28 A4).
        canon = fname or fattr
        if canon in _CANONICAL_FUNCS or canon == "runtime_root":
            # resolve_store_path keeps the legacy_path basename visible so
            # allowlist binding can still prove which store the dual-read
            # helper covers (path_components_match on email_suppression.jsonl).
            # Opaque `resolve_store_path(...)` alone unbound every A3/A4 entry.
            if canon == "resolve_store_path":
                legacy = ""
                for kw in node.keywords:
                    if kw.arg == "legacy_path":
                        legacy = _pattern_of(kw.value, helpers, _depth + 1)
                        break
                if legacy and legacy != "<*>":
                    return f"resolve_store_path(... legacy={legacy})"
            return f"{canon}(...)"
        if getattr(node.func, "attr", None) == "join" or fname in _PATH_CONSTRUCTORS:
            parts = [_pattern_of(a, helpers, _depth + 1) for a in node.args]
            return "/".join(p for p in parts if p)
        return "<*>"
    if isinstance(node, ast.Name):
        return helpers.get(node.id) or "<*>"
    if isinstance(node, ast.BoolOp):
        # `os.getenv("X") or DEFAULT` — render the env var WITH its real
        # fallback. Taking the first operand alone left the default as
        # `<unset>` even though the code plainly supplies one.
        pats = [_pattern_of(v, helpers, _depth + 1) for v in node.values]
        useful = [p for p in pats if p and p != "<*>"]
        if not useful:
            return "<*>"
        fallback = useful[-1]
        for p in useful[:-1]:
            if p.startswith("<$") and p.endswith("|<unset>>"):
                return p[: -len("|<unset>>")] + f"|{fallback}>"
        return useful[0]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return (
            f"{_pattern_of(node.left, helpers, _depth + 1)}/"
            f"{_pattern_of(node.right, helpers, _depth + 1)}"
        )
    if isinstance(node, ast.JoinedStr):
        out = []
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                out.append(part.value)
            else:
                out.append("<*>")  # never the interpolated VALUE
        return "".join(out)
    return "<*>"


def _helper_patterns(tree: ast.Module, proven: dict[str, str]) -> dict[str, str]:
    """Bounded pattern per proven helper, expanding nested helpers.

    Two passes so `_mission_path` renders `_root`'s env pattern rather than
    stopping at an opaque `<_root>`.
    """
    out: dict[str, str] = {}
    for _ in range(2):
        for name, status in proven.items():
            out[name] = _helper_pattern(tree, name, status, out)
    return out


def _helper_pattern(
    tree: ast.Module, name: str, status: str, resolved: dict[str, str] | None = None
) -> str:
    """Bounded pattern for one proven path-returning helper."""
    helpers = {name}
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if fn.name != name:
            continue
        local: dict[str, ast.AST] = {}
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Assign) and len(sub.targets) == 1:
                tgt = getattr(sub.targets[0], "id", None)
                if tgt:
                    local[tgt] = sub.value
        others = {
            f.name: (resolved or {}).get(f.name, "")
            for f in tree.body
            if isinstance(f, ast.FunctionDef | ast.AsyncFunctionDef) and f.name not in helpers
        }
        # Module-level string constants, so `... or DEFAULT_ROOT` renders the
        # literal fallback the code actually ships rather than `<*>`.
        for mod in tree.body:
            if isinstance(mod, ast.Assign) and len(mod.targets) == 1:
                tgt = getattr(mod.targets[0], "id", None)
                if tgt and isinstance(mod.value, ast.Constant) and isinstance(mod.value.value, str):
                    others.setdefault(tgt, mod.value.value)
        for n in ast.walk(fn):
            if isinstance(n, ast.Return) and n.value is not None:
                val = n.value
                # One hop through a local alias so `p = _root() / x; return p`
                # renders the composed pattern rather than the bare name.
                if isinstance(val, ast.Name) and val.id in local:
                    val = local[val.id]
                pat = _pattern_of(val, others)
                if pat and pat != "<*>":
                    return pat
    return status


def _provenance_table(tree: ast.Module) -> dict[str, ast.AST]:
    """symbol -> assignment expression, kept ONLY for path-preserving RHS.

    Fixed point over a few passes so multi-hop aliases resolve, while a name
    assigned from an unknown call never enters the table at all.
    """
    assigns: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        for t in targets:
            name = getattr(t, "id", None)
            if name:
                assigns.append((name, value))

    table: dict[str, Any] = {}
    # Helpers first: `path = _mission_path(id)` can only resolve once the
    # scanner knows what `_mission_path` returns. Recomputed after the symbol
    # fixed point so a helper that reads a module constant sees it.
    table[_HELPERS] = _path_return_helpers(tree, {})
    for _ in range(4):
        changed = False
        for name, value in assigns:
            if name in table:
                continue
            if path_provenance(value, table) in _PROVEN:
                table[name] = value
                changed = True
        if not changed:
            break
    table[_HELPERS] = _path_return_helpers(tree, {k: v for k, v in table.items() if k != _HELPERS})
    return table


def _receiver_is_pathlike(recv: ast.AST, symbols: dict[str, ast.AST] | None) -> bool:
    """Is this receiver PROVEN to be a path?

    A method name is not evidence. `text.replace(a, b)`, `items.remove(x)` and
    `stream.write(data)` all look like file APIs and none of them touch a
    filesystem. Treating the name as proof classified a prompt builder as a
    REPLACE writer and turned a READ into a destructive operation — a
    regression, not new visibility, and one a capability record must never
    launder.

    Accepted proof: a Path construction, a `/` composition, a `.parent` chain
    from a proven path, a canonical-resolver call, or a symbol that resolves to
    a path expression. A variable NAME (`path`, `out`, `config`) proves nothing.

    `symbols` here is the PROVENANCE table, never `_mutable_symbols`. Passing
    the discovery table was the defect: it made any name that had merely
    touched mutable-path analysis look like a proven path.
    """
    return path_provenance(recv, symbols or {}) in _PROVEN


def _path_argument(
    node: ast.Call, name: str, symbols: dict[str, str] | None = None
) -> ast.AST | None:
    """Return the sub-expression that is actually the PATH, or None.

    Four dispatch categories, deliberately separate:
      * module-qualified stdlib function (`os.replace(src, dst)`) -> args
      * proven Path-like receiver (`p.write_text(x)`)             -> receiver
      * bare local helper                                         -> caller
      * arbitrary object method                                   -> NO finding
    """
    fn = node.func
    if isinstance(fn, ast.Attribute) and name in _RECEIVER_PATH_CALLS:
        base = getattr(fn.value, "id", None)
        if base in _PATH_MODULES:
            return node.args[0] if node.args else None
        if not _receiver_is_pathlike(fn.value, symbols):
            return None  # arbitrary receiver — the method name proves nothing
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

    Returns {name: {"operation", "path_param", "path_index", "confidence"}}.

    WHICH parameter is the path matters as much as whether one is written. The
    first version recorded only the operation and then took `args[0]` at the
    call site, so `def write_text(content, destination)` would have had the
    CONTENT read as the path — a wrong finding and a secret-leak surface in one.
    The parameter is therefore derived from the write target itself.
    """
    # STRUCTURAL method detection. `self` is a receiver, never a call-site path
    # argument: `aq.queue_task(action)` had `self` chosen as the path parameter,
    # so `action` (position 0 at the call site) was read as a filesystem path.
    # Detected from AST structure + decorators, not from the parameter's name,
    # so a module-level function that happens to call something `self` is
    # unaffected.
    methods: dict[int, str] = {}
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        for item in cls.body:
            if not isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            decs = {getattr(d, "id", None) or getattr(d, "attr", None) for d in item.decorator_list}
            if "staticmethod" in decs:
                methods[id(item)] = "STATIC_METHOD"
            elif "classmethod" in decs:
                methods[id(item)] = "CLASS_METHOD"
            else:
                methods[id(item)] = "INSTANCE_METHOD"

    # Scope: only functions that are actually reachable by a BARE module-level
    # name may enter the registry. A closure defined inside another function is
    # invisible outside it, so registering it globally lets an inner `_append`
    # claim every unrelated `_append(...)` call site in the file.
    nested: set[int] = set()
    for fn_node in ast.walk(tree):
        if not isinstance(fn_node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for desc in ast.walk(fn_node):
            if desc is fn_node:
                continue
            if isinstance(desc, ast.FunctionDef | ast.AsyncFunctionDef):
                nested.add(id(desc))

    out: dict[str, dict[str, Any]] = {}
    for _ in range(2):  # second pass lets a helper inherit from a nested helper
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            kind = methods.get(id(node), "MODULE_FUNCTION")
            positional = [a.arg for a in node.args.args]
            # Drop the implicit receiver for instance/class methods only.
            # Static methods keep every explicit parameter.
            if kind in ("INSTANCE_METHOD", "CLASS_METHOD") and positional:
                positional = positional[1:]
            names = positional + [a.arg for a in node.args.kwonlyargs]
            params = set(names)
            if not params:
                continue

            best: dict[str, Any] | None = None
            bindings: list[dict[str, Any]] = []
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                nm = getattr(sub.func, "attr", None) or getattr(sub.func, "id", None)
                if nm is None:
                    continue

                # A bare local call wins over a same-named stdlib entry: a
                # helper called `write_text` is this module's function, not
                # Path.write_text, and routing it through the stdlib rule read
                # its CONTENT argument as the path.
                local_first = isinstance(sub.func, ast.Name) and nm in out and nm != node.name

                if nm in _CALL_OPERATIONS and not local_first:
                    # Inside a helper the parameters ARE the path evidence, so
                    # they count as proof for the receiver test.
                    # Inside a helper body the PARAMETERS are the path evidence
                    # (the helper's own contract), so they seed the provenance
                    # table for this analysis only.
                    target = _path_argument(
                        sub, nm, {p: ast.Constant(value="data/<param>") for p in params}
                    )
                    cand = _CALL_OPERATIONS[nm]
                    if nm in _ARG_ROLES and isinstance(sub.func, ast.Attribute):
                        # Two-path APIs have a fixed source/destination
                        # contract. `shutil.copyfile(src, DST)` and
                        # `os.replace(tmp, DST)` both put the authority in
                        # arg1; reading arg0 bound a helper's mutation to the
                        # file it merely READS (studio_media `src_path`).
                        roles = _ARG_ROLES[nm]
                        dest_idx = [i for i, r in enumerate(roles) if r == _DEST]
                        picked = None
                        for i in dest_idx:
                            if i < len(sub.args) and any(
                                isinstance(x, ast.Name) and x.id in params
                                for x in ast.walk(sub.args[i])
                            ):
                                picked = sub.args[i]
                                break
                        # No parameter reaches the DESTINATION slot => this
                        # helper does not take its write target as an argument.
                        target = picked
                    if nm == "open":
                        mode = "r"
                        if len(sub.args) > 1 and isinstance(sub.args[1], ast.Constant):
                            mode = str(sub.args[1].value)
                        for kw in sub.keywords:
                            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                                mode = str(kw.value.value)
                        cand = _mode_to_operation(mode)
                elif local_first or (nm in out and nm != node.name):
                    # Nested local helper: inherit its semantics, following the
                    # argument that lands in ITS path position.
                    inner = out[nm]
                    target = _arg_for_param(sub, inner["path_param"], inner["path_index"])
                    cand = inner["operation"]
                else:
                    continue

                if target is None:
                    continue
                hit = next(
                    (x.id for x in ast.walk(target) if isinstance(x, ast.Name) and x.id in params),
                    None,
                )
                if hit is None:
                    continue
                role = _binding_role(cand)
                binding = {
                    "param": hit,
                    "index": names.index(hit),
                    "role": role,
                    "operation": cand,
                }
                if binding not in bindings:
                    bindings.append(binding)
                if cand in MUTATING_OPERATIONS and role != _DEST:
                    # A MUTATION may only be projected onto the destination
                    # slot. A SOURCE / TEMPORARY / companion binding is real
                    # and stays in `path_bindings`, but binding a write to it
                    # is what marked a read-only argument as a rewrite.
                    # (A READ legitimately binds to a SOURCE — that is its
                    # authority — so the gate is mutation-specific.)
                    continue
                if best is None or _OP_SEVERITY.get(cand, 0) > _OP_SEVERITY.get(
                    best["operation"], 0
                ):
                    best = {
                        "operation": cand,
                        "path_param": hit,
                        "path_index": names.index(hit),
                        "confidence": "high",
                    }
            if best and kind == "MODULE_FUNCTION" and id(node) not in nested:
                # Only BARE local functions enter the registry. A method is
                # reachable only as `obj.name(...)`, and resolving an attribute
                # call through a global name map is how an unrelated class
                # method contaminated a module helper.
                #
                # Compatibility projection: legacy `path_param` / `path_index`
                # survive only while exactly ONE unambiguous destination exists.
                # Consumers migrate to `path_bindings`; until then an ambiguous
                # helper is reported without a projected authority rather than
                # having one guessed for it.
                dests = {b["param"] for b in bindings if b["role"] == _DEST}
                record = dict(best)
                record["path_bindings"] = bindings
                if best["operation"] in MUTATING_OPERATIONS and len(dests) != 1:
                    record["confidence"] = "ambiguous_destination"
                out.setdefault(node.name, record)
    return out


_SOURCE = "SOURCE"
_DEST = "DESTINATION_AUTHORITY"
_TEMPORARY = "TEMPORARY"
_COMPANION = "LOCK_OR_COMPANION"

# Fixed argument contracts for two-path APIs. Position -> role.
# The destination is the authority; the other slot is read or discarded, and
# treating it as the write target is how a helper's mutation got bound to the
# file it only READS.
_ARG_ROLES: dict[str, tuple[str, ...]] = {
    "copyfile": (_SOURCE, _DEST),
    "copy": (_SOURCE, _DEST),
    "copy2": (_SOURCE, _DEST),
    "copytree": (_SOURCE, _DEST),
    "move": (_SOURCE, _DEST),
    "replace": (_TEMPORARY, _DEST),
    "rename": (_TEMPORARY, _DEST),
}


def _binding_role(operation: str) -> str:
    """Role of a single-path binding, derived from what the call DOES."""
    return _DEST if operation in MUTATING_OPERATIONS else _SOURCE


def _arg_for_param(call: ast.Call, name: str, index: int) -> ast.AST | None:
    """Argument bound to a named parameter — keyword first, then position.

    Keyword call sites are normal for these helpers
    (`_write_all(records=items, destination=STORE)`), and positional-only
    lookup silently missed every one of them.
    """
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    if 0 <= index < len(call.args):
        return call.args[index]
    return None


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
                        if (
                            _looks_mutable(_literal_strings(sub.value), expr)
                            or _refs(sub.value, syms)
                            or _uses_canonical_resolver(sub.value)
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
    """Does this expression reference an already-known mutable symbol?

    Only ``ast.Name`` bindings count. Matching ``Attribute.attr`` made every
    ``os.path.join(...)`` look like a reference to a local symbol named
    ``path`` (e.g. a READ-only ``path = join("data", "inquiries.jsonl")``),
    which then re-fingerprinted dynamic writers as that unrelated store
    (2026-07-28 A4 false REPLACE on staff._trim_jsonl).
    """
    if not syms:
        return False
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in syms:
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
    # Discovery (`symbols`) and PROOF (`provenance`) are deliberately separate
    # tables. Only the provenance table may authorise a receiver-method
    # filesystem operation.
    provenance = _provenance_table(tree)
    # A proven path-returning helper gets a BOUNDED pattern, so a finding whose
    # call site is `_mission_path(id)` carries the store it actually writes
    # instead of an opaque source expression. The pattern names the env var and
    # its static fallback -- never a runtime value, id or payload.
    # Overwrites, not setdefault: discovery may already hold the raw source
    # expression, and a PROVEN bounded pattern is strictly better evidence than
    # `_root() / f'{safe}.json'`.
    symbols.update(_helper_patterns(tree, provenance.get(_HELPERS) or {}))
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

        # Same local-first rule as the inference pass: a bare `write_text(...)`
        # is this module's helper, not Path.write_text.
        # Local-helper inference requires a BARE call. `aq.queue_task(action)`
        # is an attribute call on another object and must never be resolved
        # through the local-helper registry; the old `name not in
        # _CALL_OPERATIONS` escape hatch let exactly that through.
        use_local = isinstance(fn, ast.Name) and name in local_writers
        if use_local:
            # A module-local helper that writes to the path handed to it.
            op = local_writers[name]["operation"]
            access_mode = f"{name}() [local writer]"
        elif name in _CALL_OPERATIONS:
            op = _CALL_OPERATIONS[name]
            access_mode = name
        else:
            # An attribute call whose name merely matches a local helper.
            # Not a filesystem operation, and not ours to guess.
            continue

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
        if use_local:
            # Follow the helper's DECLARED path parameter — by keyword if the
            # call site uses one. Taking args[0] blindly would read the content
            # argument of a content-first helper as a filesystem path.
            spec = local_writers[name]
            path_arg = _arg_for_param(node, spec["path_param"], spec["path_index"])
        else:
            path_arg = _path_argument(node, name, provenance)
        if path_arg is None:
            continue

        strings = _literal_strings(path_arg)
        expr = _expr_source(path_arg)
        canonical = _uses_canonical_resolver(path_arg)
        matched = _looks_mutable(strings, expr)
        via_symbol = None
        if not matched and _refs(path_arg, symbols):
            for sub in ast.walk(path_arg):
                # Name-only: see `_refs`. Attribute.attr must not bind `os.path`.
                if isinstance(sub, ast.Name) and sub.id in symbols:
                    via_symbol = sub.id
                    matched = "symbol"
                    break

        # Dual-read helpers: call site is `_queue_path(...)` / `_ledger_path(...)`
        # while the definition wraps `resolve_store_path`. Expand one hop of
        # symbol definitions so the canonical bit is not lost.
        if not canonical and via_symbol:
            hay = symbols.get(via_symbol) or ""
            for hname, hexpr in symbols.items():
                if hname != via_symbol and hname in hay:
                    hay = f"{hay} {hexpr}"
            if any(
                re.search(rf"(?<!\w){re.escape(fn)}\(", hay)
                for fn in (set(_CANONICAL_FUNCS) | {"runtime_root"})
            ):
                canonical = True

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
    #
    # Match function names at a token boundary — NEVER bare `store_path(` as a
    # substring, or `resolve_store_path(` falsely collapses to CANONICAL while
    # the call is still unresolved for fingerprint purposes.
    resolved = str(finding.get("resolved_pattern") or "")
    _canon_names = set(_CANONICAL_FUNCS) | {"runtime_root"}
    # Lookbehind is word-char only — MUST allow `rd.store_path(` (dot prefix).
    if any(re.search(rf"(?<!\w){re.escape(fn)}\(", resolved) for fn in _canon_names):
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
    """
    Recursive generator that skips excluded directories early to avoid
    filesystem errors and redundant scanning.
    """
    try:
        # Use os.scandir for speed and robustness on Windows (long paths, junctions).
        for entry in os.scandir(root):
            if entry.is_dir():
                if entry.name in _SKIP_DIRS:
                    continue
                yield from _iter_files(Path(entry.path))
            elif entry.is_file():
                if Path(entry.name).suffix in _PY_EXT | _SHELL_EXT | _YAML_EXT:
                    yield Path(entry.path)
    except OSError as e:
        logger.debug("[scan] skip unreadable dir %s: %s", root, e)


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
    out = dict.fromkeys(CLASSIFICATIONS, 0)
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
