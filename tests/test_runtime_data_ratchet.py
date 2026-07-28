"""The ratchet must let debt shrink and refuse to let it grow.

Printing counts was observability, not enforcement — a new undeclared writer
could have landed with CI still green. These tests are what make the claim
"the backlog cannot grow quietly" true rather than aspirational.
"""

from __future__ import annotations

import pathlib

import pytest

from app.platform import runtime_data_allowlist as al
from app.platform import runtime_data_baseline as baseline
from app.platform import runtime_data_ratchet as ratchet
from app.platform import runtime_data_scan as scan

_REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def current():
    from tests._runtime_data_scan_subprocess import scan_repo_in_subprocess

    return scan_repo_in_subprocess(_REPO)


def _f(**over):
    base = {
        "file": "app/example.py",
        "line": 10,
        "symbol": "STATE_PATH",
        "operation": scan.APPEND,
        "path_expression": "os.path.join('data', 'example.jsonl')",
        "resolved_pattern": "os.path.join('data', 'example.jsonl')",
        "classification": scan.UNDECLARED_MUTABLE_PATH,
        "store_id": None,
        "production_relevant": True,
    }
    base.update(over)
    return base


# ------------------------------------------------------------- current state


def test_current_state_passes_its_own_baseline(current) -> None:
    v = ratchet.evaluate(current)
    assert v["ok"], (
        f"new_unresolved={len(v['new_unresolved'])} regressions={len(v['regressions'])}\n"
        + "\n".join(ratchet.format_failures(v)[:5])
    )


def test_baseline_is_not_empty_and_is_deduplicated() -> None:
    fps = [e["finding_fingerprint"] for e in baseline.ENTRIES]
    assert fps, "baseline was not generated"
    assert len(fps) == len(set(fps)), "duplicate fingerprints in baseline"


def test_baseline_entries_are_recorded_as_unresolved_not_approved() -> None:
    """Wording matters: these are debt records, never approvals."""
    for e in baseline.ENTRIES:
        assert e["review_state"].endswith("PENDING_CLASSIFICATION")
        assert e["classification"] in ratchet.UNRESOLVED
        # No fabricated authority.
        assert "owner" not in e
        assert "migration_tier" not in e


def test_baseline_records_scanner_provenance() -> None:
    assert baseline.SCANNER_VERSION
    assert baseline.FIRST_RECORDED_HEAD
    assert baseline.FIRST_RECORDED_BRANCH


# ------------------------------------------------------------------ failures


def test_new_undeclared_finding_fails(current) -> None:
    v = ratchet.evaluate([*current, _f()])
    assert not v["ok"]
    assert len(v["new_unresolved"]) == 1
    assert "NEW_UNDECLARED_MUTABLE_PATH" in "\n".join(ratchet.format_failures(v))


def test_new_ambiguous_finding_fails(current) -> None:
    v = ratchet.evaluate([*current, _f(classification=scan.AMBIGUOUS_REQUIRES_REVIEW)])
    assert not v["ok"]
    assert len(v["new_unresolved"]) == 1


def test_swap_of_equal_counts_is_still_caught(current) -> None:
    """The reason this ratchets on fingerprints and not on counts.

    Remove one old finding, add one dangerous new writer: the total is
    identical, and a count-based gate would report no change.
    """
    trimmed = current[1:]
    v = ratchet.evaluate([*trimmed, _f()])
    assert len(trimmed) + 1 == len(current)
    assert not v["ok"], "count-neutral swap slipped through"


def test_canonical_regressing_to_legacy_fails(current) -> None:
    prior = next(
        (e for e in baseline.ENTRIES if e["classification"] == scan.UNDECLARED_MUTABLE_PATH),
        None,
    )
    assert prior is not None
    # Simulate: same identity, but classification drops below its baseline rank.
    # Baseline is already at the bottom, so build an explicit pair instead.
    high = _f(classification=scan.CANONICAL_RUNTIME_PATH, file="app/reg.py")
    low = _f(classification=scan.UNDECLARED_MUTABLE_PATH, file="app/reg.py")

    class _Base:
        ENTRIES = [
            {
                "finding_fingerprint": scan.fingerprint(high),
                "identity": ratchet._identity(high),
                "classification": high["classification"],
                "store_id": None,
            }
        ]

    original = ratchet._baseline
    try:
        ratchet._baseline = _Base  # type: ignore[assignment]
        v = ratchet.evaluate([low])
        assert not v["ok"]
        assert any(r["from"] == scan.CANONICAL_RUNTIME_PATH for r in v["regressions"])
    finally:
        ratchet._baseline = original


def test_losing_a_store_mapping_fails() -> None:
    mapped = _f(classification=scan.DECLARED_LEGACY_WRITE, store_id="billing.invoices")
    unmapped = _f(classification=scan.DECLARED_LEGACY_WRITE, store_id=None)

    class _Base:
        ENTRIES = [
            {
                "finding_fingerprint": scan.fingerprint(mapped),
                "identity": ratchet._identity(mapped),
                "classification": mapped["classification"],
                "store_id": "billing.invoices",
            }
        ]

    original = ratchet._baseline
    try:
        ratchet._baseline = _Base  # type: ignore[assignment]
        v = ratchet.evaluate([unmapped])
        assert not v["ok"]
        assert any("store=<lost>" in r["to"] for r in v["regressions"])
    finally:
        ratchet._baseline = original


# ------------------------------------------------------------ permitted moves


def test_removing_a_finding_passes(current) -> None:
    v = ratchet.evaluate(current[5:])
    assert v["ok"], "debt reduction must not fail the gate"
    assert v["removed"]


def test_unresolved_becoming_declared_passes(current) -> None:
    """Progress must not need a baseline rewrite."""
    promoted = []
    changed = 0
    for f in current:
        g = dict(f)
        if g["classification"] == scan.UNDECLARED_MUTABLE_PATH and changed < 3:
            g["classification"] = scan.DECLARED_LEGACY_WRITE
            g["store_id"] = "billing.invoices"
            changed += 1
        promoted.append(g)
    assert changed == 3
    v = ratchet.evaluate(promoted)
    assert v["ok"]
    # Current scan may already carry A4 CANONICAL promotions against the
    # frozen baseline; require at least the three we just declared.
    assert len(v["resolved"]) >= 3


def test_line_movement_alone_creates_no_debt(current) -> None:
    """A finding that shifts because an import was added is the same finding.

    A ratchet that reports it as new would fire on every unrelated edit, and a
    gate that cries wolf is a gate people switch off.
    """
    moved = [dict(f, line=f["line"] + 7) for f in current]
    v = ratchet.evaluate(moved)
    assert v["ok"]
    assert v["new_unresolved"] == []


def test_fingerprint_ignores_line_but_not_operation() -> None:
    a = _f(line=10)
    b = _f(line=99)
    c = _f(operation=scan.DELETE)
    assert scan.fingerprint(a) == scan.fingerprint(b)
    assert scan.fingerprint(a) != scan.fingerprint(c)


def test_no_bypass_exists_in_the_ratchet_path() -> None:
    for name in ("runtime_data_ratchet.py",):
        text = (_REPO / "app" / "platform" / name).read_text(encoding="utf-8")
        code = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        joined = "\n".join(code)
        for banned in ("accept_current_state", "ACCEPT_ALL", 'os.environ.get("SKIP'):
            assert banned not in joined
