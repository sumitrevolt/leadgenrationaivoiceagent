"""Contract tests for scripts/typesafe_status.py (TypeSafe local credential truth).

Context (2026-09-18): the TypeSafe integration "worked locally with no config"
only because a LIVE key sat in the module as an `os.getenv(...)` fallback default
(7317f990). 979c2229 removed it — correctly — and the local machine then went
INERT because nothing in the app loads `.env` into `os.environ`.

These tests pin the properties that must survive, in BOTH directions:
  1. state reporting is honest (PRESENT / ABSENT / INVALID / ROTATION_REQUIRED),
  2. the credential VALUE can never appear in output, argv or a report,
  3. activation refuses targets that are not repo-local, non-prod env files.

All keys below are OBVIOUSLY-SYNTHETIC dummies, never real credentials.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "typesafe_status_under_test", ROOT / "scripts" / "typesafe_status.py"
)
assert _SPEC and _SPEC.loader
ts = importlib.util.module_from_spec(_SPEC)
sys.modules["typesafe_status_under_test"] = ts
_SPEC.loader.exec_module(ts)

DUMMY_KEY = "apikey_deadbeefdeadbeefdeadbeefdeadbeef_0123456789abcdef0123456789abcdef01234567"


def _isolated(monkeypatch, tmp_path: Path) -> Path:
    """Point the module at an empty fake repo root so no real .env is consulted."""
    monkeypatch.setattr(ts, "ROOT", tmp_path)
    monkeypatch.setattr(ts, "COMPROMISED_FINGERPRINTS", dict(ts.COMPROMISED_FINGERPRINTS))
    return tmp_path


# --------------------------------------------------------------------------- #
# resolution / state
# --------------------------------------------------------------------------- #


def test_absent_when_no_env_and_no_files(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    res = ts.resolve_key(env={}, env_files=[], diagnostic_files=[])
    assert res.state == ts.STATE_ABSENT
    assert res.source == "none"
    assert res.fingerprint == ""
    assert res.key == ""


def test_env_canonical_wins_and_is_reported(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    res = ts.resolve_key(
        env={ts._CANONICAL_ENV: DUMMY_KEY}, env_files=[], diagnostic_files=[]
    )
    assert res.state == ts.STATE_PRESENT
    assert res.source == f"env:{ts._CANONICAL_ENV}"
    assert res.fingerprint == ts.fingerprint(DUMMY_KEY)


def test_legacy_env_name_still_honoured(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    res = ts.resolve_key(env={ts._LEGACY_ENV: DUMMY_KEY}, env_files=[], diagnostic_files=[])
    assert res.source == f"env:{ts._LEGACY_ENV}"
    assert res.state == ts.STATE_PRESENT


def test_env_file_is_used_by_tooling(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    envf = tmp_path / ".env"
    envf.write_text(f"# comment\n{ts._CANONICAL_ENV}={DUMMY_KEY}\n", encoding="utf-8")
    res = ts.resolve_key(env={}, env_files=[envf], diagnostic_files=[])
    assert res.state == ts.STATE_PRESENT
    assert res.source == str(envf)


def test_parked_diagnostic_file_is_reported_but_not_used(monkeypatch, tmp_path):
    """A key that only lives in .env.production.local is invisible to os.getenv()."""
    _isolated(monkeypatch, tmp_path)
    parked = tmp_path / ".env.production.local"
    parked.write_text(f"{ts._CANONICAL_ENV}={DUMMY_KEY}\n", encoding="utf-8")
    res = ts.resolve_key(env={}, env_files=[], diagnostic_files=[parked])
    assert res.state == ts.STATE_ABSENT
    assert any(".env.production.local" in n for n in res.notes)


def test_rotation_required_for_compromised_fingerprint(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    monkeypatch.setitem(ts.COMPROMISED_FINGERPRINTS, ts.fingerprint(DUMMY_KEY), "test fixture")
    res = ts.resolve_key(env={ts._CANONICAL_ENV: DUMMY_KEY}, env_files=[], diagnostic_files=[])
    assert res.state == ts.STATE_ROTATION
    assert res.key == DUMMY_KEY  # usable internally, never printable


def test_probe_state_mapping():
    res = ts.KeyResolution(state=ts.STATE_PRESENT, fingerprint="abc")
    assert ts.probe_state(res, {"success": True}) == ts.STATE_PRESENT
    assert ts.probe_state(res, {"success": False, "http_status": 401}) == ts.STATE_INVALID
    assert ts.probe_state(res, {"success": False, "http_status": 403}) == ts.STATE_INVALID
    assert ts.probe_state(res, {"success": False, "http_status": 422}) == ts.STATE_INVALID
    assert ts.probe_state(res, {"success": False, "error": "connection reset"}) == ts.STATE_INVALID
    assert ts.probe_state(res, {"success": False}) == ts.STATE_ABSENT


# --------------------------------------------------------------------------- #
# secret hygiene
# --------------------------------------------------------------------------- #


def test_rendered_output_never_contains_the_key(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    res = ts.resolve_key(env={ts._CANONICAL_ENV: DUMMY_KEY}, env_files=[], diagnostic_files=[])
    out = ts.render(res, {"success": True, "http_status": 200, "resolved_model": "jev-1.13.0",
                          "latency_sec": 0.1, "answer_keys": ["a"], "error": ""})
    assert DUMMY_KEY not in out
    assert ts.fingerprint(DUMMY_KEY) in out


def test_public_payload_never_contains_the_key(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    res = ts.resolve_key(env={ts._CANONICAL_ENV: DUMMY_KEY}, env_files=[], diagnostic_files=[])
    assert DUMMY_KEY not in str(res.public())
    assert "key" not in res.public()


def test_script_source_holds_no_credential_literal():
    """The exact failure mode being fixed: no long opaque literal in this file."""
    src = (ROOT / "scripts" / "typesafe_status.py").read_text(encoding="utf-8")
    offenders = [
        m
        for m in re.findall(r"[\"']([A-Za-z0-9_\-]{40,})[\"']", src)
        if not m.startswith(("http", "/", "app.platform", "scripts/"))
    ]
    assert offenders == []


# --------------------------------------------------------------------------- #
# activation guards
# --------------------------------------------------------------------------- #


def test_set_key_refuses_target_outside_fake_repo(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _isolated(monkeypatch, repo)
    outside = tmp_path / "server.env"
    with pytest.raises(SystemExit):
        ts.set_key(outside, DUMMY_KEY)
    assert not outside.exists()


def test_set_key_refuses_production_looking_file(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _isolated(monkeypatch, repo)
    prod = repo / ".env"
    prod.write_text("APP_ENV=production\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        ts.set_key(prod, DUMMY_KEY)
    assert prod.read_text(encoding="utf-8") == "APP_ENV=production\n"


def test_set_key_is_idempotent_backs_up_and_preserves_others(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _isolated(monkeypatch, repo)
    envf = repo / ".env"
    envf.write_text("OTHER=1\nTYPEsafe_API_KEY=old-legacy-value\n", encoding="utf-8")

    backup = ts.set_key(envf, DUMMY_KEY)
    text = envf.read_text(encoding="utf-8")
    assert backup and Path(backup).read_text(encoding="utf-8").startswith("OTHER=1")
    assert "OTHER=1" in text
    assert text.count(ts._CANONICAL_ENV) == 1
    assert "TYPEsafe_API_KEY=old-legacy-value" not in text

    ts.set_key(envf, "apikey_second_value_0000000000000000000000000000000000")
    assert envf.read_text(encoding="utf-8").count(ts._CANONICAL_ENV) == 1
    assert len(list(repo.glob(".env.bak_typesafe_*"))) == 2


def test_set_key_creates_absent_file_without_backup(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _isolated(monkeypatch, repo)
    envf = repo / ".env"
    backup = ts.set_key(envf, DUMMY_KEY)
    assert backup == ""
    assert envf.read_text(encoding="utf-8").strip() == f"{ts._CANONICAL_ENV}={DUMMY_KEY}"


# --------------------------------------------------------------------------- #
# main()
# --------------------------------------------------------------------------- #


def test_main_absent_returns_exit_2(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    monkeypatch.delenv(ts._CANONICAL_ENV, raising=False)
    monkeypatch.delenv(ts._LEGACY_ENV, raising=False)
    assert ts.main([]) == 2


def test_main_probe_success_returns_0_and_reports_model(monkeypatch, tmp_path, capsys):
    _isolated(monkeypatch, tmp_path)
    monkeypatch.setenv(ts._CANONICAL_ENV, DUMMY_KEY)
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "model": "jev-1.13.0",
        "answers": {"reachable": {"type": "noul", "noul": 0.97}},
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }
    with patch("app.platform.typesafe_integration.requests.post", return_value=resp):
        code = ts.main(["--probe"])
    out = capsys.readouterr().out
    assert code == 0
    assert "resolved" in out and "jev-1.13.0" in out
    assert DUMMY_KEY not in out


def test_main_probe_401_returns_exit_3(monkeypatch, tmp_path, capsys):
    _isolated(monkeypatch, tmp_path)
    monkeypatch.setenv(ts._CANONICAL_ENV, DUMMY_KEY)
    resp = MagicMock()
    resp.status_code = 401
    resp.text = '{"detail":{"error_type":"authentication_error"}}'
    with patch("app.platform.typesafe_integration.requests.post", return_value=resp):
        code = ts.main(["--probe", "--json"])
    assert code == 3
    assert DUMMY_KEY not in capsys.readouterr().out


def test_main_rotation_returns_exit_4(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    monkeypatch.setenv(ts._CANONICAL_ENV, DUMMY_KEY)
    monkeypatch.setitem(ts.COMPROMISED_FINGERPRINTS, ts.fingerprint(DUMMY_KEY), "test fixture")
    assert ts.main([]) == 4
