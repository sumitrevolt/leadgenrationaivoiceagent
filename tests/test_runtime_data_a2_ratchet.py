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
from tests.test_runtime_data_a1_ratchet import A1_STORE_IDS, _uncontrolled_path_findings

REPO = Path(__file__).resolve().parents[1]

#: The stores A2 migrated.
A2_STORE_IDS = frozenset(
    {
        "compliance.wa_suppression",
        "compliance.consent_ledger",
        "compliance.voice_suppression",
    }
)

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

#: Counts pinned so a "small cleanup" cannot quietly relax a neighbouring
#: control. Unchanged from A1 on purpose — see the blocker-count test below.
EXPECTED_BLOCKERS = 21
EXPECTED_ALLOWLIST_ENTRIES = 16
EXPECTED_BASELINE_FINGERPRINTS = 839

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
    "app/telephony/consent_ledger.py": {
        "data/recordings": (
            "telephony.call_recordings — Tier 2, retention-governed, and not an "
            "A2 store. It shares this module with the ledger by accident of "
            "layout, not by ownership."
        ),
    },
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

    for node in tree.body:
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


def test_no_repository_code_imports_the_retired_constants():
    """The deprecation shim is a tripwire, not a supported call style.

    `from consent_ledger import LEDGER_FILE` resolves ONCE and the importing
    module then holds a frozen Path forever, so the shim cannot deliver
    operation-time resolution to that form. Scanning imports (not substrings)
    keeps the prose in these very docstrings from failing the test.
    """
    offenders: list[str] = []
    for path in sorted((REPO / "app").rglob("*.py")) + sorted((REPO / "scripts").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(REPO).as_posix()
        if rel == "app/telephony/consent_ledger.py":
            continue  # defines the shim
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in RETIRED_CONSTANTS:
                        offenders.append(f"{rel}:{node.lineno} imports {alias.name}")
            elif isinstance(node, ast.Attribute) and node.attr in RETIRED_CONSTANTS:
                value = node.value
                if isinstance(value, ast.Name) and value.id in {"cl", "consent_ledger", "runner"}:
                    offenders.append(f"{rel}:{node.lineno} reads .{node.attr}")
    assert not offenders, offenders


# --------------------------------------------------------------- manifest
def test_exactly_the_a1_and_a2_rows_have_moved_state():
    """The single exact global assertion, owned by the newest wave.

    A3 has not landed, so any additional row in DUAL_READ_PRE_CUTOVER means a
    manifest state ran ahead of its code.
    """
    moved = {s["store_id"] for s in manifest.by_state(manifest.DUAL_READ_PRE_CUTOVER)}
    assert moved == set(A1_STORE_IDS) | set(A2_STORE_IDS), moved


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
    assert A2_STORE_IDS <= {s["store_id"] for s in blocking}


def test_no_allowlist_or_baseline_relaxation():
    """The migration must not buy its green by loosening a neighbouring control."""
    assert len(allowlist.load()) == EXPECTED_ALLOWLIST_ENTRIES
    assert len(baseline.ENTRIES) == EXPECTED_BASELINE_FINGERPRINTS
