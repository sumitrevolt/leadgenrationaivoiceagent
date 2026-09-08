"""Loader and validator for the controlled mutable-path allowlist.

An allowlist that is never checked back against the code becomes a list of
things that USED to be true. Every failure mode this validator covers has
already happened somewhere in this repo: a path moved and the note about it
didn't, a store id was typo'd, a writer was filed as read-only.

So validation is bidirectional:
  * every entry must still match a LIVE finding (no stale declarations),
  * every entry must name a real store family,
  * a writer may not be declared against a static/immutable store,
  * a production writer may not be filed as fixture-only.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from app.platform import runtime_data_allowlist_entries as _entries
from app.platform import runtime_data_manifest as _manifest
from app.platform import runtime_data_scan as _scan

ALLOWLIST_PATH = Path(__file__).with_name("runtime_data_allowlist_entries.py")

REQUIRED_FIELDS = (
    "allowlist_id",
    "file",
    "line_or_symbol",
    "path_pattern",
    "store_id",
    "access_modes",
    "reason",
    "migration_tier",
    "target_change_set",
    "owner",
    "production_relevance",
    "review_condition",
)

# Stores that cannot legitimately have a declared WRITER.
IMMUTABLE_STORE_IDS = frozenset({"static.legal_documents"})

_WRITE_MODES = frozenset(
    {"APPEND", "REWRITE", "CREATE", "DELETE", "REPLACE", "LOCK", "SQLITE", "CACHE_WRITE"}
)


def load(path: Path | None = None) -> list[dict[str, Any]]:
    """Deep copy so a caller mutating a returned entry cannot corrupt the
    declaration for everyone else in the same process."""
    return copy.deepcopy(_entries.ENTRIES)


def _store_ids() -> set[str]:
    return {s["store_id"] for s in _manifest.STORES}


def validate(
    entries: list[dict[str, Any]] | None = None,
    findings: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Return a list of problems. Empty list means the allowlist is coherent."""
    entries = load() if entries is None else entries
    problems: list[str] = []
    known_stores = _store_ids()

    seen: set[str] = set()
    for e in entries:
        eid = e.get("allowlist_id", "<missing id>")

        missing = [f for f in REQUIRED_FIELDS if f not in e or e[f] in (None, "", [])]
        if missing:
            problems.append(f"{eid}: missing required fields: {', '.join(missing)}")
            continue

        if eid in seen:
            problems.append(f"{eid}: duplicate allowlist_id")
        seen.add(eid)

        if e["store_id"] not in known_stores:
            problems.append(f"{eid}: unknown store_id {e['store_id']!r}")

        modes = set(e["access_modes"])
        if modes & _WRITE_MODES and e["store_id"] in IMMUTABLE_STORE_IDS:
            problems.append(
                f"{eid}: declares write modes {sorted(modes & _WRITE_MODES)} "
                f"against immutable store {e['store_id']}"
            )

        if not isinstance(e["migration_tier"], int):
            problems.append(f"{eid}: migration_tier must be an integer wave")

        if e["production_relevance"] == "FIXTURE" and modes & _WRITE_MODES:
            problems.append(f"{eid}: production writer filed as FIXTURE")

        src = Path(__file__).resolve().parents[2] / e["file"]
        if not src.is_file():
            problems.append(f"{eid}: file no longer exists: {e['file']}")
        else:
            problems.extend(_check_path_pattern(eid, e, src))

    if findings is not None:
        problems.extend(_check_liveness(entries, findings))
        # PRIMARY evidence. The source-text basename check above is secondary
        # defence only — it passes on comments, docstrings and dead constants.
        problems.extend(_check_finding_binding(entries, findings))
    return problems


