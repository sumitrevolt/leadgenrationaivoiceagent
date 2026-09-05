# LeadGen AI — End-to-End Project Planning & Governance Framework

> **Banaya:** 2026-09-05 · **Owner:** Sumit (solo founder + AI staff) · **Mode:** Local autopilot with explicit owner gating for external actions (push/deploy/external sends).
> **Source docs:** `docs/RACI_MATRIX.md`, `docs/AI_WORKFORCE.md`, `docs/ARCHITECTURE.md`, `docs/KPI_DASHBOARD_SPEC.md`, `deliverables/M5_DEPLOY_PACKET_2026-09-04.md`, `docs/FIRST_CUSTOMER_7DAY_SPRINT.md`.

## Read this first (3 minutes)

| # | Doc | What's in it | Audience |
|---|---|---|---|
| 01 | `01_PROJECT_CHARTER.md` | Scope, objectives, success KPIs, timeline, budget | Owner + stakeholders |
| 02 | `02_WBS.md` | Work Breakdown Structure — task IDs, estimates, dependencies | Engineering, planning |
| 03 | `03_RACI_MATRIX.md` | Responsible/Accountable/Consulted/Informed per task family | All agents + owner |
| 04 | `04_RISK_REGISTER.md` | Risks with probability/impact, mitigation, contingency | Risk owners + lead |
| 05 | `05_SPRINT_PLAN.md` | 2-week sprints, milestones, critical path, velocity targets | Engineering |
| 06 | `06_ARCHITECTURE.md` | High-level + low-level architecture with mermaid | Architects + new hires |
| 07 | `07_TECH_STACK.md` | Tech stack with justification table + alternatives considered | Architects + reviewers |
| 08 | `08_CICD_PIPELINE.md` | CI/CD pipeline + blue-green/canary deployment | DevOps |
| 09 | `09_TESTING_STRATEGY.md` | Unit, integration, performance, security (SAST/DAST) | QA + engineers |
| 10 | `10_QUALITY_GATES.md` | Quality gates with thresholds + enforcement | All committers |
| 11 | `11_CODE_REVIEW_MATRIX.md` | Approval matrix by file category + reviewer assignment | Reviewers + leads |
| 12 | `12_COMPLIANCE_CHECKLIST.md` | GDPR + DPDP Act 2023 + SOC2 controls (as applicable) | Compliance + legal |
| 13 | `13_AUTOMATION_FRAMEWORK.md` | Self-healing workflows, auto-scaling, anomaly monitoring | DevOps + SRE |
| 14 | `14_MILESTONE_REPORTING.md` | Reporting structure per milestone | Owner + leads |
| 15 | `15_OWNER_GATING_PROTOCOL.md` | **HARD HONESTY:** what IS vs ISN'T automatable without owner | Owner (read first!) |
| 16 | `16_VELOCITY_TARGETS.md` | KPIs per sprint with measurement rubric | Engineering + owner |

## Executive summary

LeadGen AI is a **solo-founder + AI-staff platform**. The "1000 engineers" framing is a planning model — the actual execution fleet is **11 dev-time subagents** (`docs/AI_WORKFORCE.md` Tier 1) + **24 platform AI-staff agents** (Tier 2) + owner-gated human-in-the-loop for external actions.

**North-star metrics (90-day):**
- **CAC < ₹400** blended (niche B2B SMB Nagpur → all-India)
- **LTV/CAC > 6** on Starter (₹1,999/mo) and Combo (₹5,999/mo)
- **D7 retention > 50%** for paying customers
- **Zero P0 outages** causing customer-visible revenue loss
- **Defect leakage < 1%** from pre-prod to prod (measured via prod_check + post-deploy canary)
- **MTTR < 30 min** for P0/P1 (auto-detect → auto-rollback-or-mitigate → human verification)

## Operating principles (non-negotiable)

1. **Owner gates external actions**: push to remote, deploy to VPS, send outbound emails/SMS/WhatsApp, payments — ALL need explicit owner one-word `deploy / ship / go / M{n` trigger, even in autopilot mode.
2. **No silent debt**: runtime-data ratchet, prod_check, billing-truth tests are BLOCKING gates; touching baseline debt requires an evidence-backed manifest edit, not a side-effect.
3. **Migrations are reversible**: every schema/migration ships with a back-out plan in `ADR-NNN_*.md` and is rehearsed against a fresh DB before merge.
4. **Test-as-product**: every behaviour change ships with a test; coverage is required not negotiable for prod paths (voice/billing/payment/DPDP).
5. **Concurrency-safe deploys**: `concurrency.cancel-in-progress: false` on every deploy workflow — racing a half-deployed image is worse than waiting.
6. **DPDP before delete**: customer-side deletion requires DPDP purge workflow (`DPDP_PURGE_KEY`) before record removal; never the other order.

## How to use this folder

- **Daily**: read `05_SPRINT_PLAN.md` for active sprint, `04_RISK_REGISTER.md` for any `R-MIT-OPEN` items
- **Weekly**: review `14_MILESTONE_REPORTING.md` template, fill in `16_VELOCITY_TARGETS.md` measurements
- **Per release**: check `10_QUALITY_GATES.md` and `15_OWNER_GATING_PROTOCOL.md` BEFORE pushing
- **Quarterly**: re-pin this charter, refresh RACI, re-score risks

> **This document is append-only except for `15_OWNER_GATING_PROTOCOL.md`** which the owner can update with one-word approval when scope shifts (e.g. adding a new external system).