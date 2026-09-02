"""Cross-wave registry ratchet — one exact-global assertion for all waves.

Lives next to ``runtime_data_waves.py`` so a new wave does not have to move
the exact-global test into a new file. Each wave's own ratchet keeps a subset
assertion only.
"""

from __future__ import annotations

from app.platform import runtime_data_manifest as manifest
from tests.runtime_data_waves import WAVE_STORE_IDS, all_declared_store_ids
from tests.test_runtime_data_a1_ratchet import EXPECTED_BLOCKERS


def test_moved_set_equals_union_of_every_declared_wave():
    """Exactly one exact-global assertion: moved == union of every wave."""
    moved = {s["store_id"] for s in manifest.by_state(manifest.CUTOVER_COMPLETE)}
    declared = set(all_declared_store_ids())
    assert moved == declared, {
        "only_in_manifest": sorted(moved - declared),
        "only_in_registry": sorted(declared - moved),
    }


def test_registry_is_non_vacuous_against_manifest():
    """Registry must agree with the manifest — not merely restate it.

    * every declared id must exist as a manifest row;
    * every manifest row whose state says it has moved must appear in
      exactly one wave.

    A row that moved without being declared, a declared id that no longer
    exists, or an id claimed by two waves must fail.
    """
    by_id = {s["store_id"]: s for s in manifest.STORES}

    missing_from_manifest = sorted(set(all_declared_store_ids()) - set(by_id))
    assert not missing_from_manifest, (
        f"registry declares store ids absent from the manifest: {missing_from_manifest}"
    )

    wave_of: dict[str, str] = {}
    for wave, ids in WAVE_STORE_IDS.items():
        for store_id in ids:
            prior = wave_of.get(store_id)
            assert prior is None, f"{store_id} is declared in both wave {prior} and wave {wave}"
            wave_of[store_id] = wave

    moved_rows = manifest.by_state(manifest.CUTOVER_COMPLETE)
    undeclared_moved = sorted(s["store_id"] for s in moved_rows if s["store_id"] not in wave_of)
    assert not undeclared_moved, (
        f"manifest rows are moved but not declared in any wave: {undeclared_moved}"
    )


def test_blocking_store_count_is_still_pinned():
    """Host cutover complete — blockers cleared (EXPECTED_BLOCKERS=0)."""
    blocking = manifest.blocking_stores()
    assert len(blocking) == EXPECTED_BLOCKERS, sorted(s["store_id"] for s in blocking)
    assert not blocking
    assert manifest.DUAL_READ_PRE_CUTOVER in manifest.BLOCKING_STATES
    assert manifest.CUTOVER_COMPLETE not in manifest.BLOCKING_STATES
