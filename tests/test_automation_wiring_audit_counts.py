"""Single-pass automation flag reference counting contracts."""

from scripts.automation_wiring_audit import _reference_counts


def test_reference_counts_preserve_exact_word_boundaries():
    blob = "FLAG FLAG_A FLAG_A XFLAG FLAG_B_SUFFIX FLAG_B"
    counts = _reference_counts(blob, ["FLAG", "FLAG_A", "FLAG_B"])
    assert counts["FLAG"] == 1
    assert counts["FLAG_A"] == 2
    assert counts["FLAG_B"] == 1


def test_reference_counts_handle_empty_registry():
    assert _reference_counts("FLAG_A", []) == {}
