"""A baseline expansion must be accounted for, not merely absorbed.

When the baseline went 691 -> 881 I reported "new unresolved = 0". That was
true and misleading: it describes the state AFTER accepting the expansion. The
190 added fingerprints were real writes that had been invisible, and nothing in
the pipeline forced anyone to say so.

These tests make the accounting mandatory.
"""

from __future__ import annotations

import pathlib

import pytest

from app.platform import runtime_data_allowlist as al
from app.platform import runtime_data_baseline as baseline
from app.platform import runtime_data_baseline_changes as changes
from app.platform import runtime_data_ratchet as ratchet
from app.platform import runtime_data_scan as scan

_REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def current():
    # Full-repo AST walk is GC-heavy; keep it out of the parent pytest process
    # (CI exit-139 cyclic-GC class — 2026-07-28). Child failure still fails CI.
    from tests._runtime_data_scan_subprocess import scan_repo_in_subprocess

    return scan_repo_in_subprocess(_REPO)


def test_change_log_is_coherent() -> None:
    problems = changes.validate()
    assert problems == [], "\n  ".join(problems)


def test_committed_baseline_matches_an_approved_record() -> None:
    ok, detail = changes.expansion_is_governed(len(baseline.ENTRIES))
    assert ok, detail


def test_change_record_arithmetic_reconciles() -> None:
    """old + added - removed must equal new, or the record explains nothing."""
    for c in changes.CHANGES:
        assert (
            c["old_baseline_count"] + c["added_fingerprints"] - c["removed_fingerprints"]
            == c["new_baseline_count"]
        ), c["change_id"]


def test_the_local_helper_expansion_stays_recorded() -> None:
    """History is append-only: the 691 -> 881 expansion must never be rewritten.

    This was originally pinned to `changes.latest()`, which quietly meant "the
    most recent record" — so the next legitimate capability change made it fail
    for the wrong reason. Look the record up by id instead: that is the property
    that actually matters and it cannot drift onto a different record.
    """
    rec = next(
        (c for c in changes.CHANGES if c["change_id"] == "bce-2026-07-26-local-helper-inference"),
        None,
    )
    assert rec is not None, "the local-helper expansion record was removed"
    assert rec["old_baseline_count"] == 691
    assert rec["new_baseline_count"] == 881
    assert rec["added_fingerprints"] == 190
    # The cause must name the detector change and the affected compliance files,
    # not just say "scanner improved".
    assert "helper" in rec["reason"].lower()
    assert "app/telephony/consent_ledger.py" in rec["affected_files"]
    assert "app/marketing/wa_campaign_runner.py" in rec["affected_files"]


def test_latest_record_explains_its_own_detector_change() -> None:
    """Whatever the newest record is, it must justify itself — not just exist."""
    rec = changes.latest()
    assert rec is not None
    assert rec["old_scanner_version"] != rec["new_scanner_version"]
    assert len(rec["detector_change"]) > 80, "detector_change must be specific"
    assert rec["affected_files"], "a capability change with no affected files is not evidence"
    assert (
        rec["old_baseline_count"] + rec["added_fingerprints"] - rec["removed_fingerprints"]
        == rec["new_baseline_count"]
    )


def test_scanner_version_must_change_for_an_expansion() -> None:
    """Growth with identical detector semantics is new debt, not better sight.

    This is the rule that stops an ordinary code change from hiding behind a
    scanner-version bump, and stops a real detector fix from being waved
    through without one.
    """
    bad = dict(changes.CHANGES[-1])
    bad["change_id"] = "bad"
    bad["old_scanner_version"] = bad["new_scanner_version"]
    original = changes.CHANGES[:]
    try:
        changes.CHANGES.append(bad)
        problems = changes.validate()
        assert any("scanner version unchanged" in p for p in problems)
    finally:
        changes.CHANGES[:] = original


def test_ungoverned_expansion_fails_the_ratchet(current) -> None:
    """Regenerating the baseline without a matching record must NOT pass."""
    ok, _ = changes.expansion_is_governed(len(baseline.ENTRIES) + 5)
    assert ok is False

    v = ratchet.evaluate(current)
    assert v["baseline_governed"] is True  # current state IS governed
    assert v["ok"] is True

    # Simulate an unaccounted-for regeneration.
    class _Bigger:
        ENTRIES = baseline.ENTRIES + [
            {
                "finding_fingerprint": "f_unaccounted",
                "identity": "app/x.py||APPEND|data/x.jsonl",
                "classification": scan.UNDECLARED_MUTABLE_PATH,
                "store_id": None,
            }
        ]

    original = ratchet._baseline
    try:
        ratchet._baseline = _Bigger  # type: ignore[assignment]
        v2 = ratchet.evaluate(current)
        assert v2["baseline_governed"] is False
        assert v2["ok"] is False
        assert any("UNGOVERNED_BASELINE_EXPANSION" in b for b in ratchet.format_failures(v2))
    finally:
        ratchet._baseline = original


def test_ratchet_reports_scanner_version(current) -> None:
    v = ratchet.evaluate(current)
    assert v["scanner_engine_version"] == changes.SCANNER_ENGINE_VERSION


def test_normal_code_change_still_fails_without_a_record(current) -> None:
    """Two ratchet modes must stay distinct.

    A code change that adds an undeclared writer is NOT a detector improvement,
    and no change record exists for it, so it must fail exactly as before.
    """
    new = {
        "file": "app/newly_added.py",
        "line": 1,
        "symbol": "_STATE",
        "operation": scan.APPEND,
        "path_expression": "os.path.join('data', 'new.jsonl')",
        "resolved_pattern": "os.path.join('data', 'new.jsonl')",
        "classification": scan.UNDECLARED_MUTABLE_PATH,
        "store_id": None,
        "production_relevant": True,
    }
    v = ratchet.evaluate([*current, new])
    assert v["ok"] is False
    assert len(v["new_unresolved"]) == 1


# ------------------------------------------------------------ secret safety


def test_scanner_output_never_serializes_content_arguments() -> None:
    """`p.write_text(secret)` once recorded the SECRET as the path expression."""
    src = (
        "from pathlib import Path\n"
        "_P = Path('data/creds.json')\n"
        "def save():\n"
        "    _P.write_text('sk_live_TOTALLY_SECRET_VALUE')\n"
    )
    findings = scan.scan_python("app/x.py", src)
    blob = repr(findings)
    assert "sk_live_TOTALLY_SECRET_VALUE" not in blob
    assert findings, "the write itself must still be detected"


def test_scanner_output_never_serializes_env_values() -> None:
    src = (
        "import os\n"
        "_P = os.path.join('data', 'x.jsonl')\n"
        "def w():\n"
        "    open(_P, 'a').write(os.environ['API_TOKEN'])\n"
    )
    blob = repr(scan.scan_python("app/x.py", src))
    assert "API_TOKEN" not in blob
