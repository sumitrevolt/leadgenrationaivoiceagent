"""Stage-0 local render proof — 9:16 / 1:1 / 16:9 sample videos + ffprobe QA.

Usage:
  .venv\\Scripts\\python.exe scripts\\video_production_local_proof.py

Writes under data/video_production_proof/ (gitignored via data/). Never contacts
WhatsApp/Postiz. Free-stack only (Pillow + ffmpeg + optional EdgeTTS).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, "data", "video_production_proof")


async def main() -> int:
    from app.marketing import video_pipeline

    os.makedirs(OUT, exist_ok=True)
    # Redirect pipeline output into proof dir
    video_pipeline._OUT_DIR = OUT  # noqa: SLF001

    slides = [
        "LeadGen AI — Daily Video Proof",
        "Free-stack FFmpeg render",
        "Customer approval required before publish",
    ]
    results = []
    for ratio in ("9:16", "1:1", "16:9"):
        r = await video_pipeline.render_creative_video(
            business_name="LeadGen AI Own-Brand",
            niche="saas",
            slides=slides,
            offer="",
            client_id="",
            ratio=ratio,
        )
        entry = {
            "ratio": ratio,
            **{k: r.get(k) for k in ("error", "size_kb", "width", "height", "took_s")},
        }
        # Never store absolute host paths in proof metadata (Windows/VPS leak risk).
        if r.get("path") and os.path.isfile(r["path"]):
            entry["path"] = os.path.basename(r["path"])
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration,size:stream=width,height,codec_name",
                    "-of",
                    "json",
                    r["path"],
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            entry["ffprobe_ok"] = probe.returncode == 0
            try:
                entry["ffprobe"] = json.loads(probe.stdout or "{}")
            except Exception:
                entry["ffprobe"] = {}
            # Contact sheet: first frame
            sheet_name = f"contact_{ratio.replace(':', 'x')}.jpg"
            sheet = os.path.join(OUT, sheet_name)
            subprocess.run(
                ["ffmpeg", "-y", "-i", r["path"], "-frames:v", "1", sheet],
                capture_output=True,
                timeout=60,
            )
            entry["contact_sheet"] = sheet_name if os.path.isfile(sheet) else None
        results.append(entry)
        print(json.dumps(entry, indent=2))

    summary = os.path.join(OUT, "proof_summary.json")
    with open(summary, "w", encoding="utf-8") as f:
        json.dump(
            {
                "ok": all(not x.get("error") for x in results),
                "note": "Local-only under data/ (gitignored). Paths are basenames only.",
                "results": results,
            },
            f,
            indent=2,
        )
    print("SUMMARY", summary)
    return 0 if all(not x.get("error") for x in results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
