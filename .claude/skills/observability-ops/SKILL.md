---
name: observability-ops
description: Operate and extend the LeadGen AI monitoring stack — Prometheus, Grafana, Alertmanager (email), Loki, Tempo, Uptime Kuma + app /metrics + OTel tracing. Use when the user says "monitoring", "alert add karo", "grafana", "metrics", "prometheus rule", "tempo/alertmanager issue", "observability", or wiring health/alerting.
---

# Observability Ops (monitoring stack)

`docker-compose.observability.yml` — 6 containers: Prometheus (:9090), Grafana (:3000), Alertmanager (:9093, email), Loki (:3100), Tempo (:4317 traces), Uptime Kuma (:3001). App side: `/metrics` (Prometheus) + Sentry (errors) + `/health` `/health/ready` + `ops_watchdog` (app-level email). Bring up: `docker compose -f docker-compose.observability.yml up -d`.

## Add an alert
1. Rule → `monitoring/alert_rules.yml` (PromQL `expr`, `for:`, `labels: {severity: critical}`, `annotations`).
2. Prometheus reload: `up -d --force-recreate prometheus` (ya `kill -HUP 1`).
3. Route → `monitoring/alertmanager.yml` (`severity="critical"` → `email-admin`, 1h repeat). Validate: `docker exec leadgen_alertmanager amtool check-config /etc/alertmanager/alertmanager.yml`.

## Alertmanager email (secret-safe)
SMTP password committed config me **NAHI** — `smtp_auth_password_file: /etc/alertmanager/smtp_pass`; file `monitoring/alertmanager_smtp_pass` **gitignored**, deploy pe `.env` `SMTP_PASSWORD` se VPS pe likhi + compose extra mount. Change ke baad alertmanager recreate.

## Traces (OTel)
`app/observability_otel.py`, gated `ENABLE_OTEL=1`. **GOTCHA**: otel packages image me NAHI (requirements.txt commented) → `ENABLE_OTEL=1` pe graceful skip-warning, traces nahi aate. Chahiye → otel pkgs `requirements.lock.txt` me add + rebuild. Tempo target `tempo:4317`.

## Gotchas (seekhe hue)
- **Tempo crash-loop**: `monitoring/tempo.yaml` me unsupported fields (`ingester`/`compactor`) image schema reject karta tha (329 restarts) → **minimal config** (server+distributor+storage only) rakho.
- Config bind-mounted → change ke baad `up -d --force-recreate <svc>` (plain restart sometimes config re-read nahi karta).
- Bind-mount file MISSING ho to Docker **directory** bana deta (mount fail) → file pehle banao, phir `up`.
- App ka `ops_watchdog` (gated) bhi email karta — Alertmanager se ALAG (app-level vs infra-level; agar app down hai to ops_watchdog bhi down → Alertmanager/Uptime catch karega).

## Verify
`amtool check-config` valid · container `status=running restarts=0` · `/metrics` 200 · Grafana :3000 up · test alert fire → email aaya.
