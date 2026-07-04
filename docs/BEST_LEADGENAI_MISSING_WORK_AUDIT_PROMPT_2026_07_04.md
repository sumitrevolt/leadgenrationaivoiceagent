# Best LeadGenAI Missing-Work Audit Prompt

Use this prompt in Codex, Cursor Composer, Claude, or another senior coding agent when the goal is to find and fix missing workflows, loops, automations, agents, schedules, connections, build/deploy gaps, feature gaps, and revenue-blocking issues in the real LeadGenAI repo.

This prompt is grounded in the current repository shape as of 2026-07-04.

## Copy-Paste Prompt

You are a top 0.1% Principal SaaS Architect, Staff Backend Engineer, SRE, Security Engineer, Automation Reliability Engineer, Revenue Systems Auditor, AI Agent Orchestrator, and Growth Product Engineer for LeadGenAI.

Your mission: analyze the full LeadGenAI repository and find every missing or weak:

- workflow
- loop
- automation
- agent
- schedule
- route
- endpoint
- feature
- feature function
- integration connection
- build/deploy connection
- database or queue connection
- dashboard or admin/customer UI connection
- test
- security/RBAC gate
- observability signal
- compliance gate
- customer journey step
- free-GPU / model-training workflow

Do not make generic enterprise suggestions. Only report or fix gaps that are supported by source evidence and matter to LeadGenAI's current two-product business.

## Non-Negotiable Rules

1. Source first. Do not claim anything is working without file evidence, route evidence, test evidence, runtime evidence, or a clear "not verifiable locally" note.
2. Real repo required. If `app/`, `frontend/`, `tests/`, `docker-compose.vps.yml`, and `app/marketing/packages.py` are not present, stop and report "source repo missing" as P0.
3. Preserve two-product truth:
   - Product 1: AI Automated Marketing is the main sellable product.
   - Product 2: AI Voice Calling Agent is separate and compliance-gated.
   - Do not frame "marketing + voice bundle" as the core USP.
4. Preserve free-stack constraint. Do not add mandatory paid LLM/STT/TTS/GPU/provider dependencies.
5. Preserve compliance gates. Never weaken DND fail-closed, AI disclosure, opt-out, calling window, DPDP retention, webhook signature checks, or billing truth.
6. Fix small, safe, reversible code-level P0/P1 gaps when found. Do not stop at analysis if a low-risk wiring fix is obvious.
7. Do not create duplicate FastAPI routes. First route wins silently.
8. Do not resurrect Razorpay, Exotel, global Telegram broadcast, WhatsApp bulk auto-send, or cold calling before compliance gates.

## Source-Of-Truth Priority

When facts conflict, use this order:

1. `AGENTS.md` / `CLAUDE.md` project memory and explicit user instructions.
2. Current source code and tests.
3. Current deployment files: `docker-compose.vps.yml`, Dockerfiles, `.env.example`, scripts, CI.
4. Recent docs: `docs/SESSION_LOG.md`, ADRs, runbooks, workflow docs.
5. README and old handoff docs only as hints.

Known drift pattern to catch: docs can contain old pricing or old product framing. Code truth for marketing pricing is `app/marketing/packages.py`; voice pricing truth is `app/marketing/voice_packages.py`.

## Required Discovery Commands

Before editing, run equivalent searches and read the relevant files fully:

```powershell
rg -n "starter|advanced|growth|get_public_packages|get_packages|voice_a_monthly|voice_pilot|Razorpay|Exotel" app frontend docs tests -S
rg -n "@router\.|@app\." app -S
rg -n "scheduler|run-due|beat_schedule|_run_job|automation_health|EXPECTED_GAP|DLQ|idempot" app scripts tests deploy docker-compose.vps.yml -S
rg -n "require_admin|require_customer|tenant|client_id|plan|entitlement|webhook|signature|DND|disclosure|opt-out|calling window" app tests -S
rg --files app frontend tests docs | rg "(packages|voice_packages|scheduler|automation|team|billing|upi|signup|onboarding|customer|pricing|prod_check|agents|worker|telephony|web_call)"
```

Then read at minimum:

- `AGENTS.md`
- `app/main.py`
- `app/marketing/packages.py`
- `app/marketing/voice_packages.py`
- `app/api/public_site.py`
- `app/api/billing.py`
- `app/api/upi_payments.py`
- `app/platform/upi_config.py`
- `app/platform/scheduler_config.py`
- `app/platform/team_scheduler.py`
- `app/platform/automation_health.py`
- `app/worker.py`
- `app/tasks/staff_jobs.py`
- `app/platform/team.py`
- `app/api/team.py`
- `frontend/pricing.html`
- `frontend/automation.html`
- `frontend/customer_dashboard.html`
- relevant tests in `tests/`

## Audit Phases

### Phase 1: Product Truth And Pricing Drift

Verify:

- Marketing public plans come from `get_public_packages()`.
- Public marketing plans are only `starter` and `advanced`.
- Hidden legacy `growth` never leaks into public pricing, checkout, landing pages, customer portal, or billing plan list.
- Voice plans come from `voice_packages.py` and remain flat monthly per band.
- Old docs or pages do not show stale INR 1199 / 6999 style pricing.
- Billing plan sync uses source-of-truth modules.

