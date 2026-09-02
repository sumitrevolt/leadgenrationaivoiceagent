"""H.4 — dr_health + litellm_costs probes.

These probes are the OPERATIONAL eyes on platform survival + margin. The
tests assert each one degrades gracefully when its dependency is absent
(NEUTRAL/INERT, never raise) and produces the correct status band when the
dependency responds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.platform import dr_health, litellm_costs


# --------------------------------------------------------------------------- #
# dr_health
# --------------------------------------------------------------------------- #
def test_dr_unconfigured_is_neutral(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DR_REPLICA_URL", raising=False)
    out = dr_health.probe()
    assert out["configured"] is False
    assert out["status"] == "NEUTRAL"


def test_dr_unreachable_returns_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """A configured but unreachable replica is a FAIL, not a NEUTRAL — silent
    'DR off' is the exact gap the audit flagged. We must NOT mask it."""
    monkeypatch.setenv("DR_REPLICA_URL", "postgres://nobody@127.0.0.1:1/db")
    out = dr_health.probe()
    assert out["configured"] is True
    assert out["status"] == "FAIL"


def test_dr_lag_bands(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force a known lag value through the connection layer to assert the
    OK/WARN/FAIL bands. We monkeypatch the psycopg2 module that probe() uses."""
    monkeypatch.setenv("DR_REPLICA_URL", "postgres://x@x/x")
    monkeypatch.setenv("DR_LAG_WARN_S", "60")
    monkeypatch.setenv("DR_LAG_FAIL_S", "600")

    class _Cursor:
        def __init__(self, value):
            self._v = value

        def execute(self, *a, **kw):
            pass

        def fetchone(self):
            return (self._v,)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    class _Conn:
        def __init__(self, value):
            self._v = value

        def cursor(self):
            return _Cursor(self._v)

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    class _PG:
        def __init__(self, val):
            self.val = val

        def connect(self, *a, **kw):
            return _Conn(self.val)

    import sys

    # Lag 0.5s -> OK
    monkeypatch.setitem(sys.modules, "psycopg2", _PG(0.5))
    assert dr_health.probe()["status"] == "OK"
    # Lag 120s -> WARN
    monkeypatch.setitem(sys.modules, "psycopg2", _PG(120.0))
    assert dr_health.probe()["status"] == "WARN"
    # Lag 800s -> FAIL
    monkeypatch.setitem(sys.modules, "psycopg2", _PG(800.0))
    assert dr_health.probe()["status"] == "FAIL"
    # NULL (replica idle) -> OK with note
    monkeypatch.setitem(sys.modules, "psycopg2", _PG(None))
    out = dr_health.probe()
    assert out["status"] == "OK"
    assert "idle" in out["summary"]


# --------------------------------------------------------------------------- #
# litellm_costs
# --------------------------------------------------------------------------- #
async def test_enabled_requires_both_flag_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LITELLM_COSTS", raising=False)
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    assert litellm_costs.enabled() is False

    monkeypatch.setenv("LITELLM_COSTS", "1")
    assert litellm_costs.enabled() is False  # still no key

    monkeypatch.setenv("LITELLM_MASTER_KEY", "secret")
    assert litellm_costs.enabled() is True


async def test_gateway_health_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LITELLM_GATEWAY_URL", raising=False)
    out = await litellm_costs.gateway_health()
    assert out["available"] is False
    assert "unset" in out["reason"]


async def test_per_key_spend_inert_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LITELLM_COSTS", raising=False)
    out = await litellm_costs.per_key_spend()
    assert out["available"] is False


async def test_per_key_spend_aggregates_and_maps_clients(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(litellm_costs, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(litellm_costs, "_KEYMAP_PATH", tmp_path / "keymap.jsonl")
    monkeypatch.setenv("LITELLM_COSTS", "1")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "test")
    monkeypatch.setenv("LITELLM_GATEWAY_URL", "http://litellm:4000")
    # Populate keymap
    (tmp_path / "keymap.jsonl").write_text(
        '{"vkey":"sk-aaa","client_id":"client_a","niche":"salon"}\n'
        '{"vkey":"sk-bbb","client_id":"client_b","niche":"clinic"}\n'
    )

    class _Resp:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {
                "data": [
                    {"key": "sk-aaa", "spend": 1.50, "call_count": 12},
                    {"key": "sk-bbb", "spend": 0.25, "call_count": 4},
                    {"key": "sk-unmapped", "spend": 0.10, "call_count": 1},
                ]
            }

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, **kw):  # noqa: ANN001
            return _Resp()

    import httpx as _httpx

    monkeypatch.setattr(_httpx, "AsyncClient", lambda *a, **kw: _Client())

    out = await litellm_costs.per_key_spend(hours=24)
    assert out["available"] is True
    assert len(out["spend"]) == 3
    assert out["total_usd"] == pytest.approx(1.85)
    a = next(r for r in out["spend"] if r["client_id"] == "client_a")
    assert a["spend_usd"] == pytest.approx(1.50)
    assert a["niche"] == "salon"
    # Unmapped key still surfaces (client_id None)
    u = next(r for r in out["spend"] if r["client_id"] is None)
    assert u["spend_usd"] == pytest.approx(0.10)


async def test_per_key_spend_gateway_5xx_inert(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITELLM_COSTS", "1")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "test")
    monkeypatch.setenv("LITELLM_GATEWAY_URL", "http://litellm:4000")

    class _Resp:
        status_code = 503

        def json(self) -> dict:
            return {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, *a, **kw):
            return _Resp()

    import httpx as _httpx

    monkeypatch.setattr(_httpx, "AsyncClient", lambda *a, **kw: _Client())
    out = await litellm_costs.per_key_spend()
    assert out["available"] is False
    assert "503" in out["reason"]


async def test_margin_alerts_flags_negative_margin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Client with $5 LLM spend vs $2 revenue -> flagged as margin-negative."""
    monkeypatch.setattr(litellm_costs, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(litellm_costs, "_KEYMAP_PATH", tmp_path / "keymap.jsonl")
    monkeypatch.setenv("LITELLM_COSTS", "1")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "x")
    monkeypatch.setenv("LITELLM_GATEWAY_URL", "http://x")
    (tmp_path / "keymap.jsonl").write_text(
        '{"vkey":"sk-aaa","client_id":"loss_maker"}\n{"vkey":"sk-bbb","client_id":"profitable"}\n'
    )

    class _Resp:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {
                "data": [
                    {"key": "sk-aaa", "spend": 5.0, "call_count": 50},
                    {"key": "sk-bbb", "spend": 1.0, "call_count": 10},
                ]
            }

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, *a, **kw):
            return _Resp()

    import httpx as _httpx

    monkeypatch.setattr(_httpx, "AsyncClient", lambda *a, **kw: _Client())

    out = await litellm_costs.margin_alerts(
        revenue_per_client_usd={"loss_maker": 2.0, "profitable": 100.0}
    )
    assert out["available"] is True
    flagged = out["flagged"]
    assert len(flagged) == 1
    assert flagged[0]["client_id"] == "loss_maker"
    assert flagged[0]["ratio"] == 2.5  # 5/2
