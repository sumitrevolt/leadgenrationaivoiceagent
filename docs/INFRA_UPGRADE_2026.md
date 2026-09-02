# Infrastructure Upgrade 2026 — Deep Gap Analysis + Billionaire-Grade Roadmap
> Verified against actual codebase (June 2026). Duplicates = 0. Every addition here is genuinely missing.

---

## Executive Summary

Tera existing stack **surprisingly mature** hai — rate limiting, security headers, PostHog wrapper, LiteLLM config, Cloudflare tunnel, pg_backup scripts, multi-tenant middleware, full observability stack sab ALREADY bana hua hai. Problem: **wired but not activated** — placeholder keys, unset env vars, missing container additions.

**Billionaire thinking:** 80% ROI milti hai sirf existing plumbing ko properly connect karne se. Naya infra add karna #2 priority hai, existing activate karna #1.

---

## Part 1 — What's ALREADY BUILT (Don't Rebuild)

| Component | Where | Status | Action Needed |
|-----------|-------|--------|---------------|
| PostHog analytics + HTML inject | `app/analytics/posthog_client.py` + `middleware/analytics_inject.py` | ✅ Built, OFF | Set `POSTHOG_API_KEY=phc_xxx` in `.env` |
| Redis-backed rate limiting (IP) | `app/middleware/__init__.py` | ✅ Built, ON prod | Already active in production |
| Security headers middleware | `app/middleware/__init__.py` | ✅ Built, ON | Already active |
| Request tracing (X-Request-ID) | `app/middleware/__init__.py` | ✅ Built, ON | Already active |
| LiteLLM gateway + Redis cache | `deploy/litellm/config.yaml` + `deploy/compose/docker-compose.edge.yml` | ✅ Built, OFF | Set `LITELLM_MASTER_KEY` → `--profile gateway up` |
| Cloudflare Tunnel (WAF + CDN) | `deploy/compose/docker-compose.edge.yml` | ✅ Built, OFF | Set `CLOUDFLARE_TUNNEL_TOKEN` → `--profile edge up` |
| pgBackRest + PITR scripts | `scripts/pg_pitr_enable.sh` + `pg_backup.sh` + `pg_restore_drill.sh` | ✅ Scripts exist | Wire cron + enable WAL archiving |
| WAL archive volume | `docker-compose.vps.yml` (`walarchive` volume) | ✅ Volume mounted | Run `scripts/pg_pitr_enable.sh` on VPS |
| Sentry error tracking | `app/main.py` (FastApiIntegration) | ✅ Built, needs `SENTRY_DSN` | Set `SENTRY_DSN` in `.env` |
| Multi-tenant white-label | `app/middleware/tenant.py` | ✅ Built, ON | Active |
| GZip compression | `app/middleware/__init__.py` | ✅ Built, ON | Active |
| RequestGuard (timeout + shed) | `app/middleware/__init__.py` | ✅ Built, OFF | Set `REQUEST_GUARD=1` |
| OpenTelemetry traces | `app/observability_otel.py` | ⚠️ Built, OFF — exporter deps NOT baked | **`ENABLE_OTEL=1` alone = silent no-op.** Lock me sirf `opentelemetry-api` baked; OTLP exporter + FastAPI/SQLAlchemy/Redis/httpx instrumentation `requirements-otel.txt` (un-baked) me → `ImportError`. Pehle in deps ko lock me add + image rebuild, PHIR `ENABLE_OTEL=1` + `OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317` |
| Full observability stack | `deploy/compose/docker-compose.observability.yml` | ✅ LIVE | Prometheus+Grafana+Loki+Tempo+Gatus+Uptime Kuma |
| Node/cAdvisor/Postgres/Redis exporters | `deploy/compose/docker-compose.observability.yml` | ✅ LIVE | Scraping active |

---

## Part 2 — Confirmed GAPS (Added This Session)

### ✅ DONE — Added in this upgrade

