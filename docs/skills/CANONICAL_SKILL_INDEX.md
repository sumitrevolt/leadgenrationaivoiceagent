# Canonical Skill Index

> **Generated 2026-07-21 from measured filesystem + git state at main `9c1bb30`.**
> Documentation and routing support ONLY. This index confers **no runtime authority**:
> nothing dispatches from it, and Owner OS remains the sole execution authority.

## Measured state

| Metric | Value |
|---|---|
| Distinct skill names | 208 |
| Present in BOTH trees, byte-identical | **184** |
| Shared name but diverged content | **0** |
| `.claude/skills` only | 1 |
| `.agents/skills` only | 23 |
| Tracked files `.claude/skills` | 403 |
| Tracked files `.agents/skills` | 446 |

## The junction overlay is LOCAL-ONLY - git holds real duplicates

In the primary working checkout, ~61 entries under `.claude/skills/` are Windows
directory junctions into `.agents/skills/`, which makes the trees look shared.
**A fresh `git worktree` checkout has ZERO junctions** (verified: 185 and 207 real
directories). Git does not store junctions - it stores both copies in full.

Consequence: anyone cloning this repo gets 184 duplicated skills, and an edit to
one copy silently diverges from the other. That already happened once - the
`audit-automation` DND fix had to be applied twice, because on disk that skill is a
real duplicate rather than a junction.

`.claude/skills/SKILLS_PARITY.md` documents the junction topology as if it were the
repository state. It is not. It also reports ~184 folders in `.claude/skills/`;
the checked-out count is 185 and the junction-masked local count is 121.

## Consolidation is NOT performed here

De-duplicating means deleting one of two trees. That is destructive, it interacts
with local junctions (a recursive delete across a junction destroys the real
content on the other side), and consumers may read either path. This index
establishes the evidence; the deletion is a separate, owner-approved change.

Recommended canonical tree: `.agents/skills/` (superset - holds all 184 shared
plus 23 exclusive). `.claude/skills/` would become generated or junctioned, with
its 1 exclusive skill ported first.

## Index

