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
    subprocess.run([sys.executable, hook], cwd=str(tmp_path), env=env,
                   input="{}", text=True, timeout=20)
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
    subprocess.run([sys.executable, hook], cwd=str(tmp_path), env=env,
                   input="{}", text=True, timeout=20)
    assert not (tmp_path / "data" / "claude_feedback.jsonl").exists()