#### 1. Celery Monitoring (`deploy/compose/docker-compose.addons.yml`)
**Gap:** 14 AI staff tasks (blog/prospect/outreach/qa/trainer/self-improve etc.) completely DARK in Prometheus/Grafana. Zero Celery metrics anywhere in `prometheus.yml`.

**Added:**
- `leadgen_celery_exporter` — danihodovic/celery-exporter, 50MB, exposes `celery_tasks_total`, `celery_tasks_runtime_seconds`, `celery_workers_online`, `celery_queue_length` per queue (celery/heavy/dlq)
- `prometheus.yml` — celery + flower scrape targets added
- `monitoring/grafana/dashboards/celery_tasks.json` — full dashboard (workers online, queue depths, task rate by state, P50/P95/P99 runtime, top slowest tasks, failure rate, DLQ watch)
- `monitoring/grafana/provisioning/dashboards/default.yml` — auto-provision (no manual Grafana import needed)
- `deploy/compose/docker-compose.observability.yml` — Grafana provisioning volumes added

**Activate:** `docker compose -f deploy/compose/docker-compose.addons.yml up -d celery-exporter`

#### 2. Flower — Celery Task UI (`deploy/compose/docker-compose.addons.yml`)
**Gap:** No way to inspect running/failed/retry tasks for 14 AI staff agents without `celery inspect` CLI.

**Added:** `leadgen_flower` (mher/flower:2.0, 256MB) — real-time task dashboard, worker management, task history, ETA/retry visibility.

**Activate:**
```bash
# .env me add karo:
FLOWER_USER=admin
FLOWER_PASSWORD=<strong_password>

docker compose -f deploy/compose/docker-compose.addons.yml up -d flower
# Access: ssh -L 5555:127.0.0.1:5555 root@72.61.245.204 → http://localhost:5555
```

#### 3. MinIO S3-Compatible Storage (`deploy/compose/docker-compose.addons.yml`)
**Gap:** `app/marketing/ai_image.py` images → `data/ai_images/` bind-mount. No S3 API, no presigned URLs, no CDN-ready paths, no lifecycle cleanup, no replication path.

**Added:**
- `leadgen_minio` — minio/minio, 512MB, S3 API :9000 + console :9001
- `leadgen_minio_setup` — one-shot bucket creation + public-read policy
- `app/storage/minio_client.py` — drop-in S3 client with local-disk fallback (zero breaking change)
- `app/storage/__init__.py`

**Activate:**
```bash
# .env me add karo:
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=<strong_password>
MINIO_URL=http://minio:9000
MINIO_BUCKET=leadgen-assets
MINIO_PRIVATE_BUCKET=leadgen-private

docker compose -f deploy/compose/docker-compose.addons.yml up -d minio minio-setup
# Console: ssh -L 9001:127.0.0.1:9001 root@72.61.245.204 → http://localhost:9001
```

**Migrate ai_image.py (2 lines):**
```python
from app.storage import get_storage
url = get_storage().public_url(f"ai_images/{filename}")
await get_storage().put(f"ai_images/{filename}", img_bytes, content_type="image/png")
```

#### 4. Plan-Tier Aware Rate Limiting (`app/middleware/__init__.py`)
**Gap:** Existing `RateLimitMiddleware` is flat per-IP (100 rpm everyone). SaaS standard: Starter < Growth < Advanced. No plan-differentiation = upsell signal missing.

**Added:** `PlanTierRateLimitMiddleware` class:
- Starter: 60 rpm
- Growth: 200 rpm
- Advanced/Voice Pro: 500 rpm
- Anonymous: 20 rpm
- Admin/Internal: unlimited
- Redis-backed sliding window, fail-open, rate headers in response

**Activate:** `PLAN_RATE_LIMIT=1` in `.env` (default OFF, zero risk)

---

## Part 3 — Immediate Activation (Zero Code, Just .env)

These are **already built** — set the env var and restart app container.

