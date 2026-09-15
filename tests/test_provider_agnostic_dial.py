"""Locks the 2026-09-15 Tata SmartFlo sole-provider dial path.

Vobiz was REMOVED 2026-09-15. These source-parsing tests guard the silent
failure mode where the queue processor starts on a dead provider, or where
a stale two-provider check leaks back into the codebase.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


class TestMainStartsQueueProcessorForSmartFlo:
    def test_call_processor_gate_is_smartflo_only(self):
        s = _src("app/main.py")
        assert 'if provider == "tata_smartflo":' in s

    def test_main_builds_call_manager_inside_gate(self):
        s = _src("app/main.py")
        gate = s.index('if provider == "tata_smartflo":')
        assert "CallManager(provider=provider)" in s[gate:gate + 900]


class TestFireCallsRouting:
    def test_provider_agnostic_queue_dialer_exists(self):
        s = _src("scripts/fire_calls.py")
        assert "async def fire_queue(" in s
        assert "await fire_queue(prospects, dry_run, call_type, provider)" in s

    def test_queue_dialer_rejects_non_smartflo_providers(self):
        s = _src("scripts/fire_calls.py")
        assert 'if provider != "tata_smartflo":' in s

    def test_dead_exotel_default_is_gone(self):
        s = _src("scripts/fire_calls.py")
        assert 'or "exotel"' not in s

    def test_backcompat_alias_exists(self):
        assert "fire_exotel = fire_queue" in _src("scripts/fire_calls.py")


class TestLoopGateSmartFlo:
    def test_loop_rejects_non_smartflo_provider(self):
        s = _src("scripts/fire_calls_loop.py")
        assert 'fc._provider() != "tata_smartflo"' in s
