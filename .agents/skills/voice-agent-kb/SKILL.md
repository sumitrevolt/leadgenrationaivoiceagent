---
name: voice-agent-kb
description: Knowledge base for the LeadGen AI voice agent internals — how the conversation brain, providers, guardrails, telephony, and automation fit together. Use when editing/debugging the voice agent, adding a provider or language, tuning prompts, fixing a conversation bug, or explaining how the agent works. Prevents breaking the carefully-wired pieces.
---

# Voice Agent Knowledge Base (LeadGen AI)

## The brain: `app/voice_agent/natural_dialog.py` (`NaturalDialogManager`)
The single orchestrator for a conversation. Flow per turn: AMD check -> guardrails input (PII redact + injection block) -> "unclear" handling -> classify intent + affect -> generate reply (LLM via brain, else rule-based) -> humanize -> guardrails output. It LAZILY loads and wires every enhancement; all are defensive (missing dep -> None -> skip, never crash).

Wired components (each its own module):
- LLM brain: `llm_brain.py` (`LLMBrain`). **Model id must be real** (e.g. `gemini-2.5-flash`); the bare value `gemini` is invalid. Provider routing keys on substrings ("gemini","gpt","Codex","vertex","local").
- KB / RAG: `knowledge_base.py` + `kb_loader.py` (`bootstrap_default_kb`) — grounded answers, keyword backend by default (Chroma if real embedder). Cached via the latency optimizer.
- In-call tools: `function_calling.py` (`build_default_registry`, `parse_tool_call`) — book_appointment, check_availability, transfer_to_human, capture_lead_info, get_pricing_info, end_call.
- AMD: `amd.py` (voicemail detection -> leave message / hangup).
- Fillers: `fillers.py` (latency-masking "ek second…").
- Guardrails: `guardrails.py` (`get_guardrails`) — PII redaction (phone/email/Aadhaar/PAN/card/UPI), prompt-injection block, output validation.
- Latency: `latency.py` (`get_optimizer`) — response cache + first-sentence chunking.
- Indic providers: `indic_providers.py` (`register_indic_providers`) — Sarvam Saaras STT + Bulbul TTS; `STT_PROVIDER=sarvam`.

## Persona rules baked into the prompt (`VOICE_SYSTEM_PROMPT`)
Short (1-2 lines), Hinglish/match-customer-language, acknowledge-then-answer, ONE question at a time, **female agent "Riya" -> feminine verbs** (samajhti hoon), never say "[Your Name]" or reveal being an AI unless asked. When editing the prompt, keep these.

## Providers (BYOK): `app/voice_agent/providers.py`
`ProviderRegistry` with STT/TTS/LLM. Selected via env `STT_PROVIDER` / `TTS_PROVIDER` / `LLM_PROVIDER`. Free defaults: Vosk/Whisper STT, EdgeTTS TTS, Gemini free-tier LLM. Add a provider by implementing `STTProvider.transcribe` / `TTSProvider.synthesize` and `registry.register(kind, name, factory)`.

## Telephony: `app/telephony/`
`telephony_service.py` (`get_telephony_service`) picks provider from env (twilio/exotel/sip/simulation). No keys -> **simulation mode** (safe). `media_stream.py` bridges Twilio Media Streams. Real calls need a SIP trunk + DLT registration (India).

## Automation: `app/automation/`
`orchestrator_pipeline.py` (`LeadGenPipeline.run_campaign`) = scrape -> clean/DND -> 9am-9pm gate -> WhatsApp -> AI call -> score -> deliver -> bill. `agent_pool.py` runs many clients concurrently.

## Test before shipping
- Eval suite (7 personas): `python -m app.voice_agent.eval_suite` (expect ~100% pass).
- Browser web-call: `/app/test-call`.
- Quality jump needs `GEMINI_API_KEY` + `DEFAULT_LLM=gemini-2.5-flash`; best Hindi voice needs `SARVAM_API_KEY` + `STT_PROVIDER=sarvam`.

## Don't break
Every enhancement is loaded defensively — keep the try/except + `None` fallbacks. Don't make any component a hard dependency, or the agent stops degrading gracefully.
