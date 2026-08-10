#!/bin/bash
# Lane C — stock vs NULL-guard greenlet diagnostic builds (scratch; never ship wheel)
set -euo pipefail
OUT=scratch/pytest9_matrix
mkdir -p "$OUT"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq gcc g++ gdb make python3-dev >/tmp/apt.log
python -m pip install -q --upgrade pip wheel setuptools
cd /tmp
rm -rf greenlet-src
python -m pip download -q --no-binary=:all: "greenlet==3.5.4"
tar xf greenlet-3.5.4.tar.gz
SRC=/tmp/greenlet-3.5.4
# Locate green_is_gc
grep -RIn "green_is_gc\|green_traverse" "$SRC" --include='*.cpp' --include='*.c' --include='*.h' \
  | tee "$OUT/C_source_hits.txt" | head -50

python - <<'PY' | tee "$OUT/C_asymmetry.txt"
from pathlib import Path
root = Path("/tmp/greenlet-3.5.4")
for path in root.rglob("*"):
    if path.suffix.lower() not in {".cpp", ".c", ".h", ".hpp"}:
        continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "green_is_gc" not in text:
        continue
    print("FILE", path)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "green_is_gc" in line or "green_traverse" in line:
            start = max(0, i - 2)
            end = min(len(lines), i + 25)
            for j in range(start, end):
                print(f"{j+1}:{lines[j]}")
            print("---")
PY

# Create guarded copy: insert NULL pimpl check mirroring green_traverse
python - <<'PY'
from pathlib import Path
root = Path("/tmp/greenlet-3.5.4")
patched = False
for path in root.rglob("*"):
    if path.suffix.lower() not in {".cpp", ".c"}:
        continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "green_is_gc" not in text:
        continue
    # Conservative: if function body lacks pimpl NULL check near start, inject after opening brace of green_is_gc
    import re
    def inject(m):
        body = m.group(0)
        if "pimpl" in body and "!self->pimpl" in body:
            return body
        # insert right after the opening { of the function
        return body.replace("{", "{\n    if (!self->pimpl) {\n        return 0;\n    }\n", 1)
    new, n = re.subn(
        r"(static\s+int\s+green_is_gc\s*\([^)]*\)\s*\{)",
        lambda m: m.group(1) + "\n    if (!self->pimpl) {\n        return 0;\n    }\n",
        text,
        count=1,
    )
    if n:
        path.write_text(new, encoding="utf-8")
        print("PATCHED", path)
        patched = True
        break
print("patched", patched)
open("/work/scratch/pytest9_matrix/C_patch_status.txt","w").write(f"patched={patched}\n")
PY

# Build stock wheel and guarded wheel into OUT
python -m pip wheel -q --no-deps -w "$OUT/wheels_stock" "greenlet==3.5.4"
# Build guarded from patched sdist
cd "$SRC"
CFLAGS="-O2 -g" python setup.py bdist_wheel >/tmp/guard_build.log 2>&1 || {
  echo "guard_build_failed" | tee "$OUT/C_guard_build.txt"
  tail -40 /tmp/guard_build.log | tee -a "$OUT/C_guard_build.txt"
  exit 0
}
mkdir -p "$OUT/wheels_guarded"
cp dist/*.whl "$OUT/wheels_guarded/" || true
ls -la "$OUT/wheels_stock" "$OUT/wheels_guarded" | tee "$OUT/C_wheels.txt"
echo LANE_C_BUILD_DONE | tee -a "$OUT/matrix.log"
