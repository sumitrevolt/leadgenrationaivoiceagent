# Project Charter — LeadGen AI (M6 → M9)

> **Banaya:** 2026-09-05 · **Sponsor:** Sumit (founder, sole R/A) · **Mode:** Solo + AI staff (autopilot) · **Period:** M6–M9 (90 days from charter sign-off).

---

## 1. Executive summary

**LeadGen AI** is a B2B-SMB (Nagpur first → all-India) marketing + voice automation platform on a FastAPI + Next.js + Postgres + Redis + Qdrant + Celery + GPT-Swara stack, deployed on a Hostinger VPS (`72.61.245.204`, Docker Compose). Mission: convert SMB owners from "online dikhna nahi hai" → paid monthly subscriber (Starter ₹1,999 / Combo ₹5,999).

**Charter scope (M6–M9, 90 days):** close the loop from M1–M5 (Sales OS, Telephony, Marketing, Consoles, Console dispatcher) into a defensible paid product with retained customers, then layer on M6 (Sales OS conversion), M7 (Live customer success loop), M8 (Multi-tenant Advanced UI), M9 (Annual contracts + agency plan).

---

## 2. Objectives (SMART)

| # | Objective | Baseline (M5) | Target (M9) | KPI source |
|---|---|---|---|---|
| O1 | Paying customers | 0 | **≥ 50 active** (M9) | `subscriptions` table count |
| O2 | MRR | ₹0 | **≥ ₹1.5L/mo** (M9) | `billing_truth_2026` |
| O3 | D7 retention | n/a | **≥ 50%** | Cohort report (`revenue_digest`) |
| O4 | CAC blended | n/a | **≤ ₹400** | Outbound spend / new customers |
| O5 | LTV/CAC | n/a | **≥ 6** | `revenue_attribution.jsonl` |
| O6 | Lead-to-customer | n/a | **≥ 8%** | `leads.jsonl` → `subscriptions` |
| O7 | Voice-call answer rate | n/a (DLT pending) | **≥ 25%** | `vobiz_call_log.jsonl` |
| O8 | P0 outages (revenue-blocking) | 0 | **0** (rolling 90-day) | Sentry + uptime checks |
| O9 | Defect leakage | n/a | **< 1%** | `prod_check.py` baseline drift |
| O10 | MTTR P0/P1 | n/a | **≤ 30 min** | Incident logs |

---

## 3. Scope

### 3.1 In scope (M6–M9)

- **M6 — Sales OS conversion**: Outreach → reply → booked call → paid. Replaces manual founder-led closing with a coached AI-staff flow (`sales_team`, `reply_agent`, `closing_agents`). Owner remains A on first 10 deals.
- **M7 — Live customer success loop**: Health scoring, churn signals, daily owner digest (CSV+MD+nfty — already shipped as `hot_queue_owner_pack`). Add the proactive intervention layer.
- **M8 — Multi-tenant Advanced UI**: Customer dashboard v3 with tier-aware feature gating (`COMBO_PRODUCT`, `ADVANCED_TIER`, `STAFF_BUS_ENABLED`, `BOOKING_REMINDERS`, etc.). Owner-OS admin thin projection layer (`owner_os.coordination_hub`).
- **M9 — Annual contracts + agency plan**: New SKUs in `packages.py` — Annual Starter (₹19,999/yr, ~16% discount), Agency plan (₹25,999/mo, white-label for 10 client sub-accounts). DPDP-grade tenant data isolation.
- **Cross-cutting**: Telephony Smartflo cutover, DLT template registration, Vobiz DID provisioning, 24/7 voice kill-switch, scheduled ops, runbook automation, observability maturation.

### 3.2 Out of scope (M6–M9)

- Mobile apps (web responsive only until MRR > ₹5L)
- Enterprise SSO/SAML (post M9; SOC2 prerequisite)
- International expansion (English-only DACH inbound only, no APAC/MEA)
- Hardware (no on-prem appliance)
- Voice fine-tuning beyond Swara flagship (no per-tenant voice cloning until DPDP-grade consent workflow lands)

### 3.3 Successor work (M10+, NOT in charter)

- SOC2 Type 1 audit (M10)
- EU expansion (post DPDP-equivalent audit) — M11
- White-label SaaS for agencies (agency plan in M9; full SaaS M10+)

---

## 4. Stakeholders & RACI summary

