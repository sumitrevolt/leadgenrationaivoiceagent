#!/usr/bin/env python3
"""Idempotent: set RAG advancement flags in /opt/leadgen/.env (VPS only)."""

from __future__ import annotations

import os
from pathlib import Path

ENV = Path(os.environ.get("LEADGEN_ENV", "/opt/leadgen/.env"))
FLAGS = {
    "USE_RERANKER": "1",
    "USE_CONTEXTUAL_INGEST": "1",
    "USE_HYBRID_SEARCH": "1",
}


def main() -> int:
    if not ENV.is_file():
        print(f"MISSING {ENV}")
        return 1
    text = ENV.read_text(encoding="utf-8", errors="ignore").splitlines()
    present = {
        ln.split("=", 1)[0].strip(): i
        for i, ln in enumerate(text)
        if "=" in ln and not ln.strip().startswith("#")
    }
    for k, v in FLAGS.items():
        if k in present:
            text[present[k]] = f"{k}={v}"
        else:
            text.append(f"{k}={v}")
    ENV.write_text("\n".join(text).rstrip() + "\n", encoding="utf-8")
    print("OK flags:", ", ".join(FLAGS))
    try:
        import subprocess

        subprocess.run(
            [
                "bash",
                "-lc",
                "cd /opt/leadgen && docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps app worker worker-heavy",
            ],
            check=True,
            timeout=120,
        )
        print("RECREATE app+workers OK")
    except Exception as e:
        print(f"WARN recreate skipped: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
