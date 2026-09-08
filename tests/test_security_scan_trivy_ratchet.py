"""Contract: security-scan.yml keeps the fixable-CRITICAL Trivy ratchet.

Dirty-tree history once tried to swap the fail-closed image scan for a
DEPLOY_ENABLED-gated advisory `:latest` scan. That would weaken compliance.
This test locks the stronger gate that already lives on main:

- repo-scan: ``Fail on fixable CRITICAL`` with ``--exit-code 1``
- image-scan: PR/push build path + explicit immutable ref (never force ``:latest``)
- image-scan: HIGH/CRITICAL fail-closed (``--exit-code 1``)
- no DEPLOY_ENABLED skip that silences image-scan on PRs
- no blanket ``.trivyignore`` / severity suppression introduced as the gate

Does not run Trivy itself — workflow text is the contract under review.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "security-scan.yml"


@pytest.fixture(scope="module")
def workflow_text() -> str:
    assert WORKFLOW.is_file(), f"missing {WORKFLOW}"
    return WORKFLOW.read_text(encoding="utf-8")


def test_repo_scan_fails_on_fixable_critical(workflow_text: str):
    assert "Fail on fixable CRITICAL" in workflow_text
    # Severity CRITICAL + ignore-unfixed + exit-code 1 = only remediable CRITICALs block.
    assert "--severity CRITICAL" in workflow_text
    assert "--ignore-unfixed" in workflow_text
    assert "--exit-code 1" in workflow_text


def test_image_scan_is_fail_closed_high_critical(workflow_text: str):
    assert "Trivy image scan (HIGH/CRITICAL — FAIL CLOSED" in workflow_text or (
        "FAIL CLOSED" in workflow_text and "trivy image" in workflow_text.lower()
    )
    assert "trivy image --severity HIGH,CRITICAL --ignore-unfixed" in workflow_text
    # The fail-closed table step must exit non-zero on findings.
    idx = workflow_text.find("trivy image --severity HIGH,CRITICAL --ignore-unfixed")
    assert idx > 0
    window = workflow_text[idx : idx + 220]
    assert "--exit-code 1" in window


def test_image_scan_builds_or_uses_exact_ref_never_latest_force(workflow_text: str):
    assert "Resolve scan target (exact ref, never :latest)" in workflow_text
    assert "Build image from Dockerfile.lock (PR/push path)" in workflow_text
    assert "Dockerfile.lock" in workflow_text
    # Must not reintroduce the advisory GHCR-:latest shortcut that skipped PRs.
    assert "vars.DEPLOY_ENABLED" not in workflow_text
    assert "Scan latest image (table, advisory)" not in workflow_text
    # Path-filter skip is allowed (merge latency) but the fail-closed build
    # path must still exist for lockfile/Dockerfile PRs and every main push.
    assert "Skip Dockerfile.lock rebuild unless image inputs changed" in workflow_text
    assert "steps.image_needed.outputs.run" in workflow_text


def test_no_blanket_trivyignore_gate_bypass(workflow_text: str):
    """A checked-in ignore file is allowed for time-limited HIGH debt only when
    explicitly reviewed — the CRITICAL enforce step must not point at one."""
    # CRITICAL enforce step should not pass --ignorefile / .trivyignore.
    crit = workflow_text.split("Fail on fixable CRITICAL")[-1].split("TODO(owner)")[0]
    assert "--ignorefile" not in crit
    assert ".trivyignore" not in crit
