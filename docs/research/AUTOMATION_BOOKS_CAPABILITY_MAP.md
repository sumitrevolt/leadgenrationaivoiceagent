# AUTOMATION BOOKS → SKILLS → RUNTIME CAPABILITY MAP

> FreeBuff mission artifact · Fresh integration worktree `freebuff/automation-opportunity-discovery-integration-20260809` (base = `origin/main` `cad958ce`) · Date: 2026-08-09 · STATUS: LOCAL-ONLY — transplanted, not committed/pushed/merged/deployed. (Historical source-worktree base was `a42d869c`.)
> Companion files: `BOOK_SOURCES_LEDGER.md` (full 18-book ledger) · `SKILL_OVERLAP_MATRIX.md` (existing-skill comparison) · `GAP_MANIFEST_AND_VERIFICATION.md` (gap manifest + evidence ledger + rollback).
> Evidence labels: PRODUCTION-PROVEN · CODE-PRESENT · TEST-PROVEN · LOCAL-ONLY · PARTIAL · STALE · UNKNOWN. Nothing here claims full-text book inspection; see ledger.

## 1. Goal

Public research se automation/marketing/RevOps/AI-agent/agency-ops books ke principles ko copyright-safe tarike se distil karo → existing `.claude/skills` catalog (~280 skills) se overlap compare karo → genuine gap par 1 lean canonical skill banayo → repo runtime + launch/revenue/automation readiness se map karo → safe vertical slice verify karo. Book = teacher, text donor nahi.

## 2. Method

