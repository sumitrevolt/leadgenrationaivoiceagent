#!/usr/bin/env bash
# Capture the EXACT working dependency set from the live venv -> requirements.lock.txt
# (the set that actually runs in prod = guaranteed self-consistent). Read-only-ish
# (only writes the lock file). Used to build a reliable image with --no-deps.
set -uo pipefail
echo "=== systemd unit (find python) ==="
systemctl cat leadgen 2>/dev/null | grep -E 'ExecStart|WorkingDirectory|EnvironmentFile' || echo "no unit"
PY=$(systemctl cat leadgen 2>/dev/null | grep -oE '/[A-Za-z0-9_./-]*/(python|uvicorn)[0-9.]*' | head -1)
case "$PY" in *uvicorn*) PY="${PY%/uvicorn*}/python";; esac
[ -x "$PY" ] || PY=/opt/leadgen/.venv/bin/python
[ -x "$PY" ] || PY=/opt/leadgen/venv/bin/python
echo "=== using python: $PY ==="
"$PY" --version 2>&1 || { echo "PYTHON NOT FOUND"; exit 1; }
PIPDIR=$(dirname "$PY")
echo "=== freeze -> /opt/leadgen/requirements.lock.txt ==="
"$PIPDIR/pip" freeze 2>/dev/null > /opt/leadgen/requirements.lock.txt || "$PY" -m pip freeze > /opt/leadgen/requirements.lock.txt
echo "lines: $(wc -l < /opt/leadgen/requirements.lock.txt)"
echo "=== problematic (vcs/editable/local path) ==="
grep -nE ' @ |@ git|^-e |file://|@ file' /opt/leadgen/requirements.lock.txt || echo "none-clean"
echo "=== key pkgs (versions that resolve the conflicts) ==="
grep -iE '^(pydantic|pydantic-settings|langgraph|langchain|langchain-core|fastapi|fastembed|pillow|qdrant-client|edge-tts|torch)([=<>]|$)' /opt/leadgen/requirements.lock.txt || echo "none-matched"
echo "FREEZE DONE"
