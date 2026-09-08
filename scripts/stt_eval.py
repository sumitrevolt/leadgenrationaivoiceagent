#!/usr/bin/env python3
"""STT eval CLI — offline transcript fixtures + optional WAV path.

python scripts/stt_eval.py                  # list fixtures
python scripts/stt_eval.py --wav clip.wav   # benchmark providers on WAV
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def _main() -> int:
    from app.voice_agent import stt_eval

    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", type=str, default="", help="WAV file to benchmark")
    ap.add_argument("--providers", type=str, default="groq,local")
    args = ap.parse_args()

    if args.wav:
        data = Path(args.wav).read_bytes()
        provs = [p.strip() for p in args.providers.split(",") if p.strip()]
        res = await stt_eval.benchmark_providers(data, providers=provs)
        print(res)
        return 0

    fixtures = stt_eval.list_transcript_fixtures(10)
    print(f"fixtures={len(fixtures)}")
    for f in fixtures[:5]:
        print(f"  [{f.get('file')}] {str(f.get('text', ''))[:80]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
