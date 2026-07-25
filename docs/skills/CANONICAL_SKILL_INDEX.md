# Canonical Skill Index

> **Current policy (ADR-131):** the single canonical tracked skill root is **`.claude/skills`**.
> `.agents/skills` is **removed** from Git and is not an active canonical registry.
> Documentation and routing support ONLY. This index confers **no runtime authority**:
> nothing dispatches from it, and Owner OS remains the sole execution authority.
>
> **Edit ownership:** edit under `.claude/skills/<skill>/` first. Do not recreate
> `.agents/skills` as a second registry. Runtime loader (`app/platform/skill_pack.py`)
> reads `.claude/skills` only. Additional bind-mounted extras may live under
> `data/skills_extra` (runtime source, not a second canonical tree).
>
> CI guard: `tests/test_skill_tree_canonical_guard.py`.

## Historical measurement (pre-ADR-131) — label: HISTORICAL

> The table below was measured at main `9c1bb30` on 2026-07-21, **before** Phase 12
> consolidation. It is retained only as audit evidence of the former dual-tree state.
> It does **not** describe current repository truth and must not be used as a routing
> recommendation.

| Metric (at `9c1bb30`, HISTORICAL) | Value |
|---|---|
| Distinct skill names | 208 |
| Present in BOTH trees, byte-identical | **184** |
| Shared name but diverged content | **0** |
| `.claude/skills` only | 1 |
| `.agents/skills` only | 23 |
| Tracked files `.claude/skills` | 403 |
| Tracked files `.agents/skills` | 446 |

### Historical note: junction overlay was LOCAL-ONLY

At that time, some workstation checkouts used Windows directory junctions from
`.claude/skills/` into `.agents/skills/`. Git did not store junctions — it stored
both trees in full, so clones carried real duplicates. That topology is obsolete
after ADR-131 consolidation.

## Current state (post-ADR-131)

| Metric | Value |
|---|---|
| Canonical root | `.claude/skills` |
| Legacy root `.agents/skills` | **absent** (removed) |
| Canonical project skills (`SKILL.md`) | 208 |
| Duplicate skill ids in canonical root | 0 |
| Policy ADR | `docs/adr/ADR-131-canonical-skill-registry.md` |

## Consolidation status

Phase 12 consolidation **is complete** on `main` (ADR-131). The 23 skills that were
unique to `.agents/skills` were merged into `.claude/skills`; the duplicate tree was
removed. This index lists **current** canonical paths only. There is no active
generator or sync workflow that recreates `.agents/skills`.

## Index

