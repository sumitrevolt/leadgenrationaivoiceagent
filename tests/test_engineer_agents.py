"""F.5 engineer agents — disabled / signal-based / disabled-vs-data behaviour.

Audit Section H said: "add an engineer agent only if it creates MEASURABLE
operational leverage." These tests assert each agent's score actually MOVES
in response to its signals — a score that always returns 100 is no signal at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.platform import engineer_agents as ea


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ea, "_DATA_DIR", tmp_path)
    # Default: all engineer flags off (lets the disabled-case tests start clean)
    for _flag in (
        "SRE_AGENT",
        "FINOPS_AGENT",
        "SECURITY_AGENT",
        "DBRE_AGENT",
        "DEPS_AGENT",
        "DATA_INTEGRITY_AGENT",
    ):
        monkeypatch.delenv(_flag, raising=False)


# --------------------------------------------------------------------------- #
# Disabled state (project ethos: INERT when flag unset)
# --------------------------------------------------------------------------- #
def test_sre_disabled_when_flag_unset() -> None:
    out = ea.run_sre()
    assert out["status"] == "disabled"
    assert out["score"] is None


def test_finops_disabled_when_flag_unset() -> None:
    out = ea.run_finops()
    assert out["status"] == "disabled"


def test_security_disabled_when_flag_unset() -> None:
    out = ea.run_security()
    assert out["status"] == "disabled"


# --------------------------------------------------------------------------- #
# Pranav — SRE / Reliability
# --------------------------------------------------------------------------- #
def _stub_psutil_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the capacity sub-score to neutral-50 so other signals are testable
    deterministically. Without this the test-host CPU load contaminates the
    expected score (test flakes under parallel test runs / high system load).

    Implementation: drop a sentinel into sys.modules that raises on attribute
    access — `import psutil` succeeds but `psutil.cpu_percent(...)` blows up,
    landing in the agent's `except Exception` -> neutral-50 fallback."""
    import sys

    class _BombPsutil:
        def __getattr__(self, _name: str):  # noqa: ANN001
            raise RuntimeError("psutil pinned-out for test isolation")

    monkeypatch.setitem(sys.modules, "psutil", _BombPsutil())


def test_sre_no_signals_returns_neutral(monkeypatch: pytest.MonkeyPatch) -> None:
    """No backup log, no heartbeat -> three neutral-50 sub-scores, NOT zero."""
    monkeypatch.setenv("SRE_AGENT", "1")
    _stub_psutil_unavailable(monkeypatch)
    out = ea.run_sre()
    assert out["status"] == "ok"
    assert out["score"] is not None
    # All three signals neutral (50/50/50) -> exactly 50
    assert out["score"] == pytest.approx(50.0)
    assert any("backup log" in a.lower() for a in out["actions"])


def test_sre_score_lifts_on_fresh_backup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Fresh backup log SHOULD lift the score vs no-signals baseline."""
    monkeypatch.setenv("SRE_AGENT", "1")
    _stub_psutil_unavailable(monkeypatch)
    base = ea.run_sre()["score"]
    (tmp_path / "pg_backup.log").write_text("ok\n", encoding="utf-8")
    after = ea.run_sre()["score"]
    # Fresh backup contributes 100, others stay neutral 50 -> (100+50+50)/3 ≈ 66.7
    assert after > base
    assert after > 60  # fresh backup is a real positive signal


def test_sre_score_drops_on_stale_backup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Stale (>48h) backup should NOT score the same as fresh one."""
    import os
    import time

    monkeypatch.setenv("SRE_AGENT", "1")
    _stub_psutil_unavailable(monkeypatch)
    p = tmp_path / "pg_backup.log"
    p.write_text("ok\n", encoding="utf-8")
    fresh = ea.run_sre()["score"]
    # Backdate the file 72h to trigger the stale branch
    old = time.time() - 72 * 3600
    os.utime(p, (old, old))
    stale = ea.run_sre()["score"]
    assert stale < fresh  # measurable signal — score actually moves


