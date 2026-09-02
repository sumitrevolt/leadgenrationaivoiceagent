#!/bin/bash
set -e
cd /opt/leadgen

# GUARD FIRST — `git reset --hard` below reverts tracked files under data/,
# which is where live invoices, consent, suppression and customer identity
# currently live. The preflight must deny before anything is mutated.
. "$(dirname "$0")/_runtime_data_guard.sh"

echo "=== [1/6] git pull ==="
git fetch --all --tags
git reset --hard origin/main
git log -1 --oneline

echo ""
echo "=== [2/6] flip MCP flags in .env (idempotent) ==="
grep -q '^MCP_PRODUCT=' .env || echo "MCP_PRODUCT=1" >> .env
grep -q '^MCP_ENGINEER=' .env || echo "MCP_ENGINEER=1" >> .env
sed -i 's/^MCP_PRODUCT=.*/MCP_PRODUCT=1/' .env
sed -i 's/^MCP_ENGINEER=.*/MCP_ENGINEER=1/' .env

if ! grep -q '^FASTAPI_MCP_TOKEN=[^[:space:]]' .env; then
  TOKEN=$(openssl rand -hex 32)
  if grep -q '^FASTAPI_MCP_TOKEN=' .env; then
    sed -i "s|^FASTAPI_MCP_TOKEN=.*|FASTAPI_MCP_TOKEN=$TOKEN|" .env
  else
    echo "FASTAPI_MCP_TOKEN=$TOKEN" >> .env
  fi
  echo "GENERATED FASTAPI_MCP_TOKEN=$TOKEN"
fi

echo "TOKEN_LINE: $(grep '^FASTAPI_MCP_TOKEN=' .env)"
echo "ARMED: MCP_PRODUCT=$(grep '^MCP_PRODUCT=' .env | cut -d= -f2), MCP_ENGINEER=$(grep '^MCP_ENGINEER=' .env | cut -d= -f2)"

echo ""
echo "=== [3/6] docker compose build app ==="
docker compose -f docker-compose.vps.yml build app 2>&1 | tail -20

echo ""
echo "=== [4/6] recreate app + worker + scheduler ==="
docker compose -f docker-compose.vps.yml up -d --no-deps app worker scheduler 2>&1 | tail -20

echo ""
echo "=== [5/6] wait 16s for app warm-up ==="
sleep 16

echo ""
echo "=== [6/6] health verify ==="
curl -s -o /dev/null -w "  health 1: %{http_code}\n" http://127.0.0.1:8000/health || echo "  health 1: timeout"
sleep 2
curl -s -o /dev/null -w "  health 2: %{http_code}\n" http://127.0.0.1:8000/health || echo "  health 2: timeout"

echo ""
echo "=== MCP smoke ==="
echo "  /mcp/ (no auth):                   $(curl -sI -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/mcp/)"
TOKEN=$(grep '^FASTAPI_MCP_TOKEN=' .env | cut -d= -f2)
echo "  /mcp/ (with bearer):               $(curl -sI -o /dev/null -w '%{http_code}' -H \"Authorization: Bearer $TOKEN\" http://127.0.0.1:8000/mcp/)"
echo "  /.well-known/agent.json:           $(curl -sI -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/.well-known/agent.json)"
echo "  /api/mcp-product/v1/discover:      $(curl -sI -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/mcp-product/v1/discover)"
echo ""
echo "  product discover body:"
curl -s http://127.0.0.1:8000/api/mcp-product/v1/discover | head -c 400
echo ""
echo "  containers status:"
docker compose -f docker-compose.vps.yml ps app worker scheduler

echo ""
echo "=== DEPLOY DONE ==="
