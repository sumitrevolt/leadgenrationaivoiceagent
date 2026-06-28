# ============================================================================
# AI4Bharat voice-stack PROOF — run on FREE Google Colab GPU (zero cost)
# ============================================================================
# HOW:
#   1. Open https://colab.research.google.com  -> New notebook
#   2. Runtime > Change runtime type > Hardware accelerator = T4 GPU  (free)
#   3. Paste this whole file into ONE cell, Run. (~5 min first time: downloads models)
#   4. It prints STT accuracy + latency, and saves a TTS sample you can play.
# This proves IndicConformer (STT) + IndicF5 (TTS) Hinglish quality on a real
# 16GB GPU — without your laptop's disk/connection/4GB limits.
# ============================================================================

# --- install (Colab has fast datacenter net — no broken downloads) ---
import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                "transformers", "torchaudio", "soundfile", "librosa", "edge-tts",
                "nest_asyncio"], check=True)

import asyncio, time
import librosa, numpy as np, soundfile as sf, torch
import nest_asyncio
from transformers import AutoModel

# Colab/Jupyter already runs an event loop → allow asyncio.run() inside it.
nest_asyncio.apply()

print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else
      "*** NO GPU — Runtime > Change runtime type > T4 GPU ***")

# ---------------- STT: IndicConformer ----------------
print("\n[1/2] Loading IndicConformer (STT)...")
t = time.time()
stt = AutoModel.from_pretrained("ai4bharat/indic-conformer-600m-multilingual",
                                trust_remote_code=True)
if torch.cuda.is_available():
    try: stt = stt.to("cuda")
    except Exception: pass
print(f"  loaded in {time.time()-t:.1f}s")

TESTS = [
    "Namaste, mera bijli ka bill bahut zyada aata hai, main solar lagwana chahta hoon.",
    "Aapke paas kya kya features hain, mujhe sab detail mein batao.",
    "Haan main interested hoon, appointment book karo kal subah gyarah baje.",
]

async def _say(text, path):
    import edge_tts
    await edge_tts.Communicate(text, "hi-IN-SwaraNeural").save(path)

print("\n--- STT results (Hinglish accuracy + latency) ---")
for i, text in enumerate(TESTS):
    asyncio.run(_say(text, f"c{i}.mp3"))
    y, _ = librosa.load(f"c{i}.mp3", sr=16000, mono=True)
    sf.write(f"c{i}.wav", y, 16000)   # wav copy (IndicF5 ref needs wav)
    wav = torch.tensor(y).unsqueeze(0)
    if torch.cuda.is_available(): wav = wav.to("cuda")
    t = time.time()
    with torch.no_grad():
        out = stt(wav, "hi", "ctc")
    heard = out if isinstance(out, str) else (out[0] if isinstance(out,(list,tuple)) else str(out))
    print(f"\nSAID : {text}")
    print(f"HEARD: {str(heard).strip()}")
    print(f"  -> {(time.time()-t)*1000:.0f}ms for {len(y)/16000:.1f}s audio")

# ---------------- TTS: IndicF5 (voice clone) ----------------
print("\n[2/2] Loading IndicF5 (TTS, voice-clone)...")
t = time.time()
tts = AutoModel.from_pretrained("ai4bharat/IndicF5", trust_remote_code=True)
if torch.cuda.is_available():
    try: tts = tts.to("cuda")
    except Exception: pass
print(f"  loaded in {time.time()-t:.1f}s")

# reference voice = clip 0 we just made with EdgeTTS (or upload your own ref.wav)
REF_AUDIO, REF_TEXT = "c0.wav", TESTS[0]
say = "Bilkul sir, main aapki poori madad karungi. Aaj hi free trial set kar deti hoon."
t = time.time()
audio = tts(say, ref_audio_path=REF_AUDIO, ref_text=REF_TEXT)
audio = np.asarray(audio)
if audio.dtype == np.int16: audio = audio.astype(np.float32)/32768.0
sf.write("indicf5_out.wav", audio.astype(np.float32), 24000)
print(f"\nTTS '{say[:40]}...' -> {(time.time()-t)*1000:.0f}ms  saved indicf5_out.wav")

# play it in Colab:
try:
    from IPython.display import Audio, display
    display(Audio("indicf5_out.wav"))
except Exception:
    pass
print("\nDONE. STT numbers + the indicf5_out.wav voice = your self-hosted quality proof.")
