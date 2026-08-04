"""Bounded git probe — redaction + allowlist + timeout surface."""

from __future__ import annotations

from app.platform.coordination_hub_git import probe_git, redact_git_text


def test_redact_secret_like_patterns():
    raw = "api_key=sk-abc1234567890 password=hunter2 Authorization: Bearer tokensecret"
    out = redact_git_text(raw)
    assert "sk-abc" not in out
    assert "hunter2" not in out
    assert "tokensecret" not in out
    assert "[redacted]" in out


def test_probe_git_returns_redacted_allowlisted(monkeypatch):
    def fake_run(args, **kwargs):
        class P:
            returncode = 0
            stdout = "api_key=supersecretvalue123\n M app/x.py\n"
            stderr = ""

        return P()

    monkeypatch.setattr("app.platform.coordination_hub_git.subprocess.run", fake_run)
    out = probe_git(timeout=2.0)
    assert out["ok"] is True
    assert out["redacted"] is True
    status_out = out["commands"]["status"]["stdout"]
    assert "supersecretvalue123" not in status_out
    assert "[redacted]" in status_out


def test_probe_git_timeout(monkeypatch):
    import subprocess as sp

    def boom(*_a, **_k):
        raise sp.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr("app.platform.coordination_hub_git.subprocess.run", boom)
    out = probe_git(timeout=1.0)
    assert out["commands"]["status"]["error"] == "timeout"
