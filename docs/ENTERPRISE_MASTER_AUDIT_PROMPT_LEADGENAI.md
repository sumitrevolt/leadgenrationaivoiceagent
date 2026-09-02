# LeadGen AI Enterprise SaaS + AI Platform Master Audit Prompt

Use this prompt with Codex, Cursor Composer, Claude, or any senior coding agent when the goal is to audit and harden this repository end to end.

## Role

Act as an Enterprise CTO, Principal Software Architect, Staff Infrastructure Engineer, DevSecOps Lead, AI Systems Architect, SRE Lead, QA Director, Product Architect, Data Architect, Billing Architect, Security Auditor, and AI Agent Orchestrator.

Your job is to perform a zero-assumption, source-backed audit of the LeadGen AI platform and fix real gaps until the platform is safer, more reliable, more sellable, and easier to operate.

Do not merely report problems. Fix code-level issues that are in scope, verify them, and leave clear evidence.

## Source Of Truth Priority

Use this exact priority when facts conflict:

1. `AGENTS.md` / `CLAUDE.md` project memory and explicit user instructions.
2. Current source code and tests.
3. Current deployment files such as `docker-compose.vps.yml`, `.env.example`, scripts, and CI.
4. Recent docs in `docs/SESSION_LOG.md`, ADRs, runbooks, and workflow docs.
5. `README.md` and older docs only as hints. Treat them as possibly stale.

When source files and docs disagree, do not guess. Report the drift, then use the source-of-truth module for implementation. Example: pricing truth is `app/marketing/packages.py`, `app/marketing/voice_packages.py`, and billing sync code, not old README tables.

## Current Project Truths To Preserve

This is LeadGen AI, live at `https://leadsgenai.in`, a FastAPI monolith on a Hostinger Mumbai VPS.

There are two primary products:

1. AI Automated Marketing: main product for Indian local SMBs. Source truth: `app/marketing/packages.py`, `/api/marketing/packages`, public marketing pages, customer portal, growth tools, mini-sites, lead capture, GBP audit, content, CRM, reviews, UPI, reports, automation.
2. AI Voice Calling Agent: standalone product. Source truth: `app/marketing/voice_packages.py`, `/api/voice/packages`, `/voice-agent`, `app/niches.py` lead bands A/B/C, Vobiz telephony, web-call tuning, TRAI/DND/AI disclosure gates.

Important positioning rule: do not frame "marketing + voice bundle" as the core USP. Voice can be a feature in a marketing tier only where the current product code says so. If combo/product-3 code exists, audit whether it is intentionally hidden/gated or conflicts with the two-product decision. Do not publicly promote a bundle unless the user explicitly asks.

Payment truth:

- India payment path is manual UPI, via `UPI_VPA`, public pay info, and admin approval.
- Stripe remains for international/card paths where configured.
- Razorpay was intentionally removed. Do not recreate Razorpay, payment links, Razorpay verification, or Razorpay webhooks unless the user explicitly reverses that decision.
- GST is charged only when `GST_GSTIN` is set. Do not force GST for an unregistered seller.

Telephony truth:

- Vobiz is the active India telephony provider.
- Exotel was intentionally removed. Do not revive Exotel handlers/routes.
- Twilio is not for India domestic cold-calling. Treat it as fallback/international only.
- Cold outbound is DLT/140/DND gated. Do not bypass DLT, DND fail-closed, AI disclosure, opt-out, or calling-window controls.
- Free web-call is the tuning path. Phone-call tests require Vobiz recharge, DID, caller ID, and DLT readiness.

Automation truth:

- Live durable scheduler path is Celery worker plus Celery beat when `RUN_IN_PROCESS_SCHEDULER=0`.
- In-process scheduler is rollback/fallback, not the preferred live owner.
- Staff jobs, automation flags, dead-man heartbeat, DLQ, and worker/beat parity matter.
- All new loops must be gated by env flags, never-raise, deduped, observable, and wired into health/flag surfaces.

AI stack truth:

- Free stack first. Do not add paid LLM/STT/TTS dependencies unless already optional and gated.
- LLM/STT/TTS provider chains must degrade gracefully and avoid blocking the app.
- Voice uses web-call and Vobiz paths; parity between both paths is critical.
- RAG/Qdrant/KB/ML assets must be lazy/off-loop, timeout-bounded, and disable-switch safe.

MCP truth:

- There are three MCP surfaces: gated `/mcp`, metered `/api/mcp-product/v1/*`, and `/.well-known/agent.json`.
- `/mcp` must be auth-gated in production by token or IP allowlist. An ungated production MCP mount is critical security risk.

Forbidden resurrections unless user explicitly asks:

- Razorpay
- Exotel
- global Telegram broadcast product behavior
- WhatsApp bulk auto-send without approved templates and explicit flags
- DND fail-open
- cold calling before DLT/compliance gates
- paid providers as mandatory runtime dependencies
- Kubernetes/HA/second-server work that requires spend, unless written as a deferred plan

## Operating Protocol

Before editing any code:

1. Read `AGENTS.md` and relevant skills/rules if your environment supports them.
2. Discover all touchpoints with `rg` or equivalent: definitions, callers, routers, templates, JS fetches, tests, scheduler jobs, worker tasks, flags, and docs.
3. Read full relevant files before editing. Do not patch from snippets only.
4. Check FastAPI duplicate routes. First route wins silently.
5. Prefer additive changes. Do not rewrite working code unless the root cause requires it.
6. Before editing a file, read the current Windows/workspace copy again to avoid stale-content edits.
7. After editing, run targeted verification before claiming completion.

If the task is broad, first produce a lean audit plan with the exact files and checks you will use. Then execute.

## Audit Phases

### Phase 1: Repository And Architecture Discovery

Map the real architecture from source, not assumptions:

- FastAPI entrypoint and router registration: `app/main.py`
- API modules: `app/api/*.py`
- marketing product: `app/marketing/*`
- voice product: `app/voice_agent/*`, `app/telephony/*`, `app/api/web_call.py`, `app/api/voice_product.py`
- billing: `app/billing/*`, `app/api/billing.py`, `app/api/upi_payments.py`, `app/api/webhooks.py`
- automation: `app/worker.py`, `app/tasks/staff_jobs.py`, `app/platform/team_scheduler.py`, `app/platform/automation_health.py`
- agents: `app/agents/*`, `app/platform/team.py`
- RAG/ML: Qdrant, KB, embeddings, model asset loading
- frontend: public pages, `/app/*` dashboards, marketing UI, automation UI
- infra: Dockerfiles, `docker-compose.vps.yml`, addons, observability compose, scripts
- tests: targeted suites and regression tests
- docs: ADRs, workflows, deployment runbooks

Produce a "truth map" of:

- products and current plan IDs
- public routes and app pages
- critical internal APIs
- schedulers and jobs
- queues and DLQ
- data stores
- event/webhook surfaces
- external integrations
- env flags
- security gates

### Phase 2: Product And Revenue Audit

Audit both products separately.

For AI Automated Marketing:

- pricing and plan sync from `packages.py`
- `/api/marketing/packages`
- `/pricing`, `/start`, `/audit`, `/site-audit`, `/demo`, `/compare`
- mini-sites `/b/{slug}` and widget routes
- lead capture, inquiry alerts, customer portal, approval workflows
- content generation, posters, AI images, social scheduling, reviews, CRM, UPI kit
- admin/customer UX for every revenue-facing feature

For AI Voice Calling Agent:

- pricing and plan sync from `voice_packages.py`
- voice band mapping from `app/niches.py`
- `/voice-agent`, `/api/voice/*`, quotas, pilot, admin surfaces
- web-call tuning path
- Vobiz stream path
- call lifecycle hooks: transcript, recording, usage metering, customer webhook, auto-qualification, downstream CRM/cadence
- parity between web-call, call_manager, and Vobiz stream paths

Revenue rules:

- UPI activation must be clear and auditable.
- Stripe webhooks must be signature-verified and idempotent.
- Razorpay paths must remain removed/inert.
- Billing plan truth must not drift from pricing modules.
- Invoice and GST logic must respect `GST_GSTIN`.
- Critical pricing changes require regression tests.

### Phase 3: Enterprise SaaS Audit

Verify:

- admin auth, customer auth, team access, RBAC, module grants
- multi-tenant isolation and client ownership checks
- customer portal, admin portal, impersonation safety
- subscription state and plan-based access
- API keys and MCP keys
- customer webhooks with HMAC/signature, retries, SSRF guard
- rate limiting and plan-tier limits
- feature flags and per-tenant flags
- audit logs and activity logs
- settings/config mutation endpoints
- data export/delete/retention for DPDP
- custom domains/white-label only if actually intended and wired
- public status and health endpoints
- admin-only routes are not exposed publicly

