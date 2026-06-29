# ============================================================================
# AI4Bharat voice-stack PROOF v2 — run on FREE Google Colab GPU (zero cost)
# ============================================================================
# HOW:
#   1. https://colab.research.google.com  ->  New notebook
#   2. Runtime > Change runtime type > Hardware accelerator = T4 GPU  (free)
#   3. Paste this WHOLE file into ONE cell, Run. (~5 min first time = model download)
#   4. Read the SUMMARY at the bottom — that is your GO / NO-GO for the GPU box.
#
# Proves IndicConformer (STT) + IndicF5 (TTS) Hinglish quality on a real 16GB GPU,
# WITHOUT your laptop's 4GB-VRAM / disk / network limits.
#
# What v2 fixes (so the decision is honest):
#   (a) WARMS UP the GPU before timing  -> real steady-state latency, not cold-start
#   (b) IndicConformer outputs DEVANAGARI (expected) -> we eyeball SAID vs HEARD,
#       and also print an APPROX script-normalized WER (eyeball is the real judge)
#   (c) also runs an 8kHz "telephony" downsample -> shows the phone-domain gap that
#       warm-start (GramVaani/Kathbath) + fine-tuning on OUR calls will close
#   (d) shows CTC and RNNT decoding (RNNT usually more accurate) + a GO/NO-GO summary
# ============================================================================

import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                "transformers", "torchaudio", "soundfile", "librosa", "edge-tts",
                "nest_asyncio", "indic-transliteration", "jiwer"], check=True)

import asyncio, os, time, re, warnings
import librosa, numpy as np, soundfile as sf, torch
import nest_asyncio
from transformers import AutoModel

nest_asyncio.apply()            # Colab already runs a loop -> allow asyncio.run()
warnings.filterwarnings("ignore")

# --- Optional HuggingFace token (ONLY if a model is GATED, e.g. IndicF5) ---
# Most of this proof needs NO key. If IndicF5 (TTS) download errors with
# "gated"/401/403:  (1) make a token at huggingface.co/settings/tokens (read role),
# (2) ACCEPT the model's terms on its HF page,  (3) Colab left sidebar 🔑 -> add a
# secret named  HF_TOKEN = <your token>  (rename your "test" secret to HF_TOKEN),
# enable "Notebook access", then re-run. The block below picks it up automatically.
try:
    from google.colab import userdata  # type: ignore
    _hf = userdata.get("HF_TOKEN")
    if _hf:
        os.environ["HF_TOKEN"] = _hf
        os.environ["HUGGING_FACE_HUB_TOKEN"] = _hf
        try:
            from huggingface_hub import login
            login(_hf)
        except Exception:
            pass
        print("HF token loaded from Colab secret HF_TOKEN.")
except Exception:
    pass  # not on Colab / no secret set -> fine for public models

DEV = "cuda" if torch.cuda.is_available() else "cpu"
print("GPU:", torch.cuda.get_device_name(0) if DEV == "cuda" else
      "*** NO GPU — Runtime > Change runtime type > T4 GPU, then re-run ***")

# ---------------- helpers ----------------
def _to_roman(s):
    """Devanagari -> rough roman (for an APPROX WER only; eyeball is the real judge)."""
    try:
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import transliterate
        return transliterate(str(s), sanscript.DEVANAGARI, sanscript.ITRANS)
    except Exception:
        return str(s)

def _norm(s):
    return re.sub(r"[^a-z0-9\s]", " ", _to_roman(s).lower()).split()

def _wer(ref, hyp):
    try:
        import jiwer
        r, h = " ".join(_norm(ref)), " ".join(_norm(hyp))
        if not r.strip():
            return None
        return jiwer.wer(r, h) * 100.0
    except Exception:
        return None

async def _say(text, path):
    import edge_tts
    await edge_tts.Communicate(text, "hi-IN-SwaraNeural").save(path)

def _stt(model, y16):
    """Run both CTC and RNNT decoding; return {'ctc':..,'rnnt':..} defensively."""
    wav = torch.tensor(y16, dtype=torch.float32).unsqueeze(0)
    if DEV == "cuda":
        wav = wav.to("cuda")
    out = {}
    for dec in ("ctc", "rnnt"):
        try:
            with torch.no_grad():
                r = model(wav, "hi", dec)
            out[dec] = r if isinstance(r, str) else (r[0] if isinstance(r, (list, tuple)) else str(r))
        except Exception as e:
            out[dec] = f"<{dec} unavailable: {str(e)[:60]}>"
    return out

# ---------------- STT: IndicConformer ----------------
print("\n[1/2] Loading IndicConformer (STT)...")
t = time.time()
stt = AutoModel.from_pretrained("ai4bharat/indic-conformer-600m-multilingual",
                                trust_remote_code=True)
if DEV == "cuda":
    try: stt = stt.to("cuda")
    except Exception: pass
print(f"  loaded in {time.time()-t:.1f}s")

TESTS = [
    "Namaste, mera bijli ka bill bahut zyada aata hai, main solar lagwana chahta hoon.",
    "Aapke paas kya kya features hain, mujhe sab detail mein batao.",
    "Haan main interested hoon, appointment book karo kal subah gyarah baje.",
]

