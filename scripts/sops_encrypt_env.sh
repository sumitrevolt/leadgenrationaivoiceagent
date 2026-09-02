#!/usr/bin/env bash
# scripts/sops_encrypt_env.sh
# ---------------------------------------------------------------------------
# /opt/leadgen/.env ko SOPS + age se encrypt karke secrets/.env.enc.yaml me
# save karo.
#
# Pre-requisites:
#   1. sops + age installed (bash scripts/sops_setup.sh)
#   2. .sops.yaml me apni age public key daali ho
#   3. SOPS_AGE_KEY_FILE env set ho (default: ~/.config/sops/age/keys.txt)
#
# Usage:
#   cd /opt/leadgen
#   bash scripts/sops_encrypt_env.sh
#
#   Ya custom paths:
#   ENV_FILE=/opt/leadgen/.env OUT_FILE=/opt/leadgen/secrets/.env.enc.yaml \
#     bash scripts/sops_encrypt_env.sh
# ---------------------------------------------------------------------------
set -euo pipefail

ENV_FILE="${ENV_FILE:-/opt/leadgen/.env}"
OUT_FILE="${OUT_FILE:-/opt/leadgen/secrets/.env.enc.yaml}"
SOPS_CONFIG="${SOPS_CONFIG_FILE:-/opt/leadgen/.sops.yaml}"

# Checks
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env file nahi mili: $ENV_FILE"
    exit 1
fi

if ! command -v sops &>/dev/null; then
    echo "ERROR: sops install nahi. Pehle: bash scripts/sops_setup.sh"
    exit 1
fi

# Output directory banao
mkdir -p "$(dirname "$OUT_FILE")"

echo "Encrypting $ENV_FILE -> $OUT_FILE ..."
echo "(SOPS config: $SOPS_CONFIG)"

sops --config "$SOPS_CONFIG" \
     --input-type dotenv \
     --output-type yaml \
     --encrypt \
     "$ENV_FILE" > "$OUT_FILE"

echo "DONE. Encrypted file: $OUT_FILE"
echo ""
echo "NEXT STEPS:"
echo "  1. secrets/.env.enc.yaml ko git me commit kar sakte ho (safely encrypted hai)."
echo "  2. Deploy pe decrypt: bash scripts/sops_decrypt_env.sh"
echo "  3. Plain .env ab GITIGNORE me rakho (pehle se hai)."
