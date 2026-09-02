# LeadGen AI — Project Overview

> Evidence-backed snapshot · 2026-07-19

## Purpose

AI marketing automation + voice lead qualification platform for Indian SMBs.
Starter plan ₹1,999: content generation, approval loop, delivery ledger, customer portal, billing (UPI/GST).

## Technology stack (verified from repo)

- **Backend:** Python, FastAPI
- **Workers:** Celery + Redis (queues: celery, heavy, video; DLQ)
- **Data:** Postgres (leads/calls/billing), JSONL stores (`data/` — clients, content, approvals, ledger, auth), Qdrant/vectorstore
- **Frontend:** Server-rendered HTML dashboards (`frontend/`), customer + admin portals
- **AI routing:** OmniRoute (optional, double-gated), free-provider chain, voice hot-path separate
- **Voice:** Swara agent (STT→LLM→TTS); outbound dial HARD-OFF by policy
- **Deploy:** Docker Compose (`docker-compose.vps.yml`) on VPS `/opt/leadgen`
- **Monitoring:** `/health`, Sentry, automation logs

## Main entry points

| Surface | Path / module |
|---|---|
| API | FastAPI routers in `app/api/` |
| Customer portal | `/app/login`, customer dashboard HTML, `/api/customer/*`, `/api/customer/auth/*` |
| Admin / Operating HQ | `/app/office` (authoritative ops surface per handoff) |
| Workers | Celery app + scheduler beat |
| Marketing engines | `app/marketing/*` (content, approval, delivery, clients_store) |
| Voice | telephony + Swara conversation path |

## Major services / data stores

- `clients_store` — marketing clients JSONL (canonical tenant record + `billing_client_ids`)
- `auto_content` — per-client content queues
- `content_approval` — draft→approve→publish gate
- `delivery_ledger` — customer-visible delivery timeline
- `customer_auth` — portal credentials JSONL + JWT
- Billing / GST invoices — Postgres + invoice JSONL
- Redis — cache, rate limits, logout blacklist, magic-link JTIs

## External integrations

Email (Hostinger SMTP), WhatsApp (WAHA / human-share links), HubSpot (optional), Google Sheets (optional), telephony (vobiz), UPI payment claims, OmniRoute gateway (local/VPS-gated).

## Deployment

- Prod: `https://leadsgenai.in` — health reports version SHA + environment
- Compose: `docker-compose.vps.yml` (app, worker, scheduler, worker_heavy, worker_video)
- Rollback: retain prior image SHA (handoff cites `1803f819` as prior rollback target; current prod observed `5e2ccb9c` this session)
