# Voice Quality — Free STT/LLM Upgrade Research (2026-06-29)

Deep-research (multi-source, partly adversarially verified) for the **best FREE, no-GPU,
CPU-VPS-deployable** way to break the Hinglish voice agent's "noob / ignore / repeat /
mishear" ceiling. Companion to `docs/superpowers/specs/2026-06-29-voice-smart-fix-bundle-design.md`
and the GPU-blocked fine-tune plan `docs/VOICE_SELFHOST_FINETUNE_PIPELINE.md`.

## Verdict — UPDATED 2026-06-30 (after POC + live A/B)
Two root causes, and **the LLM model was the bigger lever for the "noob / ignores questions"
feel** — not STT. (a) STT mangles numbers → fixed downstream with `correct_stt` digit-collapse
(IndicConformer swap POC-REJECTED, see below). (b) The voice LLM was `gemini-2.5-flash-lite`
(picked for quota) which is too weak on Hindi instruction-following → it ignored direct product
questions and marched its discovery script. **THE FIX (live): `VOICE_LLM_MODEL=gemini-2.5-flash`
(full) on the VPS .env** — A/B-verified the agent now ANSWERS "kya features" with the feature
list and handles objections, at **p50 3381ms ≈ the flash-lite 3.3s baseline (negligible latency
cost)**, free (9-key Gemini pool absorbs the lower RPM). So the original "#1 root = STT" was
incomplete; a stronger free cloud model fixed what structural fixes could not.

## STT — ranked free options
| Option | Free? | CPU-feasible | Latency | License | Verdict |
|---|---|---|---|---|---|
| **AI4Bharat IndicConformer-600m** (self-host, VEXYL-STT pattern) | ✅ fully | ✅ **2 vCPU + 4GB RAM**, 2.4GB model | ✅ Docker + WebSocket streaming, CTC ~sub-200ms | **Apache-2.0 + MIT (model) = commercial OK** | **RECOMMENDED** — India's best Indic ASR, real-time, NOT GPU-blocked. Open risk: Hinglish code-switch + Roman-output undocumented → POC-test first. |
| Oriserve **Whisper-Hindi2Hinglish-Apex** (upgrade of the already-baked model) | ✅ (HF model) | ⚠️ slow | ❌ Whisper-large int8 on CPU ≈ 3× real-time (15-30s for 5-10s audio) | model card | Hinglish-NATIVE (keeps English in Roman → fixes "trial"→"ritail"), but too slow for real-time on CPU. Use as accuracy fallback / for the label-and-learn loop. |
| Trelis **Whisper Hinglish** (mixed-code token after lang token → Roman English + Devanagari Hindi) | ✅ | ⚠️ slow (Whisper) | ❌ | check | Directly targets the script/loanword problem; same CPU-latency caveat as Apex. |
| **Bhashini / ULCA** (Govt of India, AI4Bharat-backed) cloud API | ⚠️ **PoC-ONLY — production/charging = PAID** | n/a (cloud) | cloud | PoC terms | **RULED OUT** — we charge customers (commercial); free tier is PoC-only. |
| Groq `whisper-large-v3` (current) | ✅ (undocumented limits) | n/a (cloud) | fast | — | The current STT — inherently mangles code-switched English + numbers (Whisper-hi → Devanagari). The thing to beat. |

**Whisper code-switch fact (verified-ish):** multilingual Whisper at ~5% WER monolingual jumps to
**15-20% WER on Hindi-English code-switched** speech, and transcribes English loanwords in
non-standard Devanagari — exactly our "trial→ritail / activate→aktivet" failure. `initial_prompt`
biasing helps marginally but risks prompt-leak (we saw "vishay" concerns). The real fix is a
**Hinglish-native model**, not prompt-tuning Whisper-hi.

## LLM — ranked (instruction-following / "ignore-repeat")
- **Do NOT self-host the LLM on the CPU VPS** (verified): CPU-feasible small models collapse on
  Hindi instruction-following (Qwen3-4B 66, Gemma-3-1B 38, Llama-3.2-3B 43); the current Groq
  fallback `llama-3.1-8b-instant` itself is Hindi-weak (53.6% Hindi prompt-IF vs 81.6% English).
  IF only plateaus at 12-14B+.
