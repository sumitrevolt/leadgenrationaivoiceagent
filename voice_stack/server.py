"""
Self-hosted Indian-language voice model-server — the FREE "apna Sarvam".
=======================================================================
Runs AI4Bharat IndicConformer (STT) + IndicF5 (TTS) on YOUR NVIDIA GPU
(laptop ya dedicated box). No per-minute cost — sirf compute.

Endpoints match app/voice_agent/indic_providers.py Ai4Bharat* contract, so the
LeadGen app talks to it just by setting:  AI4BHARAT_ENDPOINT=https://<your-url>

    POST /transcribe   (multipart "file" = audio)          -> {"transcript": "..."}
    POST /tts          ({"text": "...", "language": "hi"})  -> {"audio": "<base64 wav>"}
    GET  /health

VOICE CLONING (IndicF5): set REF_AUDIO (a 5-10s clean Hindi voice sample = your
agent's voice) + REF_TEXT (its exact transcript). The TTS speaks in THAT voice.

Run (laptop with NVIDIA GPU):
    pip install -r requirements.txt   # + the CUDA torch wheel (see README)
    REF_AUDIO=ref_voice.wav REF_TEXT="namaste, main swara bol rahi hoon" \
        uvicorn server:app --host 0.0.0.0 --port 8900
    cloudflared tunnel --url http://localhost:8900   # free public https URL

NOTE: models download once (~2.4GB STT + IndicF5) from HuggingFace on first run.
This is a STARTING scaffold — verify/tune on your actual GPU (see README caveats).
"""
from __future__ import annotations

import base64
import io
import os
import time

import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, File, Form, UploadFile

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
REF_AUDIO = os.environ.get("REF_AUDIO", "").strip()       # your agent voice sample (wav)
REF_TEXT = os.environ.get("REF_TEXT", "").strip()         # transcript of REF_AUDIO
STT_REPO = os.environ.get("STT_REPO", "ai4bharat/indic-conformer-600m-multilingual")
TTS_REPO = os.environ.get("TTS_REPO", "ai4bharat/IndicF5")

app = FastAPI(title="LeadGen self-hosted voice stack (AI4Bharat)")
_stt = None
_tts = None


def _load_models() -> None:
    """Lazy-load both models onto the GPU (once)."""
    global _stt, _tts
    from transformers import AutoModel

    if _stt is None:
        _stt = AutoModel.from_pretrained(STT_REPO, trust_remote_code=True)
        try:
            _stt = _stt.to(DEVICE).eval()  # nosecurity — torch eval-MODE, not Python eval()
        except Exception:
            pass
    if _tts is None:
        _tts = AutoModel.from_pretrained(TTS_REPO, trust_remote_code=True)
        try:
            _tts = _tts.to(DEVICE).eval()  # nosecurity — torch eval-MODE, not Python eval()
        except Exception:
            pass


@app.on_event("startup")
def _startup() -> None:
    try:
        _load_models()
    except Exception as e:  # don't die on startup — /health reports state
        print(f"[voice-stack] model load deferred/failed: {e}")


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "device": DEVICE,
        "cuda": torch.cuda.is_available(),
        "gpu": (torch.cuda.get_device_name(0) if torch.cuda.is_available() else None),
        "stt_loaded": _stt is not None,
        "tts_loaded": _tts is not None,
        "voice_clone_ready": bool(REF_AUDIO and REF_TEXT),
    }


def _decode_audio(data: bytes) -> tuple[np.ndarray, int]:
    """Decode any container (webm/opus from browser, wav, mp3, ogg) → mono float32 + sr.
    Tries soundfile, then PyAV (ffmpeg) for webm/opus."""
    try:
        arr, sr = sf.read(io.BytesIO(data), dtype="float32")
        if getattr(arr, "ndim", 1) > 1:
            arr = arr.mean(axis=1)
        return arr, sr
    except Exception:
        pass
    # PyAV (ffmpeg) — browser MediaRecorder webm/opus
    import av  # type: ignore

    container = av.open(io.BytesIO(data))
    stream = next(s for s in container.streams if s.type == "audio")
    sr = stream.codec_context.sample_rate or 48000
    chunks = []
    resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=sr)
    for frame in container.decode(stream):
        for rf in resampler.resample(frame):
            chunks.append(rf.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32), sr
    pcm = np.concatenate(chunks).astype(np.float32) / 32768.0
    return pcm, sr


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...), language: str = Form("hi")) -> dict:
    """Audio -> Hindi/Hinglish text via IndicConformer (CTC)."""
    if _stt is None:
        return {"transcript": "", "error": "stt_not_loaded"}
    data = await file.read()
    if not data:
        return {"transcript": ""}
    t0 = time.time()
    try:
        arr, sr = _decode_audio(data)
        wav = torch.tensor(arr, dtype=torch.float32).unsqueeze(0)  # (1, N)
        if sr != 16000:
            import torchaudio

            wav = torchaudio.transforms.Resample(sr, 16000)(wav)
        lang = (language or "hi").split("-")[0].lower()
        with torch.no_grad():
            out = _stt(wav.to(DEVICE), lang, "ctc")
        text = out if isinstance(out, str) else (out[0] if isinstance(out, (list, tuple)) else str(out))
        return {"transcript": str(text).strip(), "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {"transcript": "", "error": str(e)[:200]}


@app.post("/tts")
async def tts(payload: dict) -> dict:
    """Hindi/Hinglish text -> base64 WAV via IndicF5 (voice-cloned to REF_AUDIO)."""
    if _tts is None:
        return {"audio": "", "error": "tts_not_loaded"}
    text = (payload.get("text") or "").strip()
    if not text:
        return {"audio": ""}
    if not (REF_AUDIO and REF_TEXT):
        return {"audio": "", "error": "set REF_AUDIO + REF_TEXT (voice sample) to enable TTS"}
    t0 = time.time()
    try:
        with torch.no_grad():
            audio = _tts(text, ref_audio_path=REF_AUDIO, ref_text=REF_TEXT)
        audio = np.asarray(audio)
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        buf = io.BytesIO()
        sf.write(buf, audio.astype(np.float32), 24000, format="WAV")
        return {"audio": base64.b64encode(buf.getvalue()).decode("ascii"), "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {"audio": "", "error": str(e)[:200]}
