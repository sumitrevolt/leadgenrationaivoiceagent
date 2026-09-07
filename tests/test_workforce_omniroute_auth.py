"""Credential-boundary contracts for the local workforce OmniRoute client."""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from types import SimpleNamespace

import scripts.autonomous_workforce_orchestrator as orchestrator


def test_failed_primary_and_helper_never_claim_recovery(monkeypatch):
    events = []
    monkeypatch.setattr(orchestrator, "execute_omniroute_query", lambda *a, **k: (False, "unavailable"))
    monkeypatch.setattr(orchestrator, "log", lambda *a: None)
    monkeypatch.setattr(orchestrator, "recent_healing_events", [])
    monkeypatch.setattr(orchestrator, "agent_status_cache", {})
    monkeypatch.setitem(sys.modules, "app.platform.team", SimpleNamespace(log_event=lambda *a: events.append(a)))
    result = orchestrator.run_single_agent(orchestrator.AGENT_CONFIGS[0], 1)
    assert result["status"] == "BLOCKED"
    assert orchestrator.recent_healing_events[-1]["status"] == "FAILED"
    assert events[-1][3] == "failed"
    assert events[-1][4]["healed"] is False


def test_combo_key_resolver_never_extracts_keys_from_gateway_storage(monkeypatch):
    orchestrator._COMBO_KEY_CACHE.clear()
    monkeypatch.delenv("OMNIROUTE_API_KEY", raising=False)
    monkeypatch.delenv("OMNIROUTE_KEY_LEADSGEN_COMBO_1", raising=False)

    calls: list[bool] = []

    def forbidden(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("gateway credential extraction is forbidden")

    monkeypatch.setattr(subprocess, "check_output", forbidden)

    assert orchestrator._resolve_combo_key("leadsgen combo 1") == ""
    assert calls == []


def test_combo_key_resolver_uses_explicit_per_combo_env(monkeypatch):
    orchestrator._COMBO_KEY_CACHE.clear()
    marker = "".join(("configured", "-presence"))
    monkeypatch.setenv("OMNIROUTE_KEY_LEADSGEN_COMBO_1", marker)

    assert orchestrator._resolve_combo_key("leadsgen combo 1") == marker


def test_workforce_batch_defaults_to_four_parallel_workers():
    assert inspect.signature(orchestrator.run_continuous_batch).parameters[
        "workers_count"
    ].default == 4


def test_admission_busy_retries_once_after_two_seconds(monkeypatch):
    orchestrator._COMBO_KEY_CACHE.clear()
    monkeypatch.setenv("OMNIROUTE_KEY_LEADSGEN_COMBO_1", "configured-presence")
    attempts: list[bool] = []
    sleeps: list[int] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": "OK"}}]}
            ).encode()

    def urlopen(*_args, **_kwargs):
        attempts.append(True)
        if len(attempts) == 1:
            raise RuntimeError("HTTP Error 503: chat_admission_busy")
        return Response()

    monkeypatch.setattr(orchestrator.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(orchestrator.time, "sleep", sleeps.append)

    assert orchestrator.execute_omniroute_query("leadsgen combo 1", "ping") == (
        True,
        "OK",
    )
    assert len(attempts) == 2
    assert sleeps == [2]
