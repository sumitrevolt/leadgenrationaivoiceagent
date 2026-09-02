"""Quick proof: IndicConformer STT on this machine. Generates a Hinglish clip
(EdgeTTS), transcribes it, prints accuracy + latency. CPU is fine for the proof."""
import asyncio
import time

import librosa
import torch
from transformers import AutoModel

TEXTS = [
    "Namaste, mera bijli ka bill bahut zyada aata hai, main solar lagwana chahta hoon.",
    "Aapke paas kya kya features hain, mujhe sab detail mein batao.",
    "Haan main interested hoon, appointment book karo kal subah gyarah baje.",
]


async def _gen(text, path):
    import edge_tts

    await edge_tts.Communicate(text, "hi-IN-SwaraNeural").save(path)


print("device:", "cuda" if torch.cuda.is_available() else "cpu")
t = time.time()
model = AutoModel.from_pretrained(
    "ai4bharat/indic-conformer-600m-multilingual", trust_remote_code=True
)
print(f"model loaded in {time.time()-t:.1f}s")

for i, text in enumerate(TEXTS):
    path = f"clip_{i}.mp3"
    asyncio.run(_gen(text, path))
    y, sr = librosa.load(path, sr=16000, mono=True)
    wav = torch.tensor(y).unsqueeze(0)
    t = time.time()
    with torch.no_grad():
        out = model(wav, "hi", "ctc")
    ms = (time.time() - t) * 1000
    heard = out if isinstance(out, str) else (out[0] if isinstance(out, (list, tuple)) else str(out))
    print("\nSAID :", text)
    print(f"HEARD: {str(heard).strip()}")
    print(f"  STT: {ms:.0f}ms  (audio {len(y)/16000:.1f}s)")
