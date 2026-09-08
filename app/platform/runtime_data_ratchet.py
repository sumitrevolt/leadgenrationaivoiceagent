"""Monotonic debt ratchet for the mutable-path scanner.

The scanner made existing debt VISIBLE. Visibility is not enforcement: with
counts merely printed, a new undeclared writer could land and CI would still be
green. Saying "the backlog cannot grow quietly" while only printing it was an
overclaim, and this module is what makes the claim true.

Two ideas, kept strictly apart:

  CONTROLLED ALLOWLIST -- the finding is understood: mapped to a store family,
  access modes verified, owner domain and migration wave known, review
  condition written down.

  KNOWN_UNRESOLVED_DEBT -- the finding merely EXISTED when the baseline was
  frozen. CI tolerates it. Nothing about it has been reviewed, and it can never
  be cited as evidence that the scanner work is finished.

Calling the second one "allowed" would quietly convert 691 unexamined writers
into 691 approvals, which is the failure this whole workstream exists to avoid.

Counts alone are not a baseline: one dangerous new writer plus one unrelated
removal leaves the total unchanged. So the comparison is over FINGERPRINTS.
"""

from __future__ import annotations

from typing import Any

from app.platform import runtime_data_baseline as _baseline
from app.platform import runtime_data_baseline_changes as _changes
from app.platform import runtime_data_scan as _scan

# Classifications that represent unresolved debt.
UNRESOLVED = frozenset({_scan.UNDECLARED_MUTABLE_PATH, _scan.AMBIGUOUS_REQUIRES_REVIEW})

# Classification transitions that are REGRESSIONS regardless of counts.
_RESOLVED_RANK = {
    _scan.CANONICAL_RUNTIME_PATH: 3,
    _scan.DECLARED_LEGACY_READ: 2,
    _scan.DECLARED_LEGACY_WRITE: 2,
    _scan.FIXTURE_ONLY: 2,
    _scan.STATIC_ASSET: 2,
    _scan.GENERATED_ARTIFACT: 2,
    _scan.REBUILDABLE_CACHE: 2,
    _scan.DOCUMENTATION_EXAMPLE: 2,
    _scan.AMBIGUOUS_REQUIRES_REVIEW: 1,
    _scan.UNDECLARED_MUTABLE_PATH: 0,
}


def _identity(f: dict[str, Any]) -> str:
    """Identity WITHOUT classification, so a transition is visible as the same
    finding changing state rather than as one disappearing and another
    appearing."""
    return "|".join(
        [f["file"], str(f.get("symbol") or ""), f["operation"], _scan.normalized_path(f)]
    )


def evaluate(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare current findings against the frozen baseline.

    Returns a structured verdict; never raises.
    """
    base = {e["finding_fingerprint"]: e for e in _baseline.ENTRIES}
    base_by_identity = {e["identity"]: e for e in _baseline.ENTRIES}

    current_fps = {_scan.fingerprint(f): f for f in findings}
    current_ids = {_identity(f): f for f in findings}

    new_unresolved: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []

    for f in findings:
        fp = _scan.fingerprint(f)
        ident = _identity(f)
        prior = base_by_identity.get(ident)

        if f["classification"] in UNRESOLVED and fp not in base:
            # Unresolved AND not in the frozen inventory => genuinely new debt.
            new_unresolved.append(f)

        if prior is not None:
            was = _RESOLVED_RANK.get(prior["classification"], 0)
            now = _RESOLVED_RANK.get(f["classification"], 0)
            if now < was:
                regressions.append(
                    {
                        "file": f["file"],
                        "symbol": f.get("symbol"),
                        "operation": f["operation"],
                        "from": prior["classification"],
                        "to": f["classification"],
                        "line": f["line"],
                    }
                )
            if prior.get("store_id") and not f.get("store_id"):
                regressions.append(
                    {
                        "file": f["file"],
                        "symbol": f.get("symbol"),
                        "operation": f["operation"],
                        "from": f"store={prior['store_id']}",
                        "to": "store=<lost>",
                        "line": f["line"],
                    }
                )

    removed = [
        e for fp, e in base.items() if fp not in current_fps and e["identity"] not in current_ids
    ]
    resolved = [
        f
        for ident, f in current_ids.items()
        if ident in base_by_identity
        and base_by_identity[ident]["classification"] in UNRESOLVED
        and f["classification"] not in UNRESOLVED
    ]

    # Baseline expansions must be accounted for, not merely absorbed. Saying
    # "new unresolved = 0" right after replacing the baseline describes the
    # state AFTER accepting the expansion — which is exactly the impression I
    # gave when it went 691 -> 881.
    governed, gov_detail = _changes.expansion_is_governed(len(base))
    change_problems = _changes.validate()

    return {
        "baseline_fingerprints": len(base),
        "baseline_governed": governed,
        "baseline_governance_detail": gov_detail,
        "change_record_problems": change_problems,
        "scanner_engine_version": _changes.SCANNER_ENGINE_VERSION,
        "current_findings": len(findings),
        "new_unresolved": new_unresolved,
        "regressions": regressions,
        "removed": removed,
        "resolved": resolved,
        "unresolved_now": sum(1 for f in findings if f["classification"] in UNRESOLVED),
        "ok": (not new_unresolved and not regressions and governed and not change_problems),
    }


def format_failures(verdict: dict[str, Any], limit: int = 30) -> list[str]:
    """Actionable lines. A gate that only says FAILED teaches people to ignore it."""
    out: list[str] = []
    for f in verdict["new_unresolved"][:limit]:
        out.append(
            "NEW_{}\n  file: {}\n  symbol: {}\n  operation: {}\n  path: {}\n"
            "  action: classify the store (allowlist entry with owner, migration_tier, "
            "review_condition) or provide an evidence-backed exclusion".format(
                f["classification"],
                f["file"],
                f.get("symbol") or "<literal>",
                f["operation"],
                _scan.normalized_path(f)[:110],
            )
        )
    if not verdict.get("baseline_governed", True):
        out.append(
            "UNGOVERNED_BASELINE_EXPANSION\n  detail: {}\n"
            "  action: add a reviewed record to runtime_data_baseline_changes.CHANGES "
            "naming the detector change and the exact added fingerprints. Regenerating "
            "the baseline is not the same as accounting for it.".format(
                verdict.get("baseline_governance_detail")
            )
        )
    for p in verdict.get("change_record_problems", []):
        out.append(f"BASELINE_CHANGE_RECORD_INVALID\n  {p}")
    for r in verdict["regressions"][:limit]:
        out.append(
            "CLASSIFICATION_REGRESSION\n  file: {}:{}\n  symbol: {}\n  operation: {}\n"
            "  from: {}\n  to: {}\n  action: restore the prior classification or justify "
            "the change with evidence".format(
                r["file"],
                r["line"],
                r.get("symbol") or "<literal>",
                r["operation"],
                r["from"],
                r["to"],
            )
        )
    return out


__all__ = ["UNRESOLVED", "evaluate", "format_failures"]
