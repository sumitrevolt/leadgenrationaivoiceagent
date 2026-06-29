# Voice Self-Host + Fine-Tune Pipeline — LeadGen AI

> **Goal:** ₹0/call STT/TTS + Sarvam-level Hinglish quality, **self-hosted**, at **1500 cold-calls/day from day-1**.
> Day-1 use = our OWN AI telecaller cold-calling to sell **Product 1 (AI Marketing)**. Product 2 (voice) ko customers ko baad me bechenge (jab agent "best" ho).
> Companion to `voice_stack/` (the GPU model-server) + memory `voice-production-program-2026-06-28`.

---

## 0. Decision: model family

| Considered | Verdict | Why |
|---|---|---|
| **NVIDIA Parakeet** (`parakeet-tdt-0.6b-v3`) | ❌ REJECTED | English + 25 **European** langs. **No Hindi.** Fast but wrong language. |
| NVIDIA **NeMo Canary** (`canary-1b-v2`) | ❌ REJECTED | Same — 25 European, no Hindi. |
| `parakeet-1.1b-rnnt-multilingual` | ⚠️ has Hindi, but | Old, 1.1B, Hindi = 1 of 11 langs, weak on Indian/telephony data vs Indic models. |
| **AI4Bharat IndicConformer / IndicWhisper / IndicF5** | ✅ CHOSEN | Trained on Indian data (Shrutilipi/IndicVoices). MIT. The right family for Hindi/Hinglish. |

**Parakeet only worth it if we ever serve English-speaking calls. Not our cold-call use-case.**

---

## 1. Target stack (decided)

| Component | Model | Role | Why |
|---|---|---|---|
| **STT — live** | **IndicConformer** (streaming RNNT/CTC) | **Primary on live calls** | Streaming = low latency. Whisper-family is batch/30s-window → higher latency (was our `5-6s gap` bug). |
| **STT — label/QA** | **IndicWhisper** | Offline re-transcribe recordings → high-accuracy training labels + eval | Offline, latency irrelevant; accuracy matters → best labels. |
| **TTS** | **IndicF5** (voice-clone) primary, **EdgeTTS** fast fallback | Live speech | IndicF5 = custom cloned voice + ₹0 self-host, but flow-matching (not streaming) → **verify per-sentence latency on GPU**; never a hard-dependency. |
| **VAD** | **Silero VAD** | Turn-taking | Already wired (`app/voice_agent/turn_detector.py`, `USE_SILERO_VAD`). |
| **LLM** | existing `free_ai.py` chain (Mistral→Groq→…) | Brain | Unchanged — already free + ok-rate tuned. |
| **Bootstrap fallback** | Groq `whisper-large-v3-turbo` (free API) | STT until self-host stable | Current live STT; free; rate-limits at 1500/day → that's WHY we self-host. |

> Live path **uses Conformer (fast)**; IndicWhisper is the **labeling/eval engine**, not the live STT. This resolves the primary/fallback tension — both models have a distinct job.

---

## 2. The flywheel (core idea)

```
calls → record → label → fine-tune → eval_gate → deploy → better calls → (loop)
```

- **1500 calls/day × 30 = ~45,000 recordings/month.** The cold-call operation **IS** the data-collection pipeline. No separate "go collect 50k–1L recordings" project — they accrue.
- Off-the-shelf telephony 8kHz Hinglish WER ≈ 22–30%. Sarvam's moat is **proprietary Indian call-data + fine-tuning + continuous loop** — not the model. We replicate that loop with our own call data.
- **Don't wait for perfect data.** Bootstrap with off-the-shelf IndicConformer, record, fine-tune as data accrues. Every cycle WER drops toward Sarvam-level.

---

## 3. Phases

### Phase 0 — PROVE (this week, ₹0)
Run `voice_stack/colab_proof.py` on free Google Colab (T4 16GB) → prove IndicConformer STT + IndicF5 TTS Hinglish quality + latency at zero cost (laptop RTX 3050 4GB = unviable, proven).
**Gate:** WER + per-turn latency acceptable on real Hinglish clips. Share `/health` + numbers.

