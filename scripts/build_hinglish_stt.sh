#!/usr/bin/env sh
# =============================================================================
# build_hinglish_stt.sh — free self-host Hinglish STT (Sarvam-Saaras alternative)
# -----------------------------------------------------------------------------
# Converts an OPEN-WEIGHTS Hinglish-finetuned Whisper (HF transformers format)
# into the CTranslate2 int8 format that the project's EXISTING faster-whisper
# runtime loads directly. So we add a strong, ROMAN-Hinglish-output local STT
# model with ZERO new runtime dependency and ZERO recurring cost.
#
# This is a BUILD-TIME / OFFLINE step (baked into the image, like fastembed /
# silero). Runtime never downloads. ctranslate2 + transformers + torch are
# already in the venv (faster-whisper depends on ctranslate2; torch+transformers
# come from the silero/kokoro bakes in Dockerfile.lock).
#
# Env overrides:
#   HINGLISH_HF_MODEL    HF repo id   (default Oriserve/Whisper-Hindi2Hinglish-Swift)
#   HINGLISH_WHISPER_DIR output dir   (default /opt/hinglish_whisper)
#   HINGLISH_CT2_QUANT   quantization (default int8)
#
# Accuracy-max swap (heavier, ~3x size, large-v3 base):
#   HINGLISH_HF_MODEL=Oriserve/Whisper-Hindi2Hinglish-Prime sh scripts/build_hinglish_stt.sh
#
# Non-fatal by design: the Dockerfile guards this with `|| echo WARN` so a bake
# failure still produces a working image (falls back to whisper-base).
# =============================================================================
set -e

HF_MODEL="${HINGLISH_HF_MODEL:-Oriserve/Whisper-Hindi2Hinglish-Swift}"
OUT_DIR="${HINGLISH_WHISPER_DIR:-/opt/hinglish_whisper}"
QUANT="${HINGLISH_CT2_QUANT:-int8}"

echo "[hinglish-stt] converting ${HF_MODEL} -> ${OUT_DIR} (quant=${QUANT}) ..."

# ct2-transformers-converter is the console script shipped with ctranslate2.
# --copy_files brings the tokenizer + feature-extractor config that
# faster-whisper needs alongside the converted model.bin.
ct2-transformers-converter \
  --model "${HF_MODEL}" \
  --output_dir "${OUT_DIR}" \
  --quantization "${QUANT}" \
  --copy_files tokenizer.json preprocessor_config.json \
  --force

# World-readable so the non-root `appuser` runtime can load it.
chmod -R a+rX "${OUT_DIR}"

echo "[hinglish-stt] done -> ${OUT_DIR}"
ls -la "${OUT_DIR}" || true
