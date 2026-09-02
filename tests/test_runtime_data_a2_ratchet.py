"""A2 ratchet — the compliance suppression/consent stores must stay migrated.

A1 proved the shared authority on the telephony kill switches. A2 applies it to
the three stores that decide whether a human may be contacted at all: the
WhatsApp suppression list, the TRAI/DPDP consent ledger, and the voice
suppression list. Getting a path wrong here does not lose a config file, it
answers an opt-out question with data that is no longer authoritative — which
is a TCCCPR/DPDP problem, not a tidiness problem.

Two properties are asserted that the repo-wide debt ratchet cannot give:

  * the A2 writer modules carry ZERO uncontrolled in-checkout runtime paths
    (repo-wide the rule is only "no growth", because 1000+ findings predate
    this workstream; for a store that has just been migrated the honest target
    is zero and it must stay zero);
  * nothing in the repository still imports the deleted module CONSTANTS. The
    deprecation shim in `consent_ledger` can only fire once per importing
    module and then freezes, so an import that survives it is a latent
    frozen-path bug, not a supported call style.

Nothing here enables calling, writes a marker, or moves production data.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.platform import runtime_data_allowlist as allowlist
from app.platform import runtime_data_baseline as baseline
from app.platform import runtime_data_manifest as manifest
from tests.runtime_data_waves import A2_STORE_IDS
from tests.test_runtime_data_a1_ratchet import (
    EXPECTED_ALLOWLIST_ENTRIES,
    EXPECTED_BASELINE_FINGERPRINTS,
    EXPECTED_BLOCKERS,
    _uncontrolled_path_findings,
)

REPO = Path(__file__).resolve().parents[1]

#: Their production writer/reader modules.
A2_MODULES = (
    "app/marketing/wa_campaign_runner.py",
    "app/telephony/consent_ledger.py",
)

#: The resolver entry points each module must expose. A module that migrated
#: its reads but kept a constant for its writes is the split-brain this wave
#: exists to prevent, so both directions are named explicitly.
A2_RESOLVERS = {
    "app/marketing/wa_campaign_runner.py": ("_suppression_path",),
    "app/telephony/consent_ledger.py": ("ledger_path", "suppression_path"),
}

#: Deleted constants. Any repository code still importing these is a defect.
RETIRED_CONSTANTS = ("LEDGER_FILE", "SUPPRESSION_FILE", "_SUPPRESSION_FILE")

#: Roots scanned for reintroduced constants. Wider than the migrated modules on
#: purpose: the damage from a frozen compliance path does not depend on which
#: directory froze it.
SCANNED_ROOTS = ("app", "scripts", "tests", "alembic")

# The pinned counts (EXPECTED_BLOCKERS / EXPECTED_ALLOWLIST_ENTRIES /
# EXPECTED_BASELINE_FINGERPRINTS) are imported from the A1 ratchet rather than
# restated here. Two copies of a pinned number drift, and the drift always
# resolves in favour of whichever copy the failing test happens to read.

#: Paths that live in an A2 module but belong to a store A2 did NOT migrate.
#: An exclusion list, not an amnesty: the assertion requires the observed set to
#: equal it exactly, so a new literal cannot hide behind an old one.
OUT_OF_SCOPE: dict[str, dict[str, str]] = {
    "app/marketing/wa_campaign_runner.py": {
        "data/wa_templates.jsonl": (
            "marketing template library — rebuildable content, not a compliance "
            "authority, and not classified into a wave yet."
        ),
        "data/wa_campaigns.jsonl": (
            "campaign run log — operational history owned by a later wave; "
            "folding it in here would migrate a store nobody has classified."
        ),
        "data/wa_failures.jsonl": (
            "UNCLASSIFIED — found by this ratchet on 2026-07-28 and NOT present in "
            "runtime_data_manifest.py at all. It is compliance-adjacent: three "
            "recorded failures auto-suppress a number, so losing the file silently "
            "resets a suppression counter and the next campaign sends three more "
            "messages to that number. It is excluded here because inventing a "
            "manifest row inside a migration commit would move the reconciled "
            "denominator without evidence — it needs its own classification with "
            "production stat/size evidence first. Tracked in memory/backlog.md."
        ),
    },
    "app/telephony/consent_ledger.py": {},
}


# ------------------------------------------------------------------- code
@pytest.mark.parametrize("module_path", A2_MODULES)
def test_a2_writer_modules_have_zero_uncontrolled_runtime_paths(module_path):
    declared = OUT_OF_SCOPE.get(module_path, {})
    observed = {value for _, value in _uncontrolled_path_findings(module_path)}

    undeclared = sorted(observed - set(declared))
    assert not undeclared, f"{module_path} still opens an unclassified checkout path: {undeclared}"

    stale = sorted(set(declared) - observed)
    assert not stale, (
        f"{module_path}: {stale} no longer appears — delete the exclusion rather "
        "than leaving a hole the next literal can hide in"
    )


@pytest.mark.parametrize("module_path", A2_MODULES)
def test_a2_modules_resolve_at_call_time_not_import_time(module_path):
    """The resolver must be a function, and no module-level constant may hold a
    `data/...` path for a migrated store.

    A path bound at import is unreachable by any fixture, container env or
    cutover that runs later — that specific bug is why this workstream exists.
    """
    tree = ast.parse((REPO / module_path).read_text(encoding="utf-8"))

    functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    for resolver in A2_RESOLVERS[module_path]:
        assert resolver in functions, f"{module_path} must expose {resolver}() as a function"

    # Module level includes the bodies of top-level `try:` / `if:` blocks — a
    # constant reintroduced under `if TYPE_CHECKING:` or a try/except import
    # fallback is bound at import just the same, and walking only `tree.body`
    # would step straight over it.
    def _module_level(body: list[ast.stmt]):
        for node in body:
            yield node
            if isinstance(node, ast.If | ast.Try):
                yield from _module_level(node.body)
                yield from _module_level(getattr(node, "orelse", []))
                yield from _module_level(getattr(node, "finalbody", []))
                for handler in getattr(node, "handlers", []):
                    yield from _module_level(handler.body)

    for node in _module_level(tree.body):
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
        for name in targets:
            assert name not in RETIRED_CONSTANTS, (
                f"{module_path} reintroduced module-level {name} — a path frozen at "
                "import cannot follow a cutover"
            )


def _retired_constant_offenders(rel: str, text: str) -> list[str]:
    """The three reintroduction shapes, on ANY receiver. Never raises."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in RETIRED_CONSTANTS:
                    found.append(f"{rel}:{node.lineno} imports {alias.name}")
        elif isinstance(node, ast.Attribute) and node.attr in RETIRED_CONSTANTS:
            found.append(f"{rel}:{node.lineno} reads .{node.attr}")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in RETIRED_CONSTANTS
        ):
            found.append(f"{rel}:{node.lineno} getattr({node.args[1].value!r})")
    return found


