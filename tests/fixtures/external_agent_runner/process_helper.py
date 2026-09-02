#!/usr/bin/env python3
"""Owned real-process helper for EXTERNAL_AGENT_RUNNER integration tests.

Deterministic behaviours only. Never prints secret *values* — env dump is
names-only. Invoked solely via argument arrays (no shell).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _cmd() -> str:
    return (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()


def main() -> int:
    cmd = _cmd()
    if cmd == "env-names":
        # Names only — never values.
        print(json.dumps(sorted(os.environ.keys()), ensure_ascii=False))
        return 0
    if cmd == "env-watch":
        watch = sys.argv[2:]
        present = {k: (k in os.environ) for k in watch}
        print(json.dumps(present, ensure_ascii=False, sort_keys=True))
        return 0
    if cmd == "echo-argv":
        print(json.dumps(sys.argv[2:], ensure_ascii=False))
        return 0
    if cmd == "sleep":
        time.sleep(float(sys.argv[2] if len(sys.argv) > 2 else "2"))
        print("slept")
        return 0
    if cmd == "spawn-child":
        secs = float(sys.argv[2] if len(sys.argv) > 2 else "30")
        child = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "sleep", str(secs)],
            shell=False,
        )
        print(json.dumps({"child_pid": child.pid}))
        sys.stdout.flush()
        child.wait()
        return int(child.returncode or 0)
    if cmd == "json-ok":
        mid = sys.argv[2] if len(sys.argv) > 2 else "msn_test"
        inner = {
            "mission_id": mid,
            "executor": "cursor",
            "changed_files": ["tests/fixtures/external_agent_runner/STATUS.txt"],
            "commands": [],
            "tests": [],
            "summary": "helper-ok",
            "evidence": {},
            "scope_breach": False,
        }
        print(json.dumps({"result": json.dumps(inner)}))
        return 0
    if cmd == "json-malformed":
        print("NOT_JSON{{{{")
        return 0
    if cmd == "json-prose":
        mid = sys.argv[2] if len(sys.argv) > 2 else "msn_test"
        print("Here is the result:\n" + json.dumps({"mission_id": mid, "executor": "cursor"}))
        return 0
    if cmd == "json-wrong-mission":
        print(
            json.dumps(
                {
                    "result": json.dumps(
                        {
                            "mission_id": "msn_other",
                            "executor": "cursor",
                            "changed_files": [],
                            "commands": [],
                            "tests": [],
                            "summary": "x",
                            "evidence": {},
                            "scope_breach": False,
                        }
                    )
                }
            )
        )
        return 0
    if cmd == "json-wrong-executor":
        mid = sys.argv[2] if len(sys.argv) > 2 else "msn_test"
        print(
            json.dumps(
                {
                    "result": json.dumps(
                        {
                            "mission_id": mid,
                            "executor": "claude",
                            "changed_files": [],
                            "commands": [],
                            "tests": [],
                            "summary": "x",
                            "evidence": {},
                            "scope_breach": False,
                        }
                    )
                }
            )
        )
        return 0
    if cmd == "flood-stdout":
        n = int(sys.argv[2] if len(sys.argv) > 2 else str(600 * 1024))
        chunk = "A" * 4096
        written = 0
        while written < n:
            take = min(len(chunk), n - written)
            sys.stdout.write(chunk[:take])
            written += take
        sys.stdout.flush()
        return 0
    if cmd == "flood-both":
        n = int(sys.argv[2] if len(sys.argv) > 2 else str(200 * 1024))
        chunk = "B" * 2048
        err = "C" * 2048
        written = 0
        while written < n:
            sys.stdout.write(chunk)
            sys.stderr.write(err)
            written += len(chunk)
        sys.stdout.flush()
        sys.stderr.flush()
        return 0
    if cmd == "exit":
        return int(sys.argv[2] if len(sys.argv) > 2 else "1")
    if cmd == "write-file":
        target = Path(sys.argv[2])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("helper-write\n", encoding="utf-8")
        print(json.dumps({"wrote": str(target)}))
        return 0
    if cmd == "marker":
        # Used only by PATH-hijack decoy binaries in tests.
        print("HIJACKED_HELPER")
        return 0
    print(json.dumps({"error": "unknown_cmd", "cmd": cmd}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
