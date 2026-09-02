# SKILL OVERLAP MATRIX — book principles vs existing `.claude/skills` catalog

> FreeBuff mission artifact · Date: 2026-08-09. Catalog root `.claude/skills/` (canonical, ADR-131); ~280 skills. Rule applied: **update/merge into an existing skill when it owns the workflow; create only for a genuine behavioural gap; never duplicate**.

## A. Book → existing-skill coverage table

| Book principle cluster | Owning existing skill(s) | Coverage verdict |
|---|---|---|
| Outbound sales machine (Predictable Revenue) | `cold-email`, `cold-email-craft`, `prospecting`, `automation-pipeline`, `leadgen-revenue-readiness` | COVERED — reject |
| 3-phase funnel / offer-led growth (1-Page Marketing Plan) | `marketing-plan`, `conversion-optimization`, `lead-magnets`, `offers` | COVERED — reject |
| Customer conversation technique (Mom Test) | `customer-research`, `prospecting` | COVERED — reject |
| Positioning (Obviously Awesome) | `product-marketing`, `product-split-adr` | COVERED — reject |
| Web usability (Don't Make Me Think) | `design-review`, `cro`, `web-performance` | COVERED — reject |
| Messaging stickiness (Made to Stick) | `copywriting`, `hinglish-copywriting`, `ad-creative`, `copy-editing` | COVERED — reject |
| Habit/retention (Hooked) | `onboarding`, `churn-prevention`, `signup` | COVERED — reject |
| Customer success/expansion (Customer Success) | `churn-prevention`, `revops`, `onboarding`, `leadgen-revenue-readiness` | COVERED — reject |
| Reliability/idempotency/DLQ (DDIA) | `leadgen-automation-reliability`, `db-migration-safety`, `agent-loop-design`, `integration-engineering` | COVERED — reject |
| Stability patterns (Release It!) | `error-handling-patterns`, `integration-engineering`, `leadgen-automation-reliability` | COVERED — reject |
| Owner systems / work-on-business (E-Myth) | `fde-onboard`, `automation-control-center`, `admin-friendly-ux` | MOSTLY COVERED — merge owner-time axis into new skill |
| Operating cadence/scorecard (Traction) | `admin-friendly-ux`, `automation-control-center`, `executive-council` | MOSTLY COVERED — merge cadence axis into new skill |
| Constraint-first (The Goal) | `fable-operating-manual` (Part C), `executive-council` | PRINCIPLE present, **no executable procedure** — gap |
| Delivery metrics / change-failure (Accelerate) | `slo-error-budget`, `ship-checklist`, `observability-ops` | PRINCIPLE present, **no "what to automate next" scoring** — gap |
| Validate-before-build / MVP (Lean Startup) | `ab-testing`, `executive-council`, `fable-operating-manual` | PRINCIPLE present, **no canary→kill decision procedure** — gap |
| Problem-first discovery (Running Lean) | `customer-research`, `brainstorming`, `writing-plans` | PRINCIPLE present, **no manual-process mapping step** — gap |
| Work types / unplanned work (Phoenix Project) | `feature-change-flow`, `ship-checklist`, `prod-incident-triage` | PRINCIPLE present, **no work-type triage for automation backlog** — gap |
| Pre-flight checklist (Checklist Manifesto) | `verify-ship`, `careful`, `production-ready`, `ship-checklist` | COVERED — merged as gate inside new skill, no new skill |

## B. Candidate names (master-prompt examples) → decision

| Candidate | Existing equivalent | Decision |
|---|---|---|
| agency-automation-operating-system | `automation-pipeline` + `automation-control-center` + `leadgen-customer-journey-e2e` | DO NOT CREATE |
| automation-project-engineering | `feature-change-flow` + `plan-then-build` + `verify-ship` + `fable-operating-manual` | DO NOT CREATE |
| marketing-lifecycle-automation | `automation-pipeline` + `emails` + `lead-magnets` + `churn-prevention` | DO NOT CREATE |
| revops-automation-control | `revops` + `leadgen-revenue-readiness` + `sales-enablement` | DO NOT CREATE |
| ai-workflow-reliability | `leadgen-automation-reliability` + `agent-loop-design` + `error-handling-patterns` | DO NOT CREATE |
| automation-change-management | `feature-change-flow` + `ship-checklist` + `careful` + `agent-loop-design` | DO NOT CREATE |

## C. Genuine gap → new skill

**`automation-opportunity-discovery`** — koi existing skill repeatable, repo-grounded procedure nahi deta for: *"kaunsa manual process automate karein (or skip), score kya hai, pre-flight gates kya hain, canary kaise, kill kab, rollback kya"*.
- `fable-operating-manual` = operating discipline/manual (Part C has the *rules*).
- `advancement-roadmap` = technical backlog list.
- `executive-council` = strategic review.
- `feature-change-flow` = how to change EXISTING feature safely (assumes the feature exists).
- Gap = **front-of-pipeline decision procedure** — discovery → scoring → gate → canary → kill, with repo entrypoints and evidence contract. Books feed it: The Goal (constraint), Lean Startup/Running Lean (validate-first), Phoenix Project (work types), Accelerate (measure), Checklist Manifesto (pre-flight), E-Myth/Traction (owner-time + cadence).

Not a second control plane, not a 32nd agent, not a scheduler/CRM/billing duplicate — a decision procedure that invokes existing engines.
