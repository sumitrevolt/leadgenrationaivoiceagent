#!/usr/bin/env bash
# Generate a fresh Nostr keypair (hex + nsec + npub) using the buzz relay image.
# No Rust needed: buzz-admin generate-key is bundled in ghcr.io/block/buzz:main.
#
# Usage:
#   bash deploy/buzz/scripts/buzz-keys.sh            # print one keypair to stdout
#   bash deploy/buzz/scripts/buzz-keys.sh /tmp/k.txt # write keypair to a file (chmod 600)
set -euo pipefail

IMAGE="${BUZZ_IMAGE:-ghcr.io/block/buzz:main}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-}"

# shellcheck disable=SC2086
RAW="$(MSYS_NO_PATHCONV=1 docker run --rm --entrypoint buzz-admin "$IMAGE" generate-key 2>/dev/null)"
PUB_HEX="$(printf '%s\n' "$RAW" | sed -n 's/^Public key: *//p' | tr -d '[:space:]')"
SEC_HEX="$(printf '%s\n' "$RAW" | sed -n 's/^Secret key: *//p' | tr -d '[:space:]')"

PY="$(command -v python3 || command -v python || true)"
if [ -n "$PY" ]; then
    NSEC="$("$PY" "$SCRIPT_DIR/nostr_bech32.py" nsec "$SEC_HEX" 2>/dev/null || echo "")"
    NPUB="$("$PY" "$SCRIPT_DIR/nostr_bech32.py" npub "$PUB_HEX" 2>/dev/null || echo "")"
else
    NSEC="(python3 needed for nsec; hex works with buzz-cli)"
    NPUB=""
fi

BLOCK="Public key (hex): $PUB_HEX
Secret key (hex): $SEC_HEX
npub:              ${NPUB:-n/a}
nsec:              ${NSEC:-n/a}"

if [ -n "$OUT" ]; then
    umask 077
    printf '%s\n' "$BLOCK" > "$OUT"
    echo "keypair written to $OUT (chmod 600)"
else
    printf '%s\n' "$BLOCK"
fi