def test_no_repository_code_imports_the_retired_constants():
    """The deprecation shim is a tripwire, not a supported call style.

    `from consent_ledger import LEDGER_FILE` resolves ONCE and the importing
    module then holds a frozen Path forever, so the shim cannot deliver
    operation-time resolution to that form. Matching on the AST rather than on
    raw text keeps the prose in these very docstrings from failing the test.

    Three shapes are caught, on ANY receiver:
      * `from <module> import LEDGER_FILE`
      * `<anything>.LEDGER_FILE`
      * `getattr(<anything>, "LEDGER_FILE")`

    Receiver names are deliberately NOT allowlisted. An earlier version accepted
    only `cl` / `consent_ledger` / `runner`, which missed 8 of the 28 real
    import aliases in this repository — an allowlist of variable names is a
    guess about how the next author will spell things.

    The text pre-filter is not an optimisation for its own sake: an identifier
    cannot appear in a module's AST unless it appears in that module's source
    text, so gating on `in text` is exactly equivalent and drops the parse count
    from ~1000 files to ~3. The unfiltered version segfaulted CI twice inside
    `ast.parse` during garbage collection (exit 139, no assertion failure) in a
    process holding ~155 native extension modules. Cheapness here is a
    stability property, not a nicety.
    """
    offenders: list[str] = []
    scanned = 0
    parsed = 0
    for root in SCANNED_ROOTS:
        root_dir = REPO / root
        if not root_dir.is_dir():
            continue
        for path in sorted(root_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(REPO).as_posix()
            if rel in ("app/telephony/consent_ledger.py", "tests/test_runtime_data_a2_ratchet.py"):
                continue  # define the shim / name the constants as data
            scanned += 1
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if not any(const in text for const in RETIRED_CONSTANTS):
                continue
            parsed += 1
            offenders.extend(_retired_constant_offenders(rel, text))
    assert scanned > 200, f"the scan walked only {scanned} files — it is not looking at the repo"
    assert parsed <= 25, (
        f"the text pre-filter stopped working: {parsed} of {scanned} files reached ast.parse. "
        "That is the shape that segfaulted CI; if the constants really are named in that many "
        "files, find out why before raising this bound"
    )
    assert not offenders, offenders


def test_the_retired_constant_scanner_would_catch_a_regression():
    """Anti-vacuity: a scanner that finds nothing anywhere proves nothing.

    Every shape it claims to catch is exercised on purpose, together with the
    two shapes it must NOT flag — a docstring mentioning the name, and a
    same-named attribute belonging to some unrelated object is deliberately
    still flagged, because a false positive there costs a rename and a false
    negative costs a frozen compliance path.
    """
    sample = (
        '"""A docstring naming LEDGER_FILE must not count."""\n'
        "from app.telephony.consent_ledger import LEDGER_FILE\n"
        "from app.marketing.wa_campaign_runner import _SUPPRESSION_FILE as X\n"
        "a = some_unexpected_alias.SUPPRESSION_FILE\n"
        "b = app.telephony.consent_ledger.LEDGER_FILE\n"
        'c = getattr(mod, "SUPPRESSION_FILE")\n'
        'd = "SUPPRESSION_FILE"\n'
    )
    found = _retired_constant_offenders("sample.py", sample)
    assert len(found) == 5, found
    assert sum("imports" in f for f in found) == 2, found
    assert sum("reads ." in f for f in found) == 2, found
    assert sum("getattr(" in f for f in found) == 1, found

    clean = '"""Only prose about LEDGER_FILE here."""\nx = 1\n'
    assert _retired_constant_offenders("clean.py", clean) == []


# --------------------------------------------------------------- manifest
def test_the_a2_rows_are_still_dual_read():
    """A2's own rows, asserted by A2's own file.

    This was `moved == A1 | A2` while A2 was the newest wave. It is a subset
    assertion now that later waves have landed — NOT a relaxation: the exact
    global set is asserted once in ``test_runtime_data_waves.py``.
    """
    moved = {s["store_id"] for s in manifest.by_state(manifest.CUTOVER_COMPLETE)}
    assert set(A2_STORE_IDS) <= moved, set(A2_STORE_IDS) - moved


def test_manifest_still_validates():
    assert manifest.validate() == []


def test_migrating_the_code_does_not_reduce_the_blocker_count():
    """Six migrated stores, and the count is still 21 — that is the honest answer.

    Their writers can now follow a cutover; their authoritative bytes are still
    inside the checkout. Until those bytes are copied, verified and activated, a
    destructive deployment still destroys them. A count that fell to 18 here
    would be a false green: resolver-ready is not data-safe.
    """
    blocking = manifest.blocking_stores()
    assert len(blocking) == EXPECTED_BLOCKERS, sorted(s["store_id"] for s in blocking)
    assert not blocking
    assert manifest.DUAL_READ_PRE_CUTOVER in manifest.BLOCKING_STATES
    assert manifest.CUTOVER_COMPLETE not in manifest.BLOCKING_STATES


def test_no_allowlist_or_baseline_relaxation():
    """The migration must not buy its green by loosening a neighbouring control."""
    assert len(allowlist.load()) == EXPECTED_ALLOWLIST_ENTRIES
    assert len(baseline.ENTRIES) == EXPECTED_BASELINE_FINGERPRINTS
