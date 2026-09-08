"""GSC rank-tracking integration — contract tests (A1: SEO observability).

The module must stay INERT (flag+creds ke bina no-op), never raise, and keep
all data local (data/gsc_*.jsonl). No outbound calls in tests — API service
is mocked. Mirrors test_activation_readiness.py pure-function style.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from app.integrations import gsc

GSC_ENVS = ("GSC_ENABLED", "GSC_SERVICE_ACCOUNT_JSON", "GSC_SITE_URL")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in GSC_ENVS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(gsc, "DAILY_JSONL", os.path.join("data", "gsc_test_daily.jsonl"))
    monkeypatch.setattr(gsc, "STATE_JSON", os.path.join("data", "gsc_test_state.json"))
    for p in (gsc.DAILY_JSONL, gsc.STATE_JSON, gsc.DAILY_JSONL + ".tmp", gsc.STATE_JSON + ".tmp"):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


# --------------------------------------------------------------------------- #
# INERT matrix — no flag, no creds = zero behaviour change
# --------------------------------------------------------------------------- #
def test_enabled_false_when_flag_unset() -> None:
    assert gsc.enabled() is False


def test_enabled_false_when_flag_set_but_no_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GSC_ENABLED", "1")
    assert gsc.enabled() is False


def test_enabled_false_when_creds_path_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GSC_ENABLED", "1")
    monkeypatch.setenv("GSC_SERVICE_ACCOUNT_JSON", "C:/nope/does-not-exist.json")
    assert gsc.enabled() is False


def test_enabled_true_with_creds_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    creds = tmp_path / "sa.json"
    creds.write_text("{}")
    monkeypatch.setenv("GSC_ENABLED", "1")
    monkeypatch.setenv("GSC_SERVICE_ACCOUNT_JSON", str(creds))
    assert gsc.enabled() is True
    assert gsc.site_url() == "sc-domain:leadsgenai.in"


def test_default_site_url() -> None:
    assert gsc.site_url() == "sc-domain:leadsgenai.in"


# --------------------------------------------------------------------------- #
# run_daily — never raises, no-op when disabled
# --------------------------------------------------------------------------- #
def test_run_daily_disabled_noop() -> None:
    r = gsc.run_daily()
    assert r == {"enabled": False}


def test_run_daily_never_raises(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    creds = tmp_path / "sa.json"
    creds.write_text("{}")  # exists → enabled True; invalid creds → service build fails
    monkeypatch.setenv("GSC_ENABLED", "1")
    monkeypatch.setenv("GSC_SERVICE_ACCOUNT_JSON", str(creds))
    r = gsc.run_daily()
    assert r["enabled"] is True
    assert r["ok"] is False


# --------------------------------------------------------------------------- #
# Fetch + persistence — mocked service, tmp data paths
# --------------------------------------------------------------------------- #
def _mock_service() -> SimpleNamespace:
    rows = [
        {"clicks": 10, "impressions": 1000, "ctr": 0.01, "position": 12.4, "keys": ["2026-08-01"]},
        {"clicks": 5, "impressions": 800, "ctr": 0.00625, "position": 9.2, "keys": ["2026-08-02"]},
    ]
    qrows = [
        {"clicks": 8, "impressions": 900, "ctr": 0.0089, "position": 5.1, "keys": ["ac repair"]}
    ]
    prows = [{"clicks": 15, "impressions": 1500, "ctr": 0.01, "position": 7.7, "keys": ["/blog/x"]}]

    def query(siteUrl=None, body=None):
        dim = (body or {}).get("dimensions", ["date"])
        key = dim[0] if dim else "date"
        rows_for = {"date": rows, "query": qrows, "page": prows}.get(key, rows)
        return SimpleNamespace(execute=lambda num_retries=0: {"rows": rows_for})

    return SimpleNamespace(searchanalytics=lambda: SimpleNamespace(query=query))


def test_fetch_aggregate_shape() -> None:
    svc = _mock_service()
    snap = gsc._fetch(svc, gsc.site_url(), 30)
    assert snap["aggregate"]["clicks"] == 15
    assert snap["aggregate"]["impressions"] == 1800
    assert snap["aggregate"]["ctr"] == pytest.approx(15 / 1800)
    assert snap["aggregate"]["position"] == pytest.approx((12.4 * 1000 + 9.2 * 800) / 1800)
    assert len(snap["series"]) == 2
    assert snap["top_queries"][0]["keys"] == ["ac repair"]


def test_run_daily_success_writes_state(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    creds = tmp_path / "sa.json"
    creds.write_text("{}")
    monkeypatch.setenv("GSC_ENABLED", "1")
    monkeypatch.setenv("GSC_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setattr(gsc, "_build_service", _mock_service)
    r = gsc.run_daily()
    assert r["ok"] is True
    assert r["aggregate"]["clicks"] == 15
    state = gsc.latest_state()
    assert state["aggregate"]["clicks"] == 15
    assert len(gsc.trend(30)) == 1
    assert gsc.trend(30)[0]["clicks"] == 15


def test_latest_state_empty_when_never_run() -> None:
    s = gsc.latest_state()
    assert s["fetched_at_utc"] is None
    assert s["aggregate"] == {}


def test_trend_empty_when_no_file() -> None:
    assert gsc.trend(30) == []


def test_run_daily_append_history(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    creds = tmp_path / "sa.json"
    creds.write_text("{}")
    monkeypatch.setenv("GSC_ENABLED", "1")
    monkeypatch.setenv("GSC_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setattr(gsc, "_build_service", _mock_service)
    gsc.run_daily()
    gsc.run_daily()
    assert len(gsc.trend(30)) == 2  # append-only, no dedupe expected
    with open(gsc.DAILY_JSONL, encoding="utf-8") as f:
        assert len(f.readlines()) == 2


def test_trend_ignores_corrupt_lines(tmp_path) -> None:
    os.makedirs(os.path.dirname(gsc.DAILY_JSONL), exist_ok=True)
    with open(gsc.DAILY_JSONL, "w", encoding="utf-8") as f:
        f.write("not-json\n")
        f.write(
            json.dumps({"aggregate": {"clicks": 3, "impressions": 400}, "end_date": "2026-08-11"})
            + "\n"
        )
    rows = gsc.trend(30)
    assert len(rows) == 1
    assert rows[0]["clicks"] == 3
