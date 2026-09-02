# KPI Dashboard Specification — LeadGenAI

> **UI surfaces:** `/app/admin` · `/app/analytics` · `/app/customer` · `/api/admin/live-stats`
> **Assessment source:** [`DASHBOARD_ASSESSMENT_REPORT.md`](DASHBOARD_ASSESSMENT_REPORT.md) · **Updated:** 2026-06-20

---

## 1. North-star KPIs

| KPI | Definition | Source | Target (early stage) |
|-----|------------|--------|----------------------|
| **MRR** | Sum active plan prices | `revenue_digest`, billing | >₹0 → ₹50k |
| **Paid clients** | `plan != trial` count | `clients_store` + DB | 1 → 10 |
| **Inquiries / 7d** | Public form submits | `inquiries.jsonl` + DB | Growing WoW |
| **Speed-to-lead** | Median inquiry→first touch | `speed_to_lead.py` | <2 min (Advanced USP) |
| **Email reply rate** | Replies / sent | `reply_agent` + outreach logs | >5% |
| **Call connect rate** | Answered / dialed | `calls` table | TBD post-DLT |
| **Churn risk** | Red/yellow health bands | `client_health.py` | <20% red |

---

## 2. Admin dashboard sections

### 2.1 Executive row (cards)

| Card | API | Refresh |
|------|-----|---------|
| Est. MRR | `/api/admin/dashboard` | Page load |
| Active clients | same | Page load |
| Inquiries 24h | `/api/admin/live-stats` | 60s |
| System health | `/api/admin/system-health-detail` | Manual (`SYS_HEALTH_DETAIL=1`) |

### 2.2 Revenue analytics

| Metric | Endpoint | Chart |
|--------|----------|-------|
| Point MRR/churn/LTV | `GET /api/admin/revenue-analytics` | Cards |
| 90-day trend | `GET /api/admin/revenue-trend?days=90` | Line (`REVENUE_TRENDS=1`) |

Snapshot job: daily 00:15 IST → `data/revenue_snapshots.jsonl`

### 2.3 Growth / pipeline

| Metric | Source |
|--------|--------|
| Prospects by status | `/api/analytics/prospects-by-status` |
| Leads by source | `/api/analytics/leads-by-source` |
| Hot leads | `/api/growth/leads/hot` |
| Funnel | inquiries → prospects → clients → MRR |

### 2.4 Operations

| Metric | Source |
|--------|--------|
| Celery queue depth | `system-health-detail` |
| Worker alive | `data/job_heartbeats.json` |
| LLM provider status | Kavya pulse / `/metrics` |
| Telephony score | `telephony_readiness` |
| Activation debt | `/api/activation/readiness` |

### 2.5 Activity & audit

| Feed | Endpoint |
|------|----------|
| Agent events | `/api/admin/activity-feed` |
| Audit log | `/api/admin/audit-logs` |
| Per-client timeline | `/api/admin/clients/{id}/timeline` (`CLIENT_TIMELINE=1`) |

---

## 3. Customer dashboard KPIs

| KPI | Visible to client |
|-----|-------------------|
| Leads this month | Yes |
| Posts ready | Yes |
| Minutes used / remaining | Advanced/voice |
| Speed-to-lead badge | Yes |
| Lead status breakdown | Hot/Warm/Cold chart |

API: `/api/customer/portal/dashboard`

---

## 4. Campaign-level KPIs (voice)

| Metric | Field |
|--------|-------|
| Calls made | `calls` count by day |
| Avg duration | `duration_seconds` |
| Qualified % | `call_qualifications.jsonl` |
| Cost per call | Vobiz ₹/min × duration |
| Outcome breakdown | answered / no-answer / voicemail |

Pre-flight: `GET /api/admin/leads/ready`

---

## 5. Marketing campaign KPIs

| Metric | Source |
|--------|--------|
| Emails sent / day | outreach cap + logs |
| Bounce rate | `email_warmup.py` (<1.8% pause) |
| Open/reply proxy | reply_agent counts |
| Content scheduled | `content_schedule.jsonl` |
| Widget conversions | inquiries with `source_slug` |

---

## 6. Grafana / Prometheus (optional)

| Dashboard | File |
|-------------|------|
| Celery tasks | `monitoring/grafana/dashboards/celery_tasks.json` |
| USE metrics | Prometheus `:9090` |
| Uptime | Uptime Kuma / Gatus |

Enable: `docker compose -f deploy/compose/docker-compose.observability.yml up -d`

---

## 7. Export & reporting

| Report | Method |
|--------|--------|
| Client CSV | Admin bulk export |
| Revenue digest | Nikhil daily job → email |
| Engineer KPI | Pranav/Vidya/Arnav scheduled |

Future: scheduled email reports (backlog — WON'T HAVE deferred).

---

## 8. Data freshness SLAs

| Data | Max staleness |
|------|---------------|
| Live stats cache | 60s |
| Revenue snapshot | 24h |
| Lead score | 24h (pipeline job) |
| Team status | Real-time events |

---

## 9. Implementation status

| Spec item | Status |
|-----------|--------|
| Multi-condition filters | ✅ admin UI |
| Bulk client actions | ✅ admin UI |
| Revenue time-series | ✅ gated flag |
| Client timeline | ✅ gated flag |
| API usage per tenant | 📋 backlog |
| AI anomaly detection | 📋 deferred |
