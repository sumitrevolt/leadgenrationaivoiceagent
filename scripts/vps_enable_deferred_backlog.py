#!/usr/bin/env python3
"""Enable deferred 2026 backlog flags on VPS (.env) + optional RAG gate."""

from __future__ import annotations

import os
import re
import subprocess
import sys

ENV_PATH = "/opt/leadgen/.env"

# Safe wins first; USE_LLM_STREAM_TTS via --stream-tts after voice_stream_tts_smoke.py PASS
WANT = {
    "SEMANTIC_CACHE": "1",
    "SEMANTIC_CACHE_MIN_SIM": "0.97",
    "SEMANTIC_CACHE_TTL_S": "21600",
    "USE_TEXT_ENDPOINT": "1",
}

STREAM_TTS_KEY = "USE_LLM_STREAM_TTS"


def _read_env() -> str:
    if os.path.isfile(ENV_PATH):
        return open(ENV_PATH, encoding="utf-8", errors="replace").read()
    return ""


def _set_kv(text: str, key: str, val: str) -> tuple[str, bool]:
    pat = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    line = f"{key}={val}"
    if pat.search(text):
        if f"{key}={val}" in text:
            return text, False
        return pat.sub(line, text), True
    if text and not text.endswith("\n"):
        text += "\n"
    return text + line + "\n", True


def main() -> int:
    text = _read_env()
    changed = False
    for k, v in WANT.items():
        text, ch = _set_kv(text, k, v)
        if ch:
            print(f"SET {k}={v}")
            changed = True

    run_rag = "--rag-gate" in sys.argv
    run_stream = "--stream-tts" in sys.argv
    if run_stream:
        print("=== LLM stream TTS smoke (in-container) ===")
        r = subprocess.run(
            ["docker", "exec", "leadgen_app", "python", "scripts/voice_stream_tts_smoke.py"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        print(r.stdout or r.stderr)
        if r.returncode == 0:
            text, ch = _set_kv(text, STREAM_TTS_KEY, "1")
            if ch:
                print(f"SET {STREAM_TTS_KEY}=1 (smoke PASS)")
                changed = True
        else:
            print("Stream TTS smoke FAIL — flag unchanged")
            return 1
    if run_rag:
        print("=== RAG A/B gate ===")
        r = subprocess.run(
            ["docker", "exec", "leadgen_app", "python", "scripts/rag_retrieval_ab.py"],
            capture_output=True,
            text=True,
        )
        print(r.stdout or r.stderr)
        if r.returncode == 0:
            for k in ("USE_RERANKER", "USE_HYBRID_SEARCH"):
                text, ch = _set_kv(text, k, "1")
                if ch:
                    print(f"SET {k}=1 (gate PASS)")
                    changed = True
        else:
            print("RAG gate FAIL — retrieval flags unchanged")

    if changed:
        bak = ENV_PATH + ".bak_deferred_backlog"
        subprocess.run(["cp", ENV_PATH, bak], check=True)
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        subprocess.run(
            [
                "bash",
                "-lc",
                "cd /opt/leadgen && docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps app worker worker-heavy scheduler",
            ],
            check=True,
        )
        print("RECREATE app worker scheduler OK")
    else:
        print("FLAGS OK (no change)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
