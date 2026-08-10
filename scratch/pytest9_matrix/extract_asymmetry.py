#!/usr/bin/env python3
"""Extract green_is_gc asymmetry proof from greenlet 3.5.4 sdist (scratch)."""
from __future__ import annotations

import subprocess
import tarfile
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)
TMP = Path(tempfile.mkdtemp(prefix="greenlet_probe_"))

subprocess.check_call(
    ["python", "-m", "pip", "download", "-q", "--no-binary=:all:", "greenlet==3.5.4"],
    cwd=TMP,
)
sdist = next(TMP.glob("greenlet-*.tar.gz"))
with tarfile.open(sdist, "r:gz") as tf:

    def _safe_members(members):
        for member in members:
            name = member.name.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                continue
            yield member

    tf.extractall(TMP, members=_safe_members(tf))
src = next(TMP.glob("greenlet-*/src/greenlet/PyGreenlet.cpp"))
text = src.read_text(encoding="utf-8")

traverse_start = text.find("green_traverse")
is_gc_start = text.find("\ngreen_is_gc")
clear_start = text.find("\ngreen_clear")
traverse_block = text[traverse_start:is_gc_start]
is_gc_block = text[is_gc_start:clear_start]

proof = []
proof.append(f"source={src}")
proof.append(f"traverse_null_guard={'if (!self->pimpl)' in traverse_block}")
proof.append(f"is_gc_null_guard={'if (!self->pimpl)' in is_gc_block}")
proof.append(f"is_gc_calls_main={'main()' in is_gc_block}")
proof.append(f"is_gc_calls_active={'active()' in is_gc_block}")
proof.append(f"is_gc_calls_dead={'was_running_in_dead_thread()' in is_gc_block}")
proof.append("")
proof.append("==== green_traverse excerpt ====")
# find the null guard context
for i, line in enumerate(traverse_block.splitlines()):
    if "pimpl" in line or "traverse" in line.lower():
        proof.append(line)
proof.append("")
proof.append("==== green_is_gc excerpt ====")
proof.append(is_gc_block[:1200])

(OUT / "C_asymmetry_proof.txt").write_text("\n".join(proof) + "\n", encoding="utf-8")
print("\n".join(proof[:12]))
print("WROTE", OUT / "C_asymmetry_proof.txt")