# make clip 0 + WARM UP the GPU (first inference compiles kernels = NOT real latency)
print("  warming up GPU (discarding first inference)...")
asyncio.run(_say(TESTS[0], "c0.mp3"))
y0, _ = librosa.load("c0.mp3", sr=16000, mono=True)
sf.write("c0.wav", y0, 16000)          # wav copy = IndicF5 voice reference
_ = _stt(stt, y0)                       # warmup, discarded

clean_ms, clean_wer, phone_wer = [], [], []
print("\n--- STT: SAID vs HEARD (Devanagari output is EXPECTED) + latency + approx WER ---")
for i, text in enumerate(TESTS):
    if i > 0:
        asyncio.run(_say(text, f"c{i}.mp3"))
    y, _ = librosa.load(f"c{i}.mp3", sr=16000, mono=True)
    sf.write(f"c{i}.wav", y, 16000)
    # clean 16kHz (web-call quality)
    t = time.time(); o = _stt(stt, y); ms = (time.time() - t) * 1000; clean_ms.append(ms)
    w = _wer(text, o.get("rnnt") if "unavailable" not in str(o.get("rnnt")) else o.get("ctc"))
    if w is not None: clean_wer.append(w)
    # simulated 8kHz telephony (downsample 16k->8k->16k = phone band-limit)
    y8 = librosa.resample(librosa.resample(y, orig_sr=16000, target_sr=8000),
                          orig_sr=8000, target_sr=16000)
    op = _stt(stt, y8)
    hp = op.get("rnnt") if "unavailable" not in str(op.get("rnnt")) else op.get("ctc")
    wp = _wer(text, hp)
    if wp is not None: phone_wer.append(wp)
    print(f"\nSAID      : {text}")
    print(f"HEARD ctc : {str(o.get('ctc')).strip()}")
    print(f"HEARD rnnt: {str(o.get('rnnt')).strip()}")
    print(f"HEARD 8kHz: {str(hp).strip()}")
    extra = (f" | approx WER  clean ~{w:.0f}%  phone ~{wp:.0f}%"
             if (w is not None and wp is not None) else "")
    print(f"  latency {ms:.0f}ms for {len(y)/16000:.1f}s audio{extra}")

# ---------------- TTS: IndicF5 (voice clone) ----------------
print("\n[2/2] Loading IndicF5 (TTS, voice-clone)...")
t = time.time()
tts = AutoModel.from_pretrained("ai4bharat/IndicF5", trust_remote_code=True)
if DEV == "cuda":
    try: tts = tts.to("cuda")
    except Exception: pass
print(f"  loaded in {time.time()-t:.1f}s")

REF_AUDIO, REF_TEXT = "c0.wav", TESTS[0]     # ref voice = clip 0 (or upload your own ref.wav)
SAY = "Bilkul sir, main aapki poori madad karungi. Aaj hi free trial set kar deti hoon."

def _synth(text):
    a = tts(text, ref_audio_path=REF_AUDIO, ref_text=REF_TEXT)
    a = np.asarray(a)
    if a.dtype == np.int16:
        a = a.astype(np.float32) / 32768.0
    return a.astype(np.float32)

try:
    _ = _synth("warm up")                     # warmup, discarded
except Exception as e:
    print("  TTS warmup note:", str(e)[:80])

t = time.time()
tts_ms = None
try:
    audio = _synth(SAY)
    tts_ms = (time.time() - t) * 1000
    sf.write("indicf5_out.wav", audio, 24000)
    print(f"\nTTS: '{SAY[:40]}...' -> {tts_ms:.0f}ms  saved indicf5_out.wav")
    try:
        from IPython.display import Audio, display
        display(Audio("indicf5_out.wav"))
    except Exception:
        pass
except Exception as e:
    print("\nTTS FAILED (share this error so I fix the call signature):", str(e)[:160])

# ---------------- SUMMARY / GO–NO-GO ----------------
def _avg(x): return (sum(x) / len(x)) if x else float("nan")
print("\n" + "=" * 62)
print("SUMMARY   (FREE T4 GPU)")
print(f"  STT latency  avg : {_avg(clean_ms):.0f} ms / utterance")
if clean_wer: print(f"  STT WER clean    : ~{_avg(clean_wer):.0f}%   (approx, script-normalized)")
if phone_wer: print(f"  STT WER 8kHz     : ~{_avg(phone_wer):.0f}%   (telephony gap)")
if tts_ms is not None: print(f"  TTS latency      : {tts_ms:.0f} ms / sentence")
print("\nGO / NO-GO guide (real-time cold calls):")
print("  GREEN : eyeball HEARD ≈ SAID  +  STT < ~800ms  +  TTS < ~1500ms/sentence")
print("  AMBER : quality good but TTS slow -> EdgeTTS for LIVE, IndicF5 for premium")
print("  judge TTS by EAR (indicf5_out.wav), STT by EYE (SAID vs HEARD above)")
print("  8kHz WER >> clean WER is NORMAL — that gap = exactly why we warm-start on")
print("  telephony data (GramVaani SLR118 / Kathbath) + fine-tune on OUR calls.")
print("=" * 62)
print("Share with me: this SUMMARY + 2-3 SAID/HEARD lines + how indicf5_out.wav sounds.")
