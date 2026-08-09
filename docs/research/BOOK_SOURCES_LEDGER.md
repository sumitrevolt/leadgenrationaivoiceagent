# BOOK SOURCES LEDGER — 18-book scan with legal-access & attribution notes

> FreeBuff mission artifact · Date: 2026-08-09 · Companion: `AUTOMATION_BOOKS_CAPABILITY_MAP.md`.
> **Access honesty:** har book ka record batata hai ki kaunsa access level actually inspected tha. Kisi bhi book ka full text pirated/shad ow-source se nahi liya gaya; only authoritative publisher/catalog metadata + public previews/summaries. Principles = widely-publicised frameworks (TOC, Build-Measure-Learn, DORA, Hook Model, etc.) ko LeadGen-specific language me independently rewrite kiya gaya — **koi distinctive prose, checklist, diagram, ya template copy nahi**.
>
> Evidence tiers used throughout:
> - **D (Direct source evidence):** publisher/catalog page or official author page inspected.
> - **P (Publisher/author summary):** official description of the work.
> - **S (Secondary interpretation):** reputable summaries/reviews (used only to locate frameworks, never as primary evidence).
> - **F (FreeBuff synthesis):** our own distillation.
> - **A (LeadGen adaptation):** repo-specific operational form.

## Decision key
- **MERGE** = contribute principles to the new `automation-opportunity-discovery` skill (capability-centred, not book-centred).
- **REJECT-covered** = equivalent existing `.claude/skills` capability already present (see SKILL_OVERLAP_MATRIX.md).

---

## 1. The Goal: A Process of Ongoing Improvement (Goldratt & Cox)
- Edition/year: 4th revised (30th Anniversary), 2014; 40th Anniversary ed. 2024 · ISBN 978-0-88427-195-6 · Publisher: North River Press
- URL: https://northriverpress.com/the-goal-30th-anniversary-edition/ · Wikipedia: https://en.wikipedia.org/wiki/The_Goal_(novel)
- Access inspected: D (publisher page), P. No full text.
- Category: Business-process / constraint thinking (Theory of Constraints — Five Focusing Steps)
- Useful principles: identify the constraint → exploit → subordinate → elevate → repeat; throughput vs inventory vs operating expense; "automating the constraint-less step is waste".
- LeadGen relevance: HIGH — mid-funnel is the constraint (Hot Queue), not top-funnel volume (matches CLAUDE.md sprint + `fable-operating-manual` C1).
- Existing-skill overlap: `fable-operating-manual` Part C already codifies constraint-first. No dedicated procedure.
- Copyright: © Goldratt/Cox — principles only, independently written. No quotation reproduced.
- Decision: **MERGE** (primary source for discovery-skill §Score).

