---
name: web-call-triage
description: User bole "web call pe agent slow hai / sunta nahi / atak jata / noob lagta hai" — FREE web-call (/app/test-call, web_call.py) path ka symptom→component→fix triage workflow. Phone-path quality ke liye voice-humanization skill; yeh skill WEB path ke liye hai jahan architecture ALAG hai.
---

# Web-Call Quality Triage (browser test-mode path)

> 2026-06-12 ko user complaint se derive hua: "atak jata, thik se sunta nahi, slow bolta hai".
> Web path phone path se ALAG hai — phone wale fixes (Groq STT chain, fillers) yahan AUTO apply NAHI hote.

## Architecture TRUTH (pehle yeh samjho, fir debug)
| Stage | Web call (`app/api/web_call.py` + `frontend/web_call.html`) | Phone (vobiz/exotel) |
|---|---|---|
| STT | **Browser Web Speech API** (`webkitSpeechRecognition`, lang=hi-IN) — server STT NAHI chalta; `_transcribe_audio` sirf pipeline.transcribe try karta (practically inert, "" return) | Groq whisper-large-v3 chain (`_stt_chain`) |
| Brain | TelecallerBrain PRIMARY → NaturalDialog → pipeline → LLMBrain → echo | TelecallerBrain PRIMARY |
| TTS | EdgeTTS hi-IN-SwaraNeural +8%, **poora reply single mp3 b64** (6s cap), fallback browser speechSynthesis | EdgeTTS streamed wire-format |
| Fillers | **NAHI hain** — "thinking" state me sirf UI spinner | FILLER_AFTER_MS=450ms ack clips |
| Turn-taking | Turn-based: user bole → mic OFF → bot reply → 300ms echo-guard → mic ON. `pendingBot` ke dauran user speech DROP hoti hai (dup-guard). 13s safety-timer | Silero/RMS VAD + barge-in |
| Identity | `session.client_name` default **"Demo Co"** — start msg me na bhejo to agent "Demo Co"/generic bolega | client record se |

## Symptom → Root cause → Fix
1. **"Thik se sunta nahi / galat samajhta"** → STT = Chrome ka recognizer, Hinglish pe weak; server Groq STT wire hi nahi hai.
   - Quick: Chrome desktop + acha mic + kam background noise; `recog.lang` hi-IN already set.
   - REAL FIX (feature): frontend MediaRecorder → `{"type":"audio","audio_b64":...}` + `web_call._transcribe_audio` me `free_ai.transcribe_audio` (Groq large-v3) wire karo — phone-parity. (GROQ_API_KEY set hai.)
2. **"Slow jawab / der se bolta"** → 3 contributors, IS ORDER me check karo:
   - LLM provider degraded: `GET /api/growth/infra/llm` — ok-rate/fallback-rate/cooldowns dekho (Cerebras 429 burst, Groq TPD din-bhar). Circuit-breaker escalating cooldown = turns 5-15s.
   - EdgeTTS full-synth: poora reply synth hone tak text+audio dono rukta hai (6s cap). Lambi replies = slow feel → TelecallerBrain ≤2 sentences enforce ho raha hai ya nahi dekho.
   - Mic restart gaps: 300ms echo-guard + 250ms SR restart = har turn ~0.5s+ overhead (by design, echo se bachata).
3. **"Atak jata / stuck"** → `pendingBot` true me user input ignore hota; LLM 13s+ le to safety-timer reset karta. Atak = almost always LLM cooldown. Verify: llm endpoint + `docker logs leadgen_app | grep "TelecallerBrain reply failed"`.
4. **"Apne business ka naam nahi leta / Demo Co bolta"** → page se `start`/`user` msg me `client_name`+`client_service` pass karo (session default "Demo Co"). UI me business-name field na ho to woh feature gap hai.
5. **"Robotic/flat awaaz"** → web pe bhi EdgeTTS +8% hai; agar browser-TTS awaaz aa rahi (alag/flat) to EdgeTTS fail ho raha — `/api/web-call/config` me `natural_voice_available` check karo (edge-tts>=7.2.0 warna 403).

## Verify loop (har fix ke baad)
1. `GET /api/web-call/config` → `responder:"telecaller"` + `natural_voice_available:true` hona chahiye (kuch aur = degraded chain me gir gaya).
2. `python scripts/agent_tester.py` (free scorecard: double/empty/repeat/long/slow).
3. `GET /api/growth/infra/llm` — ok-rate > 0.7 baseline.
4. Real browser test `/app/test-call` — greeting instant aana chahiye (static script, LLM nahi).

## Lessons (repeat mat karna)
- Web-call WS me KOI sync heavy init event-loop pe nahi — `_run_blocking` (15s) pattern use karo (2026-06-12 prod-down: fastembed download ne dono workers freeze kiye).
- Web path pe naya stage add karo to phone-parity table upar update karo — drift hi "noob web call" ka root tha.
- Symptom report Hinglish/typo me aayega — pehle elicit karo: konsa path (web/exotel/vobiz), kya kharab (slow/STT/atak/content/awaaz), example utterance.