```bash
# On VPS: nano /opt/leadgen/.env  (ya Desktop Commander se edit karo)

# 1. PostHog product analytics (free 1M events/month)
# Get key: app.posthog.com → Project Settings → API Keys
POSTHOG_API_KEY=phc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
POSTHOG_HOST=https://us.i.posthog.com

# 2. Sentry error tracking (free tier: 5k errors/month)
# Get DSN: sentry.io → New Project → Python
SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx

# 3. RequestGuard (timeout 55s + load-shed 200 in-flight)
REQUEST_GUARD=1

# 4. OpenTelemetry traces (sends to existing Tempo container)
ENABLE_OTEL=1
OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317

# 5. Plan-tier rate limiting
PLAN_RATE_LIMIT=1

# 6. LiteLLM gateway (OpenAI-compatible endpoint + Redis prompt cache)
LITELLM_MASTER_KEY=sk-leadgen-internal-xxxxx
# Then: docker compose -f deploy/compose/docker-compose.edge.yml --profile gateway up -d

# 7. Cloudflare Tunnel (WAF + DDoS + CDN for origin hide)
# Get token: dash.cloudflare.com → Zero Trust → Tunnels
CLOUDFLARE_TUNNEL_TOKEN=eyJh...
# Then: docker compose -f deploy/compose/docker-compose.edge.yml --profile edge up -d
```

**After .env edit:**
```bash
docker compose -f docker-compose.vps.yml up -d --no-deps app
```

---

## Part 4 — CRITICAL Blocker (Must Fix Before First Customer)

```
🚨 UPI_VPA=  ← UNSET (manual-UPI = primary India payment path)
```

> **UPDATED 2026-06-18: Razorpay REMOVED entirely** (gateway/webhook/verify-payment code all deleted).
> India payments ab **manual UPI** (`UPI_VPA` standalone modal). Stripe path international ke liye intact.

**Action:**
1. `.env` me apna UPI VPA set karo: `UPI_VPA=yourname@okhdfcbank` (checkout UPI modal isi se banta hai)
2. (Optional, international) `STRIPE_SECRET_KEY=sk_live_xxx`
3. `docker compose -f docker-compose.vps.yml up -d --no-deps app`
4. Run `scripts/test_billing_truth_2026.py` to verify pricing-truth

---

## Part 5 — pgBackRest PITR Activation (Production Safety)

`walarchive` volume exists. Scripts exist. Just not activated.

```bash
# VPS pe run karo (one-time setup):
ssh root@72.61.245.204 "bash /opt/leadgen/scripts/pg_pitr_enable.sh"

# Verify WAL archiving is on:
docker exec leadgen_db psql -U leadgen -c "SHOW archive_mode; SHOW archive_command;"

# Backup drill (test restore):
bash /opt/leadgen/scripts/pg_restore_drill.sh

# Add to crontab (VPS):
# 0 2 * * * bash /opt/leadgen/scripts/pg_backup.sh >> /opt/leadgen/logs/pg_backup.log 2>&1
```

---

## Part 6 — Future Infrastructure (When Budget/Need Arrives)

### Tier A — Low Effort, High ROI (next 30 days)