def _check_path_pattern(eid: str, entry: dict[str, Any], src: Path) -> list[str]:
    """The declared path must actually appear in the module.

    THIS CHECK EXISTS BECAUSE I GOT IT WRONG. I declared
    `data/marketing_clients.json` for a store whose code says
    `os.path.join("data", "marketing_clients.jsonl")` -- one missing `l`. Every
    other validation passed, because nothing compared the declared PATH against
    the source. An allowlist whose path can be wrong is a document that only
    looks like evidence, and it took an outside reader spotting the mismatch.

    A plain substring test would not have caught it either: "marketing_clients
    .json" IS a prefix of "...jsonl". So the basename must be followed by a
    non-filename character.
    """
    import re

    raw = str(entry.get("path_pattern") or "")
    # `.tmp` / `.lock` companions are derived in code (`path + ".tmp"`), so the
    # thing to look for is the store file they hang off.
    core = re.sub(r"\.(tmp|lock)$", "", raw)
    basename = core.rsplit("/", 1)[-1]
    if not basename:
        return [f"{eid}: empty path_pattern"]

    text = src.read_text(encoding="utf-8", errors="replace")
    # Trailing boundary: quote, whitespace, or anything that is not a filename
    # character. This is what distinguishes `.json` from `.jsonl`.
    if not re.search(re.escape(basename) + r"(?![A-Za-z0-9_])", text):
        return [
            f"{eid}: path_pattern {raw!r} does not appear in {entry['file']} — "
            "the declared path does not match the code"
        ]
    return []


def path_components_match(declared: str, detected: str) -> bool:
    """Compare two path expressions on COMPONENT boundaries.

    Prefix matching is unsafe here and that is not hypothetical: `.json` is a
    prefix of `.jsonl`, and `data/client` is a prefix of `data/client_secrets`.
    A companion `.tmp` / `.lock` is matched against the store file it hangs off,
    because code derives it as `path + ".tmp"` and the literal never appears.
    """
    import re

    def norm(s: str) -> str:
        s = str(s).replace("\\", "/").replace('"', "'")
        s = re.sub(r"/{2,}", "/", s)
        s = re.sub(r"(?<![.\w])\./", "", s)
        return s

    core = re.sub(r"\.(tmp|lock)$", "", norm(declared))
    basename = core.rsplit("/", 1)[-1]
    if not basename:
        return False
    # Trailing boundary is the whole point: no [A-Za-z0-9_] may follow.
    return bool(re.search(re.escape(basename) + r"(?![A-Za-z0-9_])", norm(detected)))


_SYMBOL_TABLES: dict[str, dict[str, str]] = {}


def _symbol_table(file: str) -> dict[str, str]:
    """Module symbol -> path expression, cached per file."""
    if file in _SYMBOL_TABLES:
        return _SYMBOL_TABLES[file]
    import ast

    table: dict[str, str] = {}
    src = Path(__file__).resolve().parents[2] / file
    try:
        tree = ast.parse(src.read_text(encoding="utf-8"))
        table = _scan._mutable_symbols(tree)
        # Built the SAME way `scan_python` builds its symbol map, because a
        # table assembled differently means the evidence walker cannot see what
        # the scanner has already proved. A proven path-returning helper
        # contributes its BOUNDED pattern (env var + static fallback), never a
        # runtime value, so `p = _kill_file()` is compared against the store the
        # call opens instead of against the literal text `_kill_file()`.
        helpers = _scan._provenance_table(tree).get(_scan._HELPERS) or {}
        for name, pattern in _scan._helper_patterns(tree, helpers).items():
            # Only an INFORMATIVE pattern may displace what the plain symbol
            # walk already found. A helper whose root comes from a local wrapper
            # renders as an opaque `<_env>`, and taking that over the assignment
            # text would replace a path containing the real filename with a
            # placeholder — resolution going backwards, not forwards.
            if any(mark in pattern for mark in ("/", "<$", ".")) or name not in table:
                table[name] = pattern
    except Exception:  # pragma: no cover - defensive
        table = {}
    _SYMBOL_TABLES[file] = table
    return table


