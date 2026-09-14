"""Locks the 2026-09-14 Vobiz -> Tata Smartflo provider-agnostic dial path.

These are deliberately *source-parsing* tests. The failure modes being guarded
against are silent ones — the Redis call-queue processor never starting, or a
stale provider default quietly routing dials at a provider that no longer
exists — and neither is catchable from a behavioural unit test without standing
up Redis plus a live queue.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


class TestMainStartsQueueProcessorForBothProviders:
    def test_call_processor_gate_includes_tata_smartflo(self):
        s = _src("app/main.py")
        assert 'if provider in ("vobiz", "tata_smartflo"):' in s

    def test_main_still_builds_call_manager_inside_that_gate(self):
        s = _src("app/main.py")
        gate = s.index('if provider in ("vobiz", "tata_smartflo"):')
        assert "CallManager(provider=provider)" in s[gate:gate + 900]


class TestFireCallsRouting:
    def test_non_vobiz_goes_to_provider_agnostic_queue_dialer(self):
        s = _src("scripts/fire_calls.py")
        assert "async def fire_queue(" in s
        assert "await fire_queue(prospects, dry_run, call_type, provider)" in s

    def test_queue_dialer_rejects_unknown_providers_instead_of_dialling(self):
        s = _src("scripts/fire_calls.py")
        assert 'if provider not in ("vobiz", "tata_smartflo"):' in s

    def test_dead_exotel_default_is_gone(self):
        s = _src("scripts/fire_calls.py")
        assert 'or "exotel"' not in s

    def test_backcompat_alias_exists(self):
        assert "fire_exotel = fire_queue" in _src("scripts/fire_calls.py")


class TestLoopAdmitsSmartflo:
    def test_loop_gate_allows_tata_smartflo(self):
        s = _src("scripts/fire_calls_loop.py")
        assert 'not in ("vobiz", "tata_smartflo")' in s
