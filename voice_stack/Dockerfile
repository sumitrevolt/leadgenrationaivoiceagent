# Self-hosted voice model-server (AI4Bharat) — GPU container.
# Deploy on ANY NVIDIA GPU box (cloud or dedicated) in one command:
#   docker build -t leadgen-voice voice_stack/
#   docker run --gpus all -p 8900:8900 \
#       -e REF_AUDIO=/ref/ref_voice.wav -e REF_TEXT="namaste main swara bol rahi hoon" \
#       -v /path/to/ref:/ref  leadgen-voice
# Then on the app:  AI4BHARAT_ENDPOINT=http://<gpu-box-ip>:8900  STT_PROVIDER=ai4bharat  TTS_PROVIDER=ai4bharat
#
# CUDA 12.1 runtime + cuDNN. Models download on first start (cached in the image
# layer if you COPY a warm HF cache, else at runtime to /root/.cache/huggingface).

FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip ffmpeg libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
# CUDA torch first (cu121), then the rest
RUN pip3 install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cu121
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY server.py .

# Concurrency: 1500 calls/day ≈ 20-50 peak concurrent. Tune --workers to your GPU
# (1 worker per ~8GB VRAM model copy; a 24GB L4 ≈ 2-3 workers). uvicorn async handles
# I/O; the GPU forward pass is the bottleneck → add workers or a 2nd GPU to scale.
EXPOSE 8900
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8900", "--workers", "1"]