def _resolved_path_of(finding: dict[str, Any], depth: int = 4) -> str:
    """Follow a symbol chain until a real path expression appears.

    A finding on `open(path, ...)` normalizes to `path`, whose definition is
    `_CLIENTS_FILE`, whose definition is
    `os.path.join('data', 'marketing_clients.jsonl')`. Only the last of those
    carries the filename, so binding has to walk the chain — one hop is not
    enough, and stopping early is how a declaration ends up compared against a
    variable name instead of a path.
    """
    import re

    expr = _scan.normalized_path(finding)
    table = _symbol_table(finding["file"])
    for _ in range(depth):
        text = expr.strip()
        bare = re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text)
        # One hop through a path-returning helper CALL. `p = _kill_file()` and
        # `path = _mission_path(mission_id)` are not symbols, so the identifier
        # walk stopped on the call text and a declaration ended up compared
        # against `_kill_file()` rather than the store file it opens. Only
        # helpers the scanner has already PROVEN are in the table, and the
        # argument list is discarded — a runtime id must never reach a
        # declaration comparison.
        call = None if bare else re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\([^()]*\)", text)
        name = bare.group(0) if bare else (call.group(1) if call else None)
        if name is None or name not in table:
            break
        expr = table[name]
    return expr


_COMPANION_DERIVATION = None  # compiled lazily below


def _companion_of_primary(
    entry: dict[str, Any], finding: dict[str, Any], findings: list[dict[str, Any]]
) -> bool:
    """Is this finding a `.lock`/`.tmp` DERIVED from the entry's primary store?

    A companion literal never appears in code — it is built as
    `_STORE + '.lock'` or `target.with_suffix(...)`. So the binding cannot look
    for the filename; it must prove the derivation:

      1. the entry declares a `.tmp` / `.lock` companion,
      2. the detected expression is a suffix derivation, and
      3. the symbol it derives FROM resolves, in the same file, to the declared
         primary store.

    Step 3 is what stops an unrelated `.lock` in the same module being mapped
    onto this authority by resemblance, and what keeps a lock from drifting to
    a different store id than the data it protects.
    """
    import re

    global _COMPANION_DERIVATION
    if _COMPANION_DERIVATION is None:
        _COMPANION_DERIVATION = re.compile(
            # A suffixed temp name (`.tmp_kill`, `.tmp_dpdp`) is still a temp
            # companion; requiring the literal `.tmp` meant a module that
            # disambiguates its own temp files fell out of companion binding.
            # `p.with_name(...)` is the third derivation shape in this repo.
            r"(?P<base>[A-Za-z_][A-Za-z0-9_]*)\s*(?:"
            r"\+\s*['\"]\.(?:lock|tmp)[A-Za-z0-9_]*['\"]"
            r"|\.with_suffix\("
            r"|\.with_name\("
            r")"
        )

    declared = str(entry.get("path_pattern") or "")
    if not re.search(r"\.(tmp|lock)$", declared):
        return False

    detected = _scan.normalized_path(finding)
    m = _COMPANION_DERIVATION.search(detected)
    if not m:
        return False

    primary = re.sub(r"\.(tmp|lock)$", "", declared)
    base_symbol = m.group("base")

    # The base symbol must itself resolve to the declared primary store,
    # somewhere in this same file.
    for other in findings:
        if other["file"] != finding["file"]:
            continue
        if other.get("symbol") == base_symbol or base_symbol in str(
            other.get("path_expression", "")
        ):
            if path_components_match(primary, _resolved_path_of(other)):
                return True
    # The base symbol may be defined without ever producing its own finding
    # (a bare module constant). Fall back to the module's symbol table, still
    # requiring that it resolves to the DECLARED primary store.
    table = _symbol_table(finding["file"])
    seen = base_symbol
    for _ in range(4):
        nxt = table.get(seen)
        if nxt is None:
            break
        if path_components_match(primary, nxt):
            return True
        m2 = re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", nxt.strip())
        if not m2:
            break
        seen = m2.group(0)
    return False