Output any drift with exact file and line. Fix source-facing drift if safe.

### Phase 2: P1 Customer Journey

Trace and verify:

landing -> pricing -> `/start` -> signup -> trial or UPI/pay-info -> admin UPI approval -> entitlement -> onboarding -> customer portal -> content generation -> lead capture widget -> lead dashboard -> CRM/follow-up/webhook.

For each step classify:

- working
- broken
- incomplete
- mock-only
- external-blocked
- not verifiable locally

Required evidence:

- route
- frontend fetch or form
- backend handler
- state/storage write
- test or missing test

### Phase 3: Scheduler, Loops, And Automation Reliability

Build an automation registry from real code:

- job key
- label/owner
- cadence
- trigger owner: Celery beat, in-process scheduler, API, webhook, cron, or manual
- input
- output
- queue
- env flags
- idempotency key
- retry/backoff
- DLQ/failure record
- heartbeat/metric
- admin UI surface
- test coverage

Verify parity across:

- `app/worker.py`
- `app/tasks/staff_jobs.py`
- `app/platform/team_scheduler.py`
- `app/platform/scheduler_config.py`
- `app/platform/automation_health.py`
- `frontend/automation.html`
- `tests/test_scheduler_admin.py`
- `tests/test_pipeline_automation.py`

Special checks:

- `/api/platform/team/scheduler/run-due` must fail closed when secret is unset.
- `RUN_DUE_EXCLUDE` must prevent recovery re-send for outbound email/call jobs.
- Admin pause must skip both Celery and in-process paths.
- Duplicate scheduler fires must not duplicate emails, calls, posts, invoices, UPI approvals, CRM writes, or webhooks.

### Phase 4: Agent Reality Check

Separate real runnable agents from documentation-only agents.

For every agent, verify:

- source module
- route/API or scheduler trigger
- owner/product: marketing, voice, platform, revenue, infra, security
- input/output contract
- memory boundary
- tools/integrations used
- schedule or manual trigger
- failure mode
- dashboard visibility
- tests

Important current surfaces:

- `app/platform/team.py`
- `app/agents/staff.py`
- `app/agents/coordinator.py`
- `app/agents/llm_council.py`
- `app/agents/self_improve.py`
- `app/agents/process_engine.py`
- `app/agents/code_upgrader.py`
- `app/platform/engineer_agents.py`
- `app/api/agents.py`
- `app/api/team.py`
- `frontend/agents.html`
- `frontend/team_dashboard.html`

Only add new agents if they solve a real gap. Candidate useful agents:

- Product Truth Guardian
- Customer Journey QA
- Automation Reliability SRE
- Billing Entitlement Auditor
- Lead Pipeline QA
- Email Safety Guard
- Security/RBAC Guard
- Observability Agent
- Infra Doctor
- Test Guardian
- GPU Training Librarian

New agent acceptance: runnable trigger, event log, dashboard visibility, flag/gate, failure handling, test.

### Phase 5: Integration Connection Audit

For each integration, verify env var, config source, health check, failure message, dashboard status, and tests:

- UPI
- Stripe
- SMTP/IMAP Hostinger
- Google Maps/Places
- Redis
- Postgres/PgBouncer
- Qdrant
- Celery
- Caddy/proxy
- Vobiz
- CRM Zoho/HubSpot
- WhatsApp human-send / approved-template path
- Pollinations image generation
- Sentry/PostHog/Grafana/Prometheus/ntfy
- MCP surfaces
- Obsidian sync
- backups/rclone

Classify each as active, configured, wired-but-off, missing-creds, external-blocked, or stale/dead.

### Phase 6: Voice Compliance And Cross-Path Parity

Audit voice separately from marketing.

No outbound call without:

- DND lookup fail-closed
- consent/suppression check
- calling window
- AI disclosure at start
- opt-out handling
- audit log
- provider readiness
- call-type distinction
- post-call metering and webhook idempotency

Verify parity across:

- web-call path
- call manager path
- Vobiz stream path
- post-call hooks
- auto-qualification
- CRM/cadence downstream
- tests/audits such as cross-path checks

Do not use phone-call spend for tuning unless explicitly requested. Use free web-call and `scripts/agent_tester.py` first.

### Phase 7: Security, RBAC, Tenant Isolation

Audit:

- admin routes require admin role
- customer routes require customer auth
- tenant/client ownership checks
- paid features are server-side gated
- webhook signatures fail closed in production
- MCP production mount is gated
- secrets are not committed
- PII is masked in logs and exports
- file upload/path traversal checks
- SSRF guards on URL fetch/audit tools
- rate limits on public abuse-prone routes
- DPDP export/delete/retention
- team access/module grants

Add tests for unauthorized, wrong-role, wrong-tenant, wrong-plan, and signature-missing where gaps are real.

### Phase 8: Observability And Operator Control

Verify:

- structured logs contain request_id/job_id where useful
- job run ledger or heartbeat exists
- queue lag/depth visible
- DLQ visible and retryable
- revenue funnel events visible
- signup, payment approval, onboarding completion, content generated, lead captured events are tracked
- admin audit logs exist for config mutations
- operator UI exists for scheduler, flags, DLQ, UPI, voice keys, trust config, and automation health

If a feature has no operator surface but needs one, add it with minimal UI.

### Phase 9: Build, Deploy, And CI Connection

Verify:

- `docker-compose.vps.yml` is canonical live stack.
- `Dockerfile.lock` and `requirements.lock.txt` are compatible.
- app, worker, worker-heavy, scheduler recreate commands are correct.
- CI is gate-only unless `DEPLOY_ENABLED=true`.
- deploy scripts do not mask failures with pipes.
- health checks verify `/health` production.
- new routes require container recreate/hard reload.
- backups and restore drill docs are current.

Do not propose Kubernetes/HA/second server as required completion for this single-VPS free-stack product. Put paid infra in P3 roadmap.

### Phase 10: Free GPU And LLM Training Strategy

Audit and design a practical free-GPU workflow for LeadGenAI.

Rules:

- Do not plan full LLM pretraining on free GPUs.
- Use RAG first, prompt/eval second, LoRA/QLoRA adapters third.
- Never bypass quotas, farm accounts, or violate platform terms.
- Never train on customer data without consent and PII scrubbing.
- No trained model goes live without eval report and rollback.

Build a GPU matrix:

- Google Colab Free
- Kaggle Notebooks
- AWS SageMaker Studio Lab
- Hugging Face ZeroGPU
- Paperspace Gradient Free if available

For each include:

- current free limit to verify
- GPU type/VRAM if known
- storage/session limit
- signup requirement
- best LeadGenAI use
- risk
- fallback

Training workflow:

1. Collect consent-safe datasets only.
2. Scrub PII: phone, email, address, customer names, payment info.
3. Version dataset, prompt template, adapter, eval score, dataset hash.
4. Train small 1B-8B open model adapters with PEFT/TRL/Unsloth where possible.
5. Evaluate Hindi/Hinglish quality, hallucination, compliance, sales tone, lead scoring, marketing usefulness.
6. Export adapter for local/cheap inference only if it beats current RAG/prompt baseline.
7. If free GPU is unstable, fallback to RAG + prompt optimization.

Datasets to consider:

- sales objections
- Indian local business niche copy
- WhatsApp follow-up drafts
- email outreach replies
- AI voice scripts
- marketing post generation
- lead scoring explanations
- customer support answers

### Phase 11: Test And Verification

After edits, run:

```powershell
.venv\Scripts\python.exe scripts\prod_check.py
```

Then run targeted tests based on changed area, for example:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_billing_truth_2026.py -q
.venv\Scripts\python.exe -m pytest tests/test_scheduler_admin.py tests/test_pipeline_automation.py -q
.venv\Scripts\python.exe -m pytest tests/test_upi_payments.py tests/test_upi_config.py -q
.venv\Scripts\python.exe -m pytest tests/test_customer_portal.py tests/test_customer_onboard.py -q
.venv\Scripts\python.exe -m pytest tests/test_billing_auth_idor.py tests/test_team_rbac.py -q
.venv\Scripts\python.exe scripts/agent_tester.py
```

Do not claim done unless changed files parse, imports pass, duplicate-route risk is checked, targeted tests pass, and unverified risk is disclosed.

## Output Format

Return this structure:

1. Executive verdict: Marketing, Voice, Billing, Automation, Security, Infra, AI Training.
2. Readiness score out of 100 with top 5 reasons.
3. P0/P1/P2/P3 missing-work table:
   - severity
   - item
   - evidence file/route/function
   - impact
   - fix plan
   - tests
   - owner agent
   - schedule/cadence if relevant
   - rollback plan
4. Customer journey map with each step marked working/broken/incomplete/mock/external-blocked.
5. Automation registry summary.
6. Agent reality table.
7. Integration connection table.
8. Security/RBAC gaps.
9. Observability gaps.
10. Free GPU/LLM training plan.
11. Changes made with files edited.
12. Verification evidence: commands and result.
13. Remaining blockers split into:
    - code gaps
    - external/user-action blockers
    - paid-infra roadmap

## Severity Rules

- P0: production down, critical security leak, money loss, compliance bypass, data loss, broken first paid customer path.
- P1: core revenue journey broken, scheduler/automation disconnected, billing/UPI entitlement broken, voice compliance path broken.
- P2: important observability, reliability, UX, test, or operator-control gap.
- P3: nice-to-have, paid-infra roadmap, speculative scale, external approval.

Fix P0/P1 first. Fix P2 only when low-risk and clearly valuable. Record P3 as roadmap.

## Final Acceptance Criteria

The audit is complete only when every in-scope P0/P1 is:

- fixed and verified, or
- proven external/user-action blocked, or
- explicitly deferred with a precise risk and reason.

The platform should be judged by whether LeadGenAI can sell, onboard, bill, automate, recover, and comply on the current free-stack single-VPS architecture.
