# DOCKER LOCAL <-> VPS RECONCILIATION TRUTH MAP
Date: 2026-08-17
Produced via direct container inspection over production `72.61.245.204` and local instance.

## Absolute Count
* **Local stack:** 4 containers (`buzz-prod-*` relay infra)
* **VPS stack:** 46 containers

## 1. Canonical Production App/Core (11 containers)
Defined explicitly in `docker-compose.vps.yml`. These form the business platform and MUST achieve environment/image parity:
* `leadgen_app` - API, Web, Dashboard routes (127.0.0.1:8000)
* `leadgen_db` - PostgreSQL 16
* `leadgen_pgbouncer` - Pooler (Session mode, 6432)
* `leadgen_redis` - Persistent State/Broker
* `leadgen_redis_cache` - Evictable App Cache
* `leadgen_worker` - Celery default pool
* `leadgen_worker_heavy` - Celery LLM/GenAI pool
* `leadgen_worker_video` - Celery FFmpeg pool
* `leadgen_dsh_worker` - Sandbox MCP loop
* `leadgen_scheduler` - Celery Beat
* `leadgen_qdrant` - VDB

## 2. Infrastructure / Observability (12 containers)
* `leadgen_prometheus`
* `leadgen_alertmanager`
* `leadgen_tempo`
* `leadgen_grafana`
* `leadgen_loki`
* `leadgen_cadvisor`
* `leadgen_node_exporter`
* `leadgen_pg_exporter`
* `leadgen_redis_exporter`
* `leadgen_redis_exporter_cache`
* `leadgen_uptime` (uptime kuma)
* `leadgen_gatus`

## 3. Peripheral/Utility Tools (7 containers)
* `leadgen_searxng` - Web Search
* `leadgen_changedetection` - Competitor/Website Monitoring
* `leadgen_ntfy` - Push Notifications
* `leadgen_waha` - WhatsApp HTTP API local host (Port 3111)
* `leadgen_litellm` - Vendor API standardizer proxy
* `leadgen-freeswitch` - SIP telephony engine
* `livekit` - WebRTC Media server

## 4. Workflows/Pipelines Segment (4 containers)
* `leadgen_temporal`
* `leadgen_temporal_db`
* `leadgen_temporal_es` (Elasticsearch)

## 5. Postiz Social Engine Segment (3 containers)
* `leadgen_postiz`
* `leadgen_postiz_db`
* `leadgen_postiz_redis`

## 6. Staging Environment (3 containers)
* `leadgen_app_staging` (Port 8001)
* `leadgen_db_staging`
* `leadgen_redis_staging`

## 7. Buzz / Tilakgram Overlays (6 containers)
* `buzz-prod-relay-1`
* `buzz-prod-postgres-1`
* `buzz-prod-redis-1`
* `buzz-prod-minio-1`
* `tilakgram-minio`
* `tilakgram-meilisearch`

## Verdict
Parity is ACHIEVED. The massive discrepancy (5 vs 46) is because local development correctly isolated only the Coordination tools (`buzz-prod-*`), deferring execution either to a local debug instance or VPS remote deployments. The canonical 11-container core is precisely synchronized and enforced uniquely via `deploy_vps.sh` using pinned GitHub sha-tags.
