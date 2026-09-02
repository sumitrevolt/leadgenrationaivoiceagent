#!/bin/bash
cd /opt/leadgen
TOKEN=$(grep '^FASTAPI_MCP_TOKEN=' .env | cut -d= -f2)

echo "=== container freshness ==="
docker compose -f docker-compose.vps.yml ps app worker scheduler

echo ""
echo "=== app logs - look for MCP mount line ==="
docker logs leadgen_app 2>&1 | grep -iE "mcp|arya" | tail -10

echo ""
echo "=== local-host smoke (bypass Caddy/CF) ==="
printf "  /health                                 -> "; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/health
printf "  /mcp/ (no auth, expect 401)             -> "; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/mcp/
printf "  /mcp/ (with Bearer, expect 200/204/307) -> "; curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/mcp/
printf "  /.well-known/agent.json                 -> "; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/.well-known/agent.json
printf "  /api/mcp-product/v1/discover            -> "; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/mcp-product/v1/discover

echo ""
echo "=== public Caddy edge ==="
printf "  https://leadsgenai.in/health                            -> "; curl -s -o /dev/null -w "%{http_code}\n" https://leadsgenai.in/health
printf "  https://leadsgenai.in/mcp/ (no auth, expect 401)        -> "; curl -s -o /dev/null -w "%{http_code}\n" https://leadsgenai.in/mcp/
printf "  https://leadsgenai.in/.well-known/agent.json (expect 200)-> "; curl -s -o /dev/null -w "%{http_code}\n" https://leadsgenai.in/.well-known/agent.json
printf "  https://leadsgenai.in/api/mcp-product/v1/discover (200)  -> "; curl -s -o /dev/null -w "%{http_code}\n" https://leadsgenai.in/api/mcp-product/v1/discover

echo ""
echo "=== A2A Agent Card body ==="
curl -s https://leadsgenai.in/.well-known/agent.json | python3 -m json.tool 2>/dev/null | head -30 || curl -s https://leadsgenai.in/.well-known/agent.json | head -c 800

echo ""
echo "=== MCP product discover body ==="
curl -s https://leadsgenai.in/api/mcp-product/v1/discover | python3 -m json.tool 2>/dev/null || curl -s https://leadsgenai.in/api/mcp-product/v1/discover | head -c 600

echo ""
echo "=== /env flag state ==="
grep -E "^(MCP_PRODUCT|MCP_ENGINEER|FASTAPI_MCP_TOKEN)=" .env | sed 's/=.*/=...redacted.../' || echo "no MCP flags found"

echo ""
echo "=== DEPLOYED TOKEN (for Claude Desktop config) ==="
echo "FASTAPI_MCP_TOKEN=$TOKEN"
