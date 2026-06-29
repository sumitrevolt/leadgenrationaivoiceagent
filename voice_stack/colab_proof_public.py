# ============================================================================
# Voice-stack PROOF (PUBLIC models) — FREE Google Colab GPU, ZERO account needed
# ============================================================================
# Use this when you don't want to deal with HuggingFace gates/tokens. It uses only
# PUBLIC ungated models so it just runs:
#   STT : vasista22/whisper-hindi-large-v2  (IndicWhisper Hindi; public)
#         -> falls back to openai/whisper-large-v3 if unavailable
#   TTS : facebook/mms-tts-hin              (Meta MMS Hindi TTS; public, Apache)
#
# What this proves: self-hosted Hindi/Hinglish STT + TTS quality & latency on a
# free T4 — WITHOUT any login. Devanagari reference sentences => a REAL WER number.
#
# Honest gap vs the production target (IndicConformer + IndicF5, both GATED):
#   - IndicConformer (live STT) is LIGHTER -> real latency will be BETTER than the
#     Whisper here, so treat this STT latency as a worst-case upper bound.
#   - IndicF5 (TTS) is voice-CLONE (your agent's own voice); MMS here is a generic
#     Hindi voice -> proves "self-hosted Hindi TTS runs", not the final voice quality.
#   For the exact target models you'll need a HF token once (see colab_proof.py).
#
# HOW: Colab -> New notebook -> Runtime > Change runtime type > T4 GPU ->
#      paste this whole file into ONE cell -> Run (~4 min, model download).
# ============================================================================

import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                "transformers", "torchaudio", "soundfile", "librosa", "edge-tts",
                "nest_asyncio", "jiwer", "scipy"], check=True)

import asyncio, time, re, warnings
import librosa, numpy as np, soundfile as sf, torch
import nest_asyncio
nest_asyncio.apply()
warnings.filterwarnings("ignore")

DEV = "cuda" if torch.cuda.is_available() else "cpu"
print("GPU:", torch.cuda.get_device_name(0) if DEV == "cuda" else
      "*** NO GPU — Runtime > Change runtime type > T4 GPU, then re-run ***")

# Devanagari ground-truth (so WER is apples-to-apples vs the Hindi STT output);
# roman shown only for your reading.
TESTS = [
    ("नमस्ते, मेरा बिजली का बिल बहुत ज़्यादा आता है, मैं सोलर लगवाना चाहता हूँ।",
     "Namaste, mera bijli ka bill bahut zyada aata hai, main solar lagwana chahta hoon."),
    ("आपके पास क्या क्या फ़ीचर्स हैं, मुझे सब डिटेल में बताओ।",
     "Aapke paas kya kya features hain, mujhe sab detail mein batao."),
    ("हाँ मैं इंटरेस्टेड हूँ, अपॉइंटमेंट बुक करो कल सुबह ग्यारह बजे।",
     "Haan main interested hoon, appointment book karo kal subah gyarah baje."),
]

def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^ऀ-ॿ\sa-z0-9]", " ", str(s).lower())).strip()

def _wer(ref, hyp):
    try:
        import jiwer
        r, h = _norm(ref), _norm(hyp)
        if not r:
            return None
        return jiwer.wer(r, h) * 100.0
    except Exception:
        return None

async def _say(text, path):
    import edge_tts
    await edge_tts.Communicate(text, "hi-IN-SwaraNeural").save(path)

# ---------------- STT: public Hindi Whisper ----------------
print("\n[1/2] Loading STT (public IndicWhisper / Whisper)...")
from transformers import pipeline
def _build_stt():
    for mid in ("vasista22/whisper-hindi-large-v2", "openai/whisper-large-v3"):
        try:
            t = time.time()
            pipe = pipeline("automatic-speech-recognition", model=mid,
                            device=0 if DEV == "cuda" else -1, chunk_length_s=20,
                            generate_kwargs={"language": "hi", "task": "transcribe"})
            print(f"  STT model = {mid}  (loaded {time.time()-t:.1f}s)")
            return pipe
        except Exception as e:
            print(f"  {mid} unavailable ({str(e)[:60]}) -> trying next")
    raise RuntimeError("no STT model could be loaded")
stt = _build_stt()

def _stt_text(path):
    r = stt(path)
    return (r.get("text") if isinstance(r, dict) else str(r)).strip()

# generate clip 0 + warm up GPU (first inference compiles kernels = not real latency)
asyncio.run(_say(TESTS[0][0], "c0.mp3"))
print("  warming up..."); _ = _stt_text("c0.mp3")