| Tool | Gap Filled | Deploy | Cost |
|------|-----------|--------|------|
| **Infisical Cloud** | .env secrets management, key rotation, audit log | [infisical.com](https://infisical.com) free tier (25 secrets) + Python SDK | Free |
| **PostHog Feature Flags** | Runtime feature flags (replace env-based SELF_IMPROVE_LOOP etc.) | Already wired — just use `ph.feature_enabled("flag", distinct_id)` | Free (already in posthog_client.py) |
| **GrowthBook** | Proper A/B testing for pricing page, /audit CTA, /demo flow | docker-compose self-host OR growthbook.io free | Free |

### Tier B — Medium Effort (30-90 days)

| Tool | Gap Filled | Deploy | Cost |
|------|-----------|--------|------|
| **OpenMeter** | Real-time usage metering (replace JSONL lead_usage.py) | `docker compose` self-host (Go, light) | Free OSS |
| **Lago** | Full subscription management + invoicing engine (replace custom subscription.py) | Self-host (heavy: Ruby+React+Postgres) | Free OSS |
| **Cloudflare R2** | Offsite MinIO replication (disaster recovery) | R2 bucket + mc mirror cron | $0.015/GB/month |
| **Grafana Alerting** | Celery failure rate + DLQ depth alerts (Alertmanager already wired) | Add alert rules to `monitoring/alert_rules.yml` | Free |

### Tier C — Strategic (90+ days, post-revenue)

| Tool | Gap Filled | Deploy | Cost |
|------|-----------|--------|------|
| **2nd VPS (HA)** | Single-VPS SPOF elimination, PostHog self-host (needs 8GB+ for ClickHouse) | Hostinger 2nd VPS | ₹2-4k/month |
| **APISIX** | API gateway with per-tenant metering at L7, plugin ecosystem | Replace Caddy with APISIX (significant migration) | Free OSS |
| **Flagsmith** | Dynamic feature flags with UI + targeting rules | Docker self-host (uses existing Postgres+Redis) | Free OSS |
| **Apache Kafka** | Event streaming for billing events (replace Redis pub/sub) | Separate container, 2GB+ RAM | Free OSS |

---

## Part 7 — What NOT to Add (Billionaire Discipline)

| Tool | Why Skip |
|------|----------|
| **Lago now** | Ruby+React stack, 3GB+ RAM on already-tight VPS. JSONL meter good enough until 50+ clients. |
| **Trigger.dev / Inngest** | Celery is production-hardened. Migration cost >> benefit. |
| **Kong API Gateway** | Heavier than APISIX. Caddy + PLAN_RATE_LIMIT=1 covers 95% of need at zero cost. |
| **Doppler secrets** | Not open source. Infisical Cloud free tier better. |
| **PostHog self-host** | Needs ClickHouse (4GB+ RAM alone). Use PostHog Cloud free tier (1M events/mo). |
| **Kill Bill** | Java, enterprise-complexity. UPI/Stripe + custom subscription.py good enough at current scale. |
| **Separate analytics DB** | Qdrant + Postgres already handle analytics queries for current scale. |

---

## Part 8 — Activation Checklist (Priority Order)

```
[ ] 1. UPI_VPA → .env → app restart (REVENUE BLOCKER; Razorpay removed 2026-06-18)
[ ] 2. docker compose -f deploy/compose/docker-compose.addons.yml up -d   (Celery visibility + MinIO)
[ ] 3. PostHog API key → .env → app restart (product analytics ON)
[ ] 4. Sentry DSN → .env → app restart (error tracking ON)
[ ] 5. REQUEST_GUARD=1 → .env → app restart (timeout protection)
[ ] 6. PLAN_RATE_LIMIT=1 → .env (plan-tier limits ON)
[ ] 7. ENABLE_OTEL=1 → .env (distributed traces to Tempo)
[ ] 8. LITELLM_MASTER_KEY → .env + --profile gateway up (LLM cache ON)
[ ] 9. CLOUDFLARE_TUNNEL_TOKEN → .env + --profile edge up (CDN + WAF ON)
[ ] 10. pg_pitr_enable.sh on VPS + backup cron (PITR active)
[ ] 11. Infisical free tier → migrate secrets from .env
[ ] 12. FLOWER_PASSWORD + FLOWER_USER → deploy/compose/docker-compose.addons.yml up -d flower
```

---

## Part 9 — Memory Updated

Add to CLAUDE.md (infra section):

```
## Infra Additions (2026-06-15 upgrade)
- deploy/compose/docker-compose.addons.yml: celery-exporter (:9808) + flower (:5555) + minio (:9000/:9001)
- prometheus.yml: celery + flower scrape targets added
- Grafana: celery_tasks dashboard auto-provisioned (monitoring/grafana/dashboards/)
- app/middleware/__init__.py: PlanTierRateLimitMiddleware added (PLAN_RATE_LIMIT=1 to activate)
- app/storage/minio_client.py: S3-compatible storage with local-disk fallback
- ACTIVATION SEQUENCE: docs/INFRA_UPGRADE_2026.md Part 8
```
