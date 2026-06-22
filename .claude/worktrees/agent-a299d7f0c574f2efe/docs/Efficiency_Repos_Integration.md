# Efficiency Repos — open-source integrations (2026-06-08)

Goal: free-stack, CPU-only, India/Hindi-friendly open-source repos jo platform ki
efficiency/quality badhayein. Sab MIT/open (Piper GPL note niche). Paid/GPU kuch nahi.

## Priority table

| # | Repo | Kya deta hai | Free-stack? | Effort | Risk | Priority |
|---|------|--------------|-------------|--------|------|----------|
| 1 | **Silero VAD** (snakers4/silero-vad) | Robust speech/non-speech gate (RMS se behtar, noise/echo pe false-trigger nahi) | ✅ MIT, 2MB ONNX, <1ms/frame CPU | Low (module ban chuka) | Low (OFF default, fallback) | **NOW** |
| 2 | **Smart Turn v3** (pipecat-ai/smart-turn-v3) | *Semantic* end-of-turn — caller ne baat KHATAM ki ya sirf rukA, samajhta hai → mid-sentence cut-off fix | ✅ open weights, 8MB int8 ONNX, ~12ms CPU, Hindi | Medium (pipecat + audio test) | Medium | **NEXT** |
| 3 | **LiteLLM** (BerriAI/litellm) | 100+ LLM ek unified interface; built-in fallback/cooldown/retry/cost-track → `free_ai.py` hand-rolled chain replace | ✅ MIT (SDK mode, no proxy) | Medium (refactor) | Medium (working code) | OPTIONAL |
| 4 | **Piper TTS** (OHF-Voice/piper1-gpl) | Offline CPU Hindi neural TTS → EdgeTTS-403 ka offline fallback (network-free) | ⚠️ free, **GPL** (backend-only OK) | Medium | Low-Med | OPTIONAL |
| 5 | **RealtimeSTT** (KoljaB/RealtimeSTT) | faster-whisper + Silero streaming wrapper (low-latency STT loop ready-made) | ✅ MIT, CPU | Medium | Low | OPTIONAL |

Marketing-side: open-source me mature free tool nahi mila jo current custom modules
se behtar ho — yeh sab voice/AI pipeline efficiency pe focused hain (wahi sabse bada
pain point + ROI hai per session history).

---

## 1) Silero VAD — DONE (enable karna baaki)
- **Added**: `app/voice_agent/turn_detector.py` → `get_speech_gate().is_speech(pcm16_16k)`.
  Defensive: OFF default, dep/load/inference fail → `None` → purana RMS gate use hota
  (zero behaviour change jab tak enable na ho). Sandbox-verified graceful.
- **requirements.txt**: `# silero-vad>=5.1` (commented, optional).
- **Enable (test web-call pe pehle, phone baad me)**:
  1. `.venv/bin/pip install silero-vad` (VPS + Windows venv) — torch aata hai (~heavy, one-time).
  2. `.env`: `USE_SILERO_VAD=1` (+ optional `SILERO_VAD_THRESHOLD=0.5`).
  3. Wire in `app/telephony/vobiz_stream.py` (jahan RMS se speech decide hota, ~5 lines):
     ```python
     from app.voice_agent.turn_detector import get_speech_gate
     # ... per-frame speech decision ke paas:
     is_speech = rms > self._vad_rms                 # existing RMS gate
     sil = get_speech_gate().is_speech(pcm16_16k)    # 16k PCM (wahi jo STT ko jata)
     if sil is not None:                              # None = disabled -> RMS rakho
         is_speech = sil
     ```
  4. `scripts/agent_tester.py` (free) chalao → scorecard compare. Theek lage → phone verify.
- **Win**: kam false-speech triggers, saaf utterance boundaries → kam garbage STT, kam wasted LLM calls (paisa + latency bachta).

## 2) Smart Turn v3 — NEXT (biggest quality fix)
- Yeh "VAD aadha vakya kaat raha tha" ka asli fix hai — silence-timer (650ms) ki jagah
  *semantic* end-of-turn. Caller soch ke ruke to bot beech me nahi ghusega.
- **Repo/model**: `pipecat-ai/smart-turn-v3`; pipecat ke andar `LocalSmartTurnAnalyzerV3`
  (bundled `smart-turn-v3.2-cpu` ONNX, ~12ms CPU, Hindi). Scaffold + env flag already in
  `turn_detector.py` (`get_smart_turn()`, `USE_SMART_TURN=1`) — abhi conservative `None`.
- **Plan (ek alag chat me, test ke saath)**: `pip install pipecat-ai` → existing
  `app/voice_agent/pipecat_pipeline.py` skeleton ke saath wire → `LocalSmartTurnAnalyzerV3`
  ka exact inference call confirm (pipecat version pe) → `is_endpoint()` finalize →
  vobiz_stream turn-end ko silence-timer ke saath OR-combine → web-call pe tune.
- **Win**: human-jaisa turn-taking, mid-sentence cut khatam — user ki #1 voice complaint.

## 3) LiteLLM — OPTIONAL (dev-efficiency)
- `free_ai.py` ka multi-provider chain (Cerebras→Groq→xai→openrouter→Gemini) khud maintain
  karna padta. LiteLLM SDK isko ek line me + built-in fallback/cooldown(429)/retry/cost.
- Trade-off: kaam-karta code refactor = risk. Karo to: LiteLLM ko `free_ai.py` ke andar
  ek provider-adapter ki tarah lagao (poora chain replace mat karo) → A/B → confident hone
  pe switch. Abhi LLM working hai, isliye low urgency.

## 4) Piper TTS — OPTIONAL (resilience)
- EdgeTTS pe pehle 403 aaya tha (MS token). Piper offline Hindi TTS = network-free fallback.
- **License GPL** (original repo Oct-2025 archive; active fork `OHF-Voice/piper1-gpl`). Hum
  binary distribute nahi karte (SaaS backend), isliye GPL generally OK — par dhyaan rakho.
- Karo to: `tts.py` me EdgeTTS-fail → Piper fallback (voice quality EdgeTTS se halki).

## 5) RealtimeSTT — OPTIONAL
- faster-whisper + Silero VAD ka ready streaming wrapper. Hum already faster-whisper + (ab)
  Silero use kar rahe, isliye sirf tab jab apna STT loop simplify karna ho. Low priority.

---

### Recommended order
1. **Silero VAD enable + test** (module ready) — turant, low-risk win.
2. **Smart Turn v3** — alag chat, pipecat ke saath, web-call pe tune (bada quality jump).
3. LiteLLM / Piper / RealtimeSTT — jab specific zaroorat (LLM-maintenance / TTS-resilience).

Sab voice changes: pehle FREE web-call (`/app/test-call`) + `scripts/agent_tester.py`,
phone sirf final verify (Vobiz balance bachao).