| Skill | Canonical path | Mirror status | Purpose |
|---|---|---|---|
| `a2z-launch-enterprise-audit` | `.claude/skills/a2z-launch-enterprise-audit` | .claude only | LeadGen "A-to-Z Launch & Enterprise Audit" master prompt â€” does NOT stop at audit. Drives Discover â†’ Verif... |
| `ab-testing` | `.agents/skills/ab-testing` | DUPLICATED (byte-identical) | When the user wants to plan, design, or implement an A/B test or experiment, or build a growth experimentation... |
| `ad-creative` | `.agents/skills/ad-creative` | DUPLICATED (byte-identical) | "When the user wants to generate, iterate, or scale ad creative â€” headlines, descriptions, primary text, or ... |
| `admin-friendly-ux` | `.agents/skills/admin-friendly-ux` | DUPLICATED (byte-identical) | Admin/customer dashboards ko non-technical-friendly banane ka pattern â€” plain-Hinglish aggregator endpoint +... |
| `ads` | `.agents/skills/ads` | DUPLICATED (byte-identical) | "When the user wants help with paid advertising campaigns on Google Ads, Meta (Facebook/Instagram), LinkedIn, ... |
| `advancement-roadmap` | `.agents/skills/advancement-roadmap` | DUPLICATED (byte-identical) | LeadGen AI 2026 advancement backlog â€” web-researched, codebase-aware, free-stack. Use when user bole "advanc... |
| `agentkits-marketing-automation` | `.agents/skills/agentkits-marketing-automation` | .agents only | Enterprise AI marketing automation toolkit with 18 agents, 93 commands, and 28 skills for campaign planning, c... |
| `agent-loop-design` | `.agents/skills/agent-loop-design` | DUPLICATED (byte-identical) | Naya ALWAYS-ON / recurring agent loop design karne ka generalized pattern â€” self_improve/growth-pulse/proces... |
| `agent-sdk` | `.agents/skills/agent-sdk` | DUPLICATED (byte-identical) | Build and verify Python or TypeScript Agent SDK applications. Use when creating agent apps with Claude/OpenAI ... |
| `ai-seo` | `.agents/skills/ai-seo` | DUPLICATED (byte-identical) | "When the user wants to optimize content for AI search engines, get cited by LLMs, or appear in AI-generated a... |
| `analytics` | `.agents/skills/analytics` | DUPLICATED (byte-identical) | When the user wants to set up, improve, or audit analytics tracking and measurement. Also use when the user me... |
| `api-design` | `.agents/skills/api-design` | DUPLICATED (byte-identical) | FastAPI route/endpoint design discipline for the LeadGen AI platform â€” grep-first (no duplicate routes), add... |
| `api-design-principles` | `.agents/skills/api-design-principles` | .agents only | Master REST and GraphQL API design principles to build intuitive, scalable, and maintainable APIs that delight... |
| `architecture-patterns` | `.agents/skills/architecture-patterns` | .agents only | Implement proven backend architecture patterns including Clean Architecture, Hexagonal Architecture, and Domai... |
| `audit-automation` | `.agents/skills/audit-automation` | DUPLICATED (byte-identical) | Health-check the automation loops without reading code â€” heartbeat/alive, daily cost vs cap, approvals backl... |
| `automate` | `.agents/skills/automate` | DUPLICATED (byte-identical) | Set up recurring automation for LeadGen â€” Celery beat jobs, cron on VPS, or Cursor Automations when in Curso... |
| `automation-control-center` | `.agents/skills/automation-control-center` | DUPLICATED (byte-identical) | Upgrade/extend the /app/automation Mission Control so it stays the SINGLE advanced cockpit for all automation ... |
| `automation-flags` | `.agents/skills/automation-flags` | DUPLICATED (byte-identical) | The gated env-flag catalog for LeadGen AI automation engines â€” what each flag does, ban/cost risk, and the s... |
| `automation-pipeline` | `.agents/skills/automation-pipeline` | DUPLICATED (byte-identical) | Operate LeadGen AI's end-to-end automated growth pipeline â€” scrape â†’ score â†’ email outreach â†’ reply-tr... |
| `babysit` | `.agents/skills/babysit` | DUPLICATED (byte-identical) | Keep a PR merge-ready by triaging comments, resolving conflicts, and fixing CI in a loop. Use when user says b... |
| `backend-rbac` | `.agents/skills/backend-rbac` | DUPLICATED (byte-identical) | LeadGen AI ka roles + module-grants access-control + admin-side auth features. Use jab "sub admin", "team memb... |
| `brainstorming` | `.agents/skills/brainstorming` | DUPLICATED (byte-identical) | "You MUST use this before any creative work - creating features, building components, adding functionality, or... |
| `canvas` | `.agents/skills/canvas` | DUPLICATED (byte-identical) | Produce standalone visual analytical artifacts. In Cursor IDE use .canvas.tsx; in Claude Code use structured m... |
| `careful` | `.agents/skills/careful` | DUPLICATED (byte-identical) | Destructive/irreversible command se pehle RUKO aur confirm karo. Use jab koi rm -rf, DROP/TRUNCATE/DELETE-with... |
| `churn-prevention` | `.agents/skills/churn-prevention` | DUPLICATED (byte-identical) | "When the user wants to reduce churn, build cancellation flows, set up save offers, recover failed payments, o... |
| `code-review-excellence` | `.agents/skills/code-review-excellence` | .agents only | Master effective code review practices to provide constructive feedback, catch bugs early, and foster knowledg... |
| `cold-email` | `.agents/skills/cold-email` | DUPLICATED (byte-identical) | Write B2B cold emails and follow-up sequences that get replies. Use when the user wants to write cold outreach... |
| `cold-email-craft` | `.agents/skills/cold-email-craft` | DUPLICATED (byte-identical) | B2B cold-email copy craft for Rohan's daily outreach (auto_outreach.py) â€” Hinglish subject lines, 3-line bod... |
| `co-marketing` | `.agents/skills/co-marketing` | DUPLICATED (byte-identical) | "When the user wants to find co-marketing partners, plan joint campaigns, or brainstorm partnership opportunit... |
| `community-marketing` | `.agents/skills/community-marketing` | DUPLICATED (byte-identical) | "Build and leverage online communities to drive product growth and brand loyalty. Use when the user wants to c... |
| `competitor-ad-teardown` | `.agents/skills/competitor-ad-teardown` | DUPLICATED (byte-identical) | Teardown competitor ads/landing-copy from FREE public sources (Meta Ad Library, Google Ads Transparency, Linke... |
| `competitor-profiling` | `.agents/skills/competitor-profiling` | DUPLICATED (byte-identical) | "When the user wants to research, profile, or analyze competitors from their URLs. Also use when the user ment... |
| `competitors` | `.agents/skills/competitors` | DUPLICATED (byte-identical) | "When the user wants to create competitor comparison or alternative pages for SEO and sales enablement. Also u... |
| `content-marketer` | `.agents/skills/content-marketer` | .agents only | Elite content marketing strategist specializing in AI-powered content creation, omnichannel distribution, SEO ... |
| `content-strategy` | `.agents/skills/content-strategy` | DUPLICATED (byte-identical) | When the user wants to plan a content strategy, decide what content to create, or figure out what topics to co... |
| `context-first` | `.agents/skills/context-first` | DUPLICATED (byte-identical) | Claude Code edge on LeadGen â€” parallel Grep/Read BEFORE any edit (Cursor Composer default). Use at start of ... |
| `conversion-optimization` | `.agents/skills/conversion-optimization` | DUPLICATED (byte-identical) | Conversion-rate optimization (CRO) for the LeadGen AI funnel â€” landing â†’ /audit â†’ inquiry â†’ /pricing â... |
| `coordinator-orchestration` | `.agents/skills/coordinator-orchestration` | DUPLICATED (byte-identical) | STAFF coordinator se ek specific multi-agent goal ABHI execute karo â€” sequential / parallel(fanout) / hierar... |
| `copy-editing` | `.agents/skills/copy-editing` | DUPLICATED (byte-identical) | "When the user wants to edit, review, or improve existing marketing copy, or refresh outdated content. Also us... |
| `copywriting` | `.agents/skills/copywriting` | DUPLICATED (byte-identical) | When the user wants to write, rewrite, or improve marketing copy for any page â€” including homepage, landing ... |
| `create-hook` | `.agents/skills/create-hook` | DUPLICATED (byte-identical) | Create Cursor hooks (.cursor/hooks.json) for agent event automation. Use when user wants pre/post tool hooks, ... |
| `create-rule` | `.agents/skills/create-rule` | DUPLICATED (byte-identical) | Create persistent AI rules â€” Cursor .mdc rules and CLAUDE.md project memory. Use for coding standards, alway... |
| `create-skill` | `.agents/skills/create-skill` | DUPLICATED (byte-identical) | Create Agent Skills for Claude Code and Cursor. Use when authoring SKILL.md, skill structure, or migrating wor... |
| `create-subagent` | `.agents/skills/create-subagent` | DUPLICATED (byte-identical) | Launch Task subagents for parallel or isolated work. Use when exploring codebase, shell tasks, or Bugbot-style... |
| `cro` | `.agents/skills/cro` | DUPLICATED (byte-identical) | "When the user wants to optimize, improve, or increase conversions on any marketing page or form â€” including... |
| `cso-audit` | `.agents/skills/cso-audit` | DUPLICATED (byte-identical) | Security + India-compliance audit (OWASP Top 10 + TRAI + DPDP). Use jab user bole "security audit karo", naya ... |
| `customer-research` | `.agents/skills/customer-research` | DUPLICATED (byte-identical) | When the user wants to conduct, analyze, or synthesize customer research. Use when the user mentions "customer... |
| `database-migration` | `.agents/skills/database-migration` | .agents only | Execute database migrations across ORMs and platforms with zero-downtime strategies, data transformation, and ... |
| `data-retention-dpdp` | `.agents/skills/data-retention-dpdp` | DUPLICATED (byte-identical) | DPDP Act 2023 data-retention + deletion runbook â€” consent ledger, 90-din recording retention, agent_memory p... |
| `db-migration-safety` | `.agents/skills/db-migration-safety` | DUPLICATED (byte-identical) | Postgres schema-change safety on live prod â€” expand-contract pattern, PgBouncer gotchas, additive-only defau... |
| `debugging-strategies` | `.agents/skills/debugging-strategies` | .agents only | Master systematic debugging techniques, profiling tools, and root cause analysis to efficiently track down bug... |
| `deploy` | `.agents/skills/deploy` | DUPLICATED (byte-identical) | Deploy or update the LeadGen AI platform to production (Hostinger VPS, Docker, leadsgenai.in) and wire env var... |
| `deployment-pipeline-design` | `.agents/skills/deployment-pipeline-design` | .agents only | Design multi-stage CI/CD pipelines with approval gates, security checks, and deployment orchestration. Use thi... |
| `design-review` | `.agents/skills/design-review` | DUPLICATED (byte-identical) | LeadGen ke frontend/UI surfaces ka visual-craft + AI-slop review â€” generic AI-design catch, spacing/hierarch... |
| `dialer-sprint-ops` | `.agents/skills/dialer-sprint-ops` | DUPLICATED (byte-identical) | Untapped prospect phones (~90% prospects ke paas phone hai) ko human-dialer sprint se revenue me badalna â€” D... |
| `directory-submissions` | `.agents/skills/directory-submissions` | DUPLICATED (byte-identical) | When the user wants to submit their product to startup, SaaS, AI, agent, MCP, no-code, or review directories f... |
| `dispatching-parallel-agents` | `.agents/skills/dispatching-parallel-agents` | DUPLICATED (byte-identical) | Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies |
| `doc-gen` | `.agents/skills/doc-gen` | DUPLICATED (byte-identical) | Technical docs likho (Diataxis â€” reference / how-to / explanation / runbook) codebase padh ke. Use jab user ... |
| `dr-restore-drill` | `.agents/skills/dr-restore-drill` | DUPLICATED (byte-identical) | Disaster-recovery backup + RESTORE drill for leadsgenai.in â€” Postgres pg_backup, rclone offsite (Drive/R2/B2... |
| `duplicate-route-guard` | `.agents/skills/duplicate-route-guard` | DUPLICATED (byte-identical) | Prevent FastAPI duplicate routes (first-route-wins shadow). Grep all routers before adding marketing/growth/vo... |
| `e2e-testing-patterns` | `.agents/skills/e2e-testing-patterns` | .agents only | Master end-to-end testing with Playwright and Cypress to build reliable test suites that catch bugs, improve c... |
| `emails` | `.agents/skills/emails` | DUPLICATED (byte-identical) | When the user wants to create or optimize an email sequence, drip campaign, automated email flow, or lifecycle... |
| `enterprise-readiness-audit` | `.agents/skills/enterprise-readiness-audit` | DUPLICATED (byte-identical) | Master enterprise-grade SaaS audit â€” 12-domain scored matrix (security, tenant-isolation, DR, SLO, secrets, ... |
| `error-handling-patterns` | `.agents/skills/error-handling-patterns` | .agents only | Master error handling patterns across languages including exceptions, Result types, error propagation, and gra... |
| `executing-plans` | `.agents/skills/executing-plans` | DUPLICATED (byte-identical) | Use when you have a written implementation plan to execute in a separate session with review checkpoints |
| `executive-council` | `.agents/skills/executive-council` | DUPLICATED (byte-identical) | LeadGen Executive Advancement Council â€” revenue/conversion/retention/moat analysis WITHOUT generic repo audi... |
| `fable-operating-manual` | `.agents/skills/fable-operating-manual` | DUPLICATED (byte-identical) | Fable-class agent ka ACTUAL operating model â€” parallel context-gathering, subagent fan-out, task-ledger, ask... |
| `fastapi-templates` | `.agents/skills/fastapi-templates` | .agents only | Create production-ready FastAPI projects with async patterns, dependency injection, and comprehensive error ha... |
| `fde-deploy` | `.agents/skills/fde-deploy` | DUPLICATED (byte-identical) | Use the Forward Deployed Engineer (FDE) agents to "deploy" marketing + website + automation for a client in on... |
| `fde-onboard` | `.agents/skills/fde-onboard` | DUPLICATED (byte-identical) | Full done-for-you client onboarding â€” websiteâ†’KB seed, first content pack, mini-site, lead-capture widget,... |
| `feature-change-flow` | `.agents/skills/feature-change-flow` | DUPLICATED (byte-identical) | Kisi bhi EXISTING feature me change karne ka production-safe flow â€” kahan code hai, kya gate lagana, kaise v... |
| `find-skills` | `.agents/skills/find-skills` | DUPLICATED (byte-identical) | Discover skills â€” FIRST LeadGen's own ~284 skills (~103 in .claude/skills + 181 in data/skills_extra via ski... |
| `finishing-a-development-branch` | `.agents/skills/finishing-a-development-branch` | DUPLICATED (byte-identical) | Use when implementation is complete, all tests pass, and you need to decide how to integrate the work - guides... |
| `free-tools` | `.agents/skills/free-tools` | DUPLICATED (byte-identical) | When the user wants to plan, evaluate, or build a free tool for marketing purposes â€” lead generation, SEO va... |
| `genai-observability` | `.agents/skills/genai-observability` | DUPLICATED (byte-identical) | LLM/agent tracing via OpenTelemetry GenAI semantic conventions for LeadGen â€” per-provider/model/token spans,... |
| `github-actions-docs` | `.agents/skills/github-actions-docs` | DUPLICATED (byte-identical) | Use when users ask how to write, explain, customize, migrate, secure, or troubleshoot GitHub Actions workflows... |
| `github-actions-templates` | `.agents/skills/github-actions-templates` | .agents only | Create production-ready GitHub Actions workflows for automated testing, building, and deploying applications. ... |
| `godmode` | `.agents/skills/godmode` | DUPLICATED (byte-identical) | Production readiness + automation ops via Admin God Mode and Mission Control. Use when user says "god mode", "... |
| `hinglish-copywriting` | `.agents/skills/hinglish-copywriting` | DUPLICATED (byte-identical) | Hinglish copy frameworks (AIDA/PAS/4U) + marketing psychology (loss aversion, social proof, anchoring, honest ... |
| `hostinger-deploy` | `.agents/skills/hostinger-deploy` | DUPLICATED (byte-identical) | Deploy / fix / manage the LeadGen AI platform on the Hostinger KVM VPS (Docker). Use when the user mentions VP... |
| `image` | `.agents/skills/image` | DUPLICATED (byte-identical) | "When the user wants to create, generate, edit, or optimize images for marketing â€” blog heroes, social graph... |
| `integration-engineering` | `.agents/skills/integration-engineering` | DUPLICATED (byte-identical) | Add a new external integration (LLM/telephony/SMS/payment/CRM/storage/webhook/MCP) the LeadGen AI way â€” impo... |
| `investigate` | `.agents/skills/investigate` | DUPLICATED (byte-identical) | Root-cause-first debugging â€” symptom fix se pehle "kyun" pakdo. Use jab error/stack-trace mile, "ye kaam kyu... |
| `k8s-security-policies` | `.agents/skills/k8s-security-policies` | .agents only | Implement Kubernetes security policies including NetworkPolicy, PodSecurityPolicy, and RBAC for production-gra... |
| `kpi-dashboard-design` | `.agents/skills/kpi-dashboard-design` | .agents only | Design effective KPI dashboards with metrics selection, visualization best practices, and real-time monitoring... |
| `launch` | `.agents/skills/launch` | DUPLICATED (byte-identical) | "When the user wants to plan a product launch, feature announcement, or release strategy. Also use when the us... |
| `leadgen-automation-reliability` | `.agents/skills/leadgen-automation-reliability` | DUPLICATED (byte-identical) | Automation reliability hardening â€” Celery workers/beat, scheduled jobs, retries, idempotency, self-improve/c... |
| `leadgen-billing-upi` | `.agents/skills/leadgen-billing-upi` | DUPLICATED (byte-identical) | Manual UPI billing/approval/invoice/plan-activation/entitlement ko operationally safe banao (jab tak full gate... |
| `leadgen-composer` | `.agents/skills/leadgen-composer` | DUPLICATED (byte-identical) | LeadGen AI primary agent brain â€” context-first edits, Hinglish replies, free-stack, council decisions, deplo... |
| `leadgen-customer-journey-e2e` | `.agents/skills/leadgen-customer-journey-e2e` | DUPLICATED (byte-identical) | Pura P1 customer journey end-to-end validate karo â€” jaise ek paying customer. Use jab landing/pricing/signup... |
| `leadgen-email-deliverability` | `.agents/skills/leadgen-email-deliverability` | DUPLICATED (byte-identical) | Email outreach + deliverability hardening â€” account ban se bachao. Use jab SMTP disabled ho, bulk-send se su... |
| `leadgen-infra-doctor` | `.agents/skills/leadgen-infra-doctor` | DUPLICATED (byte-identical) | Deployment infra diagnose + harden â€” Docker, Caddy, FastAPI, workers, scheduler, Redis, Postgres, PgBouncer,... |
| `leadgen-lead-pipeline-quality` | `.agents/skills/leadgen-lead-pipeline-quality` | DUPLICATED (byte-identical) | Lead pipeline quality audit â€” reliable, deduplicated, explainable, useful Indian local-business acquisition.... |
| `leadgen-observability` | `.agents/skills/leadgen-observability` | DUPLICATED (byte-identical) | Enterprise observability â€” logs, metrics, traces, dashboards, alerting, health-checks, audit-logs, job-visib... |
| `leadgen-ops` | `.agents/skills/leadgen-ops` | DUPLICATED (byte-identical) | LeadGen AI ka proven ops loop â€” verify, test, push, deploy + production triage. Use when the user says "depl... |
| `leadgen-product-truth` | `.agents/skills/leadgen-product-truth` | DUPLICATED (byte-identical) | Plans/limits/products/promises ka EK source-of-truth enforce karo. Use jab pricing, packages, feature-gate, pu... |
| `leadgen-repo-learning-governance` | `.agents/skills/leadgen-repo-learning-governance` | DUPLICATED (byte-identical) | External open-source repos se SEEKHNE ka governance â€” pattern extract karo, copy mat karo. Use jab FastAPI-t... |
| `leadgen-revenue-readiness` | `.agents/skills/leadgen-revenue-readiness` | DUPLICATED (byte-identical) | P1 AI Marketing Automation ko SELLABLE banane ka audit â€” kya customer discoverâ†’payâ†’activateâ†’output tak... |
| `leadgen-security-rbac` | `.agents/skills/leadgen-security-rbac` | DUPLICATED (byte-identical) | Security + auth + RBAC + tenant-isolation + secrets + admin-permissions + API-keys + webhooks + PII handling a... |
| `leadgen-start` | `.agents/skills/leadgen-start` | DUPLICATED (byte-identical) | Session bootstrap for LeadGen AI â€” token-efficient way to start ANY task on this project. Use at the start o... |
| `leadgen-test-guardian` | `.agents/skills/leadgen-test-guardian` | DUPLICATED (byte-identical) | Testing discipline enforce karo â€” unit/integration/route-smoke/Celery-task/scheduler/E2E tests, Docker healt... |
| `leadgen-voice-compliance` | `.agents/skills/leadgen-voice-compliance` | DUPLICATED (byte-identical) | P2 voice-calling readiness + compliance gate audit â€” Vobiz/FreeSWITCH, STT/LLM/TTS, DND, consent, opt-out, A... |
| `lead-magnets` | `.agents/skills/lead-magnets` | DUPLICATED (byte-identical) | When the user wants to create, plan, or optimize a lead magnet for email capture or lead generation. Also use ... |
| `llm-council-decision` | `.agents/skills/llm-council-decision` | DUPLICATED (byte-identical) | Claude (session agent) ko Council-style faisla lene ka protocol â€” multi-agent opinions â†’ peer review â†’ C... |
| `llm-error-analysis` | `.agents/skills/llm-error-analysis` | DUPLICATED (byte-identical) | LLM/voice-agent quality girne pe systematic error analysis â€” traces padho (open-coding) â†’ failure taxonomy... |
| `llm-quota-ops` | `.agents/skills/llm-quota-ops` | DUPLICATED (byte-identical) | Free-LLM provider quota/cooldown ops â€” Groq TPD khatam, Cerebras 429 burst, ok-rate tank (0.4 jaisa), fallba... |
| `llm-security` | `.agents/skills/llm-security` | DUPLICATED (byte-identical) | LLM/agent attack-surface defense for LeadGen â€” indirect prompt injection (RAG/inbox/tool-output), jailbreaks... |
| `load-capacity-testing` | `.agents/skills/load-capacity-testing` | DUPLICATED (byte-identical) | Load testing + capacity headroom on single-VPS free stack â€” API rps limits, WEB_CONCURRENCY, PgBouncer pool,... |
| `loop` | `.agents/skills/loop` | DUPLICATED (byte-identical) | Run a prompt or skill on a recurring interval (e.g. check deploy every 5m). Use when the user asks for periodi... |
| `marketing-feature` | `.agents/skills/marketing-feature` | DUPLICATED (byte-identical) | Add a new marketing feature to LeadGen AI the proven way â€” module + API + frontend tab + test + VPS smoke. U... |
| `marketing-ideas` | `.agents/skills/marketing-ideas` | DUPLICATED (byte-identical) | "When the user needs marketing ideas, inspiration, or strategies for their SaaS or software product. Also use ... |
| `marketing-plan` | `.agents/skills/marketing-plan` | DUPLICATED (byte-identical) | When the user needs a comprehensive marketing plan for a client, a company they advise, or their own product. ... |
| `marketing-psychology` | `.agents/skills/marketing-psychology` | DUPLICATED (byte-identical) | "When the user wants to apply psychological principles, mental models, or behavioral science to marketing. Als... |
| `mcp-engineer` | `.agents/skills/mcp-engineer` | DUPLICATED (byte-identical) | Anything MCP â€” /mcp endpoint, MCP-as-product /api/mcp-product/v1/*, A2A Agent Card, mcp_keys, Arya staff age... |
| `memory-vault` | `.agents/skills/memory-vault` | DUPLICATED (byte-identical) | Rowboat-style compounding memory â€” per-prospect/client/topic markdown memory, call-prep briefs, live notes (... |
| `migrate-to-skills` | `.agents/skills/migrate-to-skills` | DUPLICATED (byte-identical) | Convert Cursor rules (.mdc) and slash commands (.md) to Agent Skills (SKILL.md). Use when consolidating rules/... |
| `model-asset-bake` | `.agents/skills/model-asset-bake` | DUPLICATED (byte-identical) | ML model assets (fastembed/silero/whisper/onnx) production me kaise rakhein â€” image-bake, off-loop load, har... |
| `multi-agent-coordination` | `.agents/skills/multi-agent-coordination` | DUPLICATED (byte-identical) | Sahi orchestration primitive chuno â€” coordinator 6 modes (plan/handoff, Reflexion-advanced, hierarchical, fa... |
| `niche-onboarding` | `.agents/skills/niche-onboarding` | DUPLICATED (byte-identical) | Naya niche add karna ya naya client onboard karna LeadGen platform pe. Use when the user says "naya niche", "a... |
| `observability-ops` | `.agents/skills/observability-ops` | DUPLICATED (byte-identical) | Operate and extend the LeadGen AI monitoring stack â€” Prometheus, Grafana, Alertmanager (email), Loki, Tempo,... |
| `offers` | `.agents/skills/offers` | DUPLICATED (byte-identical) | "When the user wants to design, construct, or improve an offer â€” the thing they actually sell â€” including ... |
| `office-hours` | `.agents/skills/office-hours` | DUPLICATED (byte-identical) | "Kya yeh worth building hai?" â€” naya feature/idea ko 6 startup forcing-questions (demand, status-quo pain, s... |
| `onboarding` | `.agents/skills/onboarding` | DUPLICATED (byte-identical) | When the user wants to optimize post-signup onboarding, user activation, first-run experience, or time-to-valu... |
| `orchestrate-goal` | `.agents/skills/orchestrate-goal` | DUPLICATED (byte-identical) | "Mere paas ek goal hai â€” kaunsa automation loop?" â€” self-improve (daily hands-off) vs coordinator (NOW mul... |
| `pairwise-test-design` | `.agents/skills/pairwise-test-design` | DUPLICATED (byte-identical) | Combinatorial (pairwise / PICT) test-case design for LeadGen AI's huge config space â€” niche Ã— band Ã— tier ... |
| `parallel-batch-build` | `.agents/skills/parallel-batch-build` | DUPLICATED (byte-identical) | 10-20 features ek session me parallel sub-agents se banane ka PROVEN pattern (batch-3 me 16 features aise hi b... |
| `paywalls` | `.agents/skills/paywalls` | DUPLICATED (byte-identical) | When the user wants to create or optimize in-app paywalls, upgrade screens, upsell modals, or feature gates. A... |
| `pipeline-hygiene` | `.agents/skills/pipeline-hygiene` | DUPLICATED (byte-identical) | Weekly funnel-data safai â€” junk deals, stale "ready" prospects, reply-classifier drift, bulk-sender leaks. U... |
| `plan-ceo-review` | `.agents/skills/plan-ceo-review` | DUPLICATED (byte-identical) | Bada feature ya product-direction faisla CEO-lens se challenge karo â€” mode (expansion/selective/hold/reducti... |
| `plan-eng-review` | `.agents/skills/plan-eng-review` | DUPLICATED (byte-identical) | Naya feature build se pehle ka engineering review â€” duplicate-route grep, ASCII architecture, state-machine,... |
| `plan-then-build` | `.agents/skills/plan-then-build` | DUPLICATED (byte-identical) | Multi-step build se PEHLE lean plan doc + project pre-checks (duplicate-route grep, file-ownership matrix, fla... |
| `popups` | `.agents/skills/popups` | DUPLICATED (byte-identical) | When the user wants to create or optimize popups, modals, overlays, slide-ins, or banners for conversion purpo... |
| `postgresql-table-design` | `.agents/skills/postgresql-table-design` | .agents only | Use this skill when designing or reviewing a PostgreSQL-specific schema. Covers best-practices, data types, in... |
| `pricing` | `.agents/skills/pricing` | DUPLICATED (byte-identical) | "When the user wants help with pricing decisions, packaging, or monetization strategy. Also use when the user ... |
| `prod-incident-triage` | `.agents/skills/prod-incident-triage` | DUPLICATED (byte-identical) | leadsgenai.in down/unhealthy/freeze â€” health 000, workers stuck, CPU 0%, "automations broken" feel. 3 real p... |
| `production-ready` | `.agents/skills/production-ready` | DUPLICATED (byte-identical) | LeadGen production readiness gate â€” live activation summary, prod_check, cross-path audit, Product-1 vs Prod... |
| `product-marketing` | `.agents/skills/product-marketing` | DUPLICATED (byte-identical) | "When the user wants to create or update their product marketing context document. Also use when the user ment... |
| `product-split-adr` | `.agents/skills/product-split-adr` | DUPLICATED (byte-identical) | Two-product split ADR-009 â€” Marketing vs Voice Agent separate SKUs, pricing truth, copy rules, niches, agent... |
| `programmatic-seo` | `.agents/skills/programmatic-seo` | DUPLICATED (byte-identical) | When the user wants to create SEO-driven pages at scale using templates and data. Also use when the user menti... |
| `prompt-engineering` | `.agents/skills/prompt-engineering` | DUPLICATED (byte-identical) | Prompt-design discipline anchored to LeadGen's free-stack LLM chain â€” cheap-model-robust instructions, Hingl... |
| `prospecting` | `.agents/skills/prospecting` | DUPLICATED (byte-identical) | When the user wants to find, qualify, and build a list of prospects to reach out to â€” across B2B SaaS, gener... |
| `public-relations` | `.agents/skills/public-relations` | DUPLICATED (byte-identical) | "When the user wants help with public relations, earned media, press coverage, journalist outreach, or media s... |
| `python-design-patterns` | `.agents/skills/python-design-patterns` | .agents only | Python design patterns including KISS, Separation of Concerns, Single Responsibility, and composition over inh... |
| `python-performance-optimization` | `.agents/skills/python-performance-optimization` | .agents only | Profile and optimize Python code using cProfile, memory profilers, and performance best practices. Use when de... |
| `python-testing-patterns` | `.agents/skills/python-testing-patterns` | .agents only | Implement comprehensive testing strategies with pytest, fixtures, mocking, and test-driven development. Use wh... |
| `receiving-code-review` | `.agents/skills/receiving-code-review` | DUPLICATED (byte-identical) | Use when receiving code review feedback, before implementing suggestions, especially if feedback seems unclear... |
| `referrals` | `.agents/skills/referrals` | DUPLICATED (byte-identical) | "When the user wants to create, optimize, or analyze a referral program, affiliate program, or word-of-mouth s... |
| `requesting-code-review` | `.agents/skills/requesting-code-review` | DUPLICATED (byte-identical) | Use when completing tasks, implementing major features, or before merging to verify work meets requirements |
| `retro` | `.agents/skills/retro` | DUPLICATED (byte-identical) | Weekly engineering retro â€” git se commits/features/bugs/streak nikaalo, prod-downs + learnings summarize kar... |
| `review` | `.agents/skills/review` | DUPLICATED (byte-identical) | PR/diff code review for the LeadGen AI platform â€” 5-lens critical pass (bugs Â· prod-killers Â· security Â· ... |
| `review-bugbot` | `.agents/skills/review-bugbot` | DUPLICATED (byte-identical) | Bug-focused code review of local changes (Bugbot-style). Use when user asks for /review-bugbot, bug review, or... |
| `revops` | `.agents/skills/revops` | DUPLICATED (byte-identical) | "When the user wants help with revenue operations, lead lifecycle management, or marketing-to-sales handoff pr... |
| `run-campaign` | `.agents/skills/run-campaign` | DUPLICATED (byte-identical) | Run a lead-generation voice campaign for a client â€” scrape prospects for a niche/city, call + qualify them w... |
| `saas-pricing-strategy` | `.agents/skills/saas-pricing-strategy` | DUPLICATED (byte-identical) | Pricing/packaging/discount decisions for LeadGen AI ke DO products â€” Marketing (PUBLIC 2 plans â€” Main â‚¹1... |
| `sales-enablement` | `.agents/skills/sales-enablement` | DUPLICATED (byte-identical) | "When the user wants to create sales collateral, pitch decks, one-pagers, objection handling docs, or demo scr... |
| `scheduler-job` | `.agents/skills/scheduler-job` | DUPLICATED (byte-identical) | Engineer a new scheduled/recurring automation job the LeadGen AI way â€” durable Celery-beat (PRIMARY, live) +... |
| `schema` | `.agents/skills/schema` | DUPLICATED (byte-identical) | When the user wants to add, fix, or optimize schema markup and structured data on their site. Also use when th... |
| `secrets-management` | `.agents/skills/secrets-management` | .agents only | Implement secure secrets management for CI/CD pipelines using Vault, AWS Secrets Manager, or native platform s... |
| `secrets-rotation` | `.agents/skills/secrets-rotation` | DUPLICATED (byte-identical) | Secrets inventory + rotation cadence + leak-response runbook â€” .env keys (LLM providers, Gemini 9-key pool, ... |
| `secure-linux-web-hosting` | `.agents/skills/secure-linux-web-hosting` | DUPLICATED (byte-identical) | Use when setting up, hardening, or reviewing a cloud server for self-hosting, including DNS, SSH, firewalls, N... |
| `security-requirement-extraction` | `.agents/skills/security-requirement-extraction` | .agents only | Derive security requirements from threat models and business context. Use when translating threats into action... |
| `security-review` | `.agents/skills/security-review` | DUPLICATED (byte-identical) | Security + hardening review for the LeadGen AI platform (FastAPI + payments + public endpoints + telephony com... |
| `self-code-review` | `.agents/skills/self-code-review` | DUPLICATED (byte-identical) | Ship se pehle solo-dev multi-pass review â€” bug-hunt, security, signature-drift, hot-path, test-gap â€” 5 ala... |
| `self-improve-control` | `.agents/skills/self-improve-control` | DUPLICATED (byte-identical) | Monitor, audit, aur safely control the self-improve forever-loop â€” health/heartbeat, cost, approvals, lesson... |
| `self-improve-loop` | `.agents/skills/self-improve-loop` | DUPLICATED (byte-identical) | Self-improving CONTINUOUS agent loop (taskâ†’task, no cron timing) â€” architecture + 12 actions + skill_libra... |
| `seo-audit` | `.agents/skills/seo-audit` | DUPLICATED (byte-identical) | When the user wants to audit, review, or diagnose SEO issues on their site. Also use when the user mentions "S... |
| `seo-growth` | `.agents/skills/seo-growth` | DUPLICATED (byte-identical) | SEO + organic-traffic growth for leadsgenai.in (programmatic blog, local SEO, Google Business Profile, schema ... |
| `shell` | `.agents/skills/shell` | DUPLICATED (byte-identical) | Execute literal shell command when user invokes /shell. Use only for explicit /shell requests â€” run command ... |
| `ship-checklist` | `.agents/skills/ship-checklist` | DUPLICATED (byte-identical) | Pre-deploy + deploy + verify checklist for the LeadGen AI live VPS (Docker, leadsgenai.in). Use when shipping ... |
| `signup` | `.agents/skills/signup` | DUPLICATED (byte-identical) | When the user wants to optimize signup, registration, account creation, or trial activation flows. Also use wh... |
| `site-architecture` | `.agents/skills/site-architecture` | DUPLICATED (byte-identical) | When the user wants to plan, map, or restructure their website's page hierarchy, navigation, URL structure, or... |
| `slo-error-budget` | `.agents/skills/slo-error-budget` | DUPLICATED (byte-identical) | SLO definitions + error-budget policy + burn-rate alerts for leadsgenai.in â€” uptime, voice-call success, ema... |
| `sms` | `.agents/skills/sms` | DUPLICATED (byte-identical) | When the user wants to plan, build, or optimize SMS or MMS marketing â€” including welcome flows, abandoned ca... |
| `social` | `.agents/skills/social` | DUPLICATED (byte-identical) | "When the user wants help creating, scheduling, or optimizing social media content for LinkedIn, Twitter/X, In... |
| `source-command-compact-check` | `.agents/skills/source-command-compact-check` | .agents only | "Decide karo ki compact karein ya nayi chat shuru â€” LeadGen AI token discipline (strategic compaction)." |
| `spec` | `.agents/skills/spec` | DUPLICATED (byte-identical) | Vague feature idea ko concrete, build-ready spec banao â€” why/user, existing-code check (duplicate-route grep... |
| `split-to-prs` | `.agents/skills/split-to-prs` | DUPLICATED (byte-identical) | Split current work into small reviewable PRs. Use when user asks to split branch, chat work, or one big diff i... |
| `sql-optimization-patterns` | `.agents/skills/sql-optimization-patterns` | .agents only | Master SQL query optimization, indexing strategies, and EXPLAIN analysis to dramatically improve database perf... |
| `statusline` | `.agents/skills/statusline` | DUPLICATED (byte-identical) | Cursor IDE statusline customization reference. Claude Code has no statusline â€” use for Cursor-only setup or ... |
| `subagent-driven-development` | `.agents/skills/subagent-driven-development` | DUPLICATED (byte-identical) | Use when executing implementation plans with independent tasks in the current session |
| `supabase-postgres-best-practices` | `.agents/skills/supabase-postgres-best-practices` | DUPLICATED (byte-identical) | Postgres performance optimization and best practices from Supabase. Use this skill when writing, reviewing, or... |
| `supply-chain-security` | `.agents/skills/supply-chain-security` | DUPLICATED (byte-identical) | Dependency + build supply-chain hygiene â€” requirements.lock.txt discipline, pip-audit CVE scan, Docker base-... |
| `systematic-debugging` | `.agents/skills/systematic-debugging` | DUPLICATED (byte-identical) | Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes |
| `tdd-contract-first` | `.agents/skills/tdd-contract-first` | DUPLICATED (byte-identical) | Red-green-refactor + "contract tests PEHLE" discipline â€” naya feature/bugfix likhne se pehle failing test, a... |
| `teach-agent-loop` | `.agents/skills/teach-agent-loop` | DUPLICATED (byte-identical) | Extend the self-improve loop safely â€” naya AI agent (staff member) ya naya action/task add karo, risk-assess... |
| `team-access-ops` | `.agents/skills/team-access-ops` | DUPLICATED (byte-identical) | Team member add/remove/modules runbook â€” sub-admin banana, member ko modules dena, password reset, deactivat... |
| `telephony-engineering` | `.agents/skills/telephony-engineering` | DUPLICATED (byte-identical) | Wire and operate telephony providers for LeadGen AI voice calls â€” Vobiz (active, India-native SIP), Twilio, ... |
| `tenant-isolation-audit` | `.agents/skills/tenant-isolation-audit` | DUPLICATED (byte-identical) | Multi-tenant isolation deep-audit â€” tenant middleware FAIL-OPEN risk, IDOR sweep beyond billing, per-tenant ... |
| `test-agent` | `.agents/skills/test-agent` | DUPLICATED (byte-identical) | Test the AI voice agent before going live â€” run the persona eval suite, have a text/web conversation, or che... |
| `test-driven-development` | `.agents/skills/test-driven-development` | DUPLICATED (byte-identical) | Use when implementing any feature or bugfix, before writing implementation code |
| `update-claude-settings` | `.agents/skills/update-claude-settings` | DUPLICATED (byte-identical) | Update project memory and agent settings â€” CLAUDE.md, AGENTS.md, .cursor/rules. Use when user wants to persi... |
| `update-cli-config` | `.agents/skills/update-cli-config` | DUPLICATED (byte-identical) | Update Claude Code or Cursor CLI configuration files. Use when user asks to change CLI model, permissions, or ... |
| `using-git-worktrees` | `.agents/skills/using-git-worktrees` | DUPLICATED (byte-identical) | Use when starting feature work that needs isolation from current workspace or before executing implementation ... |
| `using-superpowers` | `.agents/skills/using-superpowers` | DUPLICATED (byte-identical) | Use when starting any conversation - establishes how to find and use skills, requiring skill invocation before... |
| `uv-package-manager` | `.agents/skills/uv-package-manager` | .agents only | Master the uv package manager for fast Python dependency management, virtual environments, and modern Python p... |
| `verification-before-completion` | `.agents/skills/verification-before-completion` | DUPLICATED (byte-identical) | Use when about to claim work is complete, fixed, or passing, before committing or creating PRs - requires runn... |
| `verify-ship` | `.agents/skills/verify-ship` | DUPLICATED (byte-identical) | LeadGen pre-ship verify and deploy loop â€” prod_check, pytest, secrets scan, explorer_sync, git push, VPS Doc... |
| `video` | `.agents/skills/video` | DUPLICATED (byte-identical) | "When the user wants to create, generate, or produce video content using AI tools or programmatic frameworks. ... |
| `voice-agent-kb` | `.agents/skills/voice-agent-kb` | DUPLICATED (byte-identical) | LeadGen AI voice agent internals knowledge base â€” TelecallerBrain vs NaturalDialog, free_ai provider chain, ... |
| `voice-eval-metrics` | `.agents/skills/voice-eval-metrics` | DUPLICATED (byte-identical) | Objective ASR/TTS/latency metrics for LeadGen's FREE voice stack (Groq-whisper STT + EdgeTTS), upgrading agent... |
| `voice-humanization` | `.agents/skills/voice-humanization` | DUPLICATED (byte-identical) | PHONE voice agent (vobiz) ko human-like banane ka project pattern â€” Groq STT chain, TelecallerBrain, fillers... |
| `voice-roles` | `.agents/skills/voice-roles` | DUPLICATED (byte-identical) | Swara telecaller, Ananya appointment booker, Riya receptionist â€” voice role wiring, prompts, test-call flow,... |
| `watch` | `.agents/skills/watch` | DUPLICATED (byte-identical) | Watch a video (URL or local path). Downloads with yt-dlp, extracts auto-scaled frames with ffmpeg, pulls the t... |
| `web-call-triage` | `.agents/skills/web-call-triage` | DUPLICATED (byte-identical) | User bole "web call pe agent slow hai / sunta nahi / atak jata / noob lagta hai" â€” FREE web-call (/app/test-... |
| `web-performance` | `.agents/skills/web-performance` | DUPLICATED (byte-identical) | Web performance + Core Web Vitals review for the LeadGen AI public pages (landing, /pricing, /audit, /blog, /b... |
| `windows-dev-gotchas` | `.agents/skills/windows-dev-gotchas` | DUPLICATED (byte-identical) | Windows dev environment gotchas for LeadGen â€” stale sandbox, Git ssh, curl.exe, VPS deploy quoting, bat logs... |
| `writing-plans` | `.agents/skills/writing-plans` | DUPLICATED (byte-identical) | Use when you have a spec or requirements for a multi-step task, before touching code |
| `writing-skills` | `.agents/skills/writing-skills` | DUPLICATED (byte-identical) | Use when creating new skills, editing existing skills, or verifying skills work before deployment |
