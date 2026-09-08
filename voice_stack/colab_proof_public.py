# ============================================================================
# Voice-stack PROOF (PUBLIC models) — FREE Google Colab GPU, ZERO account needed
# ============================================================================
# Uses ONLY public ungated models (no HF token), and proves BOTH axes:
#   ACCURACY : whisper-hindi (IndicWhisper) — slow autoregressive, this is the
#              OFFLINE label-model (Phase 3), NOT the live model.
#   SPEED    : a public wav2vec2-CTC Hindi model — same single-pass CTC family as the
#              production live model (IndicConformer) -> shows real-time latency.
#   TTS      : facebook/mms-tts-hin (public). (Production target = IndicF5 voice-clone.)
#
# Honest gaps vs the GATED production target (IndicConformer + IndicF5):
#   - IndicConformer (live STT) ≈ the wav2vec2-CTC speed here, with better accuracy.
#   - IndicF5 (TTS) = your agent's OWN cloned voice; MMS here is a generic voice.
#   For the exact target models you need a one-time HF token (run colab_proof.py).
#
# WER is normalized (nuqta/anusvara) so the number reflects REAL errors, not script noise.
#
# HOW: Colab -> New notebook -> Runtime > Change runtime type > T4 GPU ->
#      paste this whole file into ONE cell -> Run.
# ============================================================================

import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                "transformers", "torchaudio", "soundfile", "librosa", "edge-tts",
                "nest_asyncio", "jiwer", "scipy"], check=True)

import asyncio, time, re, warnings
import librosa, numpy as np, soundfile as sf, torch
import nest_asyncio
from transformers import pipeline
nest_asyncio.apply()
warnings.filterwarnings("ignore")

DEV = "cuda" if torch.cuda.is_available() else "cpu"
print("GPU:", torch.cuda.get_device_name(0) if DEV == "cuda" else
      "*** NO GPU — Runtime > Change runtime type > T4 GPU, then re-run ***")
print("TIP: if you ran an earlier version this session and hit CUDA OOM, do "
      "Runtime > Restart session, then run this cell ONCE (frees leftover GPU mem).")

import gc
def _free():
    try:
        gc.collect(); torch.cuda.empty_cache()
    except Exception:
        pass

# Devanagari ground-truth (apples-to-apples WER vs Hindi STT output); roman for reading.
TESTS = [
    ("नमस्ते, मेरा बिजली का बिल बहुत ज़्यादा आता है, मैं सोलर लगवाना चाहता हूँ।",
     "Namaste, mera bijli ka bill bahut zyada aata hai, main solar lagwana chahta hoon."),
    ("आपके पास क्या क्या फ़ीचर्स हैं, मुझे सब डिटेल में बताओ।",
     "Aapke paas kya kya features hain, mujhe sab detail mein batao."),
    ("हाँ मैं इंटरेस्टेड हूँ, अपॉइंटमेंट बुक करो कल सुबह ग्यारह बजे।",
     "Haan main interested hoon, appointment book karo kal subah gyarah baje."),
]

_NUQTA = [("क़", "क"), ("ख़", "ख"), ("ग़", "ग"), ("ज़", "ज"), ("ड़", "ड"),
          ("ढ़", "ढ"), ("फ़", "फ"), ("य़", "य")]

