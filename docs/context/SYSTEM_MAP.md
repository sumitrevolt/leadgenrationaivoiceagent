# SYSTEM_MAP — operational domain boundaries

Only entrypoints that matter for operators/agents. Not a full file inventory.

## Authentication and authorization
- Purpose: Admin JWT + customer portal auth; fail-closed on admin destructive paths
- Entry: `app/api/auth_deps.py`, `/app/login`, customer portal routes
- Main files: `auth_deps.py`, `customer_auth.py`
- Storage: tokens / sessions per existing auth stack
- Owner: platform
- Tests: auth-related suites under `tests/`
- Risks: IDOR if client_id taken from body instead of token

## Canonical tenant identity
- Purpose: billing/login hex id ↔ marketing slug (`jiya-makeover`)
- Entry: `clients_store.canonical_client_id` / `resolve_client`
- Main files: `app/marketing/clients_store.py`, `customer_auth.py`, `product_one_delivery.py`
- Storage: `data/marketing_clients.jsonl` + Postgres clients
- Owner: marketing delivery
- Tests: `tests/test_client_identity_canonicalization_2026.py`
- Risks: raw billing id on portal = orphan drafts (ADR-123)

## Customer portal
- Purpose: customer self-serve content/delivery progress
- Entry: `/portal/*`, `/api/customer/*`
- Main files: `customer_auth.py`, `customer_dashboard*.py`, `customer_marketing_studio.py`
- Owner: product
- Risks: delivery% mislabel, studio entitlement gate

## Admin dashboard and control plane
- Purpose: delivery cockpit, clients 360, Mission Control, Owner OS
- Entry: `/api/admin/*`, `/app/automation`, `/app/office`, delivery command center
- Main files: `admin_dashboard.py`, `owner_os.py`, `frontend/delivery_command_center.html`
- Owner: ops / Sumit
- Tests: delivery cockpit / admin panel static guards
- Risks: blank Mission Control from JS syntax artifacts

## Agent OS
- Purpose: 31-agent registry + shared runtime (pilots)
- Entry: `AGENT_RUNTIME`, `/api/admin/owner-os/runtime`
- Main files: `agent_registry.py`, `agent_runtime.py`, `agent_runtime_pilots.py`, `team.py`
- Queue: `agent_task_queue` + file DLQ
- Owner: Agent-OS
- Tests: `test_agent_registry.py`, `test_agent_runtime.py`, `test_owner_os.py`
- Risks: Phase-C scheduler not converged; RED lane must stay hard-off for Swara

## OmniRoute model routing
- Purpose: free-stack LLM routing / quotas (dev control + product LLM chain)
- Entry: OmniRoute MCP / `free_ai.py` chain
- Owner: platform LLM
- Risks: 429 storms if coordinator uncapped

## Celery and scheduler
- Purpose: durable staff jobs
- Entry: `team_scheduler.py`, `worker.py`, beat profile celery
- Storage: Redis celery queues + `data/job_heartbeats.json`
- Owner: Kavya / ops
- Tests: automation health suites
- Risks: wrong compose file; queue backlog without ntfy

## Content generation
- Purpose: drafts for customers (auto_content, niche packs, GBP/review)
- Entry: content jobs, studio tools
- Main files: `auto_content.py`, studio routes
- Owner: Isha / content agents
- Risks: free-LLM quota; caption banlist

## Approval and publishing
- Purpose: HITL approve → schedule/publish
- Entry: content_approval, social_engine, Postiz
- Owner: Zara (publish) / human approve
- Risks: WhatsApp auto-send OFF; customer Meta Advanced Access

## Lead and CRM flows
- Purpose: inquiry → Hot Queue → outreach
- Entry: `/api/public/inquiry`, reply triage, prospect jobs
- Owner: growth
- Risks: email 25/day cap; ntfy for speed-to-lead

## Customer delivery matrix
- Purpose: 10 deliverables + health + assurance scan
- Entry: `product_one_delivery`, `customer_delivery`, `delivery_assurance`, delivery ledger
- Storage: content_queue + delivery_ledger + DB customer_deliverables
- Queue: `product_one_health` hourly
- Owner: nikhil (assurance) + delivery ops
- Tests: `test_delivery_assurance.py`, product_one delivery suites
- Risks: undeployed assurance; proof blocked externally

## Billing and entitlements
- Purpose: packages, UPI, Stripe intl, invoices
- Entry: `packages.py`, UPI routes, subscription sync
- Owner: billing
- Tests: `test_billing_truth_2026.py`
- Risks: Growth ₹2999 legacy hidden; never fake paid

## Notifications
- Purpose: email + ntfy + WA 1-click
- Entry: `lead_alerts`, `ntfy`, automation_health alerts
- Owner: ops
- Risks: ntfy no-op if URL/topic unset

## Observability
- Purpose: Sentry, Prometheus stack, health
- Entry: `/health`, Sentry ARMED
- Owner: SRE personas
- Risks: causal-claim discipline on error absence

## Deployment
- Purpose: Hostinger VPS Mumbai single-node
- Entry: `scripts/deploy_vps.sh` + `APP_VERSION=<sha>` + `docker-compose.vps.yml`
- Owner: deploy operator
- Risks: `:latest` skew; wrong compose file = 502