- **Best free Hindi instruction-followers = cloud:** Gemini Flash-tier (Gemini-3-Flash 89.7),
  Gemma-3-27B 85.0, Llama-3.3-70B, Qwen3-14B — reachable as FREE cloud APIs (Groq/OpenRouter/Gemini).
- **We already do the right thing:** voice primary = cloud `gemini-2.5-flash-lite` (VOICE_GEMINI_PRIMARY).
- **Optional quota-aware tweaks:** (a) voice `gemini-2.5-flash-lite` → `gemini-2.5-flash` (better Hindi
  IF, lower free RPM — the 9-key pool + breaker absorb it); (b) swap the Groq fallback
  `llama-3.1-8b-instant` → `llama-3.3-70b-versatile` (already defined as `_GROQ_LLAMA70B_MODEL`,
  free, TTFT ~0.92s) + add OpenRouter `:free` 70B deep fallback. The chain is live-tuned + quota-
  sensitive — change carefully/reversibly, keep the 429 circuit-breaker.

## Free fine-tune path (C) — deferred
Genuinely free adaptation exists (free Colab/Kaggle GPU + free Hindi ASR datasets — GramVaani SLR118,
Kathbath, IndicVoices, Shrutilipi; license-gated) but it's a weeks-long project. Do the IndicConformer
swap first; the already-running label-and-learn loop ([[voice-smart-fix-bundle]] Component 3) feeds it later.

## POC RESULT (2026-06-30) — IndicConformer-600m on 3 real web-call recordings (CPU, local)
**Latency: PASS.** CTC on CPU = **RTF 0.15-0.23** (transcribes 90-220s audio in 14-51s) = ~5× faster
than real-time → real-time-feasible on the CPU VPS (vs Whisper-large's ~3× SLOWER).
**Quality: FAIL the premise.** It does NOT fix the root cause:
- Outputs **Devanagari** (same as Groq-hi), NOT Roman — so "trial activate" → "ट्रायल एक्टिवेट" (better
  than Groq's "रिटायल अक्टिवेट" but still Devanagari, still needs downstream to_roman).
- Numbers → **number-words in Devanagari** ("1999" → "नाइन हंड्रेड नाइटी नाइन"), same as Groq.
- **Phone numbers → WORSE**: Groq gives digits "8459012607"; IndicConformer gives words
  "फाइव नाइन जीरो…" → breaks the post-close number read-back.
**VERDICT: do NOT swap to IndicConformer.** Marginal domain-word gain, no Roman/number fix, phone
regresses — not worth a gated-model + 2.4GB + new-container + VPS-RAM infra change. (HF repo is gated:
free account + accept terms + token; the model loads via `transformers` `trust_remote_code`, no NeMo.)
**Real free fix = downstream correction** (no model swap): extend `hinglish_stt_fix.correct_stt` with
Devanagari→roman + number-words→digits (free, fast, builds on shipped Component 1) + the LLM upgrade.
The Oriserve/Trelis Hinglish-Roman Whisper models are the only ones that output Roman natively but are
Whisper-large = CPU-slow (~3× real-time) → not the real-time primary; use for the offline label/learn loop.

## Recommended path (impact-per-effort)
1. **POC** IndicConformer-600m on the VPS (or Colab) on 5-10 real recordings → measure Hinglish WER +
   per-utterance latency + whether it keeps English in Roman. Compare to Groq-whisper-hi.
2. If POC wins: deploy IndicConformer as a Docker sidecar (CTC streaming), wire it as the **primary**
   STT in `free_ai`/`web_call` (Groq-whisper as fallback), gated `INDICCONFORMER_STT=1`. Watch VPS RAM
   (it already runs ~13 containers; 2.4GB model needs headroom — may need a RAM bump or model offload).
3. (Optional, parallel) LLM quota-aware tweaks above.

**Caveats flagged:** Bhashini free = PoC-only (not commercial). IndicConformer Hinglish/Roman-output is
UNVERIFIED → POC-gate it. Whisper-Apex is accurate but CPU-slow → not the real-time primary. The big
self-host LLM idea is wrong (CPU models can't do Hindi IF) — stay on cloud Gemini.
