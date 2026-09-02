from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.governor_review_submit import build_request, submit_review

ROOT = Path(__file__).resolve().parents[1]


def test_direct_script_help_bootstraps_repo_import_path():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "governor_review_submit.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Submit a scoped governor review" in result.stdout


def test_submitter_refuses_non_loopback_url(monkeypatch):
    monkeypatch.setenv("DEV_CLAUDE_REVIEW_SECRET", "c" * 40)
    with pytest.raises(ValueError, match="loopback_url_required"):
        build_request(
            base_url="https://example.com/api",
            task_id="t1",
            governor="claude",
            decision="approve",
            artifact_hash="a" * 64,
            summary="safe",
        )


def test_submitter_sends_scoped_proof_without_printing_secret(monkeypatch):
    secret = "c" * 40
    monkeypatch.setenv("DEV_CLAUDE_REVIEW_SECRET", secret)
    captured = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"review_gate":{"approved":false}}'

    def fake_urlopen(request, timeout):
        captured.update(
            url=request.full_url, headers=dict(request.headers), body=request.data, timeout=timeout
        )
        return Response()

    monkeypatch.setattr("scripts.governor_review_submit.urlopen", fake_urlopen)
    result = submit_review(
        base_url="http://127.0.0.1:8000/api",
        task_id="t1",
        governor="claude",
        decision="approve",
        artifact_hash="a" * 64,
        summary="safe",
    )
    assert result["review_gate"]["approved"] is False
    assert captured["url"].endswith("/api/dev-tasks/t1/governor-review")
    assert json.loads(captured["body"])["governor"] == "claude"
    assert secret not in repr(captured)
    assert "X-governor-signature" in captured["headers"]
    assert captured["timeout"] == 10
