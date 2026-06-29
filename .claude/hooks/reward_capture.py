#!/usr/bin/env python3
"""Stop hook (Phase 0, Loop B) — capture Claude dev-session outcome signals.

Writes ONE raw record to data/claude_feedback.jsonl. The reward SCORE is computed
on READ by app.agents.rl.reward.dev_reward (single source of truth) — this hook
stores only raw signals so it stays dependency-free and fast.

INERT unless RL_ENGINE=1. Fail-open: any error -> exit 0, never blocks the session.
Self-contained (no app import) — runs on the Claude Code host with a 10s budget.
"""
import datetime
import json
import os
import sys


def _flag_on() -> bool:
    return os.environ.get("RL_ENGINE", "").strip().lower() in ("1", "true", "yes", "on")


def _read_marker(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main() -> None:
    try:
        if not _flag_on():
            return
        raw = ""
        try:
            if not sys.stdin.isatty():
                raw = sys.stdin.read()
        except Exception:
            raw = ""
        try:
            sess = json.loads(raw) if raw.strip() else {}
        except Exception:
            sess = {}
        verify = _read_marker(os.path.join("data", ".claude_last_verify.json"))
        rec = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "task": str(sess.get("cwd") or sess.get("session_id") or "")[:120],
            "verify_pass": verify.get("pass"),
            "tests_pass": verify.get("tests_pass"),
            "review_findings": verify.get("review_findings"),
            "deploy_health": verify.get("deploy_health"),
            "user_correction": None,  # set by /learn when the user flags a mistake
        }
        os.makedirs("data", exist_ok=True)
        with open(os.path.join("data", "claude_feedback.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
