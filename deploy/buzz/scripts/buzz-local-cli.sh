#!/usr/bin/env bash
# Run buzz-cli against the LOCAL relay (Docker).
# Why a container: the built buzz binary is a Linux ELF (built via Docker), and
# --network host makes 127.0.0.1:3000 resolve to the host relay so the Host
# header matches the community key (RELAY_URL=ws://127.0.0.1:3000).
# Why rust:1.88-bookworm: debian-slim lacks the system cert store → reqwest
# client build fails with "builder error".
#
# Usage:
#   BUZZ_RELAY_URL=ws://127.0.0.1:3000 \
#   BUZZ_PRIVATE_KEY=<nsec-or-hex> \
#   bash deploy/buzz/scripts/buzz-local-cli.sh channels list
set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$KIT_DIR/bin/buzz"
NSEC_FILE="$KIT_DIR/env/.env.local.owner"
PORT="${BUZZ_HTTP_PORT:-3000}"

RELAY_URL="${BUZZ_RELAY_URL:-ws://127.0.0.1:$PORT}"
PRIV_KEY="${BUZZ_PRIVATE_KEY:-}"
if [ -z "$PRIV_KEY" ] && [ -f "$NSEC_FILE" ]; then
    PRIV_KEY="$(sed -n 's/^nsec: *//p' "$NSEC_FILE" | tr -d '[:space:]')"
fi
[ -n "$PRIV_KEY" ] || { echo "set BUZZ_PRIVATE_KEY or run buzz-local-up.sh first" >&2; exit 1; }
[ -f "$BIN" ] || { echo "buzz binary missing — run buzz-cli-build.sh first" >&2; exit 1; }

# Convert the WS URL to the HTTP form the CLI expects, keep the exact host:port.
HTTP_URL="$(printf '%s' "$RELAY_URL" | sed -e 's|^wss://|https://|' -e 's|^ws://|http://|')"

MSYS_NO_PATHCONV=1 docker run --rm --network host \
    -v "$(cygpath -w "$BIN"):/usr/local/bin/buzz" \
    -e BUZZ_PRIVATE_KEY="$PRIV_KEY" \
    rust:1.88-bookworm buzz --relay "$HTTP_URL" "$@"
