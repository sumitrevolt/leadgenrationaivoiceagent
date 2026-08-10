#!/bin/bash
# Lane B — async lifecycle variants on shard 1 (scratch; do not commit)
set -euo pipefail
OUT=scratch/pytest9_matrix
mkdir -p "$OUT"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq gcc g++ ffmpeg libsndfile1 >/tmp/apt.log
python -m pip install -q --upgrade pip wheel setuptools
grep -v -E "^(playwright|selenium)" requirements.lock.txt > /tmp/req.filtered
pip install -q --no-deps -r /tmp/req.filtered
pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cpu >/tmp/torch.log 2>&1 || true
pip install -q --no-deps "pytest-timeout==2.4.0" pytest-split
pip install -q --no-deps --force-reinstall "pydantic-core==2.46.4"
pip show pytest pytest-asyncio greenlet | tee "$OUT/B_installed.txt"
set +e
pip check >"$OUT/B_pipcheck.txt" 2>&1
echo "pip_check_exit=$?" | tee -a "$OUT/B_installed.txt"
set -e

export APP_ENV=test
export ENVIRONMENT=development
export PYTHONUNBUFFERED=1
export MISTRAL_API_KEY=dummy
export GROQ_API_KEY=dummy

run_shard() {
  local name="$1"
  shift
  echo "=== $name ===" | tee -a "$OUT/matrix.log"
  echo "ENV_EXTRA: $*" | tee -a "$OUT/matrix.log"
  set +e
  env "$@" pytest -m "not network" -q --no-header -p no:cacheprovider --timeout=60 --splits 4 --group 1 \
    >"$OUT/${name}.stdout" 2>"$OUT/${name}.stderr"
  local rc=$?
  set -e
  echo "EXIT=$rc" | tee -a "$OUT/matrix.log"
  echo "$name|$rc" >> "$OUT/results.tsv"
  if grep -Eiq "Segmentation fault|Fatal Python error" "$OUT/${name}.stderr" "$OUT/${name}.stdout" 2>/dev/null; then
    echo "$name|segfault_signature=yes" >> "$OUT/results.tsv"
  else
    echo "$name|segfault_signature=no" >> "$OUT/results.tsv"
  fi
  tail -40 "$OUT/${name}.stdout" >> "$OUT/matrix.log" || true
  tail -60 "$OUT/${name}.stderr" >> "$OUT/matrix.log" || true
}

# B0 stock function loops
run_shard B0_function_loops

# B1 session-scoped loops (supported pytest-asyncio 1.x)
run_shard B1_session_loops \
  PYTEST_ADDOPTS="-o asyncio_default_test_loop_scope=session -o asyncio_default_fixture_loop_scope=session"

echo LANE_B_DONE | tee -a "$OUT/matrix.log"
cat "$OUT/results.tsv" | tee "$OUT/B_summary.txt"
