"""Hermetic contract tests for the scheduled OmniRoute supervisor."""

from __future__ import annotations

import scripts.omniroute_autonomous_supervisor as supervisor


def test_supervisor_uses_latency_safe_combo_probe_timeout(monkeypatch):
    calls = []

    def fake_run(script, *args, timeout):
        calls.append((script, args, timeout))
        return 0

    monkeypatch.setattr(supervisor, "_run", fake_run)
    assert supervisor.main() == 0
    assert len(calls) == 2
    for script, args, timeout in calls:
        assert script == supervisor.COMBO or script == supervisor.SELF_HEAL
        if script == supervisor.COMBO:
            assert "--timeout" in args
            assert args[args.index("--timeout") + 1] == "60"
            assert args[args.index("--workers") + 1] == "1"
            assert timeout == 600
