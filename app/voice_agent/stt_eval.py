"""STT provider eval harness (offline-safe, no default chain change).

Benchmarks available STT backends on WAV bytes or ``data/call_transcripts/``
fixtures. Use before promoting a Hindi STT upgrade (#7 roadmap).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _TRANSCRIPTS() -> Path:
    """Call transcripts dir — resolved per call, never frozen at import."""
    from app.platform.runtime_recording_paths import call_transcripts_dir

    return call_transcripts_dir()


async def transcribe_eval_provider(
    wav_bytes: bytes,
    provider: str,
    language: str = "hi",
) -> tuple[str, str]:
    """Try one eval provider. Returns (text, provider_label). Never raises."""
    if not wav_bytes:
        return "", ""
    prov = (provider or "").strip().lower()
    try:
        if prov in ("groq", "primary"):
            from app.voice_agent import free_ai

            return await free_ai.transcribe_audio(wav_bytes, language=language)
        if prov in ("local", "faster-whisper", "faster_whisper"):
            return await _local_whisper(wav_bytes, language)
    except Exception:
        pass
    return "", ""


async def _local_whisper(wav_bytes: bytes, language: str) -> tuple[str, str]:
    try:
        import asyncio
        import tempfile

        def _run() -> str:
            from faster_whisper import WhisperModel

            model = WhisperModel("small", device="cpu", compute_type="int8")
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(wav_bytes)
                path = tmp.name
            try:
                segs, _ = model.transcribe(path, language=language or "hi")
                return " ".join(s.text.strip() for s in segs if s.text).strip()
            finally:
                try:
                    os.unlink(path)
                except Exception:
                    pass

        text = await asyncio.wait_for(asyncio.to_thread(_run), timeout=45.0)
        return (text or "", "local:faster-whisper") if text else ("", "")
    except Exception:
        return "", ""


def list_transcript_fixtures(limit: int = 20) -> list[dict[str, Any]]:
    """Load recent transcript JSONL rows (text-only fixtures)."""
    out: list[dict[str, Any]] = []
    if not _TRANSCRIPTS().is_dir():
        return out
    files = sorted(_TRANSCRIPTS().glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for fp in files:
        try:
            for line in fp.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("role") in ("user", "caller", "human") and row.get("content"):
                    out.append({"file": fp.name, "text": str(row["content"]), "meta": row})
                    if len(out) >= limit:
                        return out
        except Exception:
            continue
    return out


async def benchmark_providers(
    wav_bytes: bytes,
    providers: list[str] | None = None,
    language: str = "hi",
) -> dict[str, Any]:
    """Run eval providers on one audio clip. Never raises."""
    provs = providers or ["groq", "local"]
    results: dict[str, Any] = {"providers": {}, "language": language}
    for p in provs:
        text, label = await transcribe_eval_provider(wav_bytes, p, language=language)
        results["providers"][p] = {"text": text, "label": label, "chars": len(text)}
    return results


__all__ = ["transcribe_eval_provider", "list_transcript_fixtures", "benchmark_providers"]