| Role | Count | RACI tag | Notes |
|---|---|---|---|
| Sumit (founder) | 1 | **A** on all external actions + first 10 deals | Owner-gating human |
| AI subagents (Tier 1) | 11 | **R** on dev tasks | `staff-engineer`, `qa-test-engineer`, `mcp-engineer` only write |
| AI staff agents (Tier 2) | 24 | **R** on runtime ops | Scheduled, customer-facing |
| Customers (pilot) | 50 target | **I** | N=50 active paying cohort |
| Vendors (Vobiz, Smartflo, DLT, GHCR, Hostinger) | 5 | **C** | Contracted; C on outages |
| Investors (none yet) | 0 | n/a | Pre-seed, founder-funded |

Full RACI → `03_RACI_MATRIX.md`.

---

## 5. Timeline (90-day, 6 sprints of 2 weeks)

| Sprint | Dates | Theme | Milestone |
|---|---|---|---|
| **S1** | 2026-09-08 → 2026-09-19 | M6 starter — first 5 deals, voice DLT submit | First paid logo |
| **S2** | 2026-09-22 → 2026-10-03 | M6 scale — outreach automation, reply agent | 10 paid logos |
| **S3** | 2026-10-06 → 2026-10-17 | M7 customer-success loop | D7 retention ≥ 50% |
| **S4** | 2026-10-20 → 2026-10-31 | M8 Advanced UI + tier gating | First Combo upgrade |
| **S5** | 2026-11-03 → 2026-11-14 | M9 SKU packaging + agency plan | 30 paying logos |
| **S6** | 2026-11-17 → 2026-11-28 | M9 close + retros + M10 plan | 50 paying logos, MRR ₹1.5L |

Sprint plan with critical path → `05_SPRINT_PLAN.md`.

---

## 6. Budget allocation (90-day)

| Bucket | Amount (INR) | % | Notes |
|---|---|---|---|
| VPS + infra (Hostinger, GHCR, DNS, Redis Cloud free tier) | ₹6,000 | 4% | Existing; covered |
| Telephony (Vobiz DID + Smartflo SIP + DLT registration fee) | ₹45,000 | 30% | One-time DLT; per-call Vobiz |
| AI LLM API (GPT-Swara flagship + Groq fallback + Gemini) | ₹36,000 | 24% | Usage-proportional |
| Outreach tooling (LinkedIn Sales Nav trial, WAHA Premium, email warmup) | ₹18,000 | 12% | |
| Compliance (DPDP pen-test lite, security audit lite) | ₹24,000 | 16% | Q3 (S4) |
| Buffer (incidentals + retest VPS upgrade + extra DIDs) | ₹21,000 | 14% | |
| **Total** | **₹1,50,000** | 100% | ≈ ₹50k/mo infra + voice + LLM |

**Revenue target** for budget break-even: **5 paid logos × ₹5,999 = ₹30k/mo by S2** covers ops; **50 × ₹3,500 blended = ₹1.75L/mo by S6** = profit margin unlocked.

---

## 7. Assumptions

1. Vobiz/Smartflo DLT paperwork clears in S1 (existing operator, fast-track).
2. GPT-Swara flagship voice quality remains acceptable without re-fine-tune (current eval ELO ≥ top-2 SaaS peer).
3. Hostinger VPS holds 50 tenants at < 30% CPU steady-state; if not, pre-empt with `package_extra_memory` S3.
4. No new regulator-driven feature churn (DPDP already shipped, RBI recurring-mandate deferred to M10+).
5. Founder availability for owner-gating: **≥ 2 windows/day × 30 min** (otherwise M6–M9 timeline slips by 1 sprint).

---

## 8. Constraints

1. **Solo-founder ceiling**: parallel AI agents ≠ parallel human attention. Owner-gating remains the bottleneck; we design for ≤ 5 owner decisions/sprint (push/deploy/external sends).
2. **Voice channel**: kill-switched by default (`VOICE_LAUNCH_KILL=1`) until DLT clears + 1 paid customer per niche passes voice QA.
3. **No debt tolerance**: governance gates (prod_check, runtime-data ratchet, billing-truth) BLOCK deploys. Workarounds require charter amendment + owner sign-off.
4. **DPDP scope**: customer-side deletion (`/admin/remove-customer`) MUST include the 8 brand-kit, content-pack, prospect list, lead-list, segment, identity-resolver, force-stop-campaign purge steps — each idempotent and audited.

---

## 9. Approval

- **Sponsor sign-off:** required before S1 starts.
- **Charter amendments:** documented in `15_OWNER_GATING_PROTOCOL.md` with `OWNER-SCOPE-AMEND-{n}` IDs.
- **Re-charter trigger:** at end of S6 or if any of: scope change > 20%, budget burn > 130%, MTTR > 60 min for 3 consecutive P0s.