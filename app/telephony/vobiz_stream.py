"""
Vobiz WebSocket Streaming — conversational phone AI (bare-metal, no Pipecat).
=============================================================================

WHAT THIS IS
------------
Vobiz can stream a live PSTN call to our server over a WebSocket. For each call
Vobiz opens ONE WS to
``wss://<host>/api/telephony/vobiz/stream/<token>?niche=...&client_id=...`` and:

  * sends us the caller's audio as base64 **Linear PCM 16-bit little-endian,
    16 kHz, mono, ~20 ms (640-byte) frames** wrapped in JSON events — because
    our <Stream> verb requests ``contentType="audio/x-l16;rate=16000"`` (see
    vobiz_handler.build_stream_xml);
  * plays back the ``playAudio`` JSON we send (same L16/16 kHz/base64 format).

We run a full conversational loop per call:

    caller audio (PCM16 16k — already STT-ready, NO conversion needed)
        → energy/silence VAD          -> utterance boundary
        → STT (vosk | faster-whisper) -> user text
        → LLMBrain.generate_response  -> reply text  (niche-aware, Hinglish)
        → EdgeTTS (hi-IN-SwaraNeural) -> MP3 bytes
        → pydub decode + resample     -> PCM16 16k mono
        → base64, 640-byte/20ms chunks -> {"event":"playAudio", ...} to Vobiz

NO µ-LAW / NO 8k RESAMPLE (the load-bearing simplification)
-----------------------------------------------------------
contentType=audio/x-l16;rate=16000 means inbound bytes ARE already PCM16 @16 kHz
(exactly what STT wants) and we send PCM16 @16 kHz straight back. audioop is now
used ONLY for RMS in the VAD, with a pure-Python fallback (_pcm_rms) so the call
keeps working even if audioop is unimportable.

GRACEFUL DEGRADATION (robustness > completeness)
------------------------------------------------
Everything is guarded; the socket NEVER crashes. Capability flags decide what
runs, and a missing capability is logged + skipped (the call still connects):

  * TTS_AVAILABLE  -> needs ``edge-tts`` AND ``pydub`` importable.
  * STT_AVAILABLE  -> needs ``vosk`` OR ``faster-whisper`` importable.
  * audioop        -> stdlib (Python ≤3.12); on 3.13 falls back to audioop-lts.
                      Only RMS is used now; a manual int loop covers its absence.

TO GO LIVE ON THE VPS (Mumbai) you must install the heavy, optional deps:
    .venv/bin/pip install vosk            # or: faster-whisper
    # pydub + edge-tts already in requirements.txt
    # ffmpeg already installed on the VPS (deploy_vps.sh STEP 1) — pydub needs it
For vosk set ``VOSK_MODEL_PATH`` to a downloaded model dir (e.g. the small
hi/en model). Without these the WS still accepts + reads events, but cannot
hear or speak (logs "STT/TTS unavailable").

Protocol events (EXACT, per docs.vobiz.ai/xml/stream + /xml/stream/play-audio):
  recv: {"event":"start","start":{"streamSid":..,"callSid":..,"customParameters":{..}}}
        {"event":"media","media":{"payload":"<b64 PCM16 16k>"}}
        {"event":"stop"}
        {"event":"playedStream"}    # ack: our playAudio finished (no-op)
        {"event":"clearedAudio"}    # ack: clearAudio flushed buffer (no-op)
  send: {"event":"playAudio","media":{"contentType":"audio/x-l16","sampleRate":16000,"payload":"<b64 PCM16 16k>"}}
        {"event":"clearAudio"}      # flush playback on barge-in (no sid)
"""
from __future__ import annotations

