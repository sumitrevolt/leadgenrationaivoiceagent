import json
import os
import subprocess
import sys


def test_reward_capture_writes_when_on(tmp_path):
    env = dict(os.environ, RL_ENGINE="1")
    hook = os.path.abspath(os.path.join(".claude", "hooks", "reward_capture.py"))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / ".claude_last_verify.json").write_text(
        json.dumps({"pass": True, "tests_pass": True, "deploy_health": "ok"})
    )
    subprocess.run(
        [sys.executable, hook], cwd=str(tmp_path), env=env, input="{}", text=True, timeout=20
    )
    out = tmp_path / "data" / "claude_feedback.jsonl"
    assert out.exists()
    rec = json.loads(out.read_text().splitlines()[-1])
    assert rec["verify_pass"] is True
    assert rec["tests_pass"] is True


def test_reward_capture_inert_when_off(tmp_path):
    env = dict(os.environ)
    env.pop("RL_ENGINE", None)
    hook = os.path.abspath(os.path.join(".claude", "hooks", "reward_capture.py"))
    (tmp_path / "data").mkdir()
    subprocess.run(
        [sys.executable, hook], cwd=str(tmp_path), env=env, input="{}", text=True, timeout=20
    )
    assert not (tmp_path / "data" / "claude_feedback.jsonl").exists()


def test_reward_capture_consumes_marker(tmp_path):
    """Fresh marker is used once then deleted (consume-once)."""
    env = dict(os.environ, RL_ENGINE="1")
    hook = os.path.abspath(os.path.join(".claude", "hooks", "reward_capture.py"))
    marker = tmp_path / "data" / ".claude_last_verify.json"
    (tmp_path / "data").mkdir()
    marker.write_text(json.dumps({"pass": True, "tests_pass": True}))
    subprocess.run(
        [sys.executable, hook], cwd=str(tmp_path), env=env, input="{}", text=True, timeout=20
    )
    rec = json.loads((tmp_path / "data" / "claude_feedback.jsonl").read_text().splitlines()[-1])
    assert rec["verify_pass"] is True
    assert not marker.exists()  # consumed


def test_reward_capture_ignores_stale_marker(tmp_path):
    """A marker older than the freshness window is dropped to None signals."""
    env = dict(os.environ, RL_ENGINE="1")
    hook = os.path.abspath(os.path.join(".claude", "hooks", "reward_capture.py"))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / ".claude_last_verify.json").write_text(
        json.dumps({"ts": "2000-01-01T00:00:00+00:00", "pass": True, "tests_pass": True})
    )
    subprocess.run(
        [sys.executable, hook], cwd=str(tmp_path), env=env, input="{}", text=True, timeout=20
    )
    rec = json.loads((tmp_path / "data" / "claude_feedback.jsonl").read_text().splitlines()[-1])
    assert rec["verify_pass"] is None  # stale -> ignored
    assert rec["tests_pass"] is None
