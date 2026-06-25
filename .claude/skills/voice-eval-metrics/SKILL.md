---
name: voice-eval-metrics
description: Objective ASR/TTS/latency metrics for LeadGen's FREE voice stack (Groq-whisper STT + EdgeTTS), upgrading agent_tester's heuristics to measurable numbers — WER/CER, round-trip-WER, latency P50/P95/P99, barge-in, TTFA. Use when tuning voice quality, comparing a brain/prompt/provider change, "voice metrics", "kitna accurate", "latency measure", "regression pakdo", or wiring a voice eval harness.
---
# Voice Eval Metrics (objective)

`agent_tester.py` heuristic hai (double/empty/repeat/long/slow). **Yeh skill = objective, measurable metrics** taaki "behtar laga" ki jagah number ho. Sab **free** (jiwer + tumhara already-present Whisper/EdgeTTS). Source: ai-engineering-from-scratch ph06/17 ([[ai-engineering-course-reference]]).

## Metric map (hamari tasks)
| Task | Primary | Secondary |
|---|---|---|
| STT (Groq whisper-large-v3) | **WER** | CER · first-token latency |
| TTS (EdgeTTS hi-IN-Swara) | **round-trip-WER** | TTFA (time-to-first-audio) · UTMOS |
| Web/phone call (streaming S2S) | **latency P50/P95/P99** | barge-in responsiveness · WER |

## Free harness (pip `jiwer`)
**Rule 1 — normalize before scoring** (lowercase, punctuation-strip, number-expand; rule report karo):
```python
from jiwer import wer, Compose, ToLowerCase, RemovePunctuation, Strip
tx = Compose([ToLowerCase(), RemovePunctuation(), Strip()])
score = wer(truth=ref, hypothesis=hyp, truth_transform=tx, hypothesis_transform=tx)
```
**Round-trip WER (TTS intelligibility, fully free — Whisper over EdgeTTS):**
```python
def roundtrip_wer(text):
    audio = edge_tts_synth(text)          # hi-IN-SwaraNeural
    recog = groq_whisper_transcribe(audio)  # already wired
    return wer(truth=text, hypothesis=recog, truth_transform=tx, hypothesis_transform=tx)
# WER > 10% wale prompts flag karo = Swara woh line clearly nahi bol rahi
```
**Latency (streaming):** end-of-user-speech → first audible response. **P50/P95/P99 report karo, average NAHI.** Barge-in target **<150ms** (tumhara `BARGE_GUARD` isi ko serve karta — measure karo).

## 3 cardinal rules
1. **Normalize before scoring** + rule likho.
2. **Distributions, not averages** — latency P50/P95/P99; WER per-slice.
3. **Ek canonical benchmark** — Open ASR Leaderboard (HF) pe apna number, taaki apples-to-apples.

## Pitfalls (Hinglish-specific!)
- **Aggregate WER accented/Hindi speech ka failure chhupata** — 5% overall me 30% Hindi-heavy ho sakta. **Demographic/language slice pe report karo** (Hinglish vs English-heavy).
- UTMOS clean-English pe train → noisy/emotional/Hindi pe weak; round-trip-WER zyada bharosa.
- Public benchmark saturate — apna **held-out in-house set** banao jo real call-traffic reflect kare (niche-wise).

## Wire-in
- `scripts/agent_tester.py` me objective block add karo (heuristic ke saath) → scorecard me WER + P95-latency + roundtrip-WER.
- Provider/brain/prompt change ke baad **pehle-baad** diff karo; regression → `eval_gate` se gate.
- Tuning FREE web-call (`/app/test-call`) pe; phone = final verify (CLAUDE.md).

## Pairs with
`test-agent` (heuristic scorecard) · `voice-humanization` · `web-call-triage` · `prompt-engineering`.
