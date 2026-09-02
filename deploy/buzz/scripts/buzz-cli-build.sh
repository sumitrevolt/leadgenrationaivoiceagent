#!/usr/bin/env bash
# Build the buzz-cli binary locally (no Rust toolchain on the host).
# Builds in a throwaway rust:1.88 container → deploy/buzz/bin/buzz
# Usage: bash deploy/buzz/scripts/buzz-cli-build.sh [output-path]
set -euo pipefail
OUT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/bin/buzz}"

# The built binary is a Linux ELF (built via Docker): on a Linux host it runs
# natively; on Windows/Git Bash it must run inside the same rust image.
smoke() {
    if "$OUT" --help >/dev/null 2>&1; then return 0; fi
    local win_out
    win_out="$(cygpath -w "$OUT" 2>/dev/null || echo "$OUT")"
    MSYS_NO_PATHCONV=1 docker run --rm -v "$win_out:/usr/local/bin/buzz" \
        rust:1.88-bookworm buzz --help >/dev/null 2>&1
}

if [ -f "$OUT" ] && smoke; then
    echo "buzz-cli already built at $OUT"
    exit 0
fi

mkdir -p "$(dirname "$OUT")"
# Git Bash mangles `C:/...:/out` — use cygpath (Windows style) + MSYS_NO_PATHCONV.
OUTDIR="$(dirname "$OUT")"
WIN_OUT="$(cygpath -w "$OUTDIR" 2>/dev/null || echo "$OUTDIR")"
docker run --rm -e MSYS_NO_PATHCONV=1 -v "$WIN_OUT:/out" rust:1.88-bookworm bash -c '
    set -euo pipefail
    if [ ! -d /tmp/buzz/.git ]; then git clone --depth 1 https://github.com/block/buzz.git /tmp/buzz; fi
    cd /tmp/buzz
    cargo build --release -p buzz-cli
    cp target/release/buzz /out/buzz
    chmod +x /out/buzz
'
echo "buzz-cli built at $OUT"
smoke || { echo "buzz-cli smoke failed" >&2; exit 1; }
echo "buzz-cli smoke OK"
