"""Contract: PR Factory workflow permissions / triggers / pins (Wave 1)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CI_REPAIR = ROOT / ".github" / "workflows" / "pr-factory-ci-repair.yml"
GATE_A = ROOT / ".github" / "workflows" / "pr-factory-gate-a.yml"

# Public action commits — not credentials
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"  # pragma: allowlist secret
# actions/setup-python v7.0.0
SETUP_PYTHON_SHA = "5fda3b95a4ea91299a34e894583c3862153e4b97"  # pragma: allowlist secret
RUFF_PIN = "ruff==0.16.1"


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _on_block(doc: dict) -> dict:
    # PyYAML parses bare key `on:` as boolean True.
    block = doc.get("on", doc.get(True))
    assert isinstance(block, dict), "workflow on: block missing"
    return block


def _strip_comments(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_ci_repair_is_workflow_dispatch_only():
    on = _on_block(_load(CI_REPAIR))
    assert "workflow_dispatch" in on
    assert "issue_comment" not in on
    assert "pull_request_review_comment" not in on
    assert "pull_request" not in on


def test_ci_repair_permissions_read_only_contents():
    perms = _load(CI_REPAIR)["permissions"]
    assert perms.get("contents") == "read"
    assert perms.get("actions") == "read"
    assert perms.get("pull-requests") == "write"
    assert perms.get("contents") != "write"
    for forbidden in ("packages", "id-token", "deployments", "security-events"):
        assert forbidden not in perms


def test_ci_repair_has_no_coding_agent_write_step():
    text = _strip_comments(CI_REPAIR.read_text(encoding="utf-8"))
    assert "anthropics/claude-code-action@" not in text
    assert "contents: write" not in text
    assert "issue_comment" not in text
    assert "/pr-factory-repair" not in text
    assert f"actions/checkout@{CHECKOUT_SHA}" in text
    assert "persist-credentials: false" in text


def test_ci_repair_job_is_diagnose_not_repair_write():
    jobs = _load(CI_REPAIR)["jobs"]
    assert "diagnose" in jobs
    assert "repair" not in jobs
    steps = jobs["diagnose"]["steps"]
    uses = [s.get("uses", "") for s in steps if isinstance(s, dict)]
    assert any(CHECKOUT_SHA in u for u in uses)
    assert all("claude-code-action" not in u for u in uses)


def test_gate_a_pins_and_non_required_name():
    doc = _load(GATE_A)
    text = GATE_A.read_text(encoding="utf-8")
    body = _strip_comments(text)
    assert "NON-REQUIRED" in text or "non-required" in text
    assert f"actions/checkout@{CHECKOUT_SHA}" in body
    assert f"actions/setup-python@{SETUP_PYTHON_SHA}" in body
    assert "actions/setup-python@v5" not in body
    assert RUFF_PIN in body
    assert "pip install --upgrade pip" not in body
    assert "pip install ruff\n" not in body and "pip install ruff " not in body
    assert doc["jobs"]["gate-a"]["name"] == "Gate A (non-required sketch)"
    uses = [
        s.get("uses", "")
        for s in doc["jobs"]["gate-a"]["steps"]
        if isinstance(s, dict) and s.get("uses")
    ]
    assert any(CHECKOUT_SHA in u for u in uses)
    assert any(SETUP_PYTHON_SHA in u for u in uses)


def test_workflows_do_not_wire_deploy_or_billing_secrets():
    """Structural: no secrets.* refs except GITHUB_TOKEN (deny-list comments OK)."""
    for path in (CI_REPAIR, GATE_A):
        text = _strip_comments(path.read_text(encoding="utf-8"))
        secret_refs = re.findall(r"secrets\.([A-Z0-9_]+)", text)
        for name in secret_refs:
            assert name == "GITHUB_TOKEN", f"{path.name} wires secrets.{name}"
        for needle in (
            "secrets.DEPLOY",
            "secrets.SSH",
            "secrets.STRIPE",
            "secrets.UPI",
        ):
            assert needle not in text
