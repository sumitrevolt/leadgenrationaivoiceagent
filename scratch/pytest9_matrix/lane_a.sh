#!/bin/bash
# Lane A — advisory + resolver matrix (scratch only; do not commit)
set -euo pipefail
mkdir -p scratch/pytest9_matrix
OUT=scratch/pytest9_matrix
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq gcc g++ >/tmp/apt.log
python -m pip install -q --upgrade pip packaging
python <<'PY' | tee "$OUT/lane_a_advisory.txt"
from packaging.version import Version
import json, urllib.request
print("=== LANE A ADVISORY MATRIX ===")
print("GHSA-6w46-j5rx-g56g / CVE-2025-71176")
print("vulnerable_range: < 9.0.3")
print("first_patched_version: 9.0.3")
candidates = {
  "lowest_secure": "9.0.3",
  "latest_8x": "8.4.2",
  "latest_9x": "9.1.1",
}
for k, v in candidates.items():
    ok = Version(v) >= Version("9.0.3")
    print(f"{k}={v} advisory_ok={ok} ALLOW={'YES' if ok else 'NO_INSECURE'}")
data = json.load(urllib.request.urlopen("https://pypi.org/pypi/greenlet/json"))
vers = sorted(data["releases"], key=lambda s: Version(s))
print("greenlet_latest", data["info"]["version"])
print("greenlet_py312_compatible_recent", [v for v in vers if Version(v) >= Version("3.0.0")][-8:])
pa = json.load(urllib.request.urlopen("https://pypi.org/pypi/pytest-asyncio/json"))
print("pytest_asyncio_latest", pa["info"]["version"])
print("pytest_asyncio_for_pytest9", "1.4.0")
print("INSECURE_DOWNGRADE_FORBIDDEN: pytest 8.x path rejected")
PY

run_matrix() {
  local name="$1"; shift
  echo "=== RESOLVE $name ===" | tee -a "$OUT/matrix.log"
  python -m venv "/tmp/$name"
  "/tmp/$name/bin/pip" install -q --upgrade pip
  set +e
  "/tmp/$name/bin/pip" install -q "$@"
  local rc=$?
  set -e
  echo "install_exit=$rc" | tee "$OUT/${name}_install.txt"
  if [ "$rc" -eq 0 ]; then
    set +e
    "/tmp/$name/bin/pip" check >"$OUT/${name}_pipcheck.txt" 2>&1
    local pc=$?
    set -e
    echo "pip_check_exit=$pc" | tee -a "$OUT/${name}_install.txt"
    "/tmp/$name/bin/python" - <<'PY' | tee "$OUT/${name}_versions.txt"
import importlib.metadata as m
from packaging.version import Version
pt = Version(m.version("pytest"))
print("pytest", pt)
print("advisory_ok", pt >= Version("9.0.3"))
print("pytest_asyncio", m.version("pytest-asyncio"))
print("greenlet", m.version("greenlet"))
try:
    print("pytest_cov", m.version("pytest-cov"))
except Exception:
    print("pytest_cov", "missing")
PY
  fi
  echo "$name|install=$rc" >> "$OUT/results.tsv"
}

run_matrix A_secure903 pytest==9.0.3 pytest-asyncio==1.4.0 pytest-cov==7.1.0 greenlet==3.5.4
run_matrix A_latest911 pytest==9.1.1 pytest-asyncio==1.4.0 pytest-cov==7.1.0 greenlet==3.5.4
run_matrix A_pytest8_REJECT pytest==8.4.2 pytest-asyncio==0.26.0 pytest-cov==6.0.0 greenlet==3.5.4
echo LANE_A_DONE | tee -a "$OUT/matrix.log"
cat "$OUT/results.tsv"
