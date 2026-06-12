---
name: llm-quota-ops
description: Free-LLM provider quota/cooldown ops — Groq TPD khatam, Cerebras 429 burst, ok-rate tank (0.4 jaisa), fallback-rate high. Use jab "LLM slow/atka", agents degraded, ya llm_metrics kharab dikhe. llm-error-analysis = QUALITY; yeh skill = QUOTA/AVAILABILITY.
---

# LLM Quota Ops (free-stack chain ki availability)

## Chain truth (free_ai.py)
Cerebras gpt-oss-120b (free-unlimited, 429 bursts) → Groq (TPD 100k/day — content-heavy din me DOPAHAR tak khatam) → xAI (no credits) → OpenRouter → Gemini (quota PER MODEL). STT sirf Groq large-v3 (+ Gemini audio → local whisper weak).

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
- Heavy batch jobs (content/sales_team/coordinator) subah chalte hain — Groq TPD voice-calls ke liye bacha ke rakho: naya scheduled LLM job add karne se pehle estimate tokens/run × runs/day.
- Voice = TelecallerBrain lean prompt (≤90 tokens out) — kabhi verbose brain mat lagao live path pe.
- Demo/test bursts (agent_tester, eval) production-hours me mat chalao agar quota tight hai.
- Naya free provider milte hi free_ai chain me ADD karo (chain = resilience), key .env me.

## Kabhi mat karo
- Cooldown bypass/retry-hammer (ban risk + wasted latency).
- Paid provider add (user decision: NO paid LLM/STT/TTS).
- ok-rate kharab dekh ke seedha code-change — pehle quota timeline confirm karo (raat me theek ho jata hai aksar).
