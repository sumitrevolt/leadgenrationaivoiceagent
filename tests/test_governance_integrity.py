#!/usr/bin/env python3
"""Regression tests for canonical governance integrity (ADR-200 / PR #552).

Verifies archive checksums, TypeSafe skill discovery, and that Telegram
secret scanning preserves existing MTProto detection while adding bot-token.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


EXPECTED_DIRECTIVE_SHA256 = "803a4683b94f6b8cf41dccb5cb6da461b3def108c43794585d256f78a5cab6ea"


class TestArchiveChecksum:
    def test_owner_directive_archive_matches_sha256(self) -> None:
        path = ROOT / "docs" / "OWNER_DIRECTIVE_2026-09-22.md"
        assert path.exists(), f"Archive not found: {path}"
        # Use raw bytes (line endings as stored on disk)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == EXPECTED_DIRECTIVE_SHA256, (
            f"Archive SHA-256 mismatch: expected {EXPECTED_DIRECTIVE_SHA256}, got {actual}"
        )


class TestTypeSafeSkillDiscovery:
    def test_typesafe_skill_exists(self) -> None:
        path = ROOT / ".claude" / "skills" / "typesafe-ai" / "SKILL.md"
        assert path.exists(), "TypeSafe skill must exist at canonical path"

    def test_typesafe_skill_mentions_jev_latest(self) -> None:
        skill = (ROOT / ".claude" / "skills" / "typesafe-ai" / "SKILL.md").read_text()
        assert "Jev" in skill or "jev" in skill.lower(), "TypeSafe skill must reference Jev model"

    def test_typesafe_status_script_exists(self) -> None:
        path = ROOT / "scripts" / "typesafe_status.py"
        assert path.exists(), "TypeSafe status probe script must exist"

    def test_typesafe_executor_module_exists(self) -> None:
        path = ROOT / "app" / "platform" / "typesafe_executor.py"
        assert path.exists(), "TypeSafe executor module must exist"


class TestTelegramSecretScanning:
    def test_mtproto_api_hash_detection_preserved(self) -> None:
        """Existing MTProto api_hash/session_string detection must still work."""
        from scripts.check_secrets import PATTERNS
        labels = [label for label, _ in PATTERNS]
        assert any("api_hash" in l or "session_string" in l or "MTProto" in l for l in labels), (
            f"MTProto credential detection missing. Labels: {labels}"
        )

    def test_bot_token_shape_detection_added(self) -> None:
        """Bot-token shape detection must be present."""
        from scripts.check_secrets import PATTERNS
        labels = [label for label, _ in PATTERNS]
        assert any("bot-token" in l.lower() or "bot token" in l.lower() for l in labels), (
            f"Bot-token shape detection missing. Labels: {labels}"
        )

    def test_scanner_flags_bot_token_in_runbook(self) -> None:
        """Verify the bot-token pattern catches synthetic tokens."""
        import re
        # Find the bot-token pattern
        from scripts.check_secrets import PATTERNS
        bot_pat = None
        for label, pat in PATTERNS:
            if "bot-token" in label.lower():
                bot_pat = pat
                break
        assert bot_pat is not None, "bot-token pattern not found"

        # Synthetic token (built by concatenation to avoid self-flagging)
        synthetic = "8123456789:AA" + "Hk7Qm2Xp9Rt4Vb6Nz1Ld8Wy3Cs5Fg0Ju2"
        m = bot_pat.search(f"TELEGRAM_BOT_TOKEN={synthetic}")
        assert m is not None, "Bot-token pattern must catch synthetic token in config"

    def test_scanner_does_not_flag_placeholder(self) -> None:
        """Placeholder tokens must NOT be flagged."""
        from scripts.check_secrets import PATTERNS, PLACEHOLDER
        bot_pat = None
        for label, pat in PATTERNS:
            if "bot-token" in label.lower():
                bot_pat = pat
                break
        assert bot_pat is not None

        # Placeholder should not match the pattern OR should be caught by PLACEHOLDER
        placeholder = "TELEGRAM_BOT_TOKEN=your-bot-token-here"
        m = bot_pat.search(placeholder)
        if m is not None:
            # If matched, the placeholder check must catch it
            assert PLACEHOLDER.search(placeholder), (
                "Bot-token pattern matched placeholder but PLACEHOLDER filter didn't catch it"
            )
