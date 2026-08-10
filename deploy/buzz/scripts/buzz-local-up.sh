#!/usr/bin/env bash
# Local Buzz relay — idempotent bootstrap + start (Docker on port 3100, loopback only).
# Usage: bash deploy/buzz/scripts/buzz-local-up.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUZZ_DIR="${BUZZ_LOCAL_DIR:-$HOME/buzz-local}"
COMPOSE_DIR="$BUZZ_DIR/deploy/compose"
ENV_FILE="$COMPOSE_DIR/.env"
BUZZ_IMAGE="${BUZZ_IMAGE:-ghcr.io/block/buzz:main}"
PORT="${BUZZ_HTTP_PORT:-3100}"
BUZZ_BIN="${BUZZ_BIN:-$KIT_DIR/bin/buzz}"

echo "==> buzz-local @ $BUZZ_DIR (relay on 127.0.0.1:$PORT)"
# Note: the upstream compose pins project name "buzz-prod" — one local relay per
# machine. Set COMPOSE_PROJECT_NAME to run an isolated second stack.

# 1. Clone upstream (pinned main) if missing
if [ ! -d "$COMPOSE_DIR" ]; then
    echo "==> cloning block/buzz"
    mkdir -p "$BUZZ_DIR"
    git clone --depth 1 https://github.com/block/buzz.git "$BUZZ_DIR"
else
    echo "==> upstream clone present (skip; git -C $BUZZ_DIR rev-parse --short HEAD = $(git -C "$BUZZ_DIR" rev-parse --short HEAD 2>/dev/null || echo '?'))"
fi

# 1b. Pin the published relay port to loopback (upstream compose publishes on
#     0.0.0.0). Idempotent: after the first replace the pattern no longer matches.
sed -i 's|"${BUZZ_HTTP_PORT:-3000}:3000"|"127.0.0.1:${BUZZ_HTTP_PORT:-3000}:3000"|' "$COMPOSE_DIR/compose.yml"

# 2. Ensure .env exists
if [ ! -f "$ENV_FILE" ]; then
    echo "==> generating local .env + owner keypair"
    KEY_FILE="$(mktemp)"
    bash "$SCRIPT_DIR/buzz-keys.sh" "$KEY_FILE"
    OWNER_HEX="$(sed -n 's/^Public key (hex): *//p' "$KEY_FILE" | tr -d '[:space:]')"
    NSEC="$(sed -n 's/^nsec: *//p' "$KEY_FILE" | tr -d '[:space:]')"
    # Random 32-byte secrets
    R1="$(openssl rand -hex 32)"
    R2="$(openssl rand -hex 32)"
    R3="$(openssl rand -hex 32)"
    R4="$(openssl rand -hex 32)"
    R5="$(openssl rand -hex 32)"
    R6="$(openssl rand -hex 32)"
    sed -e "s/^RELAY_OWNER_PUBKEY=.*/RELAY_OWNER_PUBKEY=$OWNER_HEX/" \
        -e "s/^BUZZ_RELAY_PRIVATE_KEY=.*/BUZZ_RELAY_PRIVATE_KEY=$R1/" \
        -e "s/^BUZZ_GIT_HOOK_HMAC_SECRET=.*/BUZZ_GIT_HOOK_HMAC_SECRET=$R2/" \
        -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$R3/" \
        -e "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=$R4/" \
        -e "s/^BUZZ_S3_ACCESS_KEY=.*/BUZZ_S3_ACCESS_KEY=$R5/" \
        -e "s/^BUZZ_S3_SECRET_KEY=.*/BUZZ_S3_SECRET_KEY=$R6/" \
        -e "s/^RELAY_URL=.*/RELAY_URL=ws:\/\/127.0.0.1:$PORT/" \
        -e "s/^BUZZ_MEDIA_BASE_URL=.*/BUZZ_MEDIA_BASE_URL=http:\/\/127.0.0.1:$PORT\/media/" \
        -e "s/^BUZZ_CORS_ORIGINS=.*/BUZZ_CORS_ORIGINS=http:\/\/127.0.0.1:$PORT/" \
        -e "s/^BUZZ_HTTP_PORT=.*/BUZZ_HTTP_PORT=$PORT/" \
        "$KIT_DIR/env/.env.local.template" > "$ENV_FILE"
    umask 077
    printf 'Owner identity for LOCAL dev (import into web UI at http://localhost:%s)\n' "$PORT" > "$KIT_DIR/env/.env.local.owner"
    cat "$KEY_FILE" >> "$KIT_DIR/env/.env.local.owner"
    rm -f "$KEY_FILE"
    echo "==> owner keypair saved to deploy/buzz/env/.env.local.owner (gitignored — import nsec into the app)"
fi

# 3. Start the stack (loopback-only: relay port pinned to 127.0.0.1 in step 1b)
cd "$COMPOSE_DIR"
if ! curl -fsS "http://127.0.0.1:$PORT/_liveness" >/dev/null 2>&1; then
    echo "==> docker compose up -d --wait"
    docker compose --env-file .env up -d --wait
fi

# 4. Health + owner member (poll the HTTP port: the compose healthcheck covers
#    the 8080 probe port, which can pass before the 3000 listener is ready).
ok=""
for i in $(seq 1 20); do
    if curl -fsS "http://127.0.0.1:$PORT/_liveness" >/dev/null 2>&1; then ok=1; break; fi
    echo "   waiting for relay liveness ($i/20)..."
    sleep 2
done
echo "==> liveness: $(curl -fsS "http://127.0.0.1:$PORT/_liveness" || echo FAIL)"
[ -n "$ok" ] || { echo "relay did not become healthy on 127.0.0.1:$PORT" >&2; exit 1; }
OWNER_HEX="${OWNER_HEX:-$(sed -n 's/^RELAY_OWNER_PUBKEY=//p' "$ENV_FILE" | tr -d '[:space:]')}"
docker compose --env-file .env exec -T relay /usr/local/bin/buzz-admin add-member --pubkey "$OWNER_HEX" >/dev/null 2>&1 || echo "(owner already member or add failed — check list-members)"

# 5. Channels + workflows via buzz-cli (build once via Docker)
if [ ! -f "$BUZZ_BIN" ]; then
    echo "==> building buzz-cli (Docker, first time ~5-8 min)"
    bash "$SCRIPT_DIR/buzz-cli-build.sh" "$BUZZ_BIN"
fi

# 6. Provision channels + workflows (idempotent; needs the CLI, so runs after build)
if [ -f "$BUZZ_BIN" ]; then
    echo "==> provisioning channels + workflows"
    bash "$SCRIPT_DIR/buzz-local-configure.sh" || echo "(provisioning failed — see output above; re-run buzz-local-configure.sh)"
fi

echo "==> done. Open http://localhost:$PORT in a browser and import the nsec from deploy/buzz/env/.env.local.owner"
echo "    (relay log: docker compose -f $COMPOSE_DIR/compose.yml logs -f relay)"
