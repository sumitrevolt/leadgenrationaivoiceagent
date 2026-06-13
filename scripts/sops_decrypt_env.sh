#!/usr/bin/env bash
# scripts/sops_decrypt_env.sh
# ---------------------------------------------------------------------------
# secrets/.env.enc.yaml ko decrypt karke /opt/leadgen/.env me write karo.
# Deploy time pe chalao (CI/CD ya manual VPS deploy).
#
# Pre-requisites:
#   - sops + age installed (bash scripts/sops_setup.sh)
#   - SOPS_AGE_KEY_FILE env var point kare private key file pe
#     (default: ~/.config/sops/age/keys.txt)
#   - Encrypted file: secrets/.env.enc.yaml (committed in repo)
#
# Usage (VPS pe):
#   export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
#   cd /opt/leadgen
#   bash scripts/sops_decrypt_env.sh
#
#   Ya CI/CD me (GitHub Actions secret se key inject karo):
#   echo "$AGE_SECRET_KEY" > /tmp/age_key.txt
#   export SOPS_AGE_KEY_FILE=/tmp/age_key.txt
#   bash scripts/sops_decrypt_env.sh
#   rm -f /tmp/age_key.txt   # cleanup
# ---------------------------------------------------------------------------
set -euo pipefail

ENC_FILE="${ENC_FILE:-/opt/leadgen/secrets/.env.enc.yaml}"
OUT_ENV="${OUT_ENV:-/opt/leadgen/.env}"
SOPS_CONFIG="${SOPS_CONFIG_FILE:-/opt/leadgen/.sops.yaml}"
KEY_FILE="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"

# Checks
if [[ ! -f "$ENC_FILE" ]]; then
    echo "ERROR: Encrypted file nahi mili: $ENC_FILE"
    echo "  Pehle encrypt karo: bash scripts/sops_encrypt_env.sh"
    exit 1
fi

if [[ ! -f "$KEY_FILE" ]]; then
    echo "ERROR: Age private key nahi mili: $KEY_FILE"
    echo "  Set karo: export SOPS_AGE_KEY_FILE=<path to keys.txt>"
    exit 1
fi

if ! command -v sops &>/dev/null; then
    echo "ERROR: sops install nahi. Pehle: bash scripts/sops_setup.sh"
    exit 1
fi

# Backup existing .env agar hai
if [[ -f "$OUT_ENV" ]]; then
    cp "$OUT_ENV" "${OUT_ENV}.bak_sops_$(date +%Y%m%d_%H%M%S)"
    echo "Existing .env backed up."
fi

echo "Decrypting $ENC_FILE -> $OUT_ENV ..."
export SOPS_AGE_KEY_FILE="$KEY_FILE"

sops --config "$SOPS_CONFIG" \
     --input-type yaml \
     --output-type dotenv \
     --decrypt \
     "$ENC_FILE" > "$OUT_ENV"

# Permissions tight rakho
chmod 600 "$OUT_ENV"

echo "DONE. .env restored at: $OUT_ENV"
echo "Ab app restart karo: docker compose -f docker-compose.vps.yml up -d --force-recreate app"
