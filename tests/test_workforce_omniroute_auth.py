"""Credential-boundary contracts for the local workforce OmniRoute client."""

from __future__ import annotations

import inspect
import json
import subprocess

import scripts.autonomous_workforce_orchestrator as orchestrator


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
