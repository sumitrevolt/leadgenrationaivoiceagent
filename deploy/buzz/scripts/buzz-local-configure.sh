#!/usr/bin/env bash
# Buzz — local configure (run after buzz-local-up.sh, idempotent).
# Creates the 5 channels (if missing) + installs the local workflows via buzz-cli.
#
#   bash deploy/buzz/scripts/buzz-local-configure.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PORT="${BUZZ_HTTP_PORT:-3000}"
CHANNELS_FILE="$KIT_DIR/env/channels.local"
WORKFLOWS_DIR="$KIT_DIR/workflows"

NSEC="$(sed -n 's/^nsec: *//p' "$KIT_DIR/env/.env.local.owner" | tr -d '[:space:]')"
[ -n "$NSEC" ] || { echo "owner nsec missing — run buzz-local-up.sh first" >&2; exit 1; }
export BUZZ_PRIVATE_KEY="$NSEC"

cli() { bash "$SCRIPT_DIR/buzz-local-cli.sh" "$@"; }

# --- channels (idempotent) ---
source "$CHANNELS_FILE" 2>/dev/null || true
for name in general engineering office agents incidents; do
    var="CHAN_${name^^}"
    if [ -z "${!var:-}" ]; then
        echo "== creating channel #$name"
        out="$(cli channels create --name "$name" --type stream --visibility open 2>&1 || true)"
        uuid="$(printf '%s\n' "$out" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1 || true)"
        if [ -n "$uuid" ]; then
            echo "export CHAN_${name^^}=$uuid" >> "$CHANNELS_FILE"
        else
            echo "   (create failed or channel exists: $out)" >&2
        fi
        sleep 1
    fi
done
source "$CHANNELS_FILE" 2>/dev/null || true
echo "channels: general=${CHAN_GENERAL:-?} engineering=${CHAN_ENGINEERING:-?} office=${CHAN_OFFICE:-?} agents=${CHAN_AGENTS:-?} incidents=${CHAN_INCIDENTS:-?}"

# --- workflows (local-only: schedule / message_posted / local webhook trigger) ---
for wf in "$WORKFLOWS_DIR"/*.yml; do
    [ -f "$wf" ] || continue
    base="$(basename "$wf")"
    rendered="$(sed -e "s/{{CHAN_ENGINEERING}}/${CHAN_ENGINEERING:-}/g" \
        -e "s/{{CHAN_INCIDENTS}}/${CHAN_INCIDENTS:-}/g" \
        -e "s/{{CHAN_OFFICE}}/${CHAN_OFFICE:-}/g" "$wf")"
    chan="${CHAN_ENGINEERING:-}"
    [ "$base" = "daily-digest.yml" ] && chan="${CHAN_OFFICE:-}"
    [ "$base" = "incident-alert.yml" ] && chan="${CHAN_ENGINEERING:-}"
    echo "== installing workflow $base → channel $chan"
    out="$(cli workflows create --channel "$chan" --yaml "$rendered" 2>&1 || true)"
    printf '%s\n' "$out" | head -3
    sleep 1
done

echo
echo "==> done. Open http://127.0.0.1:$PORT in a browser and import the nsec from deploy/buzz/env/.env.local.owner"
