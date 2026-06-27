---
name: voice-agent-kb
description: LeadGen AI voice agent internals knowledge base — TelecallerBrain vs NaturalDialog, free_ai provider chain, guardrails, providers, telephony, automation pipeline kaise fit hote hain. Use jab voice agent edit/debug karo, provider ya language add karo, prompt tune karo, conversation bug fix karo, ya "agent kaise kaam karta hai" samjhana ho. Carefully-wired defensive pieces todne se bachata.
---

# Voice Agent Knowledge Base (LeadGen AI)

## Brains: TelecallerBrain (live calls) vs NaturalDialogManager (web/eval)
- **Live phone + web-call PRIMARY = `telecaller_brain.py` (`TelecallerBrain`)** — lean prompt, niche script, ≤2 sentences/1 question, KB-grounded (ACP: acknowledge-confirm-prompt). Yeh use hota hai jab call lagti hai.
- **`natural_dialog.py` (`NaturalDialogManager`)** = full orchestrator for web-call fallback + the eval suite. Flow per turn: AMD check -> guardrails input (PII redact + injection block) -> "unclear" handling -> classify intent + affect -> generate reply (LLM via brain, else rule-based) -> humanize -> guardrails output. LAZILY loads + wires every enhancement; all defensive (missing dep -> None -> skip, never crash).

Wired components (each its own module):
- LLM layer: `free_ai.py` (`chat`/`transcribe_audio`) = the real FREE multi-provider chain (Mistral mistral-small-latest primary → Groq llama-3.1-8b-instant → Cerebras gpt-oss-120b 429-prone → … → Gemini, escalating circuit-breaker) — yeh default hai, paid nahi. `llm_brain.py` (`LLMBrain`) = optional BYOK single-model wrapper; agar use karo to **model id real ho** ("gemini-2.5-flash"), bare "gemini" invalid (routing substrings: "gemini","gpt","claude","vertex","local").
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
`ProviderRegistry` with STT/TTS/LLM (BYOK swap layer, separate from the always-on `free_ai.py` chain). Selected via env `STT_PROVIDER` / `TTS_PROVIDER` / `LLM_PROVIDER`. Free defaults: **STT Groq whisper-large-v3** (Vosk/local fallback), **TTS EdgeTTS hi-IN-SwaraNeural** (`edge-tts>=7.2.0` zaroori), **LLM Mistral mistral-small-latest** primary (chain: → Groq → Cerebras → … → Gemini deep fallback, NOT default). Add a provider by implementing `STTProvider.transcribe` / `TTSProvider.synthesize` and `registry.register(kind, name, factory)`.

## Telephony: `app/telephony/`
`telephony_service.py` (`get_telephony_service`) picks provider from env (twilio/vobiz/sip/simulation; Vobiz = active India-native provider). No keys -> **simulation mode** (safe). `media_stream.py` bridges Twilio Media Streams. Real calls need a SIP trunk + DLT registration (India).

## Automation: `app/automation/`
`orchestrator_pipeline.py` (`LeadGenPipeline.run_campaign`) = scrape -> clean/DND -> calling-window gate (pipeline `CALL_WINDOW` 9-21; promo calls still bound to 9am-7pm by `compliance.py`) -> WhatsApp -> AI call -> score -> deliver -> bill. `agent_pool.py` runs many clients concurrently.

## Test before shipping
- Eval suite (7 personas): `python -m app.voice_agent.eval_suite` (expect ~100% pass).
- Browser web-call (FREE tuning path): `/app/test-call`.
- Voice change ke baad scorecard mandatory: `python scripts/agent_tester.py`. Quality already on free chain (no Gemini key needed); best Hindi voice (optional) = `SARVAM_API_KEY` + `STT_PROVIDER=sarvam` (Saaras STT + Bulbul TTS).

## Don't break
Every enhancement is loaded defensively — keep the try/except + `None` fallbacks. Don't make any component a hard dependency, or the agent stops degrading gracefully.

## Enterprise gate (voice internals = HIGH-RISK)
Operating loop — Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). **Change-risk tier: High-risk** — brain/provider/prompt/guardrail change live calls + billing + compliance ko touch karta; additive + flag-gated + defensive rakho.

**Cost/quota fallback (free-stack, never paid by default):** `free_ai.py` chain = Mistral mistral-small-latest primary → Groq llama-3.1-8b-instant → Cerebras gpt-oss-120b (429-prone) → … → Gemini deep fallback, **escalating circuit-breaker** (429/quota → 60s→2x→30min cap, credit-exhaust → straight 30min, success resets). Naya provider add = chain me deep daalo, primary mat banao bina ok-rate proof. STT Groq whisper-large-v3 → Gemini → local; TTS EdgeTTS hi-IN-SwaraNeural (`edge-tts>=7.2.0` warna 403).

**Defensive wiring (don't break):** har enhancement lazy-load + try/except + `None`-skip — koi component hard-dependency mat banao. `LLMBrain` BYOK me model-id REAL ho ("gemini-2.5-flash"; bare "gemini" invalid). Guardrails (`guardrails.py`) PII-redact + injection-block = security gate, hata mat.

**Compliance (fail-CLOSED):** persona prompt me **AI-disclosure unless-asked** rule + **never reveal-AI** balance carefully wired; greeting AI-disclosure (TRAI) telephony-side. Pipeline `compliance.py` promo calls 9am–7pm + DND fail-CLOSED — brain change isko bypass na kare. DPDP: guardrails PII-redaction intact.

**Observability:** LLM chain health `/api/growth/infra/llm` (ok-rate/fallback/cooldowns); voice change = `scripts/agent_tester.py` scorecard.

**Rollback (NAMED):** provider/prompt regression → revert + `docker compose build app` + `up -d --no-deps app` recreate (stale .pyc clear) → `/health`=`environment:production`.

**Evidence (done):** `python -m app.voice_agent.eval_suite` (~100% pass) + `python scripts/agent_tester.py` (no double/empty/repeat regression) + `.venv\Scripts\python.exe scripts\prod_check.py` green. FREE web-call (`/app/test-call`) pe verify; phone = final only.