def _check_finding_binding(
    entries: list[dict[str, Any]], findings: list[dict[str, Any]]
) -> list[str]:
    """PRIMARY evidence: every entry must bind to a real scanner finding.

    Searching the module text for the declared basename is not enough, because
    a comment, a docstring, an error message or a dead constant satisfies it.
    That is how `data/marketing_clients.json` survived: the file legitimately
    contains that substring inside `marketing_clients.jsonl`.

    So the entry must match a FINDING whose file, symbol, operation and
    normalized resolved path all agree, and that finding must not be a fixture
    or a static asset.
    """
    problems: list[str] = []
    claims: dict[str, set[str]] = {}

    for e in entries:
        eid = e["allowlist_id"]
        key = f"{e['file']}:{e['line_or_symbol']}"
        matched = [
            f
            for f in findings
            if f["file"] == e["file"]
            and (
                str(f.get("symbol")) == str(e["line_or_symbol"]) or f["line"] == e["line_or_symbol"]
            )
        ]
        if not matched:
            problems.append(f"{eid}: no scanner finding at {key} — declaration is unbound")
            continue

        path_ok = [
            f
            for f in matched
            if path_components_match(e["path_pattern"], _resolved_path_of(f))
            or _companion_of_primary(e, f, findings)
        ]
        if not path_ok:
            observed = sorted({_scan.normalized_path(f)[:70] for f in matched})
            problems.append(
                f"{eid}: declared path {e['path_pattern']!r} does not match any detected "
                f"path at {key}; detected {observed}"
            )
            continue

        for f in path_ok:
            cls = f["classification"]
            if cls in (_scan.FIXTURE_ONLY, _scan.STATIC_ASSET):
                problems.append(
                    f"{eid}: bound to a {cls} finding — an allowlist entry must "
                    "describe production state"
                )
            if e["production_relevance"] == "LIVE" and not f.get("production_relevant"):
                problems.append(f"{eid}: declared LIVE but the finding is not production-relevant")
            claims.setdefault(_scan.fingerprint(f), set()).add(e["store_id"])

    for fp, stores in claims.items():
        if len(stores) > 1:
            problems.append(f"finding {fp} is claimed by conflicting store ids: {sorted(stores)}")
    return problems


def _check_liveness(entries: list[dict[str, Any]], findings: list[dict[str, Any]]) -> list[str]:
    """Every entry must still correspond to real code, and the declared access
    modes must actually be the ones observed.

    Without this an allowlist quietly becomes documentation of the past: the
    declaration survives long after the code it excused has moved.
    """
    problems: list[str] = []
    by_key: dict[str, set[str]] = {}
    for f in findings:
        by_key.setdefault(f"{f['file']}:{f['line']}", set()).add(f["operation"])
        if f.get("symbol"):
            by_key.setdefault(f"{f['file']}:{f['symbol']}", set()).add(f["operation"])

    for e in entries:
        key = f"{e['file']}:{e['line_or_symbol']}"
        observed = by_key.get(key)
        if observed is None:
            problems.append(
                f"{e['allowlist_id']}: STALE — no live finding at {key}. "
                "Remove the entry or point it at the code that replaced it."
            )
            continue
        declared = set(e["access_modes"])
        undeclared_ops = observed - declared
        if undeclared_ops:
            problems.append(
                f"{e['allowlist_id']}: operation mismatch at {key} — code performs "
                f"{sorted(undeclared_ops)} which the entry does not declare"
            )
    return problems


def index(entries: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Entries in the shape `runtime_data_scan.scan_repo` expects."""
    return load() if entries is None else entries


def coverage(findings: list[dict[str, Any]]) -> dict[str, int]:
    """Gate-relevant counts, all derived — never hand-maintained."""
    return {
        "undeclared_mutable_paths": sum(
            1 for f in findings if f["classification"] == _scan.UNDECLARED_MUTABLE_PATH
        ),
        "ambiguous_mutable_paths": sum(
            1 for f in findings if f["classification"] == _scan.AMBIGUOUS_REQUIRES_REVIEW
        ),
        "declared_legacy_writes": sum(
            1 for f in findings if f["classification"] == _scan.DECLARED_LEGACY_WRITE
        ),
        "declared_legacy_reads": sum(
            1 for f in findings if f["classification"] == _scan.DECLARED_LEGACY_READ
        ),
        "canonical": sum(
            1 for f in findings if f["classification"] == _scan.CANONICAL_RUNTIME_PATH
        ),
    }


__all__ = [
    "ALLOWLIST_PATH",
    "REQUIRED_FIELDS",
    "IMMUTABLE_STORE_IDS",
    "load",
    "validate",
    "index",
    "coverage",
]
