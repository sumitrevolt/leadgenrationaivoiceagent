"""Knowledge OS upgrade — contract tests.

Validates the agentic-knowledge layer added in the 2026-08-28 upgrade:
registries parse, classifier is conservative/fail-closed, no secrets in
notebook exports, acceptance scenarios retrieve correctly.

Run: .venv\\Scripts\\python.exe -m pytest tests/test_knowledge_os.py -q
"""
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import validate_knowledge_os as vk  # noqa: E402


class TestRegistries:
    def test_runbook_registry_valid(self):
        errs = vk.validate_runbooks()
        assert errs == [], f"runbook registry errors: {errs}"

    def test_playbook_registry_valid(self):
        errs = vk.validate_playbooks()
        assert errs == [], f"playbook registry errors: {errs}"

    def test_owner_truth_valid(self):
        errs = vk.validate_truth()
        assert errs == [], f"owner truth errors: {errs}"

    def test_runbook_ids_unique_and_classified(self):
        reg = vk.load_yaml(ROOT / "ops" / "runbooks" / "registry.yaml")
        rbs = reg["runbooks"]
        ids = [rb["id"] for rb in rbs]
        assert len(ids) == len(set(ids)), "duplicate runbook ids"
        assert all(rb["class"] in {"GREEN", "AMBER", "RED"} for rb in rbs)
        # conservative: compliance/irreversible must not be GREEN
        red_ish = {"RB-VOICE-001", "RB-VOICE-004", "RB-INFRA-004", "RB-INFRA-006", "RB-INFRA-009", "RB-SALES-006"}
        for rb in rbs:
            if rb["id"] in red_ish:
                assert rb["class"] != "GREEN", f"{rb['id']} must not be GREEN"


class TestSecrets:
    @pytest.mark.parametrize("dirpath", ["notebook_exports", "ops"])
    def test_no_raw_secrets(self, dirpath):
        hits = vk.scan_secrets(ROOT / dirpath)
        assert hits == [], f"secrets found in {dirpath}: {hits}"


class TestAcceptance:
    """Master prompt test scenarios (test A-D)."""

    def _bundle(self, q):
        import knowledge_query as kq
        return kq.build_bundle(q)

    def test_a_busy_line(self):
        b = self._bundle("Calls are failing with Busy Line")
        ids = {rb["id"] for rb in b["runbooks"]}
        assert "RB-VOICE-002" in ids
        assert b["domain"] == "voice"

    def test_b_deploy(self):
        b = self._bundle("Deploy latest safe change")
        ids = {rb["id"] for rb in b["runbooks"]}
        pids = {pb["id"] for pb in b["playbooks"]}
        assert b["domain"] == "infra"
        assert "PB-DEPLOYMENT" in pids
        assert "RB-INFRA-007" in ids or "RB-INFRA-009" in ids

    def test_c_hot_leads(self):
        b = self._bundle("Follow up with hot leads")
        pids = {pb["id"] for pb in b["playbooks"]}
        ids = {rb["id"] for rb in b["runbooks"]}
        assert "PB-SALES" in pids
        assert any(i.startswith("RB-SALES") for i in ids)

    def test_d_swara_outage(self):
        b = self._bundle("What did we learn from the last Swara outage")
        ids = {rb["id"] for rb in b["runbooks"]}
        assert "RB-VOICE-009" in ids


class TestNotebooks:
    def test_bundles_exist(self, tmp_path):
        # Bundles are GENERATED artifacts (not committed). Verify the generator
        # produces them correctly in a throwaway dir rather than asserting
        # pre-generated files live in the repo tree.
        gen = ROOT / "scripts" / "gen_notebook_export.py"
        import subprocess
        env = dict(os.environ)
        # Point notebook-exports output into a temp dir if the generator honors an
        # override; otherwise fall back to asserting the generator runs cleanly.
        try:
            subprocess.run(
                [sys.executable, str(gen), "--out", str(tmp_path)],
                check=True,
                capture_output=True,
                timeout=60,
                env=env,
            )
            required = ["00-owner.md", "01-architecture.md", "04-voice.md", "08-incidents.md", "09-providers.md"]
            for f in required:
                assert (tmp_path / f).exists(), f"generator failed to emit {f}"
        except subprocess.CalledProcessError as e:
            raise AssertionError(
                f"gen_notebook_export.py failed: {e.stderr.decode(errors='replace')[:500]}"
            ) from e

    def test_bundles_have_version_stamp(self, tmp_path):
        gen = ROOT / "scripts" / "gen_notebook_export.py"
        import subprocess
        subprocess.run(
            [sys.executable, str(gen), "--out", str(tmp_path)],
            check=True,
            capture_output=True,
            timeout=60,
        )
        for f in (tmp_path).glob("*.md"):
            text = f.read_text(encoding="utf-8")
            assert re.search(r"Generated: \d{4}-\d{2}-\d{2}", text), f"{f.name} missing timestamp"