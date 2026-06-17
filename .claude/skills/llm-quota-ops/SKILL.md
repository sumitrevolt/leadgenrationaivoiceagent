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
