# MCP 404 Fix — "Could not find session" (SSE / multi-worker)

> Owner-facing runbook. Why Hermes/Claude MCP clients get `404` on
> `POST /mcp/messages/?session_id=…` even though `GET /mcp…` returns 200, and how
> to fix it safely. **Deployment is Owner-gated** (`scripts/deploy_vps.sh`);
> this documents the change, it does NOT deploy.

## Root cause (evidence)

fastapi-mcp SSE/Streamable-HTTP sessions are **in-memory per uvicorn worker**.
- `.venv\...\fastapi_mcp\transport\sse.py:51-54` → `handle_fastapi_post_message`
  returns **404 "Could not find session"** when `_read_stream_writers.get(session_id)` is empty.
- `docker-compose.vps.yml:58` → **`WEB_CONCURRENCY: 2`** (the app runs **2 uvicorn workers**).

So:
```
Hermes GET /mcp  ─────────────► worker-A   # SSE stream opens, session_id <X> registered
Hermes POST /mcp/messages/?session_id=<X> ──► worker-B   # <X> NOT on this worker → 404
```
The host Caddy `reverse_proxy` to `127.0.0.1:8000` does **no session affinity**, so the
GET (SSE, long-lived) and the POST (separate request) can land on different workers.
`GET …200` (connection looks fine) but every tool call 404s → MCP tools seem "connected"
but are unusable.

**Why it broke now:** MCP worked when the app ran a **single** worker. Moving to
`WEB_CONCURRENCY=2` (concurrent-burst 502 fix) silently broke SSE session affinity.
This is the actual reason `ops_hot_queue` / `ops_revenue_summary` etc. stopped
reaching the Hermes admin cockpit + sprint bots.

> Note: `docker-compose.vps.yml:53-58` explicitly says `WEB_CONCURRENCY=2` was
> chosen to fix "concurrent-burst 502", so **do NOT revert to 1** (that brings the
> 502s back). Use Option A.

## Option A (recommended) — dedicated single-worker MCP service

Serve only `/mcp*` from ONE uvicorn worker; keep the main app at 2 workers.

**A1. Add a service to `docker-compose.vps.yml`** (after the `app:` block, ~line 110),
mirroring `app` but `WEB_CONCURRENCY: 1` + a separate published port:

```yaml
  # Dedicated SINGLE-WORKER MCP backend. fastapi-mcp SSE sessions are per-worker,
  # so /mcp must NOT run on the multi-worker app. Caddy routes only /mcp* here.
  mcp:
    image: ${APP_IMAGE_REPOSITORY:-ghcr.io/sumitrevolt/leadgenrationaivoiceagent}:${APP_VERSION:?set APP_VERSION to the immutable git SHA}
    container_name: leadgen_mcp
    mem_limit: 2g
    mem_reservation: 1g
    cpus: "1.0"
    user: "0:0"   # root, matches app — keeps bind-mounted root-owned ./data writable
    env_file: .env
    environment:
      APP_ENV: production
      PORT: 8080
      WEB_CONCURRENCY: 1        # single worker -> SSE session affinity works
      RUN_IN_PROCESS_SCHEDULER: 0   # no in-process scheduler dup (durable celery path)
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-leadgen}:${POSTGRES_PASSWORD:-leadgen}@pgbouncer:6432/${POSTGRES_DB:-leadgen}
      REDIS_URL: redis://redis:6379/0
      LEADGEN_RUNTIME_DATA_DIR: ${LEADGEN_RUNTIME_DATA_DIR:-/var/lib/leadgen/runtime}
      QDRANT_URL: http://qdrant:6333
      CACHE_REDIS_URL: redis://redis-cache:6379/0
    ports:
      - "127.0.0.1:8090:8080"   # Caddy proxies /mcp* -> here
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_healthy }
      redis-cache: { condition: service_healthy }
      pgbouncer: { condition: service_healthy }
    volumes:
      - ./data:/app/data
      - ${LEADGEN_RUNTIME_DATA_HOST_DIR:-/opt/leadgen-runtime}:/var/lib/leadgen/runtime
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:8080/health/ready || exit 1"]
      interval: 30s
      timeout: 10s
      start_period: 120s
      retries: 3
    logging:
      driver: json-file
      options: { max-size: "50m", max-file: "5" }
    networks: [leadgen_net, dsh_net]
```

**A2. Add a Caddy route** (on the VPS /caddy/Caddyfile — the host Caddy, not this repo):
```
# leadgenai.in site block — add BEFORE the existing handle/reverse_proxy "":
@mcp path /mcp /mcp/*
handle @mcp {
    reverse_proxy 127.0.0.1:8090
}
handle {
    reverse_proxy 127.0.0.1:8000
}
```
Then `caddy reload`.

**A3. Apply (Owner):**
```
APP_VERSION=<git-sha> docker compose -f docker-compose.vps.yml up -d mcp
caddy reload
```

## Option B (faster, but re-introduces 502 risk)

`docker-compose.vps.yml:58` → `WEB_CONCURRENCY: 1`. Restores SSE affinity but drops
web concurrency → the "concurrent-burst 502" returns. Only use if throughput is not an
issue AND you accept the 502 regression.

## Verify

- Hermes MCP client: `POST https://leadsgenai.in/mcp/messages/?session_id=…` → **202 Accepted** (not 404).
- `hermes` tool call of `ops_revenue_summary` returns `{ok:true,…}`.
- `GET https://leadsgenai.in/mcp` still 200 (SSE opens).

## Rollback
- `docker compose -f docker-compose.vps.yml rm -fs mcp` (removes the dedicated service);
  main `app` is untouched. If A2 Caddy rule was added, remove the `handle @mcp` block + reload.
  `config.yaml` on Hermes side is unchanged.

## Related
- `app/main.py` MCP mount (~1386-1496, `_mcp.mount()`, gated by `FASTAPI_MCP_TOKEN` / `MCP_IP_ALLOWLIST`).
- `app/api/ops_mcp_tools.py` (ops_hot_queue / ops_revenue_summary MCP tools).
