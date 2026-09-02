#!/usr/bin/env python3
"""Post-deploy smoke — run ON the VPS after git pull + container recreate.

Checks: /health, public activation summary, optional in-container Qdrant ping.
Exit 0 = safe to announce deploy done. Never mutates state.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
FAIL = 0


def _get(path: str, timeout: float = 8.0) -> tuple[int, dict | str]:
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw[:200]
    except urllib.error.HTTPError as e:
        return e.code, str(e)[:120]
    except Exception as e:
        return -1, str(e)[:120]


def main() -> int:
    global FAIL
    print("=== VPS post-deploy verify ===")

    code, body = _get("/health")
    env_ok = isinstance(body, dict) and body.get("environment") == "production"
    print(
        f"{'OK' if code == 200 and env_ok else 'FAIL'} /health {code} env={body.get('environment') if isinstance(body, dict) else '?'}"
    )
    if code != 200 or not env_ok:
        FAIL += 1

    code, body = _get("/api/activation/summary")
    if isinstance(body, dict):
        blockers = body.get("blocker_count", "?")
        warns = body.get("warn_count", "?")
        ready = body.get("ready_for_launch")
        print(
            f"{'OK' if blockers == 0 else 'FAIL'} activation blockers={blockers} warns={warns} ready={ready}"
        )
        if blockers != 0:
            FAIL += 1
    else:
        print(f"FAIL activation summary: {body}")
        FAIL += 1

    code, body = _get("/health/ready")
    if isinstance(body, dict):
        checks = body.get("checks") or {}
        db = (checks.get("database") or {}).get("status")
        redis = (checks.get("redis") or {}).get("status")
        ok = db == "healthy" and redis == "healthy"
        print(f"{'OK' if ok else 'FAIL'} /health/ready db={db} redis={redis}")
        if not ok:
            FAIL += 1
    else:
        print(f"WARN /health/ready: {body}")

    # Qdrant from inside app container (uses compose QDRANT_URL default)
    try:
        r = subprocess.run(
            [
                "docker",
                "exec",
                "leadgen_app",
                "python",
                "-c",
                "import os,urllib.request; u=os.getenv('QDRANT_URL','').rstrip('/')+'/healthz'; "
                "print('skip') if not os.getenv('QDRANT_URL') else print(urllib.request.urlopen(u,timeout=3).status)",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        out = (r.stdout or "").strip()
        if out == "skip":
            print("WARN qdrant: QDRANT_URL unset in container")
        elif out == "200":
            print("OK qdrant healthz from leadgen_app")
        else:
            print(f"FAIL qdrant from container: {r.stdout or r.stderr}")
            FAIL += 1
    except Exception as e:
        print(f"WARN qdrant check skipped: {e}")

    try:
        r = subprocess.run(
            ["docker", "exec", "leadgen_app", "printenv", "USE_LLM_STREAM_TTS"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        stt = (r.stdout or "").strip()
        if stt == "1":
            print("OK USE_LLM_STREAM_TTS=1")
        else:
            print(f"WARN USE_LLM_STREAM_TTS={stt or 'unset'} (web-call latency path off)")
    except Exception as e:
        print(f"WARN stream TTS env check skipped: {e}")

    print("---")
    if FAIL:
        print(f"RESULT: {FAIL} check(s) FAILED — rollback ya fix before calling deploy done")
        return 1
    print("RESULT: PASS — production deploy verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
