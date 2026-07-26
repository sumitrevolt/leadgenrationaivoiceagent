"""The allowlist must stay tied to live code and to real store families.

An allowlist nobody re-checks becomes a record of what used to be true. Each
check here corresponds to a way that has already gone wrong somewhere in this
repo: a path moved and the note didn't, an id was typo'd, a writer was filed as
read-only.
"""

from __future__ import annotations

import copy
import pathlib

import pytest

from app.platform import runtime_data_allowlist as al
from app.platform import runtime_data_manifest as manifest
from app.platform import runtime_data_scan as scan

_REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def findings():
    return scan.scan_repo(_REPO, allowlist=al.load())


def _entry(**over):
    base = {
        "allowlist_id": "x.y",
        "file": "app/billing/gst_invoice.py",
        "line_or_symbol": "_STORE",
        "path_pattern": "data/invoices.jsonl",
        "store_id": "billing.invoices",
        "access_modes": ["APPEND"],
        "reason": "r",
        "migration_tier": 0,
        "target_change_set": "wave-0",
        "owner": "billing",
        "production_relevance": "LIVE",
        "review_condition": "c",
    }
    base.update(over)
    return base


# ------------------------------------------------------------------- shipped


def test_shipped_allowlist_is_coherent(findings) -> None:
    problems = al.validate(findings=findings)
    assert problems == [], "allowlist problems:\n  " + "\n  ".join(problems)


def test_store_family_count_is_derived_not_typed() -> None:
    """I reported "4 store families" while listing five names.

    The count must come from the data, and the names must reconcile with it —
    a summary that disagrees with its own list is how a wrong number survives
    a review.
    """
    entries = al.load()
    families = {e["store_id"] for e in entries}
    assert len(entries) == 9
    assert len(families) == 5, sorted(families)
    assert families == {
        "billing.invoices",
        "billing.upi_payments",
        "compliance.dpdp_audit",
        "compliance.email_suppression",
        "customers.identity",
    }
    # No alias: five distinct manifest authorities, not four with a rename.
    assert len({f.split(".")[0] for f in families}) == 3


def test_every_entry_maps_to_a_real_store_family() -> None:
    known = {s["store_id"] for s in manifest.STORES}
    for e in al.load():
        assert e["store_id"] in known, f"{e['allowlist_id']} -> {e['store_id']}"


def test_no_blanket_file_entries() -> None:
    """A whole-file exception would excuse writes nobody reviewed."""
    for e in al.load():
        assert e["line_or_symbol"] not in ("*", "", None)
        assert not str(e["line_or_symbol"]).startswith("*")


def test_locks_map_to_the_store_they_protect() -> None:
    """A lock is not its own logical store, and must not drift from its data."""
    by_id = {e["allowlist_id"]: e for e in al.load()}
    lock = by_id["billing.invoices.lock"]
    data = by_id["billing.invoices.store"]
    assert lock["store_id"] == data["store_id"]


# ------------------------------------------------------------ rejection cases


def test_unknown_store_id_rejected() -> None:
    problems = al.validate([_entry(store_id="does.not.exist")])
    assert any("unknown store_id" in p for p in problems)


def test_missing_owner_rejected() -> None:
    e = _entry()
    del e["owner"]
    assert any("missing required fields" in p for p in al.validate([e]))


def test_missing_migration_wave_rejected() -> None:
    e = _entry()
    del e["migration_tier"]
    assert any("missing required fields" in p for p in al.validate([e]))


def test_missing_review_condition_rejected() -> None:
    e = _entry()
    del e["review_condition"]
    assert any("missing required fields" in p for p in al.validate([e]))


def test_duplicate_entries_rejected() -> None:
    e = _entry()
    problems = al.validate([e, copy.deepcopy(e)])
    assert any("duplicate allowlist_id" in p for p in problems)


def test_writer_against_immutable_store_rejected() -> None:
    problems = al.validate([_entry(store_id="static.legal_documents", access_modes=["REWRITE"])])
    assert any("immutable store" in p for p in problems)


def test_production_writer_filed_as_fixture_rejected() -> None:
    problems = al.validate([_entry(production_relevance="FIXTURE")])
    assert any("filed as FIXTURE" in p for p in problems)


def test_stale_entry_rejected(findings) -> None:
    """The entry survives; the code it excused does not."""
    stale = _entry(
        allowlist_id="stale.one",
        file="app/billing/gst_invoice.py",
        line_or_symbol="_SYMBOL_THAT_DOES_NOT_EXIST",
    )
    problems = al.validate([stale], findings=findings)
    assert any("STALE" in p for p in problems)


def test_operation_mismatch_rejected(findings) -> None:
    """Declaring READ over code that appends must not pass.

    This check found real mismatches in the first draft of the shipped
    allowlist — parent-directory CREATE calls that the entries had not
    declared — which is precisely why it exists.
    """
    narrow = _entry(allowlist_id="narrow", access_modes=["READ"])
    problems = al.validate([narrow], findings=findings)
    assert any("operation mismatch" in p for p in problems)


def test_missing_file_rejected() -> None:
    problems = al.validate([_entry(file="app/gone/away.py")])
    assert any("no longer exists" in p for p in problems)


# --------------------------------------------------------------- gate shape


def test_coverage_counters_are_derived(findings) -> None:
    cov = al.coverage(findings)
    assert set(cov) >= {
        "undeclared_mutable_paths",
        "ambiguous_mutable_paths",
        "declared_legacy_writes",
        "declared_legacy_reads",
    }
    for v in cov.values():
        assert isinstance(v, int)


def test_declared_entries_actually_reclassify_findings(findings) -> None:
    """Anti-vacuity: the allowlist must CHANGE the outcome.

    Without this, every rejection test above could pass against an allowlist
    that the scanner ignores entirely.
    """
    with_list = al.coverage(findings)
    without = al.coverage(scan.scan_repo(_REPO, allowlist=[]))
    assert with_list["declared_legacy_writes"] > 0
    assert without["declared_legacy_writes"] == 0
    assert with_list["undeclared_mutable_paths"] < without["undeclared_mutable_paths"]


def test_store_manifest_still_validates() -> None:
    """Regression: the scanner batch must not disturb store accounting."""
    assert manifest.validate() == []
    counts = manifest.counts()
    # The scanner batch is discovery + declaration only. If either number moves
    # it means a store family was silently added or a blocker silently dropped,
    # which must happen through an evidence-backed manifest edit, not as a
    # side effect of building a scanner.
    assert counts["unique_families"] == 22
    assert counts["deployment_blockers"] == 16
