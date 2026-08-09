---
name: leadgen-observability
description: Enterprise observability — logs, metrics, traces, dashboards, alerting, health-checks, audit-logs, job-visibility, error-monitoring, product-analytics, customer-journey instrumentation. Use jab failures customer ke report karne se PEHLE visible karne ho.
---

# LeadGen Observability

> Enterprise audit skill. `observability-ops` = infra (Prometheus/Loki HTTP), `genai-observability` = LLM-semantic (OTel GenAI token/provider spans). **Yeh = product/revenue/journey-level signal layer** jo unhe tie kare. Pehle `context-first`.

## Mission
Failures customer-report se PEHLE dikhao. Sirf useful signals — revenue, automation, infra, customer-journey debug me help karein.

## Repo truth
- **Obs stack**: deploy/compose/docker-compose.observability.yml me DEFINED (12 services) par 2026-07-05 live container list me NOT RUNNING — dashboards/alerts pe bharosa karne se pehle deployment verify karo. Grafana auto-provision `monitoring/grafana/provisioning/` + `dashboards/celery_tasks.json`.
- **Sentry ARMED** (`SENTRY_DSN` set on VPS, errors capturing; FastApiIntegration global).
- **OTel** GenAI traces: Tempo raw-support ready → `ENABLE_OTEL=1` + attributes (see `genai-observability`).
- **Addons** (`deploy/compose/docker-compose.addons.yml`): celery-exporter :9808 + flower :5555 task-UI.
- **Alerts**: `ops_alerts` ntfy fan-out (G.1) — engineer-score / eval-burst / dead-letter / readiness-digest, cooldowns. ntfy `https://ntfy.leadsgenai.in`.
- **Wired-but-OFF**: PostHog (`POSTHOG_API_KEY`), LiteLLM, OTel — sirf .env keys chahiye.

## Workflow
Fill-in catalogue (per-flow table, log-field contract, alert thresholds, scoring) → `references/SIGNAL_CATALOGUE.md`.
1. Critical flows identify: P1 signup/payment/onboarding/content, automations, lead pipeline, email, infra, P2 compliance gates.
2. Har flow ke liye logs/metrics/traces/events/dashboards define.
3. Har job + request ko correlation-id (jahan practical).
4. Alert thresholds: broken revenue flow, worker fail, SMTP disabled, DB down, queue backlog, high error-rate.
5. Sensitive data logs se BAAHAR (PII/recording mask).

## Enterprise checks
- Structured logs: event-name, status, safe account-id, request-id, duration, error-class.
- Dashboards: app/worker health, queue lag, revenue funnel, content-gen, lead pipeline, email failures, voice compliance-blocks.
- Audit logs: admin approval, plan change, payment status, compliance-bypass attempt.
- Product analytics: activation, retention, feature usage.

## Output
Observability gap report · event/metric catalog · dashboard+alert plan · safe instrumentation patch · readiness /100.

## Related repo skills (duplicate mat banao)
`observability-ops` (infra Prometheus/Loki) · `genai-observability` (LLM token/provider OTel) · `leadgen-infra-doctor` (health endpoints) · `leadgen-automation-reliability` (job visibility) · `leadgen-security-rbac` (audit logs).