clean_ms, clean_wer, phone_wer = [], [], []
print("\n--- STT: SAID vs HEARD + latency + REAL WER (Devanagari) ---")
for i, (dev, roman) in enumerate(TESTS):
    if i > 0:
        asyncio.run(_say(dev, f"c{i}.mp3"))
    y, _ = librosa.load(f"c{i}.mp3", sr=16000, mono=True); sf.write(f"c{i}.wav", y, 16000)
    t = time.time(); heard = _stt_text(f"c{i}.mp3"); ms = (time.time()-t)*1000; clean_ms.append(ms)
    w = _wer(dev, heard)
    if w is not None: clean_wer.append(w)
    # 8kHz telephony simulation
    y8 = librosa.resample(librosa.resample(y, orig_sr=16000, target_sr=8000),
                          orig_sr=8000, target_sr=16000)
    sf.write("c8.wav", y8, 16000)
    heard8 = _stt_text("c8.wav"); wp = _wer(dev, heard8)
    if wp is not None: phone_wer.append(wp)
    print(f"\nSAID      : {roman}")
    print(f"  (deva)  : {dev}")
    print(f"HEARD     : {heard}")
    print(f"HEARD 8kHz: {heard8}")
    extra = (f" | WER clean ~{w:.0f}%  phone ~{wp:.0f}%" if (w is not None and wp is not None) else "")
    print(f"  latency {ms:.0f}ms for {len(y)/16000:.1f}s audio{extra}")

# ---------------- TTS: public Meta MMS Hindi ----------------
print("\n[2/2] Loading TTS (facebook/mms-tts-hin, public)...")
tts_ms = None
try:
    from transformers import VitsModel, AutoTokenizer
    t = time.time()
    mms = VitsModel.from_pretrained("facebook/mms-tts-hin")
    mtok = AutoTokenizer.from_pretrained("facebook/mms-tts-hin")
    if DEV == "cuda": mms = mms.to("cuda")
    print(f"  loaded in {time.time()-t:.1f}s")
    SAY = "बिल्कुल सर, मैं आपकी पूरी मदद करूँगी। आज ही फ्री ट्रायल सेट कर देती हूँ।"
    def _synth(text):
        ins = mtok(text, return_tensors="pt")
        if DEV == "cuda": ins = {k: v.to("cuda") for k, v in ins.items()}
        with torch.no_grad():
            wav = mms(**ins).waveform
        return wav.squeeze().detach().cpu().numpy().astype(np.float32)
    _ = _synth("नमस्ते")  # warmup
    t = time.time(); audio = _synth(SAY); tts_ms = (time.time()-t)*1000
    sf.write("mms_tts_out.wav", audio, mms.config.sampling_rate)
    print(f"\nTTS '{SAY[:30]}...' -> {tts_ms:.0f}ms  saved mms_tts_out.wav")
    try:
        from IPython.display import Audio, display
        display(Audio("mms_tts_out.wav"))
    except Exception:
        pass
except Exception as e:
    print("\nTTS step skipped/failed (share error):", str(e)[:160])

# ---------------- SUMMARY / GO–NO-GO ----------------
def _avg(x): return (sum(x)/len(x)) if x else float("nan")
print("\n" + "=" * 62)
print("SUMMARY   (FREE T4 GPU, PUBLIC models — no login)")
print(f"  STT latency avg : {_avg(clean_ms):.0f} ms / utterance  (Whisper; real Conformer = faster)")
if clean_wer: print(f"  STT WER clean   : ~{_avg(clean_wer):.0f}%   (real Devanagari WER)")
if phone_wer: print(f"  STT WER 8kHz    : ~{_avg(phone_wer):.0f}%   (telephony gap → fine-tune closes)")
if tts_ms is not None: print(f"  TTS latency     : {tts_ms:.0f} ms / sentence  (MMS; IndicF5 = clonable voice)")
print("\nGO / NO-GO read:")
print("  GREEN : HEARD ≈ SAID + clean WER < ~15% + STT < ~2s (Conformer will beat it)")
print("  this proves the CONCEPT (self-host Indian STT+TTS on free GPU works).")
print("  For the exact target stack (IndicConformer + IndicF5 voice-clone) you need")
print("  a one-time HF token -> run colab_proof.py instead. Production server.py uses")
print("  the same gated models, so you'll set the token up once anyway.")
print("=" * 62)
print("Share with me: this SUMMARY + 2-3 SAID/HEARD lines + how mms_tts_out.wav sounds.")
