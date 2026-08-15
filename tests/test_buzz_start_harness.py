"""Harness relay URL must honour BUZZ_RELAY (local-first 3100 vs hosted)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "buzz_start_harness", REPO / "scripts" / "buzz_start_harness.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["buzz_start_harness"] = mod
    spec.loader.exec_module(mod)
    return mod


harness = _load()


def test_relay_url_defaults_hosted(monkeypatch):
    monkeypatch.delenv("BUZZ_RELAY", raising=False)
    assert harness.relay_url() == harness.HOSTED_RELAY_WS


def test_relay_url_keeps_ws_local(monkeypatch):
    monkeypatch.setenv("BUZZ_RELAY", "ws://127.0.0.1:3100")
    assert harness.relay_url() == "ws://127.0.0.1:3100"


def test_relay_url_maps_https_hosted_to_wss(monkeypatch):
    monkeypatch.setenv("BUZZ_RELAY", "https://leadsgenai.communities.buzz.xyz")
    assert harness.relay_url() == "wss://leadsgenai.communities.buzz.xyz"


def test_relay_url_maps_http_to_ws(monkeypatch):
    monkeypatch.setenv("BUZZ_RELAY", "http://127.0.0.1:3100")
    assert harness.relay_url() == "ws://127.0.0.1:3100"