1. 18 credible books scanned via authoritative publisher/catalog metadata (North River Press, IT Revolution, O'Reilly, Wiley, Penguin Random House, BenBella, Page Two, etc.).
2. Access honesty: metadata + public previews/summaries inspected; **no pirated PDF, no full-text copy, no paywall bypass** (some search results surfaced pirate PDFs — explicitly NOT used).
3. Principles distilled in original LeadGen-specific language; attribution ledger kept separately; zero distinctive prose/checklists/templates reproduced.
4. Repo truth: `CLAUDE.md` §1–§8, `progress.md` (loop ledger), `docs/context/{CURRENT_STATE,ACTIVE_WORK,SESSION_HANDOFF}.md`, `memory/INDEX.md`, skill inventory, skill-eval tooling (`scripts/skill_evals/`), canonical guard test.
5. Active workstreams respected: WS-PRF1 (PR Factory), WS-GTM1 (Hot Queue → 2nd paid, revenue/owner-gated), WS-GTM2 (admin call + voice — **voice frozen**). Overlapping product-code lanes → marked `WAIT — OVERLAPPING WRITER`.

## 3. Capability groups covered

| Group | Books scanned | Existing repo coverage |
|---|---|---|
| AI marketing agency operating systems | E-Myth, Traction, 1-Page Marketing Plan, Predictable Revenue | `automation-pipeline`, `automation-control-center`, `leadgen-customer-journey-e2e`, `fde-onboard`, `niche-onboarding`, `executive-council` |
| Client acquisition → retention/expansion | Predictable Revenue, Customer Success, 1-Page Marketing Plan | `prospecting`, `cold-email`, `leadgen-email-deliverability`, `churn-prevention`, `onboarding`, `revops`, `leadgen-revenue-readiness` |
| CRM / lifecycle / lead scoring / RevOps | Predictable Revenue, Customer Success | `revops`, `leadgen-lead-pipeline-quality`, `sales-enablement`, `pipeline-hygiene` |
| Content/email/social/SEO/campaign automation | 1-Page Marketing Plan, Made to Stick | `emails`, `content-strategy`, `social`, `seo-audit`, `programmatic-seo`, `copywriting`, `hinglish-copywriting`, `lead-magnets` |
| AI agents, approval, memory, RAG, eval, guardrails | (no dedicated book scanned in top-18 — covered by existing repo skills) | `agent-loop-design`, `agent-harness-standard`, `llm-security`, `eval`-adjacent, `coordinator-orchestration` |
| Business-process / workflow automation | E-Myth, Traction, The Goal | `automation-control-center`, `scheduler-job`, `process_engine`, `agent-loop-design` |
| Automation project discovery/delivery/change mgmt | The Goal, Lean Startup, Running Lean, Phoenix Project, Checklist Manifesto | `feature-change-flow`, `plan-then-build`, `verify-ship`, `fable-operating-manual`, `verify-ship` — **gap: no executable "what to automate next" discovery/scoring procedure** → new skill |
| Event-driven / queues / retries / idempotency / DLQ | DDIA, Release It! | `leadgen-automation-reliability`, `error-handling-patterns`, `integration-engineering`, `agent-loop-design` |
| Observability / SRE / security / rollback | Accelerate, Phoenix Project, Release It!, Checklist Manifesto | `leadgen-observability`, `observability-ops`, `prod-incident-triage`, `slo-error-budget`, `secrets-rotation`, `careful`, `ship-checklist` |
| SaaS launch / monetisation / activation / retention | Lean Startup, Running Lean, Customer Success, Hooked | `launch`, `signup`, `paywalls`, `onboarding`, `directory-submissions`, `saas-pricing-strategy`, `pricing` |

## 4. 18-book scan (authoritative metadata; full ledger in BOOK_SOURCES_LEDGER.md)

| # | Book (author) | Publisher/year | Capability group | Verdict |
|---|---|---|---|---|
| 1 | The Goal (Goldratt & Cox) | North River Press, 30th Anniv | Process/constraint thinking | MERGE → new discovery skill |
| 2 | Accelerate (Forsgren, Humble, Kim) | IT Revolution, 2018 | Delivery metrics, change mgmt | MERGE → new discovery skill |
| 3 | The Lean Startup (Ries) | Crown Business, 2011 | Validate-before-build | MERGE → new discovery skill |
| 4 | Running Lean (Maurya) | O'Reilly, 2012 | Problem/solution fit, canvases | MERGE → new discovery skill |
| 5 | The Phoenix Project (Kim, Behr, Spafford) | IT Revolution, 2013 | Work types, flow, unplanned work | MERGE → new discovery skill |
| 6 | The Checklist Manifesto (Gawande) | Metropolitan, 2009 | Pre-flight checklists, discipline | MERGE → new discovery skill |
| 7 | DDIA (Kleppmann) | O'Reilly, 2017 | Reliability/event-driven | REJECT (covered by leadgen-automation-reliability) |
| 8 | Release It! (Nygard) 2nd ed | Pragmatic, 2018 | Stability patterns | REJECT (covered by error-handling-patterns/integration-engineering) |
| 9 | The E-Myth Revisited (Gerber) | HarperCollins | Agency/owner systems | MERGE (low weight) |
| 10 | Traction / EOS (Wickman) | BenBella | Operating rhythm, accountability | MERGE (low weight) |
| 11 | Predictable Revenue (Ross & Tyler) | Pebblestorm, 2011 | Outbound/revenue ops | REJECT (covered by cold-email/prospecting/revops/automation-pipeline) |
| 12 | The 1-Page Marketing Plan (Dib) | Page Two, 2016 | Lead-gen funnel | REJECT (covered by marketing-plan/conversion-optimization) |
| 13 | The Mom Test (Fitzpatrick) | Robfitz, 2013 | Customer conversations | REJECT (covered by customer-research) |
| 14 | Obviously Awesome (Dunford) | 2019 | Positioning | REJECT (covered by product-marketing) |
| 15 | Don't Make Me Think Revisited (Krug) | New Riders, 2014 | Web usability | REJECT (covered by design-review) |
| 16 | Made to Stick (Heath) | Random House, 2007 | Messaging stickiness | REJECT (covered by copywriting/hinglish-copywriting) |
| 17 | Hooked (Eyal) | Portfolio, 2014 | Habit/retention | REJECT (covered by onboarding/churn-prevention) |
| 18 | Customer Success (Mehta, Steinman, Murphy) | Wiley, 2016 | CS/retention/expansion | REJECT (covered by churn-prevention/revops/onboarding) |

Shortlist (distinct, project-relevant): **The Goal, Accelerate, Lean Startup, Running Lean, Phoenix Project, Checklist Manifesto** (primary) + **E-Myth, Traction** (secondary). Others rejected: covered or low-fit.

## 5. Principle → skill → runtime capability → revenue outcome

| Book principle (distilled) | Where it lands | Runtime entrypoint | Revenue outcome |
|---|---|---|---|
| Constraint-first: bottleneck fixes throughput, not new top-funnel (The Goal) | New skill `automation-opportunity-discovery` §Score; already embedded in `fable-operating-manual` C1 | Hot Queue `/app/inbox`, sales_autopilot, dialer sprint | 2nd paid customer (mid-funnel) |
| Automate the proven, not the hoped; 10× manual first (Lean Startup, Running Lean) | New skill §Gate | gated engines default OFF (`AUTOMATION_FLAGS` in `app/api/growth.py`) | no wasted spend/ban risk |
| Work types: business-project / internal / changes / unplanned (Phoenix Project) | New skill §Discover | scheduler jobs (`STAFF_JOBS`, Celery beat) | stable delivery, no unplanned firefights |
| Delivery cadence + change-failure measurement (Accelerate) | New skill §Measure; existing `slo-error-budget`, `ship-checklist` | `/health` + `automation_health.EXPECTED_GAP_MIN` | reliable go-live |
| Pre-flight checklist / verification discipline (Checklist Manifesto) | New skill §Gate; existing `verify-ship`, `production-ready` | `scripts/prod_check.py` | no red deploy |
| Opportunity scoring = frequency × effort × risk × revenue (synthesis) | New skill §Score | backlog → `memory/backlog.md` | ranked roadmap |
| Canary → evidence → kill-fast (Lean Startup + Phoenix Project) | New skill §Run; existing `automation-flags`, `agent-loop-design` dead-man trio | flag OFF rollback, `.env.bak-*` | no zombie loop |

## 6. Gap manifest (summary — detail in GAP_MANIFEST_AND_VERIFICATION.md)

- **G1 — MISSING SKILL (genuine):** executable "automation opportunity discovery & scoring" procedure. Principles scattered across `fable-operating-manual` (Part C), `advancement-roadmap`, `executive-council` — koi repeatable, repo-grounded procedure nahi jo owner/agent ko "kya automate karein, kya skip, canary kab, kill kab" bataye. → **SHIPPED as `automation-opportunity-discovery`** (canonical `.claude/skills/`, trigger-cases, book-sources ledger).
- **G2 — Existing-skill needs improvement:** none this pass (skill catalog already deep; touching owned skills = overlapping-writer risk).
- **G3 — Missing implementation / wiring / tests / observability:** all candidate product-code gaps land on ACTIVE_WORK lanes (WS-GTM1 revenue, WS-PRF1) or frozen surfaces (voice) → `WAIT — OVERLAPPING WRITER` or owner-gated. No speculative code shipped.

## 7. Implemented slice (safe vertical)

1. `docs/research/AUTOMATION_BOOKS_CAPABILITY_MAP.md` (this file)
2. `docs/research/BOOK_SOURCES_LEDGER.md`
3. `docs/research/SKILL_OVERLAP_MATRIX.md`
4. `docs/research/GAP_MANIFEST_AND_VERIFICATION.md`
5. `.claude/skills/automation-opportunity-discovery/SKILL.md` (new canonical skill)
6. `.claude/skills/automation-opportunity-discovery/references/book-sources.md` (skill-scoped ledger)
7. `scripts/skill_evals/cases/automation-opportunity-discovery/trigger-cases.json` (11 cases)

No product/runtime code changed, no flag flipped, no commit/push/deploy. Verification: skill CI + canonical guard + secrets + prod_check + git diff --check (ledger in GAP_MANIFEST_AND_VERIFICATION.md).

## 8. Readiness verdicts (full evidence in final report)

Product 1 (Marketing): money path CODE-PRESENT + TEST-PROVEN, 1 real paid customer PRODUCTION-PROVEN; 2nd paid = owner-gated (Hot Queue + manual UPI confirm). Product 2 (Voice): DLT/compliance-gated, frozen — audit only. Revenue: path ready, **actual 2nd revenue NOT PROVEN**. Automation: scheduler/Celery parity + flags TEST-PROVEN; per-job outcome evidence partial. Enterprise: 12-domain matrix mostly evidence-backed; gaps = owner/credential actions. Production: exact-SHA deploy PROVEN; latest release review pending owner.
