#!/usr/bin/env bash
# =============================================================================
# smartflo_vps_check.sh — read-only prod probe for the Tata Smartflo demo
# -----------------------------------------------------------------------------
# Run ON the VPS (never writes anything, never prints secret VALUES):
#   ssh root@72.61.245.204 'bash -s' < scripts/smartflo_vps_check.sh
#   # or after `cd /opt/leadgen && git pull`: bash scripts/smartflo_vps_check.sh
#
# Answers, with evidence:
#   1. Which SHA is live (/health.version) and does it contain the Smartflo code?
#   2. Are the Smartflo routes reachable (dynamic endpoint / WS / webhook)?
#   3. Is the voice-stream flag armed?  (WS probe: 404 = code not deployed,
#      403 = route present but SMARTFLO_VOICE_STREAM_ENABLED=0, 101 = ARMED)
#   4. Which TATA_SMARTFLO_* / SMARTFLO_* env NAMES reach the app container?
#   5. Does Caddy pass the WS upgrade through on the public hostname?
#   6. Any [smartflo-*] log lines already (schema line from a real call)?
# =============================================================================
set -u
cd /opt/leadgen 2>/dev/null || { echo "!! /opt/leadgen missing — wrong host?"; exit 2; }

COMPOSE="docker compose -f docker-compose.vps.yml"   # NEVER bare `docker compose` (2026-07-18 legacy-stack incident)
LOCAL="http://127.0.0.1:8000"                        # host-published app port (container listens on 8080)
PUBLIC="${PUBLIC_BASE_URL:-https://leadsgenai.in}"

hr() { printf '\n== %s ==\n' "$1"; }
code() { curl -s -o /dev/null -m 8 -w '%{http_code}' "$@" 2>/dev/null || echo "000"; }

hr "1. /health"
HEALTH="$(curl -s -m 8 "$LOCAL/health" || true)"
VER="$(printf '%s' "$HEALTH" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("version") or d.get("app_version") or "?")' 2>/dev/null || echo '?')"
ENV_="$(printf '%s' "$HEALTH" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("environment","?"))' 2>/dev/null || echo '?')"
echo "version=$VER environment=$ENV_"
[ "$VER" = "latest" ] && echo "!! version=latest → UNKNOWN provenance (ADR-097). Redeploy with APP_VERSION=<sha>."
if git cat-file -e "${VER}^{commit}" 2>/dev/null; then
  if git ls-tree -r --name-only "$VER" -- app/api/telephony_smartflo.py | grep -q .; then
    echo "OK  live SHA $VER CONTAINS app/api/telephony_smartflo.py"
  else
    echo "!!  live SHA $VER does NOT contain Smartflo code → deploy needed (merged in PR #457, 2026-09-04)"
  fi
else
  echo "?   SHA $VER not in local git (run: git fetch --all) — falling back to route probes"
fi

hr "2. Route probes (local, via host port 8000)"
printf 'POST /api/telephony/smartflo/endpoint  → %s  (200 = deployed)\n' \
  "$(code -X POST -H 'content-type: application/json' -d '{"callId":"probe","fromNumber":"0","toNumber":"0"}' "$LOCAL/api/telephony/smartflo/endpoint")"
printf 'POST /api/webhooks/tata-smartflo        → %s  (200 = deployed)\n' \
  "$(code -X POST -H 'content-type: application/json' -d '{"ref_id":"probe","status":"probe"}' "$LOCAL/api/webhooks/tata-smartflo")"
WS_LOCAL="$(code -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' "$LOCAL/api/telephony/smartflo/stream")"
printf 'WS   /api/telephony/smartflo/stream    → %s  ' "$WS_LOCAL"
case "$WS_LOCAL" in
  101) echo "(ARMED — SMARTFLO_VOICE_STREAM_ENABLED=1)";;
  403) echo "(route present, flag OFF → set SMARTFLO_VOICE_STREAM_ENABLED=1 + recreate app)";;
  404) echo "(NOT deployed)";;
  *)   echo "(unexpected — read body: curl -i ... )";;
esac

hr "3. Public path through Caddy ($PUBLIC)"
printf 'POST %s/api/telephony/smartflo/endpoint → %s\n' "$PUBLIC" \
  "$(code -X POST -H 'content-type: application/json' -d '{"callId":"probe"}' "$PUBLIC/api/telephony/smartflo/endpoint")"
WS_PUB="$(code -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' "$PUBLIC/api/telephony/smartflo/stream")"
printf 'WS   %s/api/telephony/smartflo/stream → %s  (must match local; Caddy proxies WS by default)\n' "$PUBLIC" "$WS_PUB"

hr "4. Env NAMES visible inside the app container (values hidden)"
$COMPOSE exec -T app env 2>/dev/null | grep -E '^(TATA_SMARTFLO_|SMARTFLO_)' | sed 's/=.*/=<set>/' | sort || echo "!! could not exec into app (compose file / service name?)"
echo "-- expected for the demo: TATA_SMARTFLO_API_TOKEN TATA_SMARTFLO_API_KEY TATA_SMARTFLO_DID TATA_SMARTFLO_ENABLED SMARTFLO_VOICE_STREAM_ENABLED SMARTFLO_DEFAULT_NICHE"
echo "-- .env on disk (names only):"
grep -E '^(TATA_SMARTFLO_|SMARTFLO_)' .env 2>/dev/null | sed 's/=.*/=<set>/' | sort || echo "   (none in .env)"

hr "5. Containers + image tags (skew check)"
$COMPOSE ps --format 'table {{.Service}}\t{{.Image}}\t{{.Status}}' 2>/dev/null | grep -E 'SERVICE|app|worker|scheduler' || $COMPOSE ps

hr "6. Recent Smartflo log lines (last 200 app lines)"
$COMPOSE logs --no-color --tail=200 app 2>/dev/null | grep -E 'smartflo' | tail -20 || true
echo "(after a real demo call look for: '[smartflo-stream] start schema top=[...] start=[...] mediaFormat=...')"

hr "DONE — paste this whole output back to the agent"