# --------------------------------------------------------------------------- #
# Vidya — FinOps / Cost
# --------------------------------------------------------------------------- #
def test_finops_zero_load_high_score(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINOPS_AGENT", "1")
    out = ea.run_finops()
    assert out["score"] is not None
    assert out["kpis"]["today_llm_calls"] == 0
    assert out["score"] >= 80  # no spend = max margin score


def test_finops_runaway_tokens_drop_score(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """5M+ tokens/day should drop the margin score (TPD-eating signal)."""
    import time as _t

    monkeypatch.setenv("FINOPS_AGENT", "1")
    today = _t.strftime("%Y-%m-%d")
    log = tmp_path / "llm_metrics.jsonl"
    # 6M tokens across 6000 calls, all today
    log.write_text(
        "\n".join(
            json.dumps({"ts": today + "T12:00:00", "tokens": 1000, "provider": "groq"})
            for _ in range(6000)
        ),
        encoding="utf-8",
    )
    out = ea.run_finops()
    assert out["kpis"]["today_llm_tokens"] >= 5_000_000
    assert out["score"] < 50  # runaway throughput penalized
    assert any("token throughput" in a.lower() or "tpd" in a.lower() for a in out["actions"])


def test_finops_flags_litellm_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINOPS_AGENT", "1")
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    out = ea.run_finops()
    assert out["kpis"]["litellm_active"] is False
    assert any("litellm" in a.lower() for a in out["actions"])


# --------------------------------------------------------------------------- #
# Arnav — Security / Compliance
# --------------------------------------------------------------------------- #
def test_security_unarmed_secrets_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECURITY_AGENT", "1")
    # All webhook secrets unset (Razorpay + Twilio removed — whatsapp only now;
    # Vobiz doesn't sign its callbacks so there's nothing to arm for it)
    for k in (
        "WHATSAPP_APP_SECRET",
        "TURNSTILE_SECRET_KEY",
        "GRIEVANCE_OFFICER_EMAIL",
    ):
        monkeypatch.delenv(k, raising=False)
    out = ea.run_security()
    assert out["kpis"]["webhook_secrets_armed"] == {
        "whatsapp": False,
    }
    actions = " ".join(out["actions"]).lower()
    assert "turnstile" in actions


def test_security_armed_secrets_lift_score(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECURITY_AGENT", "1")
    base = ea.run_security()["score"]
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "x")
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "x")
    monkeypatch.setenv("GRIEVANCE_OFFICER_EMAIL", "office@leadsgenai.in")
    armed = ea.run_security()["score"]
    assert armed > base  # measurable signal


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #
def test_unknown_role_returns_structured_error() -> None:
    out = ea.run("metaverse_engineer")
    assert out["status"] == "unknown_role"
    assert out["score"] is None


def test_run_all_returns_all_six(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    import app.models.base as _base

    for _flag in (
        "SRE_AGENT",
        "FINOPS_AGENT",
        "SECURITY_AGENT",
        "DBRE_AGENT",
        "DEPS_AGENT",
        "DATA_INTEGRITY_AGENT",
    ):
        monkeypatch.setenv(_flag, "1")
    # Keep run_all fast + hermetic: no real subprocess / DB.
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no")))
    monkeypatch.setattr(
        _base, "get_db_session", lambda: (_ for _ in ()).throw(RuntimeError("no db"))
    )
    out = ea.run_all()
    assert set(out) == {"sre", "finops", "security", "dbre", "deps", "dataquality"}
    assert out["sre"]["agent"] == "pranav"
    assert out["dbre"]["agent"] == "kabir"
    assert out["deps"]["agent"] == "aryan"
    assert out["dataquality"]["agent"] == "diya"


# --------------------------------------------------------------------------- #
# Council 2026-06-25 — Kabir (DBRE) / Aryan (deps) / Diya (data-integrity)
# --------------------------------------------------------------------------- #
def test_new_engineers_disabled_when_flag_unset() -> None:
    assert ea.run_dbre()["status"] == "disabled"
    assert ea.run_deps()["status"] == "disabled"
    assert ea.run_dataquality()["status"] == "disabled"


def test_dbre_db_unreachable_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """DB not configured/reachable -> neutral 'ok' result, never raises."""
    import app.models.base as _base

    monkeypatch.setenv("DBRE_AGENT", "1")
    monkeypatch.setattr(
        _base, "get_db_session", lambda: (_ for _ in ()).throw(RuntimeError("no db"))
    )
    out = ea.run_dbre()
    assert out["status"] == "ok"
    assert out["score"] is None
    assert "unavailable" in out["summary"].lower() or "not reachable" in out["summary"].lower()


def test_dbre_non_postgres_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    """SQLite rollback-mode -> pg checks skipped (not a failure)."""
    from contextlib import contextmanager

    import app.models.base as _base

    monkeypatch.setenv("DBRE_AGENT", "1")

    class _Dialect:
        name = "sqlite"

    class _Bind:
        dialect = _Dialect()

    class _DB:
        def get_bind(self):
            return _Bind()

    @contextmanager
    def _fake():
        yield _DB()

    monkeypatch.setattr(_base, "get_db_session", _fake)
    out = ea.run_dbre()
    assert out["status"] == "ok"
    assert out["score"] is None
    assert "not postgres" in out["summary"].lower()


def test_dbre_postgres_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Good pg signals (few conns, few unused idx, no slow queries) -> high score."""
    from contextlib import contextmanager

    import app.models.base as _base

    monkeypatch.setenv("DBRE_AGENT", "1")

    class _Dialect:
        name = "postgresql"

    class _Bind:
        dialect = _Dialect()

    class _Res:
        def __init__(self, v):
            self._v = v

        def scalar(self):
            return self._v

    class _DB:
        def get_bind(self):
            return _Bind()

        def execute(self, q):
            s = str(q).lower()
            if "pg_stat_activity" in s:
                return _Res(10)
            if "pg_stat_user_indexes" in s:
                return _Res(2)
            if "pg_stat_statements" in s:
                return _Res(0)
            if "pg_database_size" in s:
                return _Res(500 * 1024 * 1024)
            return _Res(0)

    @contextmanager
    def _fake():
        yield _DB()

    monkeypatch.setattr(_base, "get_db_session", _fake)
    out = ea.run_dbre()
    assert out["status"] == "ok"
    assert out["kpis"]["active_connections"] == 10
    assert out["kpis"]["unused_indexes"] == 2
    assert out["score"] is not None and out["score"] >= 80


def test_deps_unavailable_pip_audit_neutral(monkeypatch: pytest.MonkeyPatch) -> None:
    """pip-audit absent -> known_vulnerabilities None + action, never raises."""
    import subprocess

    monkeypatch.setenv("DEPS_AGENT", "1")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("no"))
    )
    out = ea.run_deps()
    assert out["status"] == "ok"
    assert out["kpis"]["known_vulnerabilities"] is None
    assert any("pip-audit" in a.lower() for a in out["actions"])


def test_deps_counts_cves(monkeypatch: pytest.MonkeyPatch) -> None:
    """Parses pip-audit JSON; CVE count surfaces + drops the supply-chain score."""
    import subprocess

    monkeypatch.setenv("DEPS_AGENT", "1")

    class _Proc:
        returncode = 1
        stdout = json.dumps(
            {
                "dependencies": [
                    {
                        "name": "foo",
                        "version": "1.0",
                        "vulns": [
                            {"id": "CVE-1"},
                            {"id": "CVE-2"},
                            {"id": "CVE-3"},
                            {"id": "CVE-4"},
                        ],
                    }
                ]
            }
        )

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc())
    out = ea.run_deps()
    assert out["kpis"]["known_vulnerabilities"] == 4
    assert any("cve" in a.lower() for a in out["actions"])


def test_dataquality_detects_duplicates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATA_INTEGRITY_AGENT", "1")
    rows = [
        {"phone": "111", "email": "a@x.com"},
        {"phone": "111", "email": "b@x.com"},  # dup phone
        {"phone": "222", "email": "a@x.com"},  # dup email
        {"phone": "", "email": ""},  # missing contact
    ]
    (tmp_path / "prospects.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
    )
    out = ea.run_dataquality()
    assert out["status"] == "ok"
    assert out["kpis"]["total_prospects"] == 4
    assert out["kpis"]["duplicate_phone"] == 1
    assert out["kpis"]["duplicate_email"] == 1
    assert out["kpis"]["missing_contact"] == 1
    assert out["score"] is not None


def test_dataquality_clean_store_high_score(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATA_INTEGRITY_AGENT", "1")
    rows = [{"phone": str(i), "email": f"u{i}@x.com"} for i in range(20)]
    (tmp_path / "prospects.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
    )
    out = ea.run_dataquality()
    assert out["kpis"]["duplicate_phone"] == 0
    assert out["score"] >= 80


def test_dataquality_empty_store_neutral(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_INTEGRITY_AGENT", "1")
    out = ea.run_dataquality()
    assert out["status"] == "ok"
    assert out["kpis"]["total_prospects"] == 0
    assert out["score"] is None


def test_api_recognizes_all_module_roles() -> None:
    """Per-role admin endpoints must accept EVERY role the module defines.
    Regression: dbre/deps/dataquality used to 422 because the API hardcoded only
    sre/finops/security in _VALID / _ROLE_TO_AGENT (cross-path drift)."""
    from app.api import engineer_agents as api_ea

    assert api_ea._VALID == set(ea.roles())
    assert {"dbre", "deps", "dataquality"} <= api_ea._VALID
    for role in ea.roles():
        assert role in api_ea._ROLE_TO_AGENT, f"{role} missing from _ROLE_TO_AGENT (history breaks)"
    assert api_ea._ROLE_TO_AGENT["dbre"] == "kabir"
