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


def _marker_fresh(marker: dict, max_age_s: int = 7200) -> bool:
    """A verify marker only describes the session that just ran /verify. Treat
    a marker with no/old `ts` as stale so we don't misattribute one verify
    result to many session-ends. No ts (back-compat) = assume fresh; consume-once
    is the real guard."""
    ts = marker.get("ts")
    if not ts:
        return True
    try:
        t = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        age = (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()
        return age <= max_age_s
    except Exception:
        return True


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
        marker_path = os.path.join("data", ".claude_last_verify.json")
        verify = _read_marker(marker_path)
        # Consume-once + freshness: clear the marker after reading so the next
        # session that didn't run /verify gets None signals (not a stale copy).
        if verify:
            fresh = _marker_fresh(verify)
            try:
                os.remove(marker_path)
            except Exception:
                pass
            if not fresh:
                verify = {}
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
