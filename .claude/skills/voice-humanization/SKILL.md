---
name: voice-humanization
description: PHONE voice agent (vobiz) ko human-like banane ka project pattern — Groq STT chain, TelecallerBrain, fillers/backchannels, EdgeTTS prosody, turn-taking. Use jab phone-call voice quality "robotic/noob/flat/dead-air" lage ya naya phone audio path add ho. (WEB /app/test-call ke liye web-call-triage skill.)
---

# Voice Humanization (Vapi/Retell/SquadStack patterns, free-stack)

## Root-cause checklist jab "agent noob lag raha hai"
1. **STT weak?** Local tiny-whisper Hindi phone-audio par garbage deta hai → conversation hi galat chalti hai. HAR audio path me chain: **Groq whisper-large-v3 (free_ai.transcribe_audio) → Gemini → local whisper**. (phone_stream._stt_chain / vobiz_stream._stt)
2. **Galat brain?** `LLMBrain` verbose/heavy hai. Live call = **TelecallerBrain** primary (lean prompt, niche script, ≤2 sentences, 1 question/turn), LLMBrain sirf fallback.
3. **Dead air?** LLM 1-6s leta hai → silence robotic lagta hai. Fix: **filler ack** ("Hmm…", "Achha…", "Ji…") — `FILLER_AFTER_MS` (default 450ms) ke baad cached clip bajao. MP3 module-cache + per-session wire-format convert (`_mp3_to_wire` — Vobiz=µ-law; naya path ka wire-format alag ho sakta).
4. **Flat delivery?** EdgeTTS default slow/flat. `PHONE_TTS_RATE=+8%` (confident pace), `PHONE_TTS_PITCH` optional. Vobiz path hard-coded +8% pehle se.
5. **Greeting slow/generic?** Opener KABHI LLM se nahi — static niche-script opening (permission-based, Gong ~11%) instant synth hota hai.
6. **Turn-taking?** `USE_SILERO_VAD=1` (noise/echo filter) + `USE_SMART_TURN=1` (mid-sentence pause pe nahi tokta) — heavy deps, capacity check pehle (`scripts/vps_capacity_check.py`).

## Env knobs (sab default = behaviour unchanged)
`PHONE_TTS_RATE` `PHONE_TTS_PITCH` `PHONE_FILLERS` `FILLER_AFTER_MS` `TURN_SILENCE_MS` `TURN_VAD_RMS` `USE_SILERO_VAD` `USE_SMART_TURN` `GROQ_STT_LANG`

## Naya audio path add karte waqt (subclass lesson)
- `PhoneCallSession` subclass karo, sirf wire format override (`_handle_media`, `_send_audio`, `_mp3_to_wire`, `_synthesize`).
- **Parent ka STT/brain/filler stack mat bypass karo** — ek purana path mahine-bhar tiny-whisper+LLMBrain pe chala kyunki subclass ne sirf protocol socha, quality stack nahi. (Vobiz path ab parent quality stack reuse karta.)
- TRAI: greeting me AI disclosure zaroori (vobiz_stream._AI_DISCLOSURE pattern).

## QA
Har voice change ke baad: `scripts/agent_tester.py` (double/empty/repeat/long/slow scorecard) + FREE web-call (`/app/test-call`) pe suno. Phone = final verify only (paisa).

## Enterprise gate (phone voice quality = HIGH-RISK)
Operating loop — Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). **Change-risk tier: High-risk** — phone audio path = live outbound calls; quality knob change bhi compliance + cross-path parity ko intact rakhna mandatory.

**Compliance (fail-CLOSED — humanization ke chakkar me kabhi mat hatao):**
- **AI-disclosure greeting** — har naya audio path me prepend (`vobiz_stream._AI_DISCLOSURE` pattern); opener static niche-script hai par disclosure usme baked rahe.
- **TRAI 9am–7pm + DND fail-CLOSED** — voice-quality change call-gating ko touch na kare (`compliance.py`).
- **Consent + 90-din retention** — opt-out / press-9 path stream cleanup me intact.

**Safety / defaults:** sab env knobs default = behaviour unchanged (`PHONE_TTS_RATE`/`PHONE_FILLERS`/`FILLER_AFTER_MS`/`USE_SILERO_VAD`/`USE_SMART_TURN`). Heavy turn-taking deps = capacity-check pehle (`scripts/vps_capacity_check.py`).

**Cross-path parity (subclass lesson):** `PhoneCallSession` subclass karo, sirf wire-format override — **parent STT/brain/filler/cleanup stack mat bypass** (purana path mahine tiny-whisper+LLMBrain pe chala). Parent `_cleanup` = `post_call_hooks.meter_call_completion` (idempotent minute-billing) + auto-qualify downstream; naya path me yeh chhoot gaya = adhoora. Guard: `scripts/cross_path_audit.py`.

**Cost/quota:** STT chain Groq whisper-large-v3 → Gemini → local (free, graceful); LLM via `free_ai.py` circuit-breaker chain — quota fallback already wired, naya hard-dep mat banao.

**Observability:** voice change = `scripts/agent_tester.py` scorecard + `scripts/call_health_check.py` (dead-air detector); LLM health `/api/growth/infra/llm`.

**Rollback (NAMED):** regression → quality flag OFF (env default-safe) ya revert → `docker compose build app` + `up -d --no-deps app` recreate → `/health`=`environment:production`.

**Evidence (done):** `python scripts/agent_tester.py` (no double/empty/repeat/slow regression) + `.venv\Scripts\python.exe scripts\cross_path_audit.py` green + FREE web-call (`/app/test-call`) listen. Phone web-call quality = final user-verify (paisa khaata).
