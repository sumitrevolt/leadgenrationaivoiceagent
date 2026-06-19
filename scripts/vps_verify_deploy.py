#!/usr/bin/env python3
"""Read-only deploy verification — run inside the prod container:

    ssh root@VPS "docker exec -i leadgen_app python -" < scripts/vps_verify_deploy.py

Confirms the LIVE image actually contains the latest code + baked deps (not just a
git-pulled checkout). Never mutates anything.
"""
import importlib.util as u
import os


def spec(name: str) -> bool:
    try:
        return u.find_spec(name) is not None
    except Exception:
        return False


print("=== DEPLOY VERIFY (live container) ===")
# app modules that only exist if app/ was rebuilt into the image
print("kokoro_tts module :", spec("app.voice_agent.kokoro_tts"))
print("eval_metrics      :", spec("app.agents.eval_metrics"))
print("hybrid_search     :", spec("app.ml.hybrid_search"))
print("reranker          :", spec("app.ml.reranker"))
# Dockerfile-baked deps (only present if the image was REBUILT, not just recreated)
print("kokoro pkg baked  :", spec("kokoro"))
print("pipecat baked     :", spec("pipecat"))
# numpy/sklearn drift that Cursor's f674f6c fixed — confirm no breakage
try:
    import numpy, sklearn, scipy  # noqa
    print("numpy/sklearn/scipy:", "OK", getattr(numpy, "__version__", "?"))
except Exception as e:
    print("numpy/sklearn/scipy:", "BROKEN", e)
# eval module actually runs
try:
    from app.agents import eval_metrics as em
    print("eval sanity score :", em.transcript_quality([{"role": "assistant", "content": "Ek line. Interested?"}]))
except Exception as e:
    print("eval sanity       :", "ERR", e)
print("flags:",
      "RERANKER=", os.environ.get("USE_RERANKER"),
      "HYBRID=", os.environ.get("USE_HYBRID_SEARCH"),
      "CONTEXTUAL=", os.environ.get("USE_CONTEXTUAL_INGEST"),
      "KOKORO=", os.environ.get("USE_KOKORO_TTS"))
print("--- end verify ---")