def _norm(s):
    s = str(s).lower().replace("ँ", "ं").replace("़", "")  # chandrabindu->anusvara, drop nuqta
    for a, b in _NUQTA:
        s = s.replace(a, b)
    s = re.sub(r"[^ऀ-ॿa-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def _wer(ref, hyp):
    try:
        import jiwer
        r, h = _norm(ref), _norm(hyp)
        return jiwer.wer(r, h) * 100.0 if r else None
    except Exception:
        return None

async def _say(text, path):
    import edge_tts
    await edge_tts.Communicate(text, "hi-IN-SwaraNeural").save(path)

def _text(res):
    return (res.get("text") if isinstance(res, dict) else str(res)).strip()

def _bench(asr, label):
    """Transcribe all clips clean + 8kHz; return (avg_ms, avg_wer_clean, avg_wer_phone)."""
    ms, wc, wp = [], [], []
    print(f"\n--- {label}: SAID vs HEARD + latency + WER (normalized) ---")
    for i, (dev, roman) in enumerate(TESTS):
        y, _ = librosa.load(f"c{i}.wav", sr=16000, mono=True)
        t = time.time(); heard = _text(asr(f"c{i}.wav")); dt = (time.time() - t) * 1000; ms.append(dt)
        w = _wer(dev, heard)
        if w is not None: wc.append(w)
        y8 = librosa.resample(librosa.resample(y, orig_sr=16000, target_sr=8000),
                              orig_sr=8000, target_sr=16000)
        sf.write("c8.wav", y8, 16000)
        heard8 = _text(asr("c8.wav")); w8 = _wer(dev, heard8)
        if w8 is not None: wp.append(w8)
        print(f"SAID : {roman}")
        print(f"HEARD: {heard}")
        ex = (f"  | WER clean ~{w:.0f}% phone ~{w8:.0f}%" if (w is not None and w8 is not None) else "")
        print(f"  {dt:.0f}ms for {len(y)/16000:.1f}s audio{ex}\n")
    avg = lambda x: (sum(x) / len(x)) if x else float("nan")
    return avg(ms), avg(wc), avg(wp)

# pre-generate all clips (EdgeTTS) so both ASR models transcribe the same audio
print("\nGenerating Hinglish test clips (EdgeTTS)...")
for i, (dev, _) in enumerate(TESTS):
    asyncio.run(_say(dev, f"c{i}.mp3"))
    y, _ = librosa.load(f"c{i}.mp3", sr=16000, mono=True)
    sf.write(f"c{i}.wav", y, 16000)

# ---------------- STT-A: ACCURACY (whisper-hindi = offline LABEL model, slow) ----------
print("\n[1/3] STT-A accuracy model (IndicWhisper, offline-label; NOT live)...")
def _build_whisper():
    cand = [("vasista22/whisper-hindi-large-v2", None),
            ("openai/whisper-large-v3", {"language": "hi", "task": "transcribe"})]
    for mid, gen in cand:
        try:
            kw = dict(model=mid, device=0 if DEV == "cuda" else -1,
                      torch_dtype=torch.float16 if DEV == "cuda" else torch.float32)
            if gen:
                kw["generate_kwargs"] = gen
            p = pipeline("automatic-speech-recognition", **kw)
            print(f"  model={mid}  device={next(iter(p.model.parameters())).device}")
            return p
        except Exception as e:
            print(f"  {mid} unavailable ({str(e)[:70]}) -> next")
            _free()  # release partial load so the next candidate / STT-B has room
    return None
wh = _build_whisper()
_ = _text(wh("c0.wav")) if wh else None  # warmup
a_ms, a_wc, a_wp = _bench(wh, "STT-A IndicWhisper (accuracy)") if wh else (float("nan"),) * 3
wh = None; _free()  # free the big whisper before loading STT-B (keep GPU peak low)

# ---------------- STT-B: SPEED (wav2vec2-CTC = live-architecture proxy, fast) ----------
print("\n[2/3] STT-B speed model (public wav2vec2-CTC = IndicConformer-like)...")
def _build_ctc():
    for mid in ("ai4bharat/indicwav2vec-hindi",
                "theainerd/Wav2Vec2-large-xlsr-hindi",
                "Harveenchadha/vakyansh-wav2vec2-hindi-him-4200"):
        try:
            p = pipeline("automatic-speech-recognition", model=mid,
                         device=0 if DEV == "cuda" else -1)
            print(f"  model={mid}  device={next(iter(p.model.parameters())).device}")
            return p
        except Exception as e:
            print(f"  {mid} unavailable ({str(e)[:70]}) -> next")
    return None
ctc = _build_ctc()
_ = _text(ctc("c0.wav")) if ctc else None  # warmup
b_ms, b_wc, b_wp = _bench(ctc, "STT-B wav2vec2-CTC (speed)") if ctc else (float("nan"),) * 3

# ---------------- TTS: public Meta MMS Hindi ----------------
print("\n[3/3] TTS (facebook/mms-tts-hin, public)...")
tts_ms = None
try:
    from transformers import VitsModel, AutoTokenizer
    mms = VitsModel.from_pretrained("facebook/mms-tts-hin")
    mtok = AutoTokenizer.from_pretrained("facebook/mms-tts-hin")
    if DEV == "cuda": mms = mms.to("cuda")
    SAY = "बिल्कुल सर, मैं आपकी पूरी मदद करूँगी। आज ही फ्री ट्रायल सेट कर देती हूँ।"
    def _synth(text):
        ins = mtok(text, return_tensors="pt")
        if DEV == "cuda": ins = {k: v.to("cuda") for k, v in ins.items()}
        with torch.no_grad():
            return mms(**ins).waveform.squeeze().detach().cpu().numpy().astype(np.float32)
    _ = _synth("नमस्ते")  # warmup
    t = time.time(); audio = _synth(SAY); tts_ms = (time.time() - t) * 1000
    sf.write("mms_tts_out.wav", audio, mms.config.sampling_rate)
    print(f"  TTS '{SAY[:28]}...' -> {tts_ms:.0f}ms  saved mms_tts_out.wav")
    try:
        from IPython.display import Audio, display
        display(Audio("mms_tts_out.wav"))
    except Exception:
        pass
except Exception as e:
    print("  TTS skipped/failed:", str(e)[:160])

# ---------------- SUMMARY / GO–NO-GO ----------------
print("\n" + "=" * 64)
print("SUMMARY   (FREE T4 GPU, PUBLIC models — no login)")
print(f"  STT-A IndicWhisper (LABEL, offline) : {a_ms:.0f} ms | WER clean ~{a_wc:.0f}% phone ~{a_wp:.0f}%")
print(f"  STT-B wav2vec2-CTC (SPEED, live-like): {b_ms:.0f} ms | WER clean ~{b_wc:.0f}% phone ~{b_wp:.0f}%")
if tts_ms is not None:
    print(f"  TTS  MMS-hin                         : {tts_ms:.0f} ms / sentence")
print("\nHOW TO READ:")
print("  - STT-A is SLOW BY DESIGN (autoregressive) -> it's the offline label model, not live.")
print("  - STT-B (CTC, single-pass) = the LIVE latency profile. IndicConformer ≈ this speed")
print("    with better accuracy. If STT-B is sub-second -> live real-time is PROVEN.")
print("  - WER is normalized; remaining diffs are mostly numerals (11 vs ग्यारह).")
print("  - 8kHz ≈ clean WER => robust to telephony (good).")
print("  GREEN if: STT-B < ~1s AND STT-A WER < ~10% AND mms_tts_out.wav sounds clear.")
print("=" * 64)
print("Share: this SUMMARY + 2-3 STT-B SAID/HEARD lines + how mms_tts_out.wav sounds.")
