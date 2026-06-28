# Apna Voice Stack — self-hosted Hindi/Hinglish STT + TTS (FREE, no per-min cost)

The "own Sarvam": **AI4Bharat IndicConformer (STT) + IndicF5 (TTS)** served from YOUR
NVIDIA GPU (laptop for dev/POC, dedicated box for 1500-calls/day production). The
LeadGen app talks to it via one env var — no app rewrite.

## Why this (vs Sarvam API)
At **1500 calls/day (~1.35 lakh min/month)** Sarvam ≈ **₹2.7 L/month**. This stack =
just compute (your laptop GPU = ₹0; a dedicated GPU box ≈ ₹40-80k/month). The models
are MIT-licensed, pre-trained on Indian datasets (Shrutilipi/IndicVoices) — no
training/scraping needed, just run them.

## Hardware
- **NVIDIA GPU.** IndicF5 (TTS) needs ~**6-8 GB VRAM** (fp16). IndicConformer (STT, 600M)
  runs on 2-4 GB / even CPU. → A laptop **RTX 3060/4060 (6-8GB)** can run BOTH for dev.
- For 1500/day production: 1× **L4 / A10G (24GB)** serves ~20-40 concurrent calls.

## Setup (laptop)
```bash
cd voice_stack
python -m venv .venv && . .venv/Scripts/activate         # (Windows) or source .venv/bin/activate
# 1) CUDA torch matching your GPU (check `nvidia-smi`):
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
# 2) rest:
pip install -r requirements.txt

# 3) VOICE: record a clean 6-10s Hindi clip = your agent's voice -> ref_voice.wav
#    and put its exact transcript in REF_TEXT.
set REF_AUDIO=ref_voice.wav
set REF_TEXT=Namaste, main Swara bol rahi hoon, aapki kaise madad karoon.

# 4) run (downloads models once, ~2.4GB STT + IndicF5):
uvicorn server:app --host 0.0.0.0 --port 8900
# check: curl http://localhost:8900/health   -> should show "cuda": true + your GPU
```

## Expose to the cloud app (free tunnel — laptop has no public IP)
```bash
# install cloudflared, then:
cloudflared tunnel --url http://localhost:8900
# -> gives a https://<random>.trycloudflare.com URL
```

## Point the LeadGen app at it (on the VPS .env)
```
AI4BHARAT_ENDPOINT=https://<your-cloudflared-url>
STT_PROVIDER=ai4bharat
TTS_PROVIDER=ai4bharat
DEFAULT_LANGUAGE=hi-IN
```
(The app's `app/voice_agent/indic_providers.py` Ai4Bharat* providers already POST to
`AI4BHARAT_ENDPOINT/transcribe` and `/tts` — the web-call path wiring is added so it
uses them when `STT_PROVIDER=ai4bharat`.)

## NVIDIA help (minimise cost for production)
- **NVIDIA Inception** (free startup program): cloud GPU credits + DGX Cloud trials +
  TensorRT/Triton for fast serving. Apply with the company — this funds the prod GPU.
- **NVIDIA NIM / NGC**: optimized inference containers; **TensorRT** ~2-4× speedup on the
  same GPU (worth it at 1500/day).
- Cheaper than always-on: **RunPod / Lambda** spot GPUs (~₹40-100/hr) for bursts.

## Honest caveats (test on YOUR GPU)
- This `server.py` is a **starting scaffold** built from the official model inference
  APIs — the IndicConformer custom-model call signature + IndicF5 ref-audio path may
  need a small tweak once you run it (the model READMEs evolve). Run `/health` first,
  then `/transcribe` + `/tts`, share any error → I fix the exact call.
- **Telephony (8kHz) WER is higher** (~22-30%) than Sarvam — fine for web (16k), for
  phone we domain-tune later.
- **Laptop ≠ 24/7 production server** (thermal/uptime/residential net). Great for POC
  + first customers; move to a GPU box once proven.
- IndicF5 is **voice-clone** TTS — quality depends on your REF_AUDIO clip (clean, 6-10s).

## Next (once it runs on your laptop)
1. You: run server + cloudflared, give me the tunnel URL + `/health` output (GPU + VRAM).
2. Me: set the app env, run a real call, measure STT/TTS latency + quality vs Sarvam,
   tune the call signatures if needed.
3. Then decide: laptop-for-now vs a ₹40-80k GPU box for the full 1500/day.