## 2. Accelerate: The Science of Lean Software and DevOps (Forsgren, Humble, Kim)
- Edition: 1st, 2018 · ISBN 978-1-942788-33-1 · Publisher: IT Revolution
- URL: https://itrevolution.com/product/accelerate/ · O'Reilly: https://www.oreilly.com/library/view/accelerate/9781457191435/
- Access inspected: D (publisher + O'Reilly), P.
- Category: Delivery performance measurement (DORA 4: deploy frequency, lead time, change-failure rate, MTTR); "measure outcomes, not output".
- Useful principles for this repo: change-failure rate as the automation-governance KPI; small batches; blame-free rollback; automation of proven steps.
- LeadGen relevance: HIGH — maps to `slo-error-budget`, `ship-checklist`, and the new skill's §Measure.
- Existing-skill overlap: `slo-error-budget`, `observability-ops`, `ship-checklist`.
- Copyright: © IT Revolution — no reproduction.
- Decision: **MERGE** (measurement/canary section).

## 3. The Lean Startup (Eric Ries)
- Edition: 1st, 2011 · ISBN 978-0-307-88789-4 · Publisher: Crown Business (Penguin Random House)
- URL: https://www.penguinrandomhouse.com/books/210088/the-lean-startup-by-eric-ries/ · Author site: https://theleanstartup.com/
- Access inspected: D (publisher), P.
- Category: Build-Measure-Learn; validated learning; MVP; pivot-or-persevere.
- Useful principles: automate only what is proven by real (not vanity) metrics; small validated experiments before scale.
- LeadGen relevance: HIGH — "automate the proven" is already a house rule (`fable-operating-manual` C1.2, `platform_dial` history); this skill makes it executable (canary → evidence → kill).
- Existing-skill overlap: `ab-testing`, `executive-council`, `fable-operating-manual`.
- Copyright: © Eric Ries — no reproduction.
- Decision: **MERGE** (validate-first gate).

## 4. Running Lean (Ash Maurya)
- Edition: 2nd, 2012 · ISBN 978-1-449-30517-8 · Publisher: O'Reilly Media
- URL: https://www.oreilly.com/library/view/running-lean-2nd/9781449321529/ · ACM: https://dl.acm.org/doi/10.5555/2663440
- Access inspected: D (O'Reilly), P.
- Category: Problem/solution fit before product/solution fit; Lean Canvas; continuous customer interviews.
- Useful principles: document the manual workflow + its failure modes BEFORE building automation; score the problem by frequency/pain before the solution by features.
- LeadGen relevance: MEDIUM-HIGH — the "map manual process first" step of the new skill.
- Existing-skill overlap: `customer-research`, `brainstorming`, `writing-plans`.
- Copyright: © Ash Maurya/O'Reilly — no reproduction.
- Decision: **MERGE** (discover step).

## 5. The Phoenix Project (Kim, Behr, Spafford)
- Edition: 1st, 2013 · ISBN 978-0-9882625-9-1 · Publisher: IT Revolution
- URL: https://itrevolution.com/product/the-phoenix-project/ · Simon & Schuster: https://www.simonandschuster.com/books/The-Phoenix-Project/Gene-Kim/The-Phoenix-Project/9781942788300
- Access inspected: D (publisher), P.
- Category: Work types (business project / internal IT / change / unplanned work); the "Three Ways" (flow, feedback, continuous improvement); deployment pipeline discipline.
- Useful principles: unplanned work destroys throughput; a change that can't be rolled back isn't finished; small-batch releases.
- LeadGen relevance: HIGH — maps 1:1 to repo's deploy discipline (`deploy_vps.sh` rollback, `ship-checklist`, unplanned-work = incident firefights in `prod-incident-triage`).
- Existing-skill overlap: `feature-change-flow`, `ship-checklist`, `prod-incident-triage`, `agent-loop-design`.
- Copyright: © Kim/Behr/Spafford, IT Revolution — no reproduction.
- Decision: **MERGE** (work-types triage in §Discover).

## 6. The Checklist Manifesto (Atul Gawande)
- Edition: 1st, 2009 · ISBN 978-0-8050-9174-8 · Publisher: Metropolitan Books (Macmillan)
- URL: https://us.macmillan.com/books/9780805091748/thechecklistmanifesto/ · Author: https://atulgawande.com/book/the-checklist-manifesto/
- Access inspected: D (publisher + author), P.
- Category: Pre-flight checklists; the power of the "killer item"; discipline beats memory in complex operations.
- Useful principles: a short pre-flight checklist for irreversible/complex steps; "checklist = shared verification, not checkbox theatre".
- LeadGen relevance: HIGH — the repo's verification culture (`prod_check.py`, `verify-ship`, `careful`) is a checklist discipline; new skill's §Gate encodes a 5-item pre-flight.
- Existing-skill overlap: `verify-ship`, `careful`, `ship-checklist`, `production-ready`.
- Copyright: © Atul Gawande — no reproduction.
- Decision: **MERGE** (pre-flight gate).

## 7. Designing Data-Intensive Applications (Martin Kleppmann)
- Edition: 1st, 2017 · ISBN 978-1-449-37332-0 · Publisher: O'Reilly Media
- URL: https://www.oreilly.com/library/view/designing-data-intensive-applications/9781491903063/
- Access inspected: D (O'Reilly), P.
- Category: Reliability/scalability/maintainability; event-driven systems; idempotency; exactly-once semantics; replication.
- LeadGen relevance: MEDIUM — repo already implements these (`dlq:failed_tasks`, idempotency keys, Celery durable, PgBouncer) and codifies them in `leadgen-automation-reliability`.
- Existing-skill overlap: `leadgen-automation-reliability`, `db-migration-safety`, `agent-loop-design`, `integration-engineering`.
- Copyright: © Kleppmann/O'Reilly — no reproduction.
- Decision: **REJECT-covered.**

## 8. Release It! (Michael Nygard)
- Edition: 2nd, 2018 · ISBN 978-1-68050-239-8 · Publisher: The Pragmatic Bookshelf
- URL: https://pragprog.com/titles/mnee2/release-it-second-edition/
- Access inspected: D (Pragmatic), P.
- Category: Stability patterns (circuit breaker, bulkhead, timeout, retry-with-backoff, chaos).
- LeadGen relevance: MEDIUM — patterns already live (`free_ai.py` escalating circuit breaker, per-call timeouts, bounded retries) and codified in `integration-engineering` + `error-handling-patterns`.
- Existing-skill overlap: `error-handling-patterns`, `integration-engineering`, `leadgen-automation-reliability`.
- Copyright: © Nygard/Pragmatic — no reproduction.
- Decision: **REJECT-covered.**

## 9. The E-Myth Revisited (Michael E. Gerber)
- Edition: Revised, 1995 (ISBN 978-0-88730-728-7) · Publisher: HarperCollins
- URL: https://www.harpercollins.com/products/the-e-myth-revisited-michael-e-gerber
- Access inspected: D (publisher), P.
- Category: Agency/business owner systems — work ON the business, not IN it; the franchise prototype.
- Useful principles: document each repeatable client workflow as a system; owner time is the scarce asset (buy back founder time).
- LeadGen relevance: MEDIUM — the FDE/onboarding "systems not heroics" pattern (`fde-onboard`, `niche-onboarding`).
- Existing-skill overlap: `fde-onboard`, `automation-control-center`, `admin-friendly-ux`.
- Copyright: © Gerber/HarperCollins — no reproduction.
- Decision: **MERGE (secondary)** — owner-time rule feeds §Score "owner-time saved" axis.

## 10. Traction / EOS (Gino Wickman)
- Edition: 1st, 2012 · ISBN 978-1-936661-83-1 · Publisher: BenBella Books
- URL: https://benbellabooks.com/shop/traction/ · https://www.eosworldwide.com/traction-book
- Access inspected: D (publisher + EOS), P.
- Category: Operating rhythm (quarterly rocks, weekly L10, scorecard, accountability chart).
- Useful principles: one metric that matters (scorecard); weekly operating cadence; clear owner for every issue.
- LeadGen relevance: MEDIUM — maps to `/app/automation` Mission Control + `admin-friendly-ux` "Aaj" tab + `automation_health` scorecard.
- Existing-skill overlap: `admin-friendly-ux`, `automation-control-center`, `executive-council`.
- Copyright: © Wickman/BenBella — no reproduction.
- Decision: **MERGE (secondary)** — cadence/scorecard rule feeds §Run cadence.

## 11. Predictable Revenue (Aaron Ross & Marylou Tyler)
- Edition: 1st, 2011 · ISBN 978-0-9843802-1-3 · Publisher: Pebblestorm
- URL: https://www.amazon.com/dp/0984380213 · Google Books record.
- Access inspected: D (catalog), P.
- Category: Outbound sales machine (cold email 2.0, seeded/event-based prospecting, qualified pipeline).
- LeadGen relevance: HIGH conceptually, but repo already operationalises it: `cold-email`/`cold-email-craft` (Hinglish outreach), `prospecting`, `automation-pipeline`, `sales_autopilot`, Hot Queue triage.
- Existing-skill overlap: `cold-email`, `prospecting`, `automation-pipeline`, `leadgen-revenue-readiness`.
- Copyright: © Ross & Tyler/Pebblestorm — no reproduction.
- Decision: **REJECT-covered.**

## 12. The 1-Page Marketing Plan (Allan Dib)
- Edition: 1st, 2016 · ISBN 978-1-989603-68-0 · Publisher: Page Two
- URL: https://www.porchlightbooks.com/products/1page-marketing-plan-allan-dib-9781989603680
- Access inspected: D (catalog), P.
- Category: 3-phase funnel (before/during/after) on one page; offer-led growth.
- LeadGen relevance: MEDIUM — repo funnel (`/audit` → inquiry → pricing → `/start` → UPI) already implements the before/during/after structure; copy/planning skills own the messaging.
- Existing-skill overlap: `marketing-plan`, `conversion-optimization`, `lead-magnets`, `offers`.
- Copyright: © Dib/Page Two — no reproduction.
- Decision: **REJECT-covered.**

## 13. The Mom Test (Rob Fitzpatrick)
- Edition: 1st, 2013 · ISBN 978-1-4921-8074-6 (self-pub Robfitz) · momtestbook.com
- URL: https://www.momtestbook.com/
- Access inspected: D (author site), P.
- Category: Customer conversation technique (ask about past behaviour, not opinions/pledges; commitments > compliments).
- LeadGen relevance: MEDIUM — repo has `customer-research` (interviews, transcripts, review mining) with the same anti-vanity-signal doctrine.
- Existing-skill overlap: `customer-research`, `prospecting`.
- Copyright: © Fitzpatrick — no reproduction.
- Decision: **REJECT-covered.**

## 14. Obviously Awesome (April Dunford)
- Edition: 1st, 2019 · ISBN 978-1-9990230-0-9 · self-published (April Dunford)
- URL: https://www.aprildunford.com/books
- Access inspected: D (author), P.
- Category: Positioning (competitive alternatives, unique attributes, value, audience, market category).
- LeadGen relevance: MEDIUM-HIGH — DO-product split (Marketing vs Voice) + `product-marketing` skill own this; repo ADR `product-split-adr` already enforces separate framing.
- Existing-skill overlap: `product-marketing`, `product-split-adr`, `marketing-plan`.
- Copyright: © Dunford — no reproduction.
- Decision: **REJECT-covered.**

## 15. Don't Make Me Think, Revisited (Steve Krug)
- Edition: 3rd ("Revisited"), 2014 · ISBN 978-0-321-96551-6 · Publisher: New Riders
- URL: https://sensible.com/dont-make-me-think/ (author)
- Access inspected: D (author), P.
- Category: Web usability (self-evident pages, scanability, no-thinking navigation).
- LeadGen relevance: MEDIUM — repo `design-review` skill operationalises the same craft with real preview tools (380px, dark, contrast).
- Existing-skill overlap: `design-review`, `cro`, `web-performance`.
- Copyright: © Krug/New Riders — no reproduction.
- Decision: **REJECT-covered.**

## 16. Made to Stick (Chip & Dan Heath)
- Edition: 1st, 2007 · ISBN 978-1-4000-6428-1 · Publisher: Random House
- URL: https://www.penguinrandomhouse.com/books/77687/made-to-stick-by-chip-and-dan-heath/
- Access inspected: D (publisher), P.
- Category: Idea stickiness (SUCCESs: simple, unexpected, concrete, credible, emotional, stories).
- LeadGen relevance: MEDIUM — repo's Hinglish copywriting + ad-creative + post-generator prompts already encode concrete/specific/honest-urgency doctrine.
- Existing-skill overlap: `copywriting`, `hinglish-copywriting`, `ad-creative`, `copy-editing`.
- Copyright: © Heath/PRH — no reproduction.
- Decision: **REJECT-covered.**

## 17. Hooked (Nir Eyal & Ryan Hoover)
- Edition: Revised, 2014 · ISBN 978-1-59184-778-6 · Publisher: Portfolio (Penguin)
- URL: https://www.penguinrandomhouse.com/books/317898/hooked-by-nir-eyal/ · https://www.nirandfar.com/hooked/
- Access inspected: D (publisher + author), P.
- Category: Habit loop (trigger → action → variable reward → investment).
- LeadGen relevance: LOW-MEDIUM — customer portal retention levers exist (`onboarding`, `churn-prevention`); habit-design is not a current product focus.
- Existing-skill overlap: `onboarding`, `churn-prevention`, `signup`.
- Copyright: © Eyal/Portfolio — no reproduction.
- Decision: **REJECT-covered.**

## 18. Customer Success (Mehta, Steinman, Murphy)
- Edition: 1st, 2016 · ISBN 978-1-119-16830-0 · Publisher: Wiley
- URL: https://www.wiley.com/en-us/customer-success-how-innovative-companies-are-reducing-churn-and-growing-recurring-revenue-p-9781119168300
- Access inspected: D (publisher), P.
- Category: Customer success = retention + expansion (health score, lifecycle touchpoints, churn-driver reduction).
- LeadGen relevance: MEDIUM-HIGH — repo `churn-prevention`, `revops`, `onboarding`, `admin-friendly-ux` (customer portal content) cover the doctrine; expansion = 1 client → upsell Combo ₹5,999.
- Existing-skill overlap: `churn-prevention`, `revops`, `onboarding`, `leadgen-revenue-readiness`.
- Copyright: © Mehta/Steinman/Murphy/Wiley — no reproduction.
- Decision: **REJECT-covered.**

---

## Copyright / licence review

- Saare 18 books are copyrighted works (© authors/publishers). No open-licence material adapted; therefore **no licence file is added and no licence is falsely asserted** on any skill content.
- The new skill contains **independent, project-specific writing** derived from general principles (publicly known frameworks), with zero reproduction of book prose, chapter structure, diagrams, tables, checklists, or templates.
- `references/book-sources.md` in the skill keeps the same ledger discipline so attribution travels with the skill.

## Evidence-tier note

- D/P tiers used for metadata and locating frameworks; the **behavioural content** of the new skill is F/A tier (FreeBuff synthesis + LeadGen adaptation), grounded in repo truth (CLAUDE.md, progress.md, memory/, skill catalog, tests).
