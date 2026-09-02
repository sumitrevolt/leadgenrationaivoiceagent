---
name: llm-quota-ops
description: Free-LLM provider quota/cooldown ops — Groq TPD khatam, Cerebras 429 burst, ok-rate tank (0.4 jaisa), fallback-rate high. Use jab "LLM slow/atka", agents degraded, ya llm_metrics kharab dikhe. llm-error-analysis = QUALITY; yeh skill = QUOTA/AVAILABILITY.
---

# LLM Quota Ops (free-stack chain ki availability)

## Chain truth (free_ai.py `chat()`)
LLM chain order = **LIVE measured ok-rate** se set (data/llm_calls.jsonl), theory se NAHI — code comment me re-tune date + per-provider ok% likha rehta hai. Current shape (2026-06-13 audit):
`mistral-small → groq llama-3.1-8b-instant → cerebras gpt-oss-120b → [ollama self-hosted] → gemini-2.0-flash-lite → sambanova 70B → openrouter (4 keys × 3 free models)`.
- **mistral/groq = proven workhorse (~96-99% ok)** isliye PEHLE; **cerebras 120B 429-queue-prone (~9%)** isliye demote hua (free-unlimited par burst pe trip karta). Saare providers retained = fallback headroom; sirf ORDER badla. Naye keys aaye to wapas tune.
- **Ollama (`OLLAMA_URL` set hote hi active)** = self-hosted, UNLIMITED, no quota/429 — guaranteed floor. `OLLAMA_PRIMARY=1` → sabse pehle.
- xAI/grok = credits-based, chain me NAHI (key-compat only).
- STT: sirf Groq `whisper-large-v3-turbo` (+ Gemini audio → local faster-whisper weak).

## Circuit-breaker behaviour (a2f1415)
- 429/quota/queue → ESCALATING cooldown 60s→2x→30min cap (`_LLM_TRIP_STREAK`).
- "per day/TPD/limit reached for model" wording → SEEDHA 30min trip.
- Success par streak reset. Matlab: TPD-day me Groq बार-बार try NAHI hota — yeh design hai, bug nahi.

## Triage (is order me)
1. `GET /api/growth/infra/llm` — per-provider calls/ok-rate/avg-ms/last-error/fallback-rate.
2. ok-rate < 0.5 → konsa provider down? last-error me "TPD/quota" = din-bhar gone, kal reset (IST midnight nahi — provider UTC dekhho).
3. Sab providers trip = LLM-degraded mode: self_improve light-only ho jata hai (designed); voice TelecallerBrain → LLMBrain → static fallback chain sambhalta hai.
4. Hermes (`GET /api/growth/infra/hermes`) fallback-rate > 0.7 flag karta hai.

## Budget rules (quota PRESERVE karo)
- Heavy batch jobs (content/sales_team/coordinator) subah chalte hain — free quota (Groq TPD, Gemini RPD) voice-calls ke liye bacha ke rakho: naya scheduled LLM job add karne se pehle estimate tokens/run × runs/day.
- Voice = TelecallerBrain lean prompt (≤90 tokens out) — kabhi verbose brain mat lagao live path pe.
- Demo/test bursts (agent_tester, eval) production-hours me mat chalao agar quota tight hai.
- Naya free provider milte hi free_ai chain me ADD karo (chain = resilience), key .env me.

## Kabhi mat karo
- Cooldown bypass/retry-hammer (ban risk + wasted latency).
- Paid provider add (user decision: NO paid LLM/STT/TTS).
- ok-rate kharab dekh ke seedha code-change — pehle quota timeline confirm karo (raat me theek ho jata hai aksar).

## Enterprise gate (provider chain = resilience, free-stack only)

- **Operating loop:** Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). Discover me: `data/llm_calls.jsonl` / `GET /api/growth/infra/llm` se LIVE ok-rate dekho — chain ORDER theory se nahi, measured se set hota.
- **Change-risk tier:** chain-ORDER ya circuit-breaker touch = **High-risk** (har LLM-dependent path — voice/agents/marketing — ek saath affect). Naya provider chain ke END me add = Standard (additive, fallback headroom).
- **Resilience gates (non-negotiable):**
  - **Graceful fallback** — koi single provider trip kabhi user-facing fail na bane: chain agle provider pe gire, sab trip = degraded-mode (self_improve light-only; voice TelecallerBrain → LLMBrain → static). Never-raise wrapper.
  - **Circuit-breaker intact** — 429/quota/queue → escalating cooldown 60s→2x→30min cap; "per day/TPD/limit reached" → seedha 30min; success pe reset. Yeh DESIGN hai (TPD-day me retry-hammer nahi) — weaken/bypass mat karo.
  - **Cost/quota fail-safe** — free-stack only (NO paid LLM/STT/TTS). Heavy batch subah; voice ke liye Groq-TPD/Gemini-RPD bacha ke rakho. Naya scheduled LLM job se pehle tokens/run × runs/day estimate.
  - **Secrets** — saare provider keys (`GROQ_API_KEY`, `NVIDIA_API_KEY`, Gemini key-pool `data/voice_gemini_keys.json`, OpenRouter) sirf `.env`/runtime-store; `scripts/check_secrets.py`.
- **Observability:** `GET /api/growth/infra/llm` (per-provider calls/ok-rate/avg-ms/last-error/fallback-rate) + Hermes `GET /api/growth/infra/hermes` (fallback-rate >0.7 flag). GenAI span-level = `genai-observability`.
- **Rollback (NAMED):** chain re-tune galat nikla → ORDER revert (additive change, easy) → container recreate; provider misbehaving = us provider ki cooldown-config tighten, key disable (`.env` se hatao = inert).
- **Evidence to close:** `GET /api/growth/infra/llm` me target provider ok-rate recover + fallback-rate normal; chain change ke baad ek live `chat()` round-trip ka log; `.venv\Scripts\python.exe scripts\prod_check.py` PASS.
