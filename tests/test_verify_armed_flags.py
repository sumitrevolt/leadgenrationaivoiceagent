"""Tests: scripts/verify_armed_flags.py — deploy post-check armed-state logic.

Covers:
  - _read_env: simple .env parsing (values, quoted, comments skipped)
  - check_env: wizard/summary flag states + cross-gate PROBLEMS/WARNINGS
  - check_manifest: both flags documented
  - exit-code mapping (0 ok / 1 problem / 2 warning)
"""

from __future__ import annotations

import pathlib

import scripts.verify_armed_flags as vaf


def _env_file(tmp_path: pathlib.Path, content: str) -> pathlib.Path:
    p = tmp_path / ".env"
    p.write_text(content, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# _read_env
# --------------------------------------------------------------------------- #


def test_read_env_basic(tmp_path):
    p = _env_file(tmp_path, "ONBOARD_WIZARD_APPLY=1\nPOST_CALL_SUMMARY=0\n# comment\nFOO=bar  \n")
    env = vaf._read_env(p)
    assert env["ONBOARD_WIZARD_APPLY"] == "1"
    assert env["POST_CALL_SUMMARY"] == "0"
    assert "FOO" in env
    assert "comment" not in env


def test_read_env_quoted(tmp_path):
    p = _env_file(tmp_path, 'WHATSAPP_SEND_ALLOWLIST="+919999999999"\n')
    env = vaf._read_env(p)
    assert env["WHATSAPP_SEND_ALLOWLIST"] == "+919999999999"


def test_read_env_missing_file_returns_empty(tmp_path):
    assert vaf._read_env(tmp_path / "nope.env") == {}


# --------------------------------------------------------------------------- #
# check_env — flag states + cross-gates
# --------------------------------------------------------------------------- #


def test_check_env_all_inert(tmp_path):
    p = _env_file(tmp_path, "")
    vaf.PROBLEMS.clear()
    vaf.WARNINGS.clear()
    env = vaf.check_env(p)
    assert env == {}
    assert vaf.PROBLEMS == []  # sab OFF = INERT correct, koi problem nahi
    # wizard INERT warning expected
    assert any("ONBOARD_WIZARD_APPLY unset" in w for w in vaf.WARNINGS)


def test_check_env_summary_armed_all_gates(tmp_path):
    p = _env_file(
        tmp_path,
        "POST_CALL_SUMMARY=1\nAUTO_QUALIFY_CALLS=1\nWHATSAPP_AUTO_SEND=1\nWHATSAPP_SEND_ALLOWLIST=+919999999999\n",
    )
    vaf.PROBLEMS.clear()
    vaf.WARNINGS.clear()
    vaf.check_env(p)
    assert vaf.PROBLEMS == []  # charo gates on = koi problem nahi


def test_check_env_summary_missing_gates(tmp_path):
    # POST_CALL_SUMMARY=1 par baaki gates off → problems
    p = _env_file(tmp_path, "POST_CALL_SUMMARY=1\n")
    vaf.PROBLEMS.clear()
    vaf.WARNINGS.clear()
    vaf.check_env(p)
    assert len(vaf.PROBLEMS) >= 3  # AUTO_QUALIFY + WHATSAPP_AUTO_SEND + allowlist


def test_check_env_qualify_on_summary_off(tmp_path):
    # AUTO_QUALIFY_CALLS=1 par POST_CALL_SUMMARY=0 → warning (not problem)
    p = _env_file(tmp_path, "AUTO_QUALIFY_CALLS=1\n")
    vaf.PROBLEMS.clear()
    vaf.WARNINGS.clear()
    vaf.check_env(p)
    assert vaf.PROBLEMS == []
    assert any("summary nahi bhejega" in w for w in vaf.WARNINGS)


# --------------------------------------------------------------------------- #
# check_manifest
# --------------------------------------------------------------------------- #


def test_check_manifest_flags_documented():
    vaf.PROBLEMS.clear()
    vaf.check_manifest()
    assert vaf.PROBLEMS == []  # dono flags manifest me hain


# --------------------------------------------------------------------------- #
# Exit-code mapping (main return via PROBLEMS/WARNINGS)
# --------------------------------------------------------------------------- #


def test_main_exit_mapping(tmp_path, monkeypatch):
    # Inert .env → warnings only → exit 2
    p = _env_file(tmp_path, "")
    monkeypatch.setattr(vaf, "ROOT", pathlib.Path(__file__).resolve().parent.parent)
    monkeypatch.setattr("sys.argv", ["verify_armed_flags.py", "--env", str(p)])
    rc = vaf.main()
    assert rc == 2  # warning (INERT default)


def test_main_problem_exit(tmp_path, monkeypatch):
    # Summary armed without gates → problems → exit 1
    p = _env_file(tmp_path, "POST_CALL_SUMMARY=1\n")
    monkeypatch.setattr("sys.argv", ["verify_armed_flags.py", "--env", str(p)])
    rc = vaf.main()
    assert rc == 1


# --------------------------------------------------------------------------- #
# Live endpoint probe (check_live) — 423 unarmed / 200 armed signals
# --------------------------------------------------------------------------- #


class _FakeHTTP:
    """Deterministic _http replacement: returns (status, json) per URL tail."""

    def __init__(self, responses: dict[str, tuple[int, dict]]):
        self.responses = responses
        self.calls: list[tuple[str, str]] = []  # (method, url)

    def __call__(self, method, url, token="", body=None):
        for key, val in self.responses.items():
            if key in url:
                self.calls.append((method, url))
                return val
        self.calls.append((method, url))
        return 404, {}


def test_check_live_unarmed_423(monkeypatch):
    fake = _FakeHTTP(
        {
            "business-types": (200, {"business_types": [{"id": "salon"}, {"id": "tiffin"}]}),
            "preview/salon": (200, {"template": {"niche": "salon_spa"}}),
            "apply": (423, {}),
        }
    )
    monkeypatch.setattr(vaf, "_http", fake)
    vaf.PROBLEMS.clear()
    vaf.WARNINGS.clear()
    vaf.check_live("https://x.in", "tok", "client_dummy")
    assert vaf.PROBLEMS == []  # 423 = INERT correct, koi problem nahi
    assert any("apply" in u for _, u in fake.calls)  # apply endpoint probe hua


def test_check_live_armed_200(monkeypatch):
    fake = _FakeHTTP(
        {
            "business-types": (200, {"business_types": [{"id": "salon"}]}),
            "preview/salon": (200, {"template": {"niche": "salon_spa"}}),
            "apply": (200, {"ok": True, "applied": ["niche_snapshot"]}),
        }
    )
    monkeypatch.setattr(vaf, "_http", fake)
    vaf.PROBLEMS.clear()
    vaf.WARNINGS.clear()
    vaf.check_live("https://x.in", "tok", "client_dummy")
    assert vaf.PROBLEMS == []  # 200 armed = expected signal (warning logged)
    assert any("apply returned 200" in w for w in vaf.WARNINGS)


def test_check_live_broken_endpoint(monkeypatch):
    fake = _FakeHTTP(
        {
            "business-types": (500, {}),
            "preview/salon": (200, {"template": {"niche": "salon_spa"}}),
            "apply": (423, {}),
        }
    )
    monkeypatch.setattr(vaf, "_http", fake)
    vaf.PROBLEMS.clear()
    vaf.WARNINGS.clear()
    vaf.check_live("https://x.in", "tok", "client_dummy")
    assert any("business-types" in p for p in vaf.PROBLEMS)  # 500 = problem


def test_check_live_no_client_id_skips_apply(monkeypatch):
    fake = _FakeHTTP(
        {
            "business-types": (200, {"business_types": [{"id": "salon"}]}),
            "preview/salon": (200, {"template": {"niche": "salon_spa"}}),
            "apply": (423, {}),
        }
    )
    monkeypatch.setattr(vaf, "_http", fake)
    vaf.PROBLEMS.clear()
    vaf.WARNINGS.clear()
    vaf.check_live("https://x.in", "tok", "")  # no apply-client-id
    assert not any("apply" in str(c) for c in fake.calls)  # apply probe skip
    assert any("apply-client-id" in w for w in vaf.WARNINGS)
