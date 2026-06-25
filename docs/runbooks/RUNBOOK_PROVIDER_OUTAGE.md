# Runbook — Provider Outage (LLM / STT / TTS)

## Scenario
A free-stack AI provider degrades: rate-limit (429), quota/credit exhaustion, or hard
outage. Symptoms: agents slow/empty, voice "deaf" (STT=0) or silent (TTS 403),
council/marketing drafts failing.

## Detection
- `llm_metrics` per-provider ok-rate drops; circuit-breaker cooldowns spike.
- Voice: `scripts/call_health_check.py` / `agent_tester.py` scorecard regressions.
- Sentry error burst; ntfy `ops_alerts`.

## Architecture (why a single provider rarely takes you down)
- **LLM chain** (`free_ai.py` ~L420): Ollama → **Mistral `mistral-small-latest` (primary)**
  → Groq `llama-3.1-8b-instant` → Cerebras → Gemini → SambaNova → **NVIDIA NIM** → OpenRouter.
- **Circuit-breaker:** 429/quota → escalating cooldown 60s→2x…→30min cap; "per day/TPD/limit"
  + credit-exhaust (402) → straight 30min; success resets. Failover is automatic per-call.
- **Voice LLM:** Gemini 2.5-flash-lite primary (`VOICE_GEMINI_PRIMARY=1`) with a **9-key
  rotation pool** (`data/voice_gemini_keys.json`, 429 → `advance_key` auto-rotate) → falls
  back to the `free_ai` chain on quota.
- **STT:** Groq `whisper-large-v3` → Gemini audio → local faster-whisper.
- **TTS:** EdgeTTS `hi-IN-SwaraNeural` (needs `edge-tts>=7.2.0`, else 403).

## Immediate Response
1. Confirm it is the provider, not the app: check `llm_metrics` / breaker state.
2. **LLM:** chain auto-fails-over — usually no action. If the *primary* is flapping,
   the breaker already routed around it. Watch ok-rate recover.
3. **Voice quota:** if Gemini pool is exhausted, add keys (no restart) via admin
   "Voice Keys" page / `POST /api/admin/voice/gemini-keys` (per-key Google-validate).
4. **NVIDIA NIM** is deep-tail (≈5k LIFETIME credits) — if it is burning, an upstream
   provider is down; fix that, don't lean on NIM.

## Diagnosis
- Which provider, which error class (429 vs 402-credit vs 5xx)? `llm_metrics`.
- TTS 403 → check `edge-tts` version in the image.
- STT=0 on phone → check `VOBIZ_AUDIO_TRACK=both` + flat-payload fallback (`phone-agent-deaf` lesson).
- Pending in-container patches: `scripts/patch_status.py` (approve/reject CLI).

## Recovery
1. Let the breaker drain cooldowns (success auto-resets). No code change for a transient 429.
2. Add Gemini keys to the pool for sustained voice load.
3. If a provider is permanently changed (model renamed/removed), update `free_ai.py`
   chain + env model var, then deploy (`/ship`).

## Post-Incident
- RCA: was it quota planning (TPD) or a genuine outage? Tune chain order / breaker if a
  provider is chronically unreliable.
- Regression: `tests/test_circuit_breaker.py`, `test_llm` suites; voice → `agent_tester.py`.
- Never hardcode a paid provider into the hot path (user decision: free-stack).
