#!/usr/bin/env bash
# scripts/sops_setup.sh
# ---------------------------------------------------------------------------
# SOPS + age install karo aur ek naya age keypair generate karo.
# Idempotent — baar baar chalana safe hai.
#
# Usage (VPS pe root/sudo se):
#   bash scripts/sops_setup.sh
#
# Ke baad:
#   - Public key copy karo (age1... line)
#   - .sops.yaml me "age1REPLACE..." ki jagah paste karo
#   - Private key SIRF ~/.config/sops/age/keys.txt me rehti hai (VPS pe only)
# ---------------------------------------------------------------------------
set -euo pipefail

SOPS_VERSION="3.8.1"
AGE_VERSION="1.1.1"
AGE_KEYS_FILE="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"

echo "=== Step 1: age install ==="
if command -v age &>/dev/null; then
    echo "age already installed: $(age --version)"
else
    echo "age download kar raha hai v${AGE_VERSION}..."
    TMP=$(mktemp -d)
    curl -fsSL "https://github.com/FiloSottile/age/releases/download/v${AGE_VERSION}/age-v${AGE_VERSION}-linux-amd64.tar.gz" \
        -o "$TMP/age.tar.gz"
    tar -xzf "$TMP/age.tar.gz" -C "$TMP"
    install -m 755 "$TMP/age/age" /usr/local/bin/age
    install -m 755 "$TMP/age/age-keygen" /usr/local/bin/age-keygen
    rm -rf "$TMP"
    echo "age installed: $(age --version)"
fi

echo ""
echo "=== Step 2: sops install ==="
if command -v sops &>/dev/null; then
    echo "sops already installed: $(sops --version)"
else
    echo "sops download kar raha hai v${SOPS_VERSION}..."
    curl -fsSL "https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops-v${SOPS_VERSION}.linux.amd64" \
        -o /usr/local/bin/sops
    chmod 755 /usr/local/bin/sops
    echo "sops installed: $(sops --version)"
fi

echo ""
echo "=== Step 3: age keypair generate ==="
mkdir -p "$(dirname "$AGE_KEYS_FILE")"
chmod 700 "$(dirname "$AGE_KEYS_FILE")"

if [[ -f "$AGE_KEYS_FILE" ]]; then
    echo "Keypair pehle se hai: $AGE_KEYS_FILE"
    echo "Existing public key:"
    grep "^# public key:" "$AGE_KEYS_FILE" | sed 's/# public key: //'
else
    age-keygen -o "$AGE_KEYS_FILE"
    chmod 600 "$AGE_KEYS_FILE"
    echo "Naya keypair bana: $AGE_KEYS_FILE"
fi

echo ""
echo "=== PUBLIC KEY (yeh .sops.yaml me daalo) ==="
grep "^# public key:" "$AGE_KEYS_FILE" | sed 's/# public key: //'
echo ""
echo "DONE. Private key sirf $AGE_KEYS_FILE me hai — VPS pe rakho, commit mat karo."