### Phase 1 — SERVE (GPU box)
Deploy `voice_stack/server.py` on **1× L4/A10G (24GB)** — serves ~20–40 concurrent; our concurrency at 1500/day over 10h ≈ 5–8, so one box is plenty. Fund via **NVIDIA Inception** (free startup GPU credits) or RunPod/Lambda burst.
Set on VPS `.env`: `AI4BHARAT_ENDPOINT=<url>`, `STT_PROVIDER=ai4bharat`, `TTS_PROVIDER=ai4bharat`. Keep Groq as fallback (inert without endpoint). Flag-gated.

### Phase 2 — CAPTURE (data pipeline)
Every call recording → durable store. **Already wired:** `app/telephony/consent_ledger.py` (consent + 90-day retention). Build a **dataset extractor** → `(audio_path, asr_hypothesis, lang, call_id)` tuples → `data/voice_train/raw.jsonl`.

### Phase 3 — LABEL
Offline job re-transcribes recordings with **IndicWhisper** (+ Groq-large cross-check) → weak labels. **Human-correct a stratified subset** (low-confidence / disagreement cases) via a small admin review UI. Output: `data/voice_train/labeled.jsonl` `{audio_path, text, lang, source: auto|human}`.

### Phase 4 — FINE-TUNE
**NeMo** fine-tune **IndicConformer** on domain data, with **telephony 8kHz augmentation** (downsample/codec/noise). Train job off-peak on the same GPU box (or RunPod burst). Checkpoints versioned in a registry dir.

### Phase 5 — EVAL GATE (no-regression)
New checkpoint vs current on a **held-out test set**: WER + `voice_turn_score`. Deploy **only if better**. Reuse: `app/agents/eval_gate.py`, `app/platform/regression_detector.py`, `scripts/agent_tester.py`, `app/voice_agent/voice_self_improve.py`. **Never auto-apply to live** — gated promote, like the existing proposal flow.

### Phase 6 — LOOP
Re-run Phase 3→5 monthly (or per N-thousand calls). WER trends toward Sarvam-level. Wire into `self_improve` cadence.

---

## 3.5 Public datasets — warm-start ONLY, not the moat

**Key distinction — don't conflate two needs:**

- **General Hinglish ASR (pre-training):** Vistaar (10.7k h), Krutrim IndicST (10.8k h), BhasaAnuvaad (44k h), Shrutilipi, IndicVoices, FLEURS, Common Voice. **These are ALREADY baked into our base models** — IndicWhisper trained on Vistaar; IndicConformer on Shrutilipi/IndicVoices. Re-training on them just reproduces IndicWhisper → **GPU/time waste. Skip.**
- **Domain gap (the real work):** telephony 8kHz + sales/appointment conversational style + our product vocab/objections/city-accents. Off-the-shelf lacks this → the 22–30% WER. Only the **telephony** datasets help here.

