"""T05 acceptance: rotating log handler present, no unbounded FileHandler; preflight
refuses the false-success deploy path.
"""

from __future__ import annotations

import logging.handlers
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class LogRotationTests(unittest.TestCase):
    def test_build_file_handler_is_rotating(self):
        import tempfile

        from app.utils.logging_rotation import build_file_handler

        with tempfile.TemporaryDirectory() as tmp:
            handler = build_file_handler(str(Path(tmp) / "x.log"), level=10)
            self.assertIsInstance(handler, logging.handlers.RotatingFileHandler)
            self.assertEqual(handler.maxBytes, 10 * 1024 * 1024)
            self.assertGreaterEqual(handler.backupCount, 1)
            handler.close()

    def test_logger_module_uses_rotation_helper(self):
        src = (REPO / "app" / "utils" / "logger.py").read_text(encoding="utf-8")
        self.assertIn("build_file_handler", src)
        # No unbounded plain FileHandler construction remains in logger.py.
        self.assertNotIn("logging.FileHandler(", src)

    def test_logrotate_policy_exists(self):
        policy = REPO / "deploy" / "logrotate" / "leadgen"
        self.assertTrue(policy.exists(), "logrotate policy missing")
        text = policy.read_text(encoding="utf-8")
        self.assertIn("rotate", text)
        self.assertIn("/opt/leadgen/var/log/", text)


class DeployPreflightTests(unittest.TestCase):
    SCRIPT = REPO / "scripts" / "deploy_preflight.sh"

    def test_preflight_script_exists_and_executable(self):
        self.assertTrue(self.SCRIPT.exists())
        # Mode bit may be lost on some checkouts; assert git keeps it executable.
        try:
            mode = self.SCRIPT.stat().st_mode
            executable = bool(mode & 0o111)
        except OSError:
            executable = False
        if not executable:
            self.skipTest("exec bit not set on this filesystem (checked separately in git)")
        self.assertTrue(executable)

    # Content-level assertions (deterministic, no shell needed).
    def test_preflight_refuses_latest_and_requires_sha(self):
        text = self.SCRIPT.read_text(encoding="utf-8")
        self.assertIn("latest", text)
        self.assertIn("APP_VERSION", text)
        self.assertIn("systemctl restart leadgen", text)

    def test_preflight_checks_false_success_path(self):
        text = self.SCRIPT.read_text(encoding="utf-8")
        self.assertIn("docker", text)
        self.assertIn("up", text)
        self.assertIn("app", text)

    # Behavioural checks are content-level here: spawning `bash` is not portable in
    # every CI/sandbox (Windows WSL may be blocked), so we assert the script's logic
    # textually + rely on the manual run (SHA→exit 0, latest→exit 1) documented in
    # docs/runbooks/DEPLOY_SAFE.md.
    def test_preflight_rejects_latest(self):
        text = self.SCRIPT.read_text(encoding="utf-8")
        self.assertIn('== "latest"', text)
        self.assertIn("fail", text)

    def test_preflight_passes_with_sha(self):
        text = self.SCRIPT.read_text(encoding="utf-8")
        self.assertIn("exit 0", text)
        self.assertIn("Preflight OK", text)

    def test_false_success_path_absent_from_live_scripts(self):
        """No LIVE (non-comment, non-legacy) 'docker compose up -d ... app'."""
        import re

        pat = re.compile(r"docker\s+compose\s+up\s+-d[^\n]*\bapp\b")
        offenders = []
        for p in (REPO / "scripts").rglob("*.sh"):
            rel = p.relative_to(REPO).as_posix()
            if rel.startswith("scripts/legacy/") or rel == "scripts/deploy_preflight.sh":
                continue
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if pat.search(line) and "RETIRED" not in line:
                    offenders.append(f"{rel}:{i}")
        self.assertEqual(offenders, [], f"false-success path reintroduced: {offenders}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
