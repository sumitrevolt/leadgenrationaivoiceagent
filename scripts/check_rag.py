"""Verify the vector RAG fix: embedder loads + semantic retrieve works (not keyword).
Run on VPS: cd /opt/leadgen && .venv/bin/python scripts/check_rag.py
(First run downloads the fastembed model — may take ~30-60s.)
"""

import os
import sys

for _p in ("/opt/leadgen/.env", ".env"):
    if os.path.exists(_p):
        for _ln in open(_p, encoding="utf-8"):
            _ln = _ln.strip()
            if _ln and not _ln.startswith("#") and "=" in _ln:
                _k, _v = _ln.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
        break
sys.path.insert(0, os.getcwd())

from app.voice_agent import knowledge_base as KB

try:
    KB._get_qdrant_embedder()
    print("EMBEDDER: OK ->", KB._E5_MODEL_NAME, "dim=", KB._QDRANT_VECTOR_SIZE)
except Exception as e:
    print("EMBEDDER: FAIL ->", repr(e))

kb = KB.get_knowledge_base()
try:
    kb.add_documents(
        [
            "Solar panels lagane se bijli ka monthly bill 70 percent tak kam ho jata hai, 25 saal warranty milti hai."
        ],
        source="ragtest",
        namespace="niche:ragtest",
    )
    hits = kb.retrieve("electricity bill kaise kam karu", k=2, namespace="niche:ragtest")
    print(
        "RETRIEVE: hits=",
        len(hits),
        "| top_score=",
        (round(hits[0].get("score", 0), 3) if hits else None),
    )
    print("TOP:", (hits[0].get("text", "")[:70] if hits else "—"))
except Exception as e:
    print("RETRIEVE: FAIL ->", repr(e))