| Dataset | Relevance to us | Use |
|---|---|---|
| **Hindi Telephone Dialogues 760h** | ⭐ HIGHEST — real telephony 8kHz | One-time domain warm-start |
| GramVaani (phone-quality Hindi) | High — telephony-style | Warm-start |
| MUCS (Hindi telephony + code-switch subset) | High — code-switch + phone | Warm-start |
| Vistaar / IndicST / BhasaAnuvaad / Shrutilipi / IndicVoices | Low — already in base models | Skip (don't re-train) |
| FLEURS / Common Voice | Low — clean/read mic-quality, domain-mismatch | Skip |

**More free datasets (web research 2026-06-29) — ranked for OUR use-case:**

*Tier 1 — Hinglish + phone (warm-start training):*
- **Kathbath** (AI4Bharat) — 1,684h colloquial, **smartphone-recorded**, **CC-BY-4.0 (commercial OK)** — github.com/AI4Bharat/Kathbath ⭐
- **Hindi-English Code-Switch Corpus** (Microsoft/MUCS) — 7k utt, 71 spk, **phone-recorded + code-switch** — arxiv 1810.00662 (⚠️ verify commercial license)
- **HiACC** — 5.24h pure Hinglish code-switch, Zenodo zenodo.org/records/15551669 (⚠️ verify license)

*Tier 2 — accent/dialect robustness:*
- **Lahaja** (AI4Bharat) — 12.5h, **83 districts**, multi-accent Hindi **benchmark** → use as **accent EVAL set** (WER-by-accent), HF huggingface.co/datasets/ai4bharat/Lahaja ⭐
- **Vaani** (IISc-Google) — district-level spontaneous, large
- **Awadhi/Bhojpuri/Braj/Magahi** annotated corpus — Hindi-belt dialects (rural cold-calls), arxiv 2206.12931

*Tier 3 — Indian-English (only if English calls):* Svarah · NPTEL2020-Indian-English · SPIRE-SIES.

*Hubs to mine:* **OpenSLR** (openslr.org, per-set license) · **Bhashini/ULCA** (govt NLTM, biggest free Indian repo) · **AI4Bharat Indic NLP Catalog** (master index) · **AIKosh** (aikosh.indiaai.gov.in — IndiaAI govt dataset platform) · HuggingFace (filter Hindi+ASR).

*Round-2 finds (web 2026-06-29, high value):*
- **GramVaani 1111h Hindi ASR Challenge** (OpenSLR **SLR118**) ⭐⭐⭐ — **spontaneous TELEPHONE Hindi, regional dialects, 100h labelled + 1000h unlabelled, 8kHz–48kHz mp3.** The single **best free telephony-Hindi** match — beats the 760h set. openslr.org/118 (free, register)
- **SPRING-INX** (IIT-Madras SPRING Lab) — **~2000h**, 10 langs incl Hindi, manually transcribed, open-source (NLTM), domains news/healthcare/entertainment. huggingface.co/SPRINGLab
- **MUCS 2021** (OpenSLR **SLR103**) — Hindi + Hindi-English code-switch challenge data. openslr.org/103
- **RESPIN** (IISc, Gates Foundation) — inclusive/rural Indian ASR, high-quality (sister of SYSPIN).
- **Snow Mountain** — Hindi + **Haryanvi / Bilaspuri / Dogri** dialects (Bible audio, read-style → dialect coverage). arxiv 2206.01205
- **IndicVoices (full)** — 23.7k h, **15% conversational** + extempore, 400+ districts, 11.2k transcribed — conversational subset useful (base models use only part). huggingface.co/datasets/ai4bharat/IndicVoices
- *TTS-side (alt voices for IndicF5):* **IndicVoices-R** (1,704h) · **SYSPIN** (720h studio, **CC-BY-4.0**, incl Bhojpuri/Magahi/Maithili).

*Round-3 finds (final sweep):*
- **Project Vaani** (ARTPARK-IISc + Google) ⭐⭐⭐ — **31,255h spontaneous speech, 156k speakers, 165 districts, 109 langs**, geocentric accent capture. **Largest open Indian speech corpus**; filter/download by district. HF `ARTPARK-IISc/Vaani` + vaani.iisc.ac.in
- **YODAS / CS-YODAS** (espnet) — 369k+ h YouTube, 100+ langs incl Hindi, CC license, labeled+unlabeled; **CS-YODAS = mined code-switch** subset. Massive self-supervised / pseudo-label PRE-train pool (YouTube-domain, not telephony).
- **Common Voice Hindi** (Mozilla) — **CC0 (zero restriction)**, scripted 24.0 + spontaneous 2.0 releases.
- **760h Hindi Telephone Dialogues** — confirmed free on **Kaggle** (`unidpro/hindi-speech-recognition-dataset`).
- *English-accent (if English calls):* **AccentDB**. *Small TTS:* CVIT IndicSpeech (Hindi 24h).

**✅ FINAL RECOMMENDED FREE MIX (decision-ready):**
- **Telephony warm-start (8kHz domain):** GramVaani SLR118 (1111h) + 760h Hindi-Telephone (Kaggle) + Kathbath (smartphone, CC-BY)
- **Hinglish / code-switch:** MUCS SLR103 + CS-YODAS + HiACC
- **Volume + spontaneous:** SPRING-INX (~2000h) + Project Vaani (district spontaneous) + IndicVoices conversational subset
- **Accent EVAL (held-out, NEVER train on):** Lahaja (83-district) — measure WER-by-accent
- **Dialect robustness:** Snow Mountain (Haryanvi/Dogri) + Awadhi/Bhojpuri/Braj/Magahi
- **License-safest to start:** Common Voice (CC0) + Kathbath / SYSPIN (CC-BY-4.0)
- Then → **continuous loop on OUR calls = the moat.**

> **Free exact-match Hindi call-center data is scarce** — the on-target call-center sets (Macgence/FutureBee/Shaip/Databricks) are all PAID. Confirms: public data = warm-start only; **our own calls = the moat.**

**The moat = our own ~45k calls/month** — no public set has our exact pitch/product/objections/accents.

**Two-stage data strategy:**
1. **One-time warm-start** (before our calls accrue): fine-tune IndicConformer on 760h-Telephone + GramVaani + MUCS-telephony → closes the 8kHz gap → better day-1 starting WER.
2. **Continuous loop** (Phase 3→6): fine-tune on OUR calls → toward Sarvam-level.

> **⚠️ LICENSE GATE:** verify each dataset permits **commercial** fine-tuning before using in a production model. Common Voice = CC0 (OK). "Research release" sets (BhasaAnuvaad, some IndicST sources) may restrict commercial use → legal risk. Check license per-dataset first.

---

## 4. Wiring map — built vs to-build

**Already built (reuse, don't rebuild):**
- `voice_stack/server.py` — GPU model-server scaffold (IndicConformer + IndicF5)
- `app/voice_agent/indic_providers.py` — Ai4Bharat STT/TTS provider contract
- `app/telephony/consent_ledger.py` — recording consent + 90-day retention
- `app/agents/eval_gate.py` + `app/platform/regression_detector.py` + `scripts/agent_tester.py` — eval/no-regression
- `app/voice_agent/voice_self_improve.py` — per-call failure→proposal→gated-promote (the loop's spine)
- Silero VAD (`turn_detector.py`)

**To-build (the genuine gap):**
1. Dataset extractor (recordings → `raw.jsonl`)
2. IndicWhisper labeling job (`raw.jsonl` → `labeled.jsonl`)
3. Human-correction admin review UI (stratified subset)
4. NeMo fine-tune job + 8kHz augmentation + checkpoint registry
5. ASR eval harness (WER on held-out telephony test set)
6. Checkpoint hot-swap in `server.py`

---

## 5. Flags / safety
- All new = **flag-gated, inert** without GPU endpoint/keys.
- Fine-tuned model deploy = **eval_gate-gated** (no regression), never auto-apply to live.
- Compliance unchanged & ON: **9am–7pm** promo window, **DND fail-closed**, **AI-disclosure**, recording consent (DPDP purge honored). Training data = only consented recordings.

---

## 6. Cost (real numbers, 1500/day)
| Item | Cost | Note |
|---|---|---|
| **Telephony minutes** | **~₹40–80k/mo** | 1500 × ~2–3 min ≈ 90k min/mo @ ₹0.45. **Unavoidable** — phone network can't be self-hosted. + DID. |
| **GPU box** | ~₹40–80k/mo or **₹0** | NVIDIA Inception free credits; else L4/A10G rental. |
| **STT/TTS API** | **₹0** | Self-host (Phase 1+); Groq free during bootstrap. |
| **Fine-tune compute** | occasional | Off-peak on same GPU, or RunPod burst. |

**The real bottleneck/cost = telephony + DID, NOT the AI model.**

---

## 7. Honest risks
- **IndicF5 TTS latency** on modest GPU — verify; EdgeTTS fallback ready.
- **8kHz WER high** until domain fine-tune — accept rougher first weeks; ramp.
- **Fine-tuning = real ML work** (labeled data + eval discipline), not a flag-flip.
- **Telephony recharge + DID** pending (Vobiz) — confirm before scaling. DLT = done per records; keep gates ON.
- **Don't 0→1500 day-1.** Ramp 50 → 200 → 1500 over 2–3 weeks; tune agent on real cold-calls first (free Groq fine at low volume).

---

## 8. Next action
**Phase 0:** run `voice_stack/colab_proof.py` on Colab → share `/health` (GPU+VRAM) + Hinglish WER + per-turn latency. That gate decides whether we commit to the GPU box.
