#!/usr/bin/env bash
# Postiz self-host setup — VPS pe root se chalao:
#   bash /opt/leadgen/scripts/setup_postiz.sh
#
# PRE-REQ (user, 1 min): Hostinger DNS me A record add karo:
#   postiz.leadsgenai.in  ->  72.61.245.204
# (script khud check karega; record ke bina HTTPS/OAuth kaam nahi karega)
set -euo pipefail
cd /opt/leadgen

DOMAIN="postiz.leadsgenai.in"
ENV_FILE="deploy/postiz/.env"

# 1) DNS check
if ! getent hosts "$DOMAIN" >/dev/null 2>&1; then
  echo "❌ DNS record missing: $DOMAIN"
  echo "   Hostinger hPanel -> leadsgenai.in -> DNS -> A record: postiz -> 72.61.245.204"
  echo "   Record add karke 5-10 min baad ye script dobara chalao."
  exit 1
fi
echo "✓ DNS ok: $DOMAIN"

# 2) Secrets (one-time generate; .env gitignored path)
mkdir -p deploy/postiz
if [ ! -f "$ENV_FILE" ]; then
  {
    echo "POSTIZ_MAIN_URL=https://$DOMAIN"
    echo "POSTIZ_JWT_SECRET=$(openssl rand -hex 32)"
    echo "POSTIZ_DB_PASSWORD=$(openssl rand -hex 16)"
    echo "POSTIZ_DISABLE_REGISTRATION=false"
    echo "# Platform OAuth keys (jab milen tab bharo, phir: docker compose -f deploy/compose/docker-compose.postiz.yml --env-file $ENV_FILE up -d)"
    echo "X_API_KEY="
    echo "X_API_SECRET="
    echo "LINKEDIN_CLIENT_ID="
    echo "LINKEDIN_CLIENT_SECRET="
    echo "FACEBOOK_APP_ID="
    echo "FACEBOOK_APP_SECRET="
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "✓ secrets generated -> $ENV_FILE"
else
  echo "✓ $ENV_FILE already exists (kept)"
fi

# 3) Stack up
git fetch origin -q && git checkout origin/main -- deploy/compose/docker-compose.postiz.yml scripts/setup_postiz.sh || true
docker compose -f deploy/compose/docker-compose.postiz.yml --env-file "$ENV_FILE" up -d
echo "✓ postiz stack up (leadgen_postiz on 127.0.0.1:5000)"

# 4) Caddy route (host Caddy, idempotent append + reload)
CADDYFILE="/etc/caddy/Caddyfile"
if [ -f "$CADDYFILE" ] && ! grep -q "postiz.leadsgenai.in" "$CADDYFILE"; then
  cat >> "$CADDYFILE" <<EOF

postiz.leadsgenai.in {
    reverse_proxy 127.0.0.1:5000
}
EOF
  systemctl reload caddy || caddy reload --config "$CADDYFILE" || true
  echo "✓ Caddy route added + reloaded"
else
  echo "✓ Caddy route already present (ya Caddyfile missing — manually add karo)"
fi

sleep 8
echo "--- health ---"
curl -s -o /dev/null -w "local :5000 -> HTTP %{http_code}\n" http://127.0.0.1:5000 || true
curl -s -o /dev/null -w "https://$DOMAIN -> HTTP %{http_code}\n" "https://$DOMAIN" || true

cat <<'EOT'

AGLA STEP (browser me, ~5 min):
1. https://postiz.leadsgenai.in kholo -> account REGISTER karo (pehla = admin).
2. Turant deploy/postiz/.env me POSTIZ_DISABLE_REGISTRATION=true karke:
   docker compose -f deploy/compose/docker-compose.postiz.yml --env-file deploy/postiz/.env up -d
3. Channels connect karo (X/LinkedIn/FB — jinke OAuth keys .env me bhare hon).
4. Settings -> API se API key copy karo, channel ids note karo.
5. Key ko app me daalo (encrypted vault, no-restart):
   docker exec leadgen_app python -c "from app.social_engine import vault; import json; print(vault.put('_global','postiz','<API_KEY>', meta={'api_url':'https://postiz.leadsgenai.in/api','integrations':'<id1,id2>'}))"
   printf '{"enabled": true}\n' > /opt/leadgen/data/social_engine.json
6. Verify: curl -s localhost:8000/api/growth/social/postiz/status (admin token ke saath)
   -> postiz_configured:true + social_engine_enabled:true = Zara LIVE.
EOT
