"""A8 ratchet — external mission root must stay migrated.

Easy win: ``devcontrol.external_missions`` already had ``EXTERNAL_MISSION_DIR``.
A8 wires the default through ``resolve_store_path`` with
``override_env="EXTERNAL_MISSION_DIR"`` and ``target_segments=("external_missions",)``.

Two properties the repo-wide debt ratchet cannot give:

  * the A8 writer modules carry ZERO uncontrolled in-checkout runtime paths
    for the migrated store (survivors must be named in OUT_OF_SCOPE);
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
from tests.runtime_data_waves import A8_STORE_IDS
from tests.test_runtime_data_a1_ratchet import (
    EXPECTED_ALLOWLIST_ENTRIES,
    EXPECTED_BASELINE_FINGERPRINTS,
    EXPECTED_BLOCKERS,
    _uncontrolled_path_findings,
)

REPO = Path(__file__).resolve().parents[1]

#: Their production writer modules.
A8_MODULES = (
    "app/dev_control/external_agents/store.py",
    "app/dev_control/external_agents/cas.py",
)

#: Resolver entry points each module must expose as functions.
A8_RESOLVERS = {
    "app/dev_control/external_agents/store.py": ("_root",),
    "app/dev_control/external_agents/cas.py": (),
}

#: Retired import-time constants. Reintroducing them as Assign is a defect.
RETIRED_CONSTANTS = ("DEFAULT_ROOT",)

#: Paths that live in an A8 module but belong to a store A8 did NOT migrate.
#: Docstrings mentioning data/external_missions are exempt by the detector;
#: any remaining literal must be named here or removed.
OUT_OF_SCOPE: dict[str, dict[str, str]] = {
    "app/dev_control/external_agents/store.py": {},
    "app/dev_control/external_agents/cas.py": {},
}


# ------------------------------------------------------------------- code
@pytest.mark.parametrize("module_path", A8_MODULES)
def test_a8_writer_modules_have_zero_uncontrolled_runtime_paths(module_path):
    declared = OUT_OF_SCOPE.get(module_path, {})
    observed = {value for _, value in _uncontrolled_path_findings(module_path)}

    undeclared = sorted(observed - set(declared))
    assert not undeclared, f"{module_path} still opens an unclassified checkout path: {undeclared}"

    stale = sorted(set(declared) - observed)
    assert not stale, (
        f"{module_path}: {stale} no longer appears — delete the exclusion rather "
        "than leaving a hole the next literal can hide in"
    )


@pytest.mark.parametrize("module_path", A8_MODULES)
def test_a8_modules_resolve_at_call_time_not_import_time(module_path):
    """The resolver must be a function, and no module-level Assign may hold a
    retired constant name for a migrated store.
    """
    tree = ast.parse((REPO / module_path).read_text(encoding="utf-8"))

    functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    for resolver in A8_RESOLVERS[module_path]:
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


def test_a8_cas_get_backend_uses_resolve_store_path():
    """cas.get_backend must call resolve_store_path when root is unset."""
    src = (REPO / "app/dev_control/external_agents/cas.py").read_text(encoding="utf-8")
    assert "resolve_store_path" in src
    assert 'override_env="EXTERNAL_MISSION_DIR"' in src
    assert 'or "data/external_missions"' not in src


# --------------------------------------------------------------- manifest
def test_the_a8_rows_are_still_dual_read():
    """A8's own rows, asserted by A8's own file.

    Subset only — the exact global set is asserted once in
    ``test_runtime_data_waves.py`` as the union of every declared wave.
    """
    moved = {s["store_id"] for s in manifest.by_state(manifest.CUTOVER_COMPLETE)}
    assert set(A8_STORE_IDS) <= moved, set(A8_STORE_IDS) - moved


def test_manifest_still_validates():
    assert manifest.validate() == []


def test_migrating_the_code_does_not_reduce_the_blocker_count():
    """Migrated stores, and the count is still 21 — that is the honest answer."""
    blocking = manifest.blocking_stores()
    assert len(blocking) == EXPECTED_BLOCKERS, sorted(s["store_id"] for s in blocking)
    assert not blocking
    assert manifest.DUAL_READ_PRE_CUTOVER in manifest.BLOCKING_STATES
    assert manifest.CUTOVER_COMPLETE not in manifest.BLOCKING_STATES


def test_no_allowlist_or_baseline_relaxation():
    """The migration must not buy its green by loosening a neighbouring control."""
    assert len(allowlist.load()) == EXPECTED_ALLOWLIST_ENTRIES
    assert len(baseline.ENTRIES) == EXPECTED_BASELINE_FINGERPRINTS
