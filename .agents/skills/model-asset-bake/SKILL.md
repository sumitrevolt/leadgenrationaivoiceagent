---
name: model-asset-bake
description: ML model assets (fastembed/silero/whisper/onnx) production me kaise rakhein — image-bake, off-loop load, hard deadline, disable-switch. Use jab koi naya model/embedding/VAD/STT asset add ho, "app freeze/unhealthy after rebuild" / "CPU 0% workers stuck" debug karna ho, ya runtime model-download hang suspect ho.
---

# Model Asset Bake — runtime download = prod down

## Incident (2026-06-12, isi se yeh skill bana)
Image rebuild ne fastembed model cache wipe kiya → pehli web-call websocket par
`TextEmbedding()` ne HuggingFace se ~250MB runtime download shuru kiya — SYNC,
event loop par → dono uvicorn workers freeze → poora prod down (CPU 0%, health
timeout). py-spy dump se pakda: `_get_qdrant_embedder` me atka tha.

## Rule (har model asset ke liye, NO exceptions)
1. **BAKE in image** — Dockerfile me build-time download + fixed path env:
   ```dockerfile
   ENV FASTEMBED_CACHE_PATH=/opt/fastembed_cache
   RUN (python -c "from fastembed import TextEmbedding; TextEmbedding('<model>')" \
       && chmod -R a+rX /opt/fastembed_cache) || echo "WARN: bake failed"
   ```
   - torch chahiye to CPU wheels: `--index-url https://download.pytorch.org/whl/cpu`
     (PyPI default linux torch = CUDA ~2.5GB).
   - silero-vad pip package me model wheel ke andar bundled hai (no download).
   - Bake fail = non-fatal (`|| echo WARN`) — image phir bhi bane, runtime fallback.
2. **Load OFF the event loop** — async path me KABHI direct heavy init nahi:
   `await asyncio.wait_for(asyncio.to_thread(init_fn), timeout=10-15s)`, fail → degrade.
   (web_call.py `_run_blocking`, phone_stream `_llm_reply` pattern dekho.)
3. **Hard deadline + disable-switch** — loader thread + `threading.Event.wait(timeout)`;
   timeout par process-level `_DISABLED=True` set karo taaki har call dobara na latke
   (knowledge_base.py `_get_qdrant_embedder` pattern). Orphan thread complete ho jaye
   to singleton set = agla use fast.
4. **Health check** — Hermes `_check_embedder` jaisa disk-only check (model load mat
   karo health me!): cache dir me `*.onnx` exists? Missing = alert "rebuild/bake karo".

## Debug checklist ("app unhealthy + CPU ~0%")
1. `docker inspect leadgen_app --format '{{json .State.Health}}'` — timeout streak?
2. HOST se: `pip install py-spy --break-system-packages; docker top leadgen_app` →
   worker PIDs → `py-spy dump --pid <pid>` (container ke andar py-spy = ptrace denied).
3. Stack me model/network init dikhe → yeh skill follow karo.
4. Turant recover: `docker restart leadgen_app`; warm: `docker exec -d leadgen_app python -c "<model init>"`.

## Current baked assets (update karte rehna)
- fastembed `paraphrase-multilingual-MiniLM-L12-v2` → `/opt/fastembed_cache` (Dockerfile.lock)
- silero-vad (wheel-bundled model, torch CPU) → `USE_SILERO_VAD=1`