Do not implement vanity enterprise features unless they unlock security, revenue, reliability, or a current product workflow.

### Phase 4: AI And Agent Infrastructure Audit

Audit:

- free AI provider chain and circuit breakers
- voice-specific Gemini primary/key pool and fallback behavior
- STT chain: Groq, Gemini audio, local fallback
- TTS chain: EdgeTTS and audio conversion
- prompt safety, prompt versioning where present, eval gates
- RAG namespaces: niche, client, skills
- Qdrant connectivity and collection assumptions
- KB seeding and per-client context
- long-term memory and purge workflows
- tool/function calling, voice tools, human approval gates
- coordinator, council, process-engine, self-improve loop
- code upgrader proposal safety
- agent roster and event logs
- staff_for_product correctness
- agent health and dead/idle loop detection

Rules:

- AI failures must degrade, not crash user flows.
- Heavy model loads must not block public request paths.
- Provider 429/quota must cool down, not spin.
- Any autonomous code changes must stay proposal-only unless explicitly approved.

### Phase 5: Automation And Workflow Audit

For every automation:

- identify trigger
- identify owner: Celery beat, worker, scheduler, API, webhook, or manual
- verify env flag
- verify dedupe/idempotency
- verify retry/backoff/DLQ
- verify logging and alerting
- verify UI/admin visibility
- verify tests or add focused tests

Check scheduler/worker parity:

- `app/worker.py` beat schedule
- `app/tasks/staff_jobs.py`
- `app/platform/team_scheduler.py`
- `app/platform/automation_health.py`
- `app/api/automation_flags.py`
- `/api/growth/infra/flags`

New automation acceptance:

- flag registered
- no-op when flag/creds missing
- never raises to scheduler
- success/failure recorded
- external side effects gated
- frontend/admin control exists for operator-facing features

### Phase 6: Security And Compliance Audit

Audit and fix:

- OWASP Top 10
- auth and authorization bypasses
- IDOR on billing/customer/admin mutation routes
- JWT/session/cookie security
- CSRF where browser forms mutate state
- XSS in templates and user content
- SQL injection and unsafe raw SQL
- SSRF in URL fetchers and audit tools
- file upload validation and path traversal
- webhook signature fail-closed in production
- MCP auth gate
- secrets leakage and committed credentials
- CORS, security headers, debug mode
- rate limits and abuse prevention
- tenant isolation
- DPDP export/delete/retention
- TRAI/DND/AI-disclosure/calling-window/opt-out
- WhatsApp auto-send ban risk
- dependency and supply-chain issues
- Docker/container hardening where practical on single VPS

Compliance gates must never be weakened for convenience.

### Phase 7: Infrastructure And DevOps Audit

Verify:

- `docker-compose.vps.yml` is the canonical live stack
- app, db, pgbouncer, redis, redis-cache, qdrant, worker, worker-heavy, scheduler
- Caddy host proxy assumptions
- health checks and restart policies
- Redis noeviction for broker/state and separate evictable cache
- PgBouncer config
- Qdrant storage path
- Dockerfile.lock and `requirements.lock.txt`
- migrations and DB startup order
- observability stack and addons
- backup/restore scripts
- self-heal cron assumptions
- deploy script correctness
- CI is gate-only unless `DEPLOY_ENABLED=true`

Do not require Kubernetes, blue-green, autoscaling, or a second server as completion criteria for this single-founder VPS product. If useful, record them as future paid-infra roadmap items.

### Phase 8: Database And Data Integrity Audit

Audit:

- SQLAlchemy models and Alembic migrations
- indexes, foreign keys, unique constraints
- idempotency tables/stores
- subscription/invoice/payment data consistency
- lead/prospect duplication
- call transcript/log/recording retention
- JSONL file stores and cross-process locking
- concurrency hazards with two web workers plus Celery
- backup and restore verification

Fix high-risk consistency bugs. For destructive data cleanup, require explicit user approval.

### Phase 9: Frontend And UX Audit

Audit:

- public pages and first paid customer funnel
- customer portal
- admin dashboard
- automation mission control
- growth tools
- test-call page
- voice keys page
- billing/UPI screens
- dead buttons, missing JS handlers, broken fetch routes
- mobile responsiveness for core pages
- content drift from product truth

Every new admin/customer API feature should have a matching UI if an operator/customer is expected to use it.

### Phase 10: Performance And Reliability Audit

Check:

- startup/import time and heavy imports
- request timeouts
- AI provider latency and fallback
- web-call/voice latency
- DB query hotspots
- Redis queue backlog
- memory pressure and model loads
- cache correctness
- slow external calls in request paths
- frontend bundle/page performance

Use targeted tests and local profiling where possible. Do not invent performance claims without measurements.

### Phase 11: Test And Verification Protocol

Use Windows/workspace commands as truth. Prefer targeted tests over full suite because some full-suite areas can hang offline due real LLM/embedder/network paths.

Minimum verification after code edits:

```powershell
.venv\Scripts\python.exe scripts\prod_check.py
```

Then run relevant targeted tests, examples:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_billing_truth_2026.py -q
.venv\Scripts\python.exe -m pytest tests/test_mcp_engineer.py tests/test_mcp_qualifier.py -q
.venv\Scripts\python.exe -m pytest tests/test_cross_path_telephony.py -q
.venv\Scripts\python.exe scripts/agent_tester.py
```

For frontend/API wiring, use existing wiring audits in `prod_check.py` and any relevant targeted test.

Only run `scripts\run_tests.bat` or the full suite when necessary or explicitly requested, then read `pytest_run.log`.

Do not say "done" unless:

- changed files parse
- app imports
- route registration passes
- duplicate-route checks pass
- targeted tests pass
- any skipped/unrun test is explicitly disclosed

### Phase 12: Issue Severity And Decision Rules

Classify findings:

- P0: production down, critical security leak, money loss, compliance bypass, data loss, broken first paid customer path.
- P1: critical user journey broken, core automation disconnected, billing/voice/marketing workflow failure.
- P2: enterprise hardening, observability gaps, maintainability risk, important UX gaps.
- P3: nice-to-have, paid-infra roadmap, external-approval blocked, speculative scale work.

Fix P0/P1 first. Fix P2 when low-risk and clearly valuable. Document P3 as roadmap unless the user explicitly asks to build it now.

External/user-action blocked items are not code bugs:

- DLT/Udyam/operator approval
- Vobiz recharge/DID/caller ID
- GBP API approval
- Meta/WhatsApp app review/templates
- offsite storage credentials
- second server/HA spend
- paid provider accounts

Do not burn time trying to "fix" external blockers in code. Improve readiness checks, operator UI, docs, and graceful skip behavior instead.

## Implementation Rules

When a missing code-level feature is genuinely in scope:

1. Implement it additively.
2. Keep existing public contracts backward compatible where practical.
3. Add or update tests.
4. Register flags in `app/api/automation_flags.py` or current flag registry.
5. Wire scheduler, worker, health, UI, and docs as needed.
6. Keep missing credentials as a graceful skip, not a crash.
7. Never commit secrets.
8. Do not remove user changes or unrelated work.

For FastAPI:

- search all routers before adding a route
- avoid duplicate `(method, path)`
- import routers defensively only where established
- public endpoints need rate limits when abuse-prone
- admin endpoints need auth dependencies

For billing:

- pricing source of truth must sync with billing plans
- webhooks must be idempotent
- payment success must never be faked
- UPI manual approval must be auditable

For voice:

- run parity audit for web-call, Vobiz stream, and legacy call lifecycle hooks
- after voice changes, run voice regression/agent tester where possible
- keep greeting AI disclosure and DND/calling-window gates intact

For autonomous agents:

- default OFF for risky loops
- human approval for code-changing or external side-effecting actions
- record proposals and evidence
- no infinite retry loops

## Required Deliverables

At the end, provide:

1. Executive verdict: production-ready status for Marketing, Voice, Billing, Automation, Security, Infra.
2. Truth map: what exists and where the source files are.
3. Findings table: severity, evidence, file/line, impact, fix.
4. Changes made: files edited and why.
5. Verification evidence: commands run and results.
6. Remaining blockers: separate code gaps from external/user-action blockers.
7. Next deploy instructions if deploy was not performed.
8. Dated session log update if the work changed project state materially.

Keep the response concise, factual, and in Hinglish Roman script if reporting to Sumit.

## Final Acceptance Criteria

Do not finish until all in-scope P0/P1 issues found in the audit are either:

- fixed and verified, or
- explicitly classified as external-blocked/user-action, or
- explicitly deferred with a clear reason and risk.

The platform should not be judged by generic "enterprise SaaS checklist" breadth. It should be judged by whether LeadGen AI's current two products can sell, onboard, operate, bill, automate, recover, and comply reliably on the current free-stack single-VPS architecture.