| Skill | Canonical path | Status | Purpose |
|---|---|---|---|
| `a2z-launch-enterprise-audit` | `.claude/skills/a2z-launch-enterprise-audit` | canonical (ADR-131) | LeadGen "A-to-Z Launch & Enterprise Audit" master prompt â€” does NOT stop at audit. Drives Discover â†’ Verif... |
| `ab-testing` | `.claude/skills/ab-testing` | canonical (ADR-131) | When the user wants to plan, design, or implement an A/B test or experiment, or build a growth experimentation... |
| `ad-creative` | `.claude/skills/ad-creative` | canonical (ADR-131) | "When the user wants to generate, iterate, or scale ad creative â€” headlines, descriptions, primary text, or ... |
| `admin-friendly-ux` | `.claude/skills/admin-friendly-ux` | canonical (ADR-131) | Admin/customer dashboards ko non-technical-friendly banane ka pattern â€” plain-Hinglish aggregator endpoint +... |
| `ads` | `.claude/skills/ads` | canonical (ADR-131) | "When the user wants help with paid advertising campaigns on Google Ads, Meta (Facebook/Instagram), LinkedIn, ... |
| `advancement-roadmap` | `.claude/skills/advancement-roadmap` | canonical (ADR-131) | LeadGen AI 2026 advancement backlog â€” web-researched, codebase-aware, free-stack. Use when user bole "advanc... |
| `agentkits-marketing-automation` | `.claude/skills/agentkits-marketing-automation` | canonical (ADR-131) | Enterprise AI marketing automation toolkit with 18 agents, 93 commands, and 28 skills for campaign planning, c... |
| `agent-loop-design` | `.claude/skills/agent-loop-design` | canonical (ADR-131) | Naya ALWAYS-ON / recurring agent loop design karne ka generalized pattern â€” self_improve/growth-pulse/proces... |
| `agent-sdk` | `.claude/skills/agent-sdk` | canonical (ADR-131) | Build and verify Python or TypeScript Agent SDK applications. Use when creating agent apps with Claude/OpenAI ... |
| `ai-seo` | `.claude/skills/ai-seo` | canonical (ADR-131) | "When the user wants to optimize content for AI search engines, get cited by LLMs, or appear in AI-generated a... |
| `analytics` | `.claude/skills/analytics` | canonical (ADR-131) | When the user wants to set up, improve, or audit analytics tracking and measurement. Also use when the user me... |
| `api-design` | `.claude/skills/api-design` | canonical (ADR-131) | FastAPI route/endpoint design discipline for the LeadGen AI platform â€” grep-first (no duplicate routes), add... |
| `api-design-principles` | `.claude/skills/api-design-principles` | canonical (ADR-131) | Master REST and GraphQL API design principles to build intuitive, scalable, and maintainable APIs that delight... |
| `architecture-patterns` | `.claude/skills/architecture-patterns` | canonical (ADR-131) | Implement proven backend architecture patterns including Clean Architecture, Hexagonal Architecture, and Domai... |
| `audit-automation` | `.claude/skills/audit-automation` | canonical (ADR-131) | Health-check the automation loops without reading code â€” heartbeat/alive, daily cost vs cap, approvals backl... |
| `automate` | `.claude/skills/automate` | canonical (ADR-131) | Set up recurring automation for LeadGen â€” Celery beat jobs, cron on VPS, or Cursor Automations when in Curso... |
| `automation-control-center` | `.claude/skills/automation-control-center` | canonical (ADR-131) | Upgrade/extend the /app/automation Mission Control so it stays the SINGLE advanced cockpit for all automation ... |
| `automation-flags` | `.claude/skills/automation-flags` | canonical (ADR-131) | The gated env-flag catalog for LeadGen AI automation engines â€” what each flag does, ban/cost risk, and the s... |
| `automation-pipeline` | `.claude/skills/automation-pipeline` | canonical (ADR-131) | Operate LeadGen AI's end-to-end automated growth pipeline â€” scrape â†’ score â†’ email outreach â†’ reply-tr... |
| `babysit` | `.claude/skills/babysit` | canonical (ADR-131) | Keep a PR merge-ready by triaging comments, resolving conflicts, and fixing CI in a loop. Use when user says b... |
| `backend-rbac` | `.claude/skills/backend-rbac` | canonical (ADR-131) | LeadGen AI ka roles + module-grants access-control + admin-side auth features. Use jab "sub admin", "team memb... |
| `brainstorming` | `.claude/skills/brainstorming` | canonical (ADR-131) | "You MUST use this before any creative work - creating features, building components, adding functionality, or... |
| `canvas` | `.claude/skills/canvas` | canonical (ADR-131) | Produce standalone visual analytical artifacts. In Cursor IDE use .canvas.tsx; in Claude Code use structured m... |
| `careful` | `.claude/skills/careful` | canonical (ADR-131) | Destructive/irreversible command se pehle RUKO aur confirm karo. Use jab koi rm -rf, DROP/TRUNCATE/DELETE-with... |
| `churn-prevention` | `.claude/skills/churn-prevention` | canonical (ADR-131) | "When the user wants to reduce churn, build cancellation flows, set up save offers, recover failed payments, o... |
| `code-review-excellence` | `.claude/skills/code-review-excellence` | canonical (ADR-131) | Master effective code review practices to provide constructive feedback, catch bugs early, and foster knowledg... |
| `cold-email` | `.claude/skills/cold-email` | canonical (ADR-131) | Write B2B cold emails and follow-up sequences that get replies. Use when the user wants to write cold outreach... |
| `cold-email-craft` | `.claude/skills/cold-email-craft` | canonical (ADR-131) | B2B cold-email copy craft for Rohan's daily outreach (auto_outreach.py) â€” Hinglish subject lines, 3-line bod... |
| `co-marketing` | `.claude/skills/co-marketing` | canonical (ADR-131) | "When the user wants to find co-marketing partners, plan joint campaigns, or brainstorm partnership opportunit... |
| `community-marketing` | `.claude/skills/community-marketing` | canonical (ADR-131) | "Build and leverage online communities to drive product growth and brand loyalty. Use when the user wants to c... |
| `competitor-ad-teardown` | `.claude/skills/competitor-ad-teardown` | canonical (ADR-131) | Teardown competitor ads/landing-copy from FREE public sources (Meta Ad Library, Google Ads Transparency, Linke... |
| `competitor-profiling` | `.claude/skills/competitor-profiling` | canonical (ADR-131) | "When the user wants to research, profile, or analyze competitors from their URLs. Also use when the user ment... |
| `competitors` | `.claude/skills/competitors` | canonical (ADR-131) | "When the user wants to create competitor comparison or alternative pages for SEO and sales enablement. Also u... |
| `content-marketer` | `.claude/skills/content-marketer` | canonical (ADR-131) | Elite content marketing strategist specializing in AI-powered content creation, omnichannel distribution, SEO ... |
| `content-strategy` | `.claude/skills/content-strategy` | canonical (ADR-131) | When the user wants to plan a content strategy, decide what content to create, or figure out what topics to co... |
| `context-first` | `.claude/skills/context-first` | canonical (ADR-131) | Claude Code edge on LeadGen â€” parallel Grep/Read BEFORE any edit (Cursor Composer default). Use at start of ... |
| `conversion-optimization` | `.claude/skills/conversion-optimization` | canonical (ADR-131) | Conversion-rate optimization (CRO) for the LeadGen AI funnel â€” landing â†’ /audit â†’ inquiry â†’ /pricing â... |
| `coordinator-orchestration` | `.claude/skills/coordinator-orchestration` | canonical (ADR-131) | STAFF coordinator se ek specific multi-agent goal ABHI execute karo â€” sequential / parallel(fanout) / hierar... |
| `copy-editing` | `.claude/skills/copy-editing` | canonical (ADR-131) | "When the user wants to edit, review, or improve existing marketing copy, or refresh outdated content. Also us... |
| `copywriting` | `.claude/skills/copywriting` | canonical (ADR-131) | When the user wants to write, rewrite, or improve marketing copy for any page â€” including homepage, landing ... |
| `create-hook` | `.claude/skills/create-hook` | canonical (ADR-131) | Create Cursor hooks (.cursor/hooks.json) for agent event automation. Use when user wants pre/post tool hooks, ... |
| `create-rule` | `.claude/skills/create-rule` | canonical (ADR-131) | Create persistent AI rules â€” Cursor .mdc rules and CLAUDE.md project memory. Use for coding standards, alway... |
| `create-skill` | `.claude/skills/create-skill` | canonical (ADR-131) | Create Agent Skills for Claude Code and Cursor. Use when authoring SKILL.md, skill structure, or migrating wor... |
| `create-subagent` | `.claude/skills/create-subagent` | canonical (ADR-131) | Launch Task subagents for parallel or isolated work. Use when exploring codebase, shell tasks, or Bugbot-style... |
| `cro` | `.claude/skills/cro` | canonical (ADR-131) | "When the user wants to optimize, improve, or increase conversions on any marketing page or form â€” including... |
| `cso-audit` | `.claude/skills/cso-audit` | canonical (ADR-131) | Security + India-compliance audit (OWASP Top 10 + TRAI + DPDP). Use jab user bole "security audit karo", naya ... |
| `customer-research` | `.claude/skills/customer-research` | canonical (ADR-131) | When the user wants to conduct, analyze, or synthesize customer research. Use when the user mentions "customer... |
| `database-migration` | `.claude/skills/database-migration` | canonical (ADR-131) | Execute database migrations across ORMs and platforms with zero-downtime strategies, data transformation, and ... |
| `data-retention-dpdp` | `.claude/skills/data-retention-dpdp` | canonical (ADR-131) | DPDP Act 2023 data-retention + deletion runbook â€” consent ledger, 90-din recording retention, agent_memory p... |
| `db-migration-safety` | `.claude/skills/db-migration-safety` | canonical (ADR-131) | Postgres schema-change safety on live prod â€” expand-contract pattern, PgBouncer gotchas, additive-only defau... |
| `debugging-strategies` | `.claude/skills/debugging-strategies` | canonical (ADR-131) | Master systematic debugging techniques, profiling tools, and root cause analysis to efficiently track down bug... |
| `deploy` | `.claude/skills/deploy` | canonical (ADR-131) | Deploy or update the LeadGen AI platform to production (Hostinger VPS, Docker, leadsgenai.in) and wire env var... |
| `deployment-pipeline-design` | `.claude/skills/deployment-pipeline-design` | canonical (ADR-131) | Design multi-stage CI/CD pipelines with approval gates, security checks, and deployment orchestration. Use thi... |
| `design-review` | `.claude/skills/design-review` | canonical (ADR-131) | LeadGen ke frontend/UI surfaces ka visual-craft + AI-slop review â€” generic AI-design catch, spacing/hierarch... |
| `dialer-sprint-ops` | `.claude/skills/dialer-sprint-ops` | canonical (ADR-131) | Untapped prospect phones (~90% prospects ke paas phone hai) ko human-dialer sprint se revenue me badalna â€” D... |
| `directory-submissions` | `.claude/skills/directory-submissions` | canonical (ADR-131) | When the user wants to submit their product to startup, SaaS, AI, agent, MCP, no-code, or review directories f... |
| `dispatching-parallel-agents` | `.claude/skills/dispatching-parallel-agents` | canonical (ADR-131) | Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies |
| `doc-gen` | `.claude/skills/doc-gen` | canonical (ADR-131) | Technical docs likho (Diataxis â€” reference / how-to / explanation / runbook) codebase padh ke. Use jab user ... |
| `dr-restore-drill` | `.claude/skills/dr-restore-drill` | canonical (ADR-131) | Disaster-recovery backup + RESTORE drill for leadsgenai.in â€” Postgres pg_backup, rclone offsite (Drive/R2/B2... |
| `duplicate-route-guard` | `.claude/skills/duplicate-route-guard` | canonical (ADR-131) | Prevent FastAPI duplicate routes (first-route-wins shadow). Grep all routers before adding marketing/growth/vo... |
| `e2e-testing-patterns` | `.claude/skills/e2e-testing-patterns` | canonical (ADR-131) | Master end-to-end testing with Playwright and Cypress to build reliable test suites that catch bugs, improve c... |
| `emails` | `.claude/skills/emails` | canonical (ADR-131) | When the user wants to create or optimize an email sequence, drip campaign, automated email flow, or lifecycle... |
| `enterprise-readiness-audit` | `.claude/skills/enterprise-readiness-audit` | canonical (ADR-131) | Master enterprise-grade SaaS audit â€” 12-domain scored matrix (security, tenant-isolation, DR, SLO, secrets, ... |
| `error-handling-patterns` | `.claude/skills/error-handling-patterns` | canonical (ADR-131) | Master error handling patterns across languages including exceptions, Result types, error propagation, and gra... |
| `executing-plans` | `.claude/skills/executing-plans` | canonical (ADR-131) | Use when you have a written implementation plan to execute in a separate session with review checkpoints |
| `executive-council` | `.claude/skills/executive-council` | canonical (ADR-131) | LeadGen Executive Advancement Council â€” revenue/conversion/retention/moat analysis WITHOUT generic repo audi... |
| `fable-operating-manual` | `.claude/skills/fable-operating-manual` | canonical (ADR-131) | Fable-class agent ka ACTUAL operating model â€” parallel context-gathering, subagent fan-out, task-ledger, ask... |
| `fastapi-templates` | `.claude/skills/fastapi-templates` | canonical (ADR-131) | Create production-ready FastAPI projects with async patterns, dependency injection, and comprehensive error ha... |
| `fde-deploy` | `.claude/skills/fde-deploy` | canonical (ADR-131) | Use the Forward Deployed Engineer (FDE) agents to "deploy" marketing + website + automation for a client in on... |
| `fde-onboard` | `.claude/skills/fde-onboard` | canonical (ADR-131) | Full done-for-you client onboarding â€” websiteâ†’KB seed, first content pack, mini-site, lead-capture widget,... |
| `feature-change-flow` | `.claude/skills/feature-change-flow` | canonical (ADR-131) | Kisi bhi EXISTING feature me change karne ka production-safe flow â€” kahan code hai, kya gate lagana, kaise v... |
| `find-skills` | `.claude/skills/find-skills` | canonical (ADR-131) | Discover skills â€” FIRST LeadGen's own ~284 skills (~103 in .claude/skills + 181 in data/skills_extra via ski... |
| `finishing-a-development-branch` | `.claude/skills/finishing-a-development-branch` | canonical (ADR-131) | Use when implementation is complete, all tests pass, and you need to decide how to integrate the work - guides... |
| `free-tools` | `.claude/skills/free-tools` | canonical (ADR-131) | When the user wants to plan, evaluate, or build a free tool for marketing purposes â€” lead generation, SEO va... |
| `genai-observability` | `.claude/skills/genai-observability` | canonical (ADR-131) | LLM/agent tracing via OpenTelemetry GenAI semantic conventions for LeadGen â€” per-provider/model/token spans,... |
| `github-actions-docs` | `.claude/skills/github-actions-docs` | canonical (ADR-131) | Use when users ask how to write, explain, customize, migrate, secure, or troubleshoot GitHub Actions workflows... |
| `github-actions-templates` | `.claude/skills/github-actions-templates` | canonical (ADR-131) | Create production-ready GitHub Actions workflows for automated testing, building, and deploying applications. ... |
| `godmode` | `.claude/skills/godmode` | canonical (ADR-131) | Production readiness + automation ops via Admin God Mode and Mission Control. Use when user says "god mode", "... |
| `hinglish-copywriting` | `.claude/skills/hinglish-copywriting` | canonical (ADR-131) | Hinglish copy frameworks (AIDA/PAS/4U) + marketing psychology (loss aversion, social proof, anchoring, honest ... |
| `hostinger-deploy` | `.claude/skills/hostinger-deploy` | canonical (ADR-131) | Deploy / fix / manage the LeadGen AI platform on the Hostinger KVM VPS (Docker). Use when the user mentions VP... |
| `image` | `.claude/skills/image` | canonical (ADR-131) | "When the user wants to create, generate, edit, or optimize images for marketing â€” blog heroes, social graph... |
| `integration-engineering` | `.claude/skills/integration-engineering` | canonical (ADR-131) | Add a new external integration (LLM/telephony/SMS/payment/CRM/storage/webhook/MCP) the LeadGen AI way â€” impo... |
| `investigate` | `.claude/skills/investigate` | canonical (ADR-131) | Root-cause-first debugging â€” symptom fix se pehle "kyun" pakdo. Use jab error/stack-trace mile, "ye kaam kyu... |
| `k8s-security-policies` | `.claude/skills/k8s-security-policies` | canonical (ADR-131) | Implement Kubernetes security policies including NetworkPolicy, PodSecurityPolicy, and RBAC for production-gra... |
| `kpi-dashboard-design` | `.claude/skills/kpi-dashboard-design` | canonical (ADR-131) | Design effective KPI dashboards with metrics selection, visualization best practices, and real-time monitoring... |
| `launch` | `.claude/skills/launch` | canonical (ADR-131) | "When the user wants to plan a product launch, feature announcement, or release strategy. Also use when the us... |
| `leadgen-automation-reliability` | `.claude/skills/leadgen-automation-reliability` | canonical (ADR-131) | Automation reliability hardening â€” Celery workers/beat, scheduled jobs, retries, idempotency, self-improve/c... |
| `leadgen-billing-upi` | `.claude/skills/leadgen-billing-upi` | canonical (ADR-131) | Manual UPI billing/approval/invoice/plan-activation/entitlement ko operationally safe banao (jab tak full gate... |
| `leadgen-composer` | `.claude/skills/leadgen-composer` | canonical (ADR-131) | LeadGen AI primary agent brain â€” context-first edits, Hinglish replies, free-stack, council decisions, deplo... |
| `leadgen-customer-journey-e2e` | `.claude/skills/leadgen-customer-journey-e2e` | canonical (ADR-131) | Pura P1 customer journey end-to-end validate karo â€” jaise ek paying customer. Use jab landing/pricing/signup... |
| `leadgen-email-deliverability` | `.claude/skills/leadgen-email-deliverability` | canonical (ADR-131) | Email outreach + deliverability hardening â€” account ban se bachao. Use jab SMTP disabled ho, bulk-send se su... |
| `leadgen-infra-doctor` | `.claude/skills/leadgen-infra-doctor` | canonical (ADR-131) | Deployment infra diagnose + harden â€” Docker, Caddy, FastAPI, workers, scheduler, Redis, Postgres, PgBouncer,... |
| `leadgen-lead-pipeline-quality` | `.claude/skills/leadgen-lead-pipeline-quality` | canonical (ADR-131) | Lead pipeline quality audit â€” reliable, deduplicated, explainable, useful Indian local-business acquisition.... |
| `leadgen-observability` | `.claude/skills/leadgen-observability` | canonical (ADR-131) | Enterprise observability â€” logs, metrics, traces, dashboards, alerting, health-checks, audit-logs, job-visib... |
| `leadgen-ops` | `.claude/skills/leadgen-ops` | canonical (ADR-131) | LeadGen AI ka proven ops loop â€” verify, test, push, deploy + production triage. Use when the user says "depl... |
| `leadgen-product-truth` | `.claude/skills/leadgen-product-truth` | canonical (ADR-131) | Plans/limits/products/promises ka EK source-of-truth enforce karo. Use jab pricing, packages, feature-gate, pu... |
| `leadgen-repo-learning-governance` | `.claude/skills/leadgen-repo-learning-governance` | canonical (ADR-131) | External open-source repos se SEEKHNE ka governance â€” pattern extract karo, copy mat karo. Use jab FastAPI-t... |
| `leadgen-revenue-readiness` | `.claude/skills/leadgen-revenue-readiness` | canonical (ADR-131) | P1 AI Marketing Automation ko SELLABLE banane ka audit â€” kya customer discoverâ†’payâ†’activateâ†’output tak... |
| `leadgen-security-rbac` | `.claude/skills/leadgen-security-rbac` | canonical (ADR-131) | Security + auth + RBAC + tenant-isolation + secrets + admin-permissions + API-keys + webhooks + PII handling a... |
| `leadgen-start` | `.claude/skills/leadgen-start` | canonical (ADR-131) | Session bootstrap for LeadGen AI â€” token-efficient way to start ANY task on this project. Use at the start o... |
| `leadgen-test-guardian` | `.claude/skills/leadgen-test-guardian` | canonical (ADR-131) | Testing discipline enforce karo â€” unit/integration/route-smoke/Celery-task/scheduler/E2E tests, Docker healt... |
| `leadgen-voice-compliance` | `.claude/skills/leadgen-voice-compliance` | canonical (ADR-131) | P2 voice-calling readiness + compliance gate audit â€” Vobiz/FreeSWITCH, STT/LLM/TTS, DND, consent, opt-out, A... |
| `lead-magnets` | `.claude/skills/lead-magnets` | canonical (ADR-131) | When the user wants to create, plan, or optimize a lead magnet for email capture or lead generation. Also use ... |
| `llm-council-decision` | `.claude/skills/llm-council-decision` | canonical (ADR-131) | Claude (session agent) ko Council-style faisla lene ka protocol â€” multi-agent opinions â†’ peer review â†’ C... |
| `llm-error-analysis` | `.claude/skills/llm-error-analysis` | canonical (ADR-131) | LLM/voice-agent quality girne pe systematic error analysis â€” traces padho (open-coding) â†’ failure taxonomy... |
| `llm-quota-ops` | `.claude/skills/llm-quota-ops` | canonical (ADR-131) | Free-LLM provider quota/cooldown ops â€” Groq TPD khatam, Cerebras 429 burst, ok-rate tank (0.4 jaisa), fallba... |
| `llm-security` | `.claude/skills/llm-security` | canonical (ADR-131) | LLM/agent attack-surface defense for LeadGen â€” indirect prompt injection (RAG/inbox/tool-output), jailbreaks... |
| `load-capacity-testing` | `.claude/skills/load-capacity-testing` | canonical (ADR-131) | Load testing + capacity headroom on single-VPS free stack â€” API rps limits, WEB_CONCURRENCY, PgBouncer pool,... |
| `loop` | `.claude/skills/loop` | canonical (ADR-131) | Run a prompt or skill on a recurring interval (e.g. check deploy every 5m). Use when the user asks for periodi... |
| `marketing-feature` | `.claude/skills/marketing-feature` | canonical (ADR-131) | Add a new marketing feature to LeadGen AI the proven way â€” module + API + frontend tab + test + VPS smoke. U... |
| `marketing-ideas` | `.claude/skills/marketing-ideas` | canonical (ADR-131) | "When the user needs marketing ideas, inspiration, or strategies for their SaaS or software product. Also use ... |
| `marketing-plan` | `.claude/skills/marketing-plan` | canonical (ADR-131) | When the user needs a comprehensive marketing plan for a client, a company they advise, or their own product. ... |
| `marketing-psychology` | `.claude/skills/marketing-psychology` | canonical (ADR-131) | "When the user wants to apply psychological principles, mental models, or behavioral science to marketing. Als... |
| `mcp-engineer` | `.claude/skills/mcp-engineer` | canonical (ADR-131) | Anything MCP â€” /mcp endpoint, MCP-as-product /api/mcp-product/v1/*, A2A Agent Card, mcp_keys, Arya staff age... |
| `memory-vault` | `.claude/skills/memory-vault` | canonical (ADR-131) | Rowboat-style compounding memory â€” per-prospect/client/topic markdown memory, call-prep briefs, live notes (... |
| `migrate-to-skills` | `.claude/skills/migrate-to-skills` | canonical (ADR-131) | Convert Cursor rules (.mdc) and slash commands (.md) to Agent Skills (SKILL.md). Use when consolidating rules/... |
| `model-asset-bake` | `.claude/skills/model-asset-bake` | canonical (ADR-131) | ML model assets (fastembed/silero/whisper/onnx) production me kaise rakhein â€” image-bake, off-loop load, har... |
| `multi-agent-coordination` | `.claude/skills/multi-agent-coordination` | canonical (ADR-131) | Sahi orchestration primitive chuno â€” coordinator 6 modes (plan/handoff, Reflexion-advanced, hierarchical, fa... |
| `niche-onboarding` | `.claude/skills/niche-onboarding` | canonical (ADR-131) | Naya niche add karna ya naya client onboard karna LeadGen platform pe. Use when the user says "naya niche", "a... |
| `observability-ops` | `.claude/skills/observability-ops` | canonical (ADR-131) | Operate and extend the LeadGen AI monitoring stack â€” Prometheus, Grafana, Alertmanager (email), Loki, Tempo,... |
| `offers` | `.claude/skills/offers` | canonical (ADR-131) | "When the user wants to design, construct, or improve an offer â€” the thing they actually sell â€” including ... |
| `office-hours` | `.claude/skills/office-hours` | canonical (ADR-131) | "Kya yeh worth building hai?" â€” naya feature/idea ko 6 startup forcing-questions (demand, status-quo pain, s... |
| `onboarding` | `.claude/skills/onboarding` | canonical (ADR-131) | When the user wants to optimize post-signup onboarding, user activation, first-run experience, or time-to-valu... |
| `orchestrate-goal` | `.claude/skills/orchestrate-goal` | canonical (ADR-131) | "Mere paas ek goal hai â€” kaunsa automation loop?" â€” self-improve (daily hands-off) vs coordinator (NOW mul... |
| `pairwise-test-design` | `.claude/skills/pairwise-test-design` | canonical (ADR-131) | Combinatorial (pairwise / PICT) test-case design for LeadGen AI's huge config space â€” niche Ã— band Ã— tier ... |
| `parallel-batch-build` | `.claude/skills/parallel-batch-build` | canonical (ADR-131) | 10-20 features ek session me parallel sub-agents se banane ka PROVEN pattern (batch-3 me 16 features aise hi b... |
| `paywalls` | `.claude/skills/paywalls` | canonical (ADR-131) | When the user wants to create or optimize in-app paywalls, upgrade screens, upsell modals, or feature gates. A... |
| `pipeline-hygiene` | `.claude/skills/pipeline-hygiene` | canonical (ADR-131) | Weekly funnel-data safai â€” junk deals, stale "ready" prospects, reply-classifier drift, bulk-sender leaks. U... |
| `plan-ceo-review` | `.claude/skills/plan-ceo-review` | canonical (ADR-131) | Bada feature ya product-direction faisla CEO-lens se challenge karo â€” mode (expansion/selective/hold/reducti... |
| `plan-eng-review` | `.claude/skills/plan-eng-review` | canonical (ADR-131) | Naya feature build se pehle ka engineering review â€” duplicate-route grep, ASCII architecture, state-machine,... |
| `plan-then-build` | `.claude/skills/plan-then-build` | canonical (ADR-131) | Multi-step build se PEHLE lean plan doc + project pre-checks (duplicate-route grep, file-ownership matrix, fla... |
| `popups` | `.claude/skills/popups` | canonical (ADR-131) | When the user wants to create or optimize popups, modals, overlays, slide-ins, or banners for conversion purpo... |
| `postgresql-table-design` | `.claude/skills/postgresql-table-design` | canonical (ADR-131) | Use this skill when designing or reviewing a PostgreSQL-specific schema. Covers best-practices, data types, in... |
| `pricing` | `.claude/skills/pricing` | canonical (ADR-131) | "When the user wants help with pricing decisions, packaging, or monetization strategy. Also use when the user ... |
| `prod-incident-triage` | `.claude/skills/prod-incident-triage` | canonical (ADR-131) | leadsgenai.in down/unhealthy/freeze â€” health 000, workers stuck, CPU 0%, "automations broken" feel. 3 real p... |
| `production-ready` | `.claude/skills/production-ready` | canonical (ADR-131) | LeadGen production readiness gate â€” live activation summary, prod_check, cross-path audit, Product-1 vs Prod... |
| `product-marketing` | `.claude/skills/product-marketing` | canonical (ADR-131) | "When the user wants to create or update their product marketing context document. Also use when the user ment... |
| `product-split-adr` | `.claude/skills/product-split-adr` | canonical (ADR-131) | Two-product split ADR-009 â€” Marketing vs Voice Agent separate SKUs, pricing truth, copy rules, niches, agent... |
| `programmatic-seo` | `.claude/skills/programmatic-seo` | canonical (ADR-131) | When the user wants to create SEO-driven pages at scale using templates and data. Also use when the user menti... |
| `prompt-engineering` | `.claude/skills/prompt-engineering` | canonical (ADR-131) | Prompt-design discipline anchored to LeadGen's free-stack LLM chain â€” cheap-model-robust instructions, Hingl... |
| `prospecting` | `.claude/skills/prospecting` | canonical (ADR-131) | When the user wants to find, qualify, and build a list of prospects to reach out to â€” across B2B SaaS, gener... |
| `public-relations` | `.claude/skills/public-relations` | canonical (ADR-131) | "When the user wants help with public relations, earned media, press coverage, journalist outreach, or media s... |
| `python-design-patterns` | `.claude/skills/python-design-patterns` | canonical (ADR-131) | Python design patterns including KISS, Separation of Concerns, Single Responsibility, and composition over inh... |
| `python-performance-optimization` | `.claude/skills/python-performance-optimization` | canonical (ADR-131) | Profile and optimize Python code using cProfile, memory profilers, and performance best practices. Use when de... |
| `python-testing-patterns` | `.claude/skills/python-testing-patterns` | canonical (ADR-131) | Implement comprehensive testing strategies with pytest, fixtures, mocking, and test-driven development. Use wh... |
| `receiving-code-review` | `.claude/skills/receiving-code-review` | canonical (ADR-131) | Use when receiving code review feedback, before implementing suggestions, especially if feedback seems unclear... |
| `referrals` | `.claude/skills/referrals` | canonical (ADR-131) | "When the user wants to create, optimize, or analyze a referral program, affiliate program, or word-of-mouth s... |
| `requesting-code-review` | `.claude/skills/requesting-code-review` | canonical (ADR-131) | Use when completing tasks, implementing major features, or before merging to verify work meets requirements |
| `retro` | `.claude/skills/retro` | canonical (ADR-131) | Weekly engineering retro â€” git se commits/features/bugs/streak nikaalo, prod-downs + learnings summarize kar... |
| `review` | `.claude/skills/review` | canonical (ADR-131) | PR/diff code review for the LeadGen AI platform â€” 5-lens critical pass (bugs Â· prod-killers Â· security Â· ... |
| `review-bugbot` | `.claude/skills/review-bugbot` | canonical (ADR-131) | Bug-focused code review of local changes (Bugbot-style). Use when user asks for /review-bugbot, bug review, or... |
| `revops` | `.claude/skills/revops` | canonical (ADR-131) | "When the user wants help with revenue operations, lead lifecycle management, or marketing-to-sales handoff pr... |
| `run-campaign` | `.claude/skills/run-campaign` | canonical (ADR-131) | Run a lead-generation voice campaign for a client â€” scrape prospects for a niche/city, call + qualify them w... |
| `saas-pricing-strategy` | `.claude/skills/saas-pricing-strategy` | canonical (ADR-131) | Pricing/packaging/discount decisions for LeadGen AI ke DO products â€” Marketing (PUBLIC 2 plans â€” Main â‚¹1... |
| `sales-enablement` | `.claude/skills/sales-enablement` | canonical (ADR-131) | "When the user wants to create sales collateral, pitch decks, one-pagers, objection handling docs, or demo scr... |
| `scheduler-job` | `.claude/skills/scheduler-job` | canonical (ADR-131) | Engineer a new scheduled/recurring automation job the LeadGen AI way â€” durable Celery-beat (PRIMARY, live) +... |
| `schema` | `.claude/skills/schema` | canonical (ADR-131) | When the user wants to add, fix, or optimize schema markup and structured data on their site. Also use when th... |
| `secrets-management` | `.claude/skills/secrets-management` | canonical (ADR-131) | Implement secure secrets management for CI/CD pipelines using Vault, AWS Secrets Manager, or native platform s... |
| `secrets-rotation` | `.claude/skills/secrets-rotation` | canonical (ADR-131) | Secrets inventory + rotation cadence + leak-response runbook â€” .env keys (LLM providers, Gemini 9-key pool, ... |
| `secure-linux-web-hosting` | `.claude/skills/secure-linux-web-hosting` | canonical (ADR-131) | Use when setting up, hardening, or reviewing a cloud server for self-hosting, including DNS, SSH, firewalls, N... |
| `security-requirement-extraction` | `.claude/skills/security-requirement-extraction` | canonical (ADR-131) | Derive security requirements from threat models and business context. Use when translating threats into action... |
| `security-review` | `.claude/skills/security-review` | canonical (ADR-131) | Security + hardening review for the LeadGen AI platform (FastAPI + payments + public endpoints + telephony com... |
| `self-code-review` | `.claude/skills/self-code-review` | canonical (ADR-131) | Ship se pehle solo-dev multi-pass review â€” bug-hunt, security, signature-drift, hot-path, test-gap â€” 5 ala... |
| `self-improve-control` | `.claude/skills/self-improve-control` | canonical (ADR-131) | Monitor, audit, aur safely control the self-improve forever-loop â€” health/heartbeat, cost, approvals, lesson... |
| `self-improve-loop` | `.claude/skills/self-improve-loop` | canonical (ADR-131) | Self-improving CONTINUOUS agent loop (taskâ†’task, no cron timing) â€” architecture + 12 actions + skill_libra... |
| `seo-audit` | `.claude/skills/seo-audit` | canonical (ADR-131) | When the user wants to audit, review, or diagnose SEO issues on their site. Also use when the user mentions "S... |
| `seo-growth` | `.claude/skills/seo-growth` | canonical (ADR-131) | SEO + organic-traffic growth for leadsgenai.in (programmatic blog, local SEO, Google Business Profile, schema ... |
| `shell` | `.claude/skills/shell` | canonical (ADR-131) | Execute literal shell command when user invokes /shell. Use only for explicit /shell requests â€” run command ... |
| `ship-checklist` | `.claude/skills/ship-checklist` | canonical (ADR-131) | Pre-deploy + deploy + verify checklist for the LeadGen AI live VPS (Docker, leadsgenai.in). Use when shipping ... |
| `signup` | `.claude/skills/signup` | canonical (ADR-131) | When the user wants to optimize signup, registration, account creation, or trial activation flows. Also use wh... |
| `site-architecture` | `.claude/skills/site-architecture` | canonical (ADR-131) | When the user wants to plan, map, or restructure their website's page hierarchy, navigation, URL structure, or... |
| `slo-error-budget` | `.claude/skills/slo-error-budget` | canonical (ADR-131) | SLO definitions + error-budget policy + burn-rate alerts for leadsgenai.in â€” uptime, voice-call success, ema... |
| `sms` | `.claude/skills/sms` | canonical (ADR-131) | When the user wants to plan, build, or optimize SMS or MMS marketing â€” including welcome flows, abandoned ca... |
| `social` | `.claude/skills/social` | canonical (ADR-131) | "When the user wants help creating, scheduling, or optimizing social media content for LinkedIn, Twitter/X, In... |
| `source-command-compact-check` | `.claude/skills/source-command-compact-check` | canonical (ADR-131) | "Decide karo ki compact karein ya nayi chat shuru â€” LeadGen AI token discipline (strategic compaction)." |
| `spec` | `.claude/skills/spec` | canonical (ADR-131) | Vague feature idea ko concrete, build-ready spec banao â€” why/user, existing-code check (duplicate-route grep... |
| `split-to-prs` | `.claude/skills/split-to-prs` | canonical (ADR-131) | Split current work into small reviewable PRs. Use when user asks to split branch, chat work, or one big diff i... |
| `sql-optimization-patterns` | `.claude/skills/sql-optimization-patterns` | canonical (ADR-131) | Master SQL query optimization, indexing strategies, and EXPLAIN analysis to dramatically improve database perf... |
| `statusline` | `.claude/skills/statusline` | canonical (ADR-131) | Cursor IDE statusline customization reference. Claude Code has no statusline â€” use for Cursor-only setup or ... |
| `subagent-driven-development` | `.claude/skills/subagent-driven-development` | canonical (ADR-131) | Use when executing implementation plans with independent tasks in the current session |
| `supabase-postgres-best-practices` | `.claude/skills/supabase-postgres-best-practices` | canonical (ADR-131) | Postgres performance optimization and best practices from Supabase. Use this skill when writing, reviewing, or... |
| `supply-chain-security` | `.claude/skills/supply-chain-security` | canonical (ADR-131) | Dependency + build supply-chain hygiene â€” requirements.lock.txt discipline, pip-audit CVE scan, Docker base-... |
| `systematic-debugging` | `.claude/skills/systematic-debugging` | canonical (ADR-131) | Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes |
| `tdd-contract-first` | `.claude/skills/tdd-contract-first` | canonical (ADR-131) | Red-green-refactor + "contract tests PEHLE" discipline â€” naya feature/bugfix likhne se pehle failing test, a... |
| `teach-agent-loop` | `.claude/skills/teach-agent-loop` | canonical (ADR-131) | Extend the self-improve loop safely â€” naya AI agent (staff member) ya naya action/task add karo, risk-assess... |
| `team-access-ops` | `.claude/skills/team-access-ops` | canonical (ADR-131) | Team member add/remove/modules runbook â€” sub-admin banana, member ko modules dena, password reset, deactivat... |
| `telephony-engineering` | `.claude/skills/telephony-engineering` | canonical (ADR-131) | Wire and operate telephony providers for LeadGen AI voice calls â€” Vobiz (active, India-native SIP), Twilio, ... |
| `tenant-isolation-audit` | `.claude/skills/tenant-isolation-audit` | canonical (ADR-131) | Multi-tenant isolation deep-audit â€” tenant middleware FAIL-OPEN risk, IDOR sweep beyond billing, per-tenant ... |
| `test-agent` | `.claude/skills/test-agent` | canonical (ADR-131) | Test the AI voice agent before going live â€” run the persona eval suite, have a text/web conversation, or che... |
| `test-driven-development` | `.claude/skills/test-driven-development` | canonical (ADR-131) | Use when implementing any feature or bugfix, before writing implementation code |
| `update-claude-settings` | `.claude/skills/update-claude-settings` | canonical (ADR-131) | Update project memory and agent settings â€” CLAUDE.md, AGENTS.md, .cursor/rules. Use when user wants to persi... |
| `update-cli-config` | `.claude/skills/update-cli-config` | canonical (ADR-131) | Update Claude Code or Cursor CLI configuration files. Use when user asks to change CLI model, permissions, or ... |
| `using-git-worktrees` | `.claude/skills/using-git-worktrees` | canonical (ADR-131) | Use when starting feature work that needs isolation from current workspace or before executing implementation ... |
| `using-superpowers` | `.claude/skills/using-superpowers` | canonical (ADR-131) | Use when starting any conversation - establishes how to find and use skills, requiring skill invocation before... |
| `uv-package-manager` | `.claude/skills/uv-package-manager` | canonical (ADR-131) | Master the uv package manager for fast Python dependency management, virtual environments, and modern Python p... |
| `verification-before-completion` | `.claude/skills/verification-before-completion` | canonical (ADR-131) | Use when about to claim work is complete, fixed, or passing, before committing or creating PRs - requires runn... |
| `verify-ship` | `.claude/skills/verify-ship` | canonical (ADR-131) | LeadGen pre-ship verify and deploy loop â€” prod_check, pytest, secrets scan, explorer_sync, git push, VPS Doc... |
| `video` | `.claude/skills/video` | canonical (ADR-131) | "When the user wants to create, generate, or produce video content using AI tools or programmatic frameworks. ... |
| `voice-agent-kb` | `.claude/skills/voice-agent-kb` | canonical (ADR-131) | LeadGen AI voice agent internals knowledge base â€” TelecallerBrain vs NaturalDialog, free_ai provider chain, ... |
| `voice-eval-metrics` | `.claude/skills/voice-eval-metrics` | canonical (ADR-131) | Objective ASR/TTS/latency metrics for LeadGen's FREE voice stack (Groq-whisper STT + EdgeTTS), upgrading agent... |
| `voice-humanization` | `.claude/skills/voice-humanization` | canonical (ADR-131) | PHONE voice agent (vobiz) ko human-like banane ka project pattern â€” Groq STT chain, TelecallerBrain, fillers... |
| `voice-roles` | `.claude/skills/voice-roles` | canonical (ADR-131) | Swara telecaller, Ananya appointment booker, Riya receptionist â€” voice role wiring, prompts, test-call flow,... |
| `watch` | `.claude/skills/watch` | canonical (ADR-131) | Watch a video (URL or local path). Downloads with yt-dlp, extracts auto-scaled frames with ffmpeg, pulls the t... |
| `web-call-triage` | `.claude/skills/web-call-triage` | canonical (ADR-131) | User bole "web call pe agent slow hai / sunta nahi / atak jata / noob lagta hai" â€” FREE web-call (/app/test-... |
| `web-performance` | `.claude/skills/web-performance` | canonical (ADR-131) | Web performance + Core Web Vitals review for the LeadGen AI public pages (landing, /pricing, /audit, /blog, /b... |
| `windows-dev-gotchas` | `.claude/skills/windows-dev-gotchas` | canonical (ADR-131) | Windows dev environment gotchas for LeadGen â€” stale sandbox, Git ssh, curl.exe, VPS deploy quoting, bat logs... |
| `writing-plans` | `.claude/skills/writing-plans` | canonical (ADR-131) | Use when you have a spec or requirements for a multi-step task, before touching code |
| `writing-skills` | `.claude/skills/writing-skills` | canonical (ADR-131) | Use when creating new skills, editing existing skills, or verifying skills work before deployment |
