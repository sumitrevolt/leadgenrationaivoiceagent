# SESSION_HANDOFF - overwrite every session end

## Session objective
Owner: GEMINI rotate mat karo — jo AI keys pehle se hain unpe chalao.

## Done (PRODUCTION-PROVEN)
- **Voice LLM primary → free stack** (2026-08-03):
  - `VOICE_GEMINI_PRIMARY=0` · `GEMINI_TTS=0` · `GEMINI_PRIMARY=false`
  - `data/voice_gemini_keys.json` → `voice_primary=false` (was True — yeh Gemini force kar raha tha)
  - Recreated app/worker/scheduler `APP_VERSION=303b061f`
- **Live proof:** `TelecallerBrain._voice_gemini_primary()=False` · `free_ai.chat` → provider **`mistral`** reply OK · Groq/Mistral/Cerebras/OpenRouter HTTP 200 · `/health` healthy `303b061f` · celery/DLQ=0
- Backups: `.env.bak-freeai-20260803131156` · `data/voice_gemini_keys.json.bak-freeai-*`
- STT stays Groq whisper primary; TTS stays EdgeTTS (`GEMINI_TTS=0`)
- Gemini keys pool abhi file me hai as deep fallback only — primary nahi

## Earlier same day (still true)
- bash_history GEMINI scrub done; key rotate skipped per owner
- Post-call WA ON; cold WA OFF; Buzz admin complete

## Owner next
1. Live Swara call smoke (LLM should come free_ai / mistral|groq|cerebras, not gemini-first)
2. Estique → real ₹1999 before PAID
3. Optional later: revoke burned Gemini key in Google console

## Do not
Re-enable `voice_primary=true` / `VOICE_GEMINI_PRIMARY=1` without healthy new Gemini pool · cold WA blast ON
