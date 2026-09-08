"""A3 ratchet — the remaining compliance stores must stay migrated.

A1 proved the shared authority on telephony kill switches. A2 (when present)
applies it to WhatsApp/consent/voice suppression. A3 finishes the compliance
tier-0 set: the unified email suppression ledger and the DPDP audit/requests
pair.

Two properties the repo-wide debt ratchet cannot give:

  * the A3 writer modules carry ZERO uncontrolled in-checkout runtime paths
    for the migrated stores (survivors must be named in OUT_OF_SCOPE);
  * resolvers are functions, not import-time Path/str constants.

Nothing here enables calling, writes a marker, or moves production data.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.platform import runtime_data_allowlist as allowlist
from app.platform import runtime_data_baseline as baseline
from app.platform import runtime_data_manifest as manifest
from tests.runtime_data_waves import A3_STORE_IDS
from tests.test_runtime_data_a1_ratchet import (
    EXPECTED_ALLOWLIST_ENTRIES,
    EXPECTED_BASELINE_FINGERPRINTS,
    EXPECTED_BLOCKERS,
    _uncontrolled_path_findings,
)

REPO = Path(__file__).resolve().parents[1]

#: Their production writer modules.
A3_MODULES = (
    "app/platform/email_unsub.py",
    "app/platform/dpdp.py",
)

#: Resolver entry points each module must expose as functions.
A3_RESOLVERS = {
    "app/platform/email_unsub.py": ("_store_path",),
    "app/platform/dpdp.py": ("_AUDIT_FILE", "_REQUESTS_FILE"),
}

#: Retired import-time constants. Reintroducing them as Assign is a defect.
RETIRED_CONSTANTS = ("_STORE", "_AUDIT_FILE", "_REQUESTS_FILE")

#: Paths that live in an A3 module but belong to a store A3 did NOT migrate.
OUT_OF_SCOPE: dict[str, dict[str, str]] = {
    "app/platform/email_unsub.py": {},
    "app/platform/dpdp.py": {
        # Subject-data JSONL stores (_STORES / _CRM_DIR) scanned for erasure
        # discovery — other families, not compliance.dpdp_audit. Folding them
        # into this wave would migrate stores nobody classified under the audit
        # row. A2's scanner reconstructs literal joins, so each path is named.
        "data/inquiries.jsonl": "erasure-scan subject store (not dpdp_audit)",
        "data/prospects.jsonl": "erasure-scan subject store (not dpdp_audit)",
        "data/widget_chats.jsonl": "erasure-scan subject store (not dpdp_audit)",
        "data/reply_drafts.jsonl": "erasure-scan subject store (not dpdp_audit)",
        "data/cadence_leads.jsonl": "erasure-scan subject store (not dpdp_audit)",
        "data/dialer_logs.jsonl": "erasure-scan subject store (not dpdp_audit)",
        "data/customer_wish_drafts.jsonl": "erasure-scan subject store (not dpdp_audit)",
        "data/crm": "erasure-scan CRM dir (not dpdp_audit)",
    },
}


# ------------------------------------------------------------------- code
@pytest.mark.parametrize("module_path", A3_MODULES)
def test_a3_writer_modules_have_zero_uncontrolled_runtime_paths(module_path):
    declared = OUT_OF_SCOPE.get(module_path, {})
    observed = {value for _, value in _uncontrolled_path_findings(module_path)}

    undeclared = sorted(observed - set(declared))
    assert not undeclared, f"{module_path} still opens an unclassified checkout path: {undeclared}"

    stale = sorted(set(declared) - observed)
    assert not stale, (
        f"{module_path}: {stale} no longer appears — delete the exclusion rather "
        "than leaving a hole the next literal can hide in"
    )


@pytest.mark.parametrize("module_path", A3_MODULES)
def test_a3_modules_resolve_at_call_time_not_import_time(module_path):
    """The resolver must be a function, and no module-level Assign may hold a
    retired constant name for a migrated store.
    """
    tree = ast.parse((REPO / module_path).read_text(encoding="utf-8"))

    functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    for resolver in A3_RESOLVERS[module_path]:
        assert resolver in functions, f"{module_path} must expose {resolver}() as a function"

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
        targets: list[str] = []
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
        for name in targets:
            assert name not in RETIRED_CONSTANTS, (
                f"{module_path} reintroduced module-level {name} — a path frozen "
                "at import cannot follow a cutover"
            )


# --------------------------------------------------------------- manifest
def test_the_a3_rows_are_still_dual_read():
    """A3's own rows, asserted by A3's own file.

    Subset only — the exact global set is asserted once in
    ``test_runtime_data_waves.py`` as the union of every declared wave.
    """
    moved = {s["store_id"] for s in manifest.by_state(manifest.CUTOVER_COMPLETE)}
    assert set(A3_STORE_IDS) <= moved, set(A3_STORE_IDS) - moved


def test_manifest_still_validates():
    assert manifest.validate() == []


def test_migrating_the_code_does_not_reduce_the_blocker_count():
    """Migrated stores, and the count is still 21 — that is the honest answer.

    Writers can now follow a cutover; authoritative bytes are still inside the
    checkout. A count that fell to 19 here would be a false green.
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
