---
name: web-call-triage
description: User bole "web call pe agent slow hai / sunta nahi / atak jata / noob lagta hai" — FREE web-call (/app/test-call, app/api/web_call.py + frontend/web_call.html) path ka symptom→component→fix triage. Phone-path quality = voice-humanization skill; yeh skill WEB path ke liye hai jahan architecture thoda ALAG hai.
---

# Web-Call Quality Triage (browser test-mode path)

> 2026-06-12 user complaint se derive hua ("atak jata, thik se sunta nahi, slow bolta"). Tab se web path ko phone-parity tak laaya gaya — ab STT chain + fillers WEB pe bhi hain. Yeh skill us updated reality ke liye.

## Architecture TRUTH (pehle yeh samjho, fir debug)
| Stage | Web call (`app/api/web_call.py` + `frontend/web_call.html`) | Phone (vobiz) |
|---|---|---|
| STT | **Server Groq whisper-large-v3 PRIMARY** — frontend MediaRecorder raw audio `{audio_b64}` bhejta, server `_transcribe_audio` → `free_ai.transcribe_audio` (phone-parity). Browser Web Speech API (`webkitSpeechRecognition`, hi-IN) = sirf FALLBACK text jab server STT khali aaye | Groq whisper-large-v3 chain (`_stt_chain`) |
| Brain | TelecallerBrain PRIMARY → NaturalDialog → pipeline → LLMBrain → echo | TelecallerBrain PRIMARY |
| TTS | EdgeTTS hi-IN-SwaraNeural +8%, **sentence-split streaming** (`_split_sentences`, har sentence ka mp3 b64 alag), fallback browser speechSynthesis | EdgeTTS streamed wire-format |
| Fillers | **Hain** — TelecallerBrain ke sochne se pehle `{type:"filler", audio_b64}` ack clip jaata hai (`_filler_b64`) | FILLER_AFTER_MS=450ms ack clips |
| Turn-taking | Turn-based: user bole → mic OFF → bot reply → ~300ms echo-guard → mic ON. `pendingBot` ke dauran user speech DROP (dup-guard). Safety-timer | Silero/RMS VAD + barge-in |
| Identity | `session.client_name` default **"Demo Co"** — start/user msg me na bhejo to agent "Demo Co"/generic bolega | client record se |

## Symptom → Root cause → Fix
1. **"Thik se sunta nahi / galat samajhta"** → ab server Groq STT PRIMARY hai, isliye pehle confirm karo woh chal raha:
   - `GET /api/web-call/config` → STT degrade ka direct flag nahi; `docker logs leadgen_app | grep "free_ai STT failed"` dekho — agar fail ho raha to browser Web Speech (Hinglish pe weak) pe gir raha.
   - Frontend audio bhej raha? Browser console me MediaRecorder/getUserMedia error (mic permission denied) = audio_b64 nahi jaa raha → server STT skip → browser-text. Mic permission + Chrome desktop check.
   - GROQ_API_KEY set hai (SET ✓); na ho to server STT inert → browser fallback.
2. **"Slow jawab / der se bolta"** → 3 contributors, IS ORDER me check karo:
   - LLM provider degraded: `GET /api/growth/infra/llm` — ok-rate/fallback-rate/cooldowns. Circuit-breaker escalating cooldown = turns 5-15s. (Chain LIVE-tuned: mistral/groq pehle, cerebras 429-prone — `llm-quota-ops` skill.)
   - EdgeTTS synth: sentence-split streaming hai par lambi reply = zyada chunks = slow feel → TelecallerBrain ≤2 sentences enforce ho raha hai ya nahi dekho.
   - Mic restart gaps: echo-guard + SR restart = har turn ~0.5s overhead (by design, echo se bachata).
3. **"Atak jata / stuck"** → `pendingBot` true me user input ignore hota; LLM lamba le to safety-timer reset karta. Atak = almost always LLM cooldown. Verify: llm endpoint + `docker logs leadgen_app | grep "TelecallerBrain reply failed"`.
4. **"Apne business ka naam nahi leta / Demo Co bolta"** → page se `start`/`user` msg me `client_name`+`client_service` pass karo (session default "Demo Co"). UI me business-name field na ho to woh feature gap hai.
5. **"Robotic/flat awaaz"** → web pe bhi EdgeTTS +8% hai; agar browser-TTS awaaz aa rahi (alag/flat) to EdgeTTS fail ho raha — `/api/web-call/config` me `natural_voice_available` check karo (edge-tts>=7.2.0 warna 403).

## Verify loop (har fix ke baad)
1. `GET /api/web-call/config` → `responder:"telecaller"` + `natural_voice_available:true` hona chahiye (kuch aur = degraded chain me gir gaya).
2. `python scripts/agent_tester.py` (free scorecard: double/empty/repeat/long/slow).
3. `GET /api/growth/infra/llm` — ok-rate > 0.7 baseline.
4. Real browser test `/app/test-call` — greeting instant aana chahiye (static niche-script, LLM nahi) + mic permission allow karke bolo (server STT tabhi chalega).

## Lessons (repeat mat karna)
- Web-call WS me KOI sync heavy init event-loop pe nahi — `_run_blocking` (15s) pattern use karo (2026-06-12 prod-down: fastembed download ne dono workers freeze kiye).
- Web path pe naya stage add karo to phone-parity table upar update karo — drift hi "noob web call" ka original root tha.
- Symptom report Hinglish/typo me aayega — pehle elicit karo: konsa path (web/vobiz), kya kharab (slow/STT/atak/content/awaaz), example utterance.

## Enterprise gate (web-call path = HIGH-RISK, public WS)
Operating loop — Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). **Change-risk tier: High-risk** — web-call WS public hai aur live audio serve karta; ek freeze dono workers maar sakta (3 prod-downs isi se).

**Bounded-awaits (the #1 lesson):** WS handler me KOI sync heavy init event-loop pe nahi — `_run_blocking` (15s deadline) pattern (2026-06-12 prod-down: fastembed download ne dono workers freeze). HAR `await` (chat_stream token loop, local-STT, KB) ko timeout + THINK-watchdog se bound karo — unbounded await = `_thinking` stuck = dead-air (2026-06-22 fix). Naya ML/KB load = off-loop (`asyncio.to_thread`) + deadline + disable-switch.

**Defensive WS:** handler exception before its try-block = 1006 close + no log → ASGI driver se traceback surface (`debug-ws-handler-crash` lesson). AI-disclosure greeting web pe bhi (`ai_marketing` parity).

**Phone-parity (drift = root cause):** web pe naya stage add karo to architecture-TRUTH table upar update karo — STT/brain/TTS/filler parity drift hi "noob web call" ka original root tha.

**Observability:** `GET /api/web-call/config` (`responder:"telecaller"` + `natural_voice_available:true`) · `GET /api/growth/infra/llm` (ok-rate>0.7) · `docker logs leadgen_app | grep "free_ai STT failed|TelecallerBrain reply failed"` · `scripts/call_health_check.py` (dead-air detector).

**Cost/quota:** STT Groq → browser-WebSpeech fallback; LLM `free_ai.py` circuit-breaker chain (cooldown = "atak/slow" ka #1 root). Free-stack, no paid.

**Rollback (NAMED):** regression → revert + `docker compose build app` + `up -d --no-deps app` recreate (stale .pyc clear) → `/health`=`environment:production` + `/api/web-call/config` re-check.

**Evidence (done):** verify-loop upar (config + agent_tester + llm endpoint + real `/app/test-call` browser test) + `scripts/call_health_check.py` clean + `.venv\Scripts\python.exe scripts\prod_check.py` green.
