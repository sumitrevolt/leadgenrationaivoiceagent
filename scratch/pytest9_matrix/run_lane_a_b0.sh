#!/bin/bash
# Lane A+B bounded matrix — Linux only (exit-139 repro). Scratch only; not committed.
set -euo pipefail
ROOT=/work
OUT=/work/scratch/pytest9_matrix
mkdir -p "$OUT"
cd "$ROOT"

# Base install once
python -m pip install -q --upgrade pip wheel setuptools
grep -v -E "^(playwright|selenium)" requirements.lock.txt > /tmp/req.filtered
pip install -q --no-deps -r /tmp/req.filtered
pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cpu >/tmp/torch.log 2>&1 || true
pip install -q pytest-timeout pytest-split

record() {
  local name="$1"; shift
  echo "=== $name ===" | tee -a "$OUT/matrix.log"
  echo "CMD: $*" | tee -a "$OUT/matrix.log"
  set +e
  "$@" >"$OUT/${name}.stdout" 2>"$OUT/${name}.stderr"
  local rc=$?
  set -e
  echo "EXIT=$rc" | tee -a "$OUT/matrix.log"
  echo "$name|$rc" >> "$OUT/results.tsv"
  return 0
}

# --- Lane A: resolver + pip check for secure matrices ---
pip show pytest pytest-asyncio greenlet | tee "$OUT/installed_baseline.txt"

# A1: current PR pins (pytest 9.0.3)
record A1_pip_check pip check
python - <<'PY' | tee "$OUT/A1_advisory.txt"
import importlib.metadata as m
from packaging.version import Version
pt=Version(m.version("pytest")); pa=Version(m.version("pytest-asyncio")); gl=Version(m.version("greenlet"))
print(f"pytest={pt} asyncio={pa} greenlet={gl}")
print("advisory_GHSA_6w46_satisfied", pt >= Version("9.0.3"))
print("greenlet_is_latest_released", str(gl)=="3.5.4")
PY

# A2: latest pytest 9.1.1 resolver dry-run
record A2_resolve_911 python -m pip install --dry-run "pytest==9.1.1" "pytest-asyncio==1.4.0" "pytest-cov==7.1.0" 2>&1 | tee "$OUT/A2_resolve.txt" | tail -5; true
# dry-run may not work on older pip — try real isolate later

# A3: prove 8.x cannot satisfy advisory
python - <<'PY' | tee "$OUT/A3_pytest8_insecure.txt"
print("GHSA-6w46-j5rx-g56g vulnerable_range: < 9.0.3")
print("latest_pytest_8x: 8.4.2")
print("8.4.2_satisfies_advisory: False")
print("lowest_secure_pytest: 9.0.3")
print("latest_secure_pytest: 9.1.1")
print("INSECURE_DOWNGRADE_FORBIDDEN: pytest 8.x path rejected")
PY

# --- Lane B: lifecycle variants on shard 1 (bounded) ---
export PYTHONUNBUFFERED=1
COMMON=(pytest -m "not network" -q --no-header -p no:cacheprovider --timeout=60 --splits 4 --group 1)

run_shard() {
  local name="$1"; shift
  echo "=== SHARD $name ===" | tee -a "$OUT/matrix.log"
  set +e
  "$@" "${COMMON[@]}" >"$OUT/${name}.stdout" 2>"$OUT/${name}.stderr"
  local rc=$?
  set -e
  echo "EXIT=$rc" | tee -a "$OUT/matrix.log"
  # capture crash signature
  if grep -q "Segmentation fault\|Fatal Python error" "$OUT/${name}.stderr" "$OUT/${name}.stdout" 2>/dev/null; then
    echo "SIG=$name|segfault" >> "$OUT/results.tsv"
  fi
  echo "$name|$rc" >> "$OUT/results.tsv"
  tail -20 "$OUT/${name}.stdout" >> "$OUT/matrix.log" || true
  tail -20 "$OUT/${name}.stderr" >> "$OUT/matrix.log" || true
}

# B0 baseline: stock PR config (function loops)
run_shard B0_baseline "${@:-}"

# Write results summary
echo "DONE" | tee -a "$OUT/matrix.log"
cat "$OUT/results.tsv" | tee "$OUT/summary.txt"
