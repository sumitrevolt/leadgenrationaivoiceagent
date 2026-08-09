---
name: observability-ops
description: Operate and extend the LeadGen AI monitoring stack — Prometheus, Grafana, Alertmanager (email), Loki, Tempo, Uptime Kuma + Celery (flower / celery-exporter) + app /metrics + OTel tracing. Use when the user says "monitoring", "alert add karo", "grafana", "metrics", "prometheus rule", "flower", "celery dashboard", "tempo/alertmanager issue", "observability", or wiring health/alerting.
---

# Observability Ops (monitoring stack)

`deploy/compose/docker-compose.observability.yml` — 6 containers: Prometheus (:9090), Grafana (:3000), Alertmanager (:9093, email), Loki (:3100), Tempo (:4317 traces), Uptime Kuma (:3001). App side: `/metrics` (Prometheus) + Sentry (errors, gated `SENTRY_DSN`) + `/health` `/health/ready` + `ops_watchdog` (app-level email). Bring up: `docker compose -f deploy/compose/docker-compose.observability.yml up -d`.

> **KYA measure + kab freeze →** `slo-error-budget` (SLO table, burn-rate rules, error-budget policy). Yeh skill = stack HOW; woh = targets WHAT.

## Celery observability (addons — `deploy/compose/docker-compose.addons.yml`)
Scheduler = Celery durable (LIVE), so Celery visibility zaroori hai:
- **celery-exporter** (`leadgen_celery_exporter` :9808) — Prometheus Celery metrics (task counts/states/runtimes, `celery_workers_online`, `celery_queue_length` incl. DLQ watch). Bina iske 14 AI-staff tasks Grafana me DARK the.
- **flower** (`leadgen_flower` :5555, HTTP Basic `FLOWER_USER`/`FLOWER_PASSWORD`) — real-time task UI (state/retry/ETA/worker health). SSH tunnel se access: `ssh -L 5555:127.0.0.1:5555 ...` → http://localhost:5555. Public expose mat karo.
- prometheus.yml me dono scrape targets ALREADY hain (`celery` :9808 + `flower` :5555). Bring up: `docker compose -f deploy/compose/docker-compose.addons.yml up -d`. Grafana Celery dashboard auto-provisioned (`monitoring/grafana/dashboards/celery_tasks.json`).
- Same addons file me **minio** (`leadgen_minio` :9000 S3 API / :9001 console) — object store (AI images/client assets), abhi opt-in (app code `data/ai_images/` bind-mount pe graceful fallback; `app/storage/minio_client.py`).

## Add an alert
Full procedure (reload, validate, verify table, rollback, the two bind-mount traps) → `references/ALERT_RUNBOOK.md`.
1. Rule → `monitoring/alert_rules.yml` (PromQL `expr`, `for:`, `labels: {severity: critical}`, `annotations`).
2. Prometheus reload: `up -d --force-recreate prometheus` (ya `kill -HUP 1`).
3. Route → `monitoring/alertmanager.yml` (`severity="critical"` → `email-admin`, 1h repeat). Validate: `docker exec leadgen_alertmanager amtool check-config /etc/alertmanager/alertmanager.yml`.

## Alertmanager email (secret-safe)
SMTP password committed config me **NAHI** — `smtp_auth_password_file: /etc/alertmanager/smtp_pass`; file `monitoring/alertmanager_smtp_pass` **gitignored**, deploy pe `.env` `SMTP_PASSWORD` se VPS pe likhi + compose extra mount. Change ke baad alertmanager recreate.

## Traces (OTel)
`app/observability_otel.py`, gated `ENABLE_OTEL=1`. **GOTCHA**: full OTel stack (sdk + otlp-exporter + instrumentation) image me NAHI (sirf `opentelemetry-api` lock me hai) → `ENABLE_OTEL=1` pe graceful skip-warning, traces nahi aate. Chahiye → otel sdk/exporter pkgs `requirements.lock.txt` me add + rebuild. Tempo target `tempo:4317`.

## Sentry — ARMED (live, 2026-06-22)
Sentry error-tracking LIVE: `SENTRY_DSN` SET in VPS `.env` + `ENVIRONMENT=production`, capturing. No longer wired-but-OFF.

## Wired-but-OFF (sirf .env keys chahiye)
PostHog (`POSTHOG_API_KEY`), LiteLLM (`LITELLM_MASTER_KEY`), Cloudflare (`CLOUDFLARE_TUNNEL_TOKEN`), OTel (`ENABLE_OTEL=1`), RequestGuard (`REQUEST_GUARD=1`), PlanTierRateLimit (`PLAN_RATE_LIMIT=1`). Checklist: `docs/INFRA_UPGRADE_2026.md` Part 8.

## Gotchas (seekhe hue)
- **Tempo crash-loop**: `monitoring/tempo.yaml` me unsupported fields (`ingester`/`compactor`) image schema reject karta tha (329 restarts) → **minimal config** (server+distributor+storage only) rakho.
- Config bind-mounted → change ke baad `up -d --force-recreate <svc>` (plain restart sometimes config re-read nahi karta).
- Bind-mount file MISSING ho to Docker **directory** bana deta (mount fail) → file pehle banao, phir `up`.
- App ka `ops_watchdog` (gated) bhi email karta — Alertmanager se ALAG (app-level vs infra-level; app down ho to ops_watchdog bhi down → Alertmanager/Uptime catch karega).

## Verify
`amtool check-config` valid · container `status=running restarts=0` · `/metrics` 200 · Grafana :3000 up · flower :5555 reachable (tunnel) · celery-exporter :9808/metrics 200 · test alert fire → email aaya.

## Enterprise gate (monitoring change = config-safe + reversible)

- **Operating loop:** Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). Discover me: rule/route/container already exists kya (`monitoring/alert_rules.yml`, prometheus scrape targets) + config bind-mount hai ya image-baked.
- **Change-risk tier: Standard** (alert rule / dashboard add) → **High-risk** jab alertmanager SMTP secret, public-expose, ya core scrape-config touch ho.
- **Operating gates:**
  - **Secret-safe** — SMTP password committed config me KABHI nahi: `smtp_auth_password_file: /etc/alertmanager/smtp_pass`, file `monitoring/alertmanager_smtp_pass` gitignored, VPS pe `.env` `SMTP_PASSWORD` se likhi. `FLOWER_USER/PASSWORD`, Grafana creds = `.env`. Diff pe repo ka secret-scan gate (`check_secrets.py`) chalao.
  - **No public expose** — flower (:5555) / celery-exporter (:9808) / Grafana SSH-tunnel ya internal only; internet pe mat kholo.
  - **Don't break the watcher** — alert change ke baad alertmanager/prometheus self-monitoring intact; `automation_health` + `ops_watchdog` (app-level) + Alertmanager (infra-level) dono layers chahiye (ek down to dusra catch kare).
  - **Alert noise/cooldown** — naya critical rule ko `for:` + repeat-interval (1h) do, warna alert-storm. Severity-route sahi (`severity="critical"` → `email-admin`).
- **Rollback (NAMED):** bad rule/route → `monitoring/alert_rules.yml` / `alertmanager.yml` revert + `up -d --force-recreate <svc>` (bind-mount config plain-restart pe kabhi re-read nahi karta). Crash-loop (Tempo lesson) → minimal config pe wapas.
- **Evidence to close:** `docker exec leadgen_alertmanager amtool check-config ...` valid + target container `restarts=0` + scrape target `/metrics` 200 + test alert fire → email mila. Bina firing-proof "alert add ho gaya" mat bolo.
