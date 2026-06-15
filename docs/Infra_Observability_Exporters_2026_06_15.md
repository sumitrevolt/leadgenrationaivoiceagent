# Infrastructure Upgrade — Resource/USE Observability (Exporters)

**Date:** 2026-06-15 · **Scope:** Deep infra analysis; add the genuinely-missing observability layer (no spend, single-VPS).
**Outcome:** node_exporter + cAdvisor + postgres_exporter + redis_exporter ×2 + scrape jobs + 7 infra alerts. YAML validated. Deploy = obs-compose only (no app rebuild).

---

## 1. Gap (proven, deep analysis)

`docker-compose.observability.yml` me tha: prometheus, alertmanager, loki, tempo, grafana, uptime-kuma, gatus. `monitoring/prometheus.yml` scrape karta **sirf**: `leadgen_app:8080/metrics`, prometheus, alertmanager.

**Matlab tu BLIND tha** in sab pe (USE = Utilization/Saturation/Errors — persona principle, aur exactly jo audit me change hua):
| Missing | Kya nahi dikhta tha | Audit link |
|---|---|---|
| **cAdvisor** | per-container CPU/mem/restarts — container mem_limit hit ho raha ya nahi | P1-1 limits |
| **node_exporter** | host disk/mem/CPU/load trends (disk-fill = single-VPS data-loss risk) | — |
| **postgres_exporter** | DB connections/max, slow queries, cache-hit, locks | P1-2 pool sizing |
| **redis_exporter** | `evicted_keys`, memory/maxmemory, ops — per instance | **P0-1** noeviction validate! |

App-level `/metrics` (LLM/queue-depth — P1-3) tha, par **infra/resource layer poora missing** tha. Yeh #1 infra gap.

## 2. Fix — exporter suite (best-stack, free, single-host)

`docker-compose.observability.yml` me 5 naye services (research-confirmed standard suite, ~700MB total, sab **mem_limit'd**, **koi host-port nahi** = Prometheus internally scrape karta = secure):
- **node-exporter** (host /proc,/sys,/ mounts) — host CPU/mem/disk/load.
- **cadvisor** (privileged, docker.sock) — per-container resources.
- **postgres-exporter** (→ `db:5432`, creds .env se) — DB health.
- **redis-exporter** (→ main redis, noeviction) + **redis-exporter-cache** (→ redis-cache, lru) — alag jobs taaki dono instance distinct dikhein.

`monitoring/prometheus.yml` — 5 naye scrape jobs (node/cadvisor 10s — volatile; postgres/redis 30s).

`monitoring/alert_rules.yml` — naya `infrastructure` group (USE alerts):
- **HostDiskLow** (<10% free, critical) · **HostMemoryHigh** (<10% avail) · **ContainerNearMemLimit** (>90% of mem_limit — P1-1 OOM pre-warn).
- **RedisMainNearFull** (>85% — noeviction = writes-fail imminent, P0-1) · **RedisMainEvictions** (main pe eviction = misconfig, critical) · **PostgresConnectionsHigh** (>80% max — P1-2) · **PostgresDown** (pg_up==0).

## 3. Why this (discipline)
- **No spend / single-VPS-fit**: sab open-source, light containers — koi 2nd-server/cloud nahi (HA spend-blocked hai, yeh us constraint ke andar).
- **Additive, not duplicate**: Prometheus/Grafana already the — sirf data-sources (exporters) + rules add kiye, parallel stack nahi.
- **Directly validates audit**: P0-1 (redis evictions), P1-1 (container limits), P1-2 (pg connections) ab measurable.
- **Skipped (over-engineering for now)**: remote-write to cloud, Thanos/long-term storage, per-query pg_stat_statements collector (heavy) — single-VPS pe abhi zaroorat nahi.

## 4. Deploy (obs-compose only — NO app rebuild)

```bash
# VPS (Git ssh): monitoring files pull + exporters up + prometheus reload
cd /opt/leadgen && git pull --ff-only origin main
docker compose -f docker-compose.observability.yml up -d        # 5 naye exporters
docker compose -f docker-compose.observability.yml exec -T prometheus \
  promtool check config /etc/prometheus/prometheus.yml           # validate (optional)
curl -fsS -X POST http://127.0.0.1:9090/-/reload                 # naye scrape jobs + rules load (--web.enable-lifecycle on hai)
```
**Verify:** Prometheus → http://127.0.0.1:9090/targets (SSH tunnel) — node/cadvisor/postgres/redis/redis-cache sab **UP** hone chahiye. **Grafana dashboards import-by-ID** (Grafana → + → Import): node_exporter **1860**, cAdvisor **14282**, postgres **9628**, redis **763**.
**Rollback:** `docker compose -f docker-compose.observability.yml rm -sf node-exporter cadvisor postgres-exporter redis-exporter redis-exporter-cache` + revert monitoring files + reload.

### Files
- `docker-compose.observability.yml` (5 exporters) · `monitoring/prometheus.yml` (5 jobs) · `monitoring/alert_rules.yml` (infrastructure group)

## Sources
- node_exporter/cAdvisor/postgres/redis docker-compose suite — https://github.com/Yang-HangWA/Prometheus · https://grafana.com/docs/grafana-cloud/send-data/metrics/metrics-prometheus/prometheus-config-examples/docker-compose-linux/
- Prometheus + exporters single-host — https://last9.io/blog/prometheus-with-docker-compose/
- Grafana dashboards: node 1860 · cAdvisor 14282 · postgres 9628 · redis 763