import asyncio
import base64
import importlib.util
import io
import json
import os
from typing import Any, Dict, List, Optional

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# --------------------------------------------------------------------------- #
# Capability detection — light (find_spec does NOT import the heavy module).
# --------------------------------------------------------------------------- #
def _have(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


_VOSK_OK = _have("vosk")
_FWHISPER_OK = _have("faster_whisper")
STT_AVAILABLE = _VOSK_OK or _FWHISPER_OK
TTS_AVAILABLE = _have("edge_tts") and _have("pydub")

# audioop is stdlib on Python ≤3.12; removed in 3.13 (use audioop-lts backport).
try:  # pragma: no cover - environment dependent
    import audioop  # type: ignore

    _AUDIOOP_OK = True
except Exception:  # pragma: no cover
    try:
        import audioop_lts as audioop  # type: ignore

        _AUDIOOP_OK = True
    except Exception:
        audioop = None  # type: ignore
        _AUDIOOP_OK = False


# --------------------------------------------------------------------------- #
# Tunables (env-overridable) — phone audio, so frames are 20 ms / 160 µ-law B.
# --------------------------------------------------------------------------- #
SAMPLE_RATE = 16000     # Vobiz L16 stream rate (contentType audio/x-l16;rate=16000)
STT_RATE = 16000        # STT models want 16 kHz PCM16 (== SAMPLE_RATE: no resample)
FRAME_PCM = 640         # 20 ms of PCM16 @ 16 kHz (16000 * 0.02 * 2 bytes)
PCM_SILENCE = b"\x00"   # PCM16 silence == zero bytes

_VAD_RMS = int(os.environ.get("VOBIZ_VAD_RMS", "300"))   # PCM16 RMS speech gate
SILENCE_MS = 700.0      # trailing silence that ends an utterance
MIN_SPEECH_MS = 200.0   # ignore sub-200ms blips (coughs/clicks)
MAX_UTTER_MS = 15000.0  # hard cap so a long monologue still gets processed
BARGE_MIN_FRAMES = 5    # ~100 ms of speech while we talk = barge-in


# --------------------------------------------------------------------------- #
# STT engine — lazy singleton (model load is heavy; reuse across calls).
# --------------------------------------------------------------------------- #
_STT_ENGINE: Optional[tuple] = None   # ("vosk", model) | ("whisper", model)
_STT_INIT = False


def _get_stt() -> Optional[tuple]:
    """Load (once) the best available STT model. vosk if VOSK_MODEL_PATH set,
    else faster-whisper 'tiny'. Returns None if neither usable."""
    global _STT_ENGINE, _STT_INIT
    if _STT_INIT:
        return _STT_ENGINE
    _STT_INIT = True

    vosk_path = os.environ.get("VOSK_MODEL_PATH")
    if _VOSK_OK and vosk_path and os.path.isdir(vosk_path):
        try:
            import vosk  # type: ignore

            vosk.SetLogLevel(-1)
            _STT_ENGINE = ("vosk", vosk.Model(vosk_path))
            logger.info(f"[vobiz-stream] STT engine: vosk ({vosk_path})")
            return _STT_ENGINE
        except Exception as e:
            logger.warning(f"[vobiz-stream] vosk load failed: {e}")

    if _FWHISPER_OK:
        try:
            from faster_whisper import WhisperModel  # type: ignore

            # base >> tiny for Hindi (tiny Hindi pe bahut weak hai); CPU pe
            # short utterances ~1-2.5s — acceptable. Env: FWHISPER_MODEL.
            model_size = os.environ.get("FWHISPER_MODEL", "base")
            _STT_ENGINE = ("whisper", WhisperModel(model_size, device="cpu", compute_type="int8"))
            logger.info(f"[vobiz-stream] STT engine: faster-whisper ({model_size})")
            return _STT_ENGINE
        except Exception as e:
            logger.warning(f"[vobiz-stream] faster-whisper load failed: {e}")

    logger.warning("[vobiz-stream] no STT engine available — call will be deaf")
    _STT_ENGINE = None
    return None


def _stt_sync(kind: str, model: Any, pcm16: bytes) -> str:
    """Blocking transcription of PCM16 16 kHz bytes -> text. Runs in executor."""
    try:
        if kind == "vosk":
            import vosk  # type: ignore

            rec = vosk.KaldiRecognizer(model, STT_RATE)
            rec.AcceptWaveform(pcm16)
            res = json.loads(rec.FinalResult() or "{}")
            return (res.get("text") or "").strip()
        if kind == "whisper":
            import numpy as np  # numpy is a core dep

            audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
            # LANGUAGE FORCE (live-call lesson 2026-06-07): bina language ke
            # whisper Hindi speech ko English samajh ke garbage deta tha
            # ("Bory", "You have to call it a group here") → LLM bhi bhatak
            # jata tha. hi = Hindi/Hinglish dono ke liye sahi (Devanagari out,
            # Gemini handle karta hai). Env override: FWHISPER_LANG (e.g. en).
            lang = os.environ.get("FWHISPER_LANG", "hi")
            segments, _ = model.transcribe(
                audio,
                beam_size=1,
                language=lang,
                vad_filter=True,  # whisper-side VAD trims noise/silence edges
                condition_on_previous_text=False,  # short utterances — no drift
            )
            return " ".join(seg.text for seg in segments).strip()
    except Exception as e:
        logger.warning(f"[vobiz-stream] STT failed: {e}")
    return ""


# --------------------------------------------------------------------------- #
# VAD helper — RMS of signed-16-bit LE PCM. Prefers audioop; never raises.
# --------------------------------------------------------------------------- #
def _pcm_rms(pcm16: bytes) -> int:
    """RMS amplitude of PCM16 (little-endian) bytes for energy VAD.

    Uses audioop.rms when available; falls back to a pure-Python loop so VAD
    keeps working even if audioop could not be imported. If both fail, returns
    a high value so we err on the side of 'speech' rather than going deaf."""
    if not pcm16:
        return 0
    if _AUDIOOP_OK:
        try:
            return audioop.rms(pcm16, 2)
        except Exception:
            pass
    try:
        import struct

        n = len(pcm16) // 2
        if n == 0:
            return 0
        samples = struct.unpack("<%dh" % n, pcm16[: n * 2])
        return int((sum(s * s for s in samples) / n) ** 0.5)
    except Exception:
        return 32767  # last resort: treat as speech (never permanently deaf)


# --------------------------------------------------------------------------- #
# Per-call session — one instance per WebSocket (per Vobiz docs).
# --------------------------------------------------------------------------- #
class VobizStreamSession:
    """Drives one streamed phone call: listen -> understand -> reply -> speak,
    with energy-VAD turn-taking and barge-in. Never raises out of handle()."""

    def __init__(self, websocket: Any, niche: str = "general",
                 client_id: Optional[str] = None, client_name: str = "Demo Co",
                 voice: str = "hi-IN-SwaraNeural") -> None:
        self.ws = websocket
        self.niche = (niche or "general").strip() or "general"
        self.client_id = client_id
        self.client_name = client_name or "Demo Co"
        self.voice = voice

        self.stream_sid: Optional[str] = None
        self.hist: List[Dict[str, str]] = []   # {role: user|assistant, content}
        self._closed = False

        # turn-taking / VAD state
        self._speech_buf: List[bytes] = []
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._had_speech = False
        self._vad_rms = _VAD_RMS

        # playback / barge-in state
        self._speaking = False
        self._play_task: Optional[asyncio.Task] = None
        self._barge_frames = 0
        self._thinking = False
        self._bg_tasks: set = set()   # keep refs so tasks aren't GC'd mid-run

        # lazy helpers
        self._brain = None
        self._brain_tried = False
        self._ndm = None          # NaturalDialogManager fallback (cached — heavy)
        self._ndm_tried = False

    # ------------------------------------------------------------------ #
    # Main receive loop
    # ------------------------------------------------------------------ #
    async def handle(self) -> None:
        try:
            await self.ws.accept()
        except Exception as e:
            logger.warning(f"[vobiz-stream] accept failed: {e}")
            return
        logger.info(
            f"[vobiz-stream] WS open niche={self.niche} client={self.client_id} "
            f"(STT={STT_AVAILABLE} TTS={TTS_AVAILABLE} audioop={_AUDIOOP_OK})"
        )
        try:
            while not self._closed:
                try:
                    msg = await self.ws.receive()
                except Exception:
                    break  # disconnected
                mtype = msg.get("type")
                if mtype == "websocket.disconnect":
                    break
                raw = msg.get("text")
                if raw is None and msg.get("bytes") is not None:
                    try:
                        raw = msg["bytes"].decode("utf-8", "ignore")
                    except Exception:
                        raw = None
                if not raw:
                    continue
                try:
                    await self._on_event(raw)
                except Exception as e:
                    logger.warning(f"[vobiz-stream] event error: {e}")
        finally:
            await self._cleanup()

    async def _on_event(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except Exception:
            logger.warning(f"[vobiz-stream] non-JSON frame: {raw[:120]!r}")
            return
        # Protocol visibility: pehle kuch raw events INFO me — Vobiz ke exact
        # field names/shape capture karne ke liye (media payload truncate).
        self._event_count = getattr(self, "_event_count", 0) + 1
        if self._event_count <= 6 and data.get("event") != "media":
            logger.info(f"[vobiz-stream] raw#{self._event_count}: {str(data)[:300]}")
        elif self._event_count <= 3:
            logger.info(f"[vobiz-stream] raw#{self._event_count} media keys: {list(data.keys())}")

        event = data.get("event")
        # Vobiz stream id field = "streamId" (NOT Twilio's streamSid). Capture
        # any known variant, top-level or inside start{}. playAudio doesn't even
        # need it — we only keep it for logging/checkpoints.
        start = data.get("start") or {}
        sid = (
            data.get("streamId") or data.get("streamSid") or data.get("stream_sid")
            or start.get("streamId") or start.get("streamSid") or start.get("stream_sid")
        )
        if sid and not self.stream_sid:
            self.stream_sid = sid

        if event == "media":
            payload = (data.get("media") or {}).get("payload")
            if payload:
                # Greet on first audio too (in case start was missed); NOT gated
                # on sid — Vobiz playAudio carries no stream id.
                await self._maybe_greet()
                await self._on_media(payload)
        elif event == "start":
            params = start.get("customParameters") or {}
            self.niche = (params.get("niche") or self.niche).strip() or "general"
            self.client_id = params.get("client_id") or self.client_id
            logger.info(f"[vobiz-stream] start streamId={self.stream_sid} niche={self.niche}")
            await self._maybe_greet()
        elif event == "dtmf":
            digit = (data.get("dtmf") or {}).get("digit")
            logger.info(f"[vobiz-stream] dtmf={digit}")
        elif event == "stop":
            logger.info(f"[vobiz-stream] stop sid={self.stream_sid}")
            self._closed = True
        elif event == "playedStream":
            logger.debug("[vobiz-stream] playedStream (playAudio finished) — no-op")
        elif event == "clearedAudio":
            logger.debug("[vobiz-stream] clearedAudio (buffer flushed) — no-op")
        elif event == "connected":
            logger.info("[vobiz-stream] connected event")

    async def _maybe_greet(self) -> None:
        """Greet exactly once. NOT gated on stream id — Vobiz playAudio needs
        no sid, so we can (and must) speak as soon as the stream starts."""
        if getattr(self, "_greeted", False):
            return
        self._greeted = True
        await self._greet()

    # ------------------------------------------------------------------ #
    # Inbound audio -> VAD -> utterance
    # ------------------------------------------------------------------ #
    async def _on_media(self, payload: str) -> None:
        # L16: the base64 payload IS raw PCM16 @16 kHz already — NO µ-law decode
        # and NO 8k->16k resample. Decoded bytes go straight to VAD + STT buffer.
        try:
            pcm16 = base64.b64decode(payload)
        except Exception:
            return
        if not pcm16:
            return
        rms = _pcm_rms(pcm16)
        is_speech = rms >= self._vad_rms
        dur_ms = (len(pcm16) / 2) / SAMPLE_RATE * 1000.0  # 640 bytes == 20 ms

        # While we're speaking: only watch for barge-in.
        if self._speaking:
            if is_speech:
                self._barge_frames += 1
                if self._barge_frames < BARGE_MIN_FRAMES:
                    return
                await self._barge_in()  # cancels playback, sends clearAudio, falls through
            else:
                self._barge_frames = 0
                return

        # While thinking (STT+LLM+synth in flight): drop input to avoid pile-up.
        if self._thinking:
            return

        if is_speech:
            self._speech_buf.append(pcm16)
            self._speech_ms += dur_ms
            self._silence_ms = 0.0
            self._had_speech = True
        elif self._had_speech:
            self._speech_buf.append(pcm16)  # keep a little trailing silence
            self._silence_ms += dur_ms

        ended = self._had_speech and self._silence_ms >= SILENCE_MS and self._speech_ms >= MIN_SPEECH_MS
        too_long = self._speech_ms >= MAX_UTTER_MS
        if ended or too_long:
            utt = b"".join(self._speech_buf)
            self._reset_speech()
            self._spawn(self._on_utterance(utt))

    def _spawn(self, coro) -> None:
        """Fire-and-forget a coroutine, holding a ref until it finishes."""
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    def _reset_speech(self) -> None:
        self._speech_buf = []
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._had_speech = False

    async def _on_utterance(self, pcm16: bytes) -> None:
        if self._thinking:
            return
        self._thinking = True
        try:
            text = await self._stt(pcm16)
            if not text:
                return
            logger.info(f"[vobiz-stream {self.stream_sid}] user: {text}")
            self.hist.append({"role": "user", "content": text})
            reply = await self._think(text)
            if reply:
                logger.info(f"[vobiz-stream {self.stream_sid}] bot: {reply}")
                self.hist.append({"role": "assistant", "content": reply})
                await self._say(reply)
        except Exception as e:
            logger.warning(f"[vobiz-stream] utterance handling failed: {e}")
        finally:
            self._thinking = False

    async def _stt(self, pcm16: bytes) -> str:
        eng = _get_stt()
        if not eng:
            return ""
        kind, model = eng
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, _stt_sync, kind, model, pcm16)
        except Exception as e:
            logger.warning(f"[vobiz-stream] STT executor failed: {e}")
            return ""

    # ------------------------------------------------------------------ #
    # Thinking (LLM) — niche-aware Hinglish reply, defensive fallbacks.
    # ------------------------------------------------------------------ #
    async def _think(self, text: str) -> str:
        brain = self._get_brain()
        if brain is not None:
            try:
                reply = await brain.generate_response(
                    conversation_history=self.hist,
                    niche=self.niche,
                    client_name=self.client_name,
                    client_service=self.niche,
                )
                if reply and str(reply).strip():
                    return str(reply).strip()
            except Exception as e:
                logger.warning(f"[vobiz-stream] LLM failed: {e}")

        # Fallback: NaturalDialogManager (rule-based reply, degrades w/o LLM).
        ndm = self._get_ndm()
        if ndm is not None:
            try:
                state = ndm.new_conversation()
                state.history = list(self.hist)
                out = await ndm.respond(text, state)
                if getattr(out, "text", "").strip():
                    return out.text.strip()
            except Exception as e:
                logger.debug(f"[vobiz-stream] natural_dialog fallback failed: {e}")

        return "Maaf kijiye, awaaz thodi clear nahi aayi — aap dobara bata sakte hain?"

    def _get_ndm(self):
        if self._ndm_tried:
            return self._ndm
        self._ndm_tried = True
        try:
            from app.voice_agent.natural_dialog import NaturalDialogManager

            # brain=False sentinel keeps it rule-based (None would auto-build LLM).
            self._ndm = NaturalDialogManager(
                niche=self.niche, client_name=self.client_name,
                client_service=self.niche, brain=False,
            )
        except Exception as e:
            logger.debug(f"[vobiz-stream] NaturalDialogManager unavailable: {e}")
            self._ndm = None
        return self._ndm

    def _get_brain(self):
        if self._brain_tried:
            return self._brain
        self._brain_tried = True
        try:
            from app.voice_agent.llm_brain import LLMBrain

            self._brain = LLMBrain()
        except Exception as e:
            logger.warning(f"[vobiz-stream] LLMBrain unavailable: {e}")
            self._brain = None
        return self._brain

    # ------------------------------------------------------------------ #
    # Outbound speech — EdgeTTS -> µ-law -> 20 ms frames
    # ------------------------------------------------------------------ #
    def _opening_line(self) -> str:
        hook = ""
        try:
            from app.niches import NICHES

            hook = (NICHES.get(self.niche, {}).get("pitch_hook") or "").strip()
        except Exception:
            pass
        if hook:
            return (f"Namaste! Main {self.client_name} ki taraf se baat kar rahi hoon. "
                    f"Hum {hook}. Do minute baat kar sakte hain?")
        return ("Namaste! Main LeadGen AI ki taraf se ek demo call kar rahi hoon. "
                "Do minute baat kar sakte hain?")

    async def _greet(self) -> None:
        line = self._opening_line()
        self.hist.append({"role": "assistant", "content": line})
        await self._say(line)

    async def _say(self, text: str) -> None:
        if not text or not text.strip():
            return
        if not TTS_AVAILABLE:
            logger.warning("[vobiz-stream] TTS unavailable (edge-tts/pydub) — skipping speak")
            return
        self._stop_play()
        self._speaking = True       # set early so synth window also detects barge-in
        self._barge_frames = 0
        try:
            pcm = await self._synth_pcm(text)
        except Exception as e:
            logger.warning(f"[vobiz-stream] TTS synth failed: {e}")
            self._speaking = False
            return
        if not pcm or not self._speaking:   # barged-in during synthesis
            self._speaking = False
            return
        self._play_task = asyncio.create_task(self._run_play(pcm))

    async def _synth_pcm(self, text: str) -> bytes:
        """EdgeTTS MP3 -> raw PCM16 16k mono (L16) bytes. Heavy decode in executor.
        NO µ-law, NO 8k — Vobiz playAudio takes L16 @16 kHz directly."""
        import edge_tts  # lazy

        communicate = edge_tts.Communicate(text, self.voice)
        mp3 = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                mp3.write(chunk.get("data") or b"")
        data = mp3.getvalue()
        if not data:
            return b""

        def _decode(mp3_bytes: bytes) -> bytes:
            from pydub import AudioSegment  # needs ffmpeg at runtime

            seg = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
            seg = seg.set_frame_rate(SAMPLE_RATE).set_channels(1).set_sample_width(2)
            return seg.raw_data

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _decode, data)

    async def _run_play(self, pcm: bytes) -> None:
        try:
            for i in range(0, len(pcm), FRAME_PCM):
                frame = pcm[i:i + FRAME_PCM]
                if len(frame) < FRAME_PCM:
                    frame = frame + PCM_SILENCE * (FRAME_PCM - len(frame))
                # Vobiz playAudio: L16 @16k, base64 payload, NO streamSid field.
                await self._send({
                    "event": "playAudio",
                    "media": {
                        "contentType": "audio/x-l16",
                        "sampleRate": SAMPLE_RATE,
                        "payload": base64.b64encode(frame).decode("ascii"),
                    },
                })
                await asyncio.sleep(0.02)  # pace at ~real-time (20 ms/frame)
        except asyncio.CancelledError:
            pass  # barge-in
        except Exception as e:
            logger.debug(f"[vobiz-stream] playback error: {e}")
        finally:
            self._speaking = False

    def _stop_play(self) -> None:
        if self._play_task and not self._play_task.done():
            self._play_task.cancel()
        self._play_task = None

    async def _barge_in(self) -> None:
        """User started talking over us — stop playback and flush Vobiz buffer."""
        self._barge_frames = 0
        self._stop_play()
        self._speaking = False
        await self._send({"event": "clearAudio"})
        logger.debug("[vobiz-stream] barge-in: playback cleared (clearAudio)")

    # ------------------------------------------------------------------ #
    async def _send(self, obj: Dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            await self.ws.send_text(json.dumps(obj))
        except Exception as e:
            logger.debug(f"[vobiz-stream] send failed: {e}")
            self._closed = True

    async def _cleanup(self) -> None:
        self._closed = True
        self._stop_play()
        turns = len([m for m in self.hist if m.get("role") == "user"])
        logger.info(f"[vobiz-stream] WS closed sid={self.stream_sid} user_turns={turns}")


__all__ = ["VobizStreamSession", "STT_AVAILABLE", "TTS_AVAILABLE"]
