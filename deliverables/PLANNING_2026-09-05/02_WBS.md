# Work Breakdown Structure (WBS) — M6–M9 (90 days, 6 sprints)

> **Format:** `M{n}-{S{n}-{WBS-ID}` where `M{n}`=milestone, `S{n}`=sprint, `WBS-ID`=incremental task ID. Estimates are engineer-days (1 ED = 6 productive hours including review + test + buffer).

## Top-level summary

| Milestone | Sprints | Tasks | EDs | Critical-path? |
|---|---|---|---|---|
| **M6 — Sales OS conversion** | S1–S2 | 24 | 28 ED | **Yes** |
| **M7 — Customer success loop** | S3 | 12 | 14 ED | Yes (D7 retention blocks Combo upsell) |
| **M8 — Multi-tenant Advanced UI** | S4 | 14 | 18 ED | Yes (Combo gating is revenue lever) |
| **M9 — Annual contracts + agency** | S5–S6 | 18 | 22 ED | No (independent of M6/M7) |
| **Cross-cutting (security, observability, billing)** | All sprints | 16 | 12 ED | No (parallel lanes) |
| **Total** | | **84 tasks** | **94 ED** | |

Throughput target: ~5 ED/week sustained (matches `staff-engineer` solo-agent throughput on disjoint file groups). Owner-gating time budget: ≤ 30 min/day on push/deploy/external sends.

---

## M6 — Sales OS conversion (S1 + S2, 28 ED, 24 tasks)

### S1 — First 5 deals, voice DLT submit

| ID | Task | Owner (R) | Accountable | Est (ED) | Depends on | Critical path |
|---|---|---|---|---|---|---|
| M6-S1-001 | DLT template registration (3 voice templates: intro, follow-up, no-answer) | Sumit (paperwork) + DLT-vendor | Sumit | 2 | — | **Yes** |
| M6-S1-002 | Vobiz DID provisioning (1 Nagpur local) | Sumit + Vobiz | Sumit | 1 | M6-S1-001 | **Yes** |
| M6-S1-003 | Voice channel arm (`VOICE_LAUNCH_KILL=0` for 1 pilot tenant) | Sumit (decision) + ops-engineer | Sumit | 0.5 | M6-S1-002 | **Yes** |
| M6-S1-004 | Pilot onboarding SOP (`docs/PILOT_ONBOARDING.md`, 7-day activation playbook) | sales-engineer | sales-engineer | 1.5 | — | No |
| M6-S1-005 | Outreach batch #1 (50 Nagpur solar leads, manual LEGAL source + auto Prospector) | outreach-engineer | sales-engineer | 2 | M6-S1-004 | **Yes** |
| M6-S1-006 | Reply agent coaching (Tara persona, 3 personas approved) | reply-engineer + Sumit (voice approve) | Sumit | 1.5 | M6-S1-005 | **Yes** |
| M6-S1-007 | Booked-call scheduler (Calendly embed + custom flow) | closing-engineer | sales-engineer | 1 | M6-S1-005 | **Yes** |
| M6-S1-008 | Closing SOP (5-step script, objection handler) | closing-engineer + Sumit | Sumit | 1 | — | **Yes** |
| M6-S1-009 | UPI payment + activation flow (existing; verify on ₹1,999 pilot) | billing-engineer | billing-engineer | 0.5 | — | Yes (no skip) |
| M6-S1-010 | Daily owner digest (already shipped; verify first-5 paying) | ops-engineer | ops-engineer | 0.5 | — | No |
| M6-S1-011 | Pilot customer dashboard v2 walk-through (recorded, owner-curated) | frontend-engineer | frontend-engineer | 1.5 | — | No |
| M6-S1-012 | Runbook: voice DLT regression test (synthetic Vobiz canary / hour) | sre-engineer | sre-engineer | 1 | M6-S1-003 | **Yes** |
| M6-S1-013 | Runbook: WhatsApp reply canary (5 min interval, owner-alert on miss) | ops-engineer | ops-engineer | 0.5 | — | No |
| M6-S1-014 | Risk: voice DLT clearance slip — mitigation: voice OFF, push only after DLT | Sumit | Sumit | 0 | M6-S1-001 | (Risk-tracked) |

### S2 — Outreach automation, reply agent (10 paid logos)

| ID | Task | Owner (R) | Accountable | Est (ED) | Depends on |
|---|---|---|---|---|---|
| M6-S2-015 | Outreach batch #2 + #3 (150 leads, 2nd/3rd niches — coaching + interior) | outreach-engineer | sales-engineer | 2 | M6-S1-005 |
| M6-S2-016 | Reply agent v2 (objection library, GPT-Swara fine-tune) | reply-engineer + ml-engineer | Sumit | 3 | M6-S1-006 |
| M6-S2-017 | Closing agent v1 (assistant mode; owner approves send) | closing-engineer + Sumit | Sumit | 2 | M6-S1-008 |
| M6-S2-018 | Sales OS dashboard (cohort, funnel, response-rate) | data-engineer + frontend-engineer | sales-engineer | 2 | — |
| M6-S2-019 | WhatsApp human-queue integration (already M4-shipped; verify at scale) | ops-engineer | ops-engineer | 0.5 | — |
| M6-S2-020 | Compliance audit — DLT templates + Vobiz call recording retention | compliance-engineer | Sumit | 1 | M6-S1-001 |
| M6-S2-021 | 10-logo milestone retrospective | Sumit | Sumit | 0.5 | M6-S1-005..010 |
| M6-S2-022 | Combo-product upsell playbook (Starter → Combo, ₹1,999 → ₹5,999) | sales-engineer + Sumit | Sumit | 1 | M6-S1-008 |
| M6-S2-023 | Risk: GPT-Swara outage — fallback to Groq + replay queue | ml-engineer | ml-engineer | 1 | — |
| M6-S2-024 | Risk: WhatsApp WAHA queue overflow — throttle + owner alert | ops-engineer | ops-engineer | 0.5 | — |

---

## M7 — Customer success loop (S3, 14 ED, 12 tasks)

| ID | Task | Owner (R) | Accountable | Est (ED) | Critical path |
|---|---|---|---|---|---|
| M7-S3-001 | Customer health score v1 (engagement × payment × voice-calls × content-views) | data-engineer + cs-engineer | cs-engineer | 2 | **Yes** |
| M7-S3-002 | Churn signal detector (D7 silent, payment × 2 fail, NPS<6, voice-cancel) | data-engineer | cs-engineer | 2 | **Yes** |
| M7-S3-003 | Proactive intervention: in-app nudge + WhatsApp nudge (warm, not spammy) | frontend-engineer + ops-engineer | cs-engineer | 2 | **Yes** |
| M7-S3-004 | Owner digest: at-risk customers (replaces ad-hoc check) | ops-engineer | ops-engineer | 1 | Yes (no skip) |
| M7-S3-005 | D7 / D14 / D30 cohort report (auto-generated, owner-validated) | data-engineer | data-engineer | 1.5 | **Yes** |
| M7-S3-006 | NPS weekly poll (in-app, WhatsApp, fallback email) | frontend-engineer + ops-engineer | cs-engineer | 1 | No |
| M7-S3-007 | Reactivation playbook (D7-D14 silent → 3-touch reactivation) | sales-engineer | cs-engineer | 1 | No |
| M7-S3-008 | Customer testimonial capture (in-app after NPS ≥9) | frontend-engineer | cs-engineer | 0.5 | No |
| M7-S3-009 | Live console: customer-side success dashboard | frontend-engineer | cs-engineer | 1 | No |
| M7-S3-010 | Risk: false-positive churn signal — mitigation: 2-of-3 confirmation + owner review | data-engineer | cs-engineer | 0.5 | (Risk-tracked) |
| M7-S3-011 | Risk: noise in cohort stats — mitigation: bootstrap CI + owner manual spot-check | data-engineer | data-engineer | 0.5 | (Risk-tracked) |
| M7-S3-012 | D7 ≥ 50% validation gate (BLOCKING for Combo upsell push) | Sumit | Sumit | 0.5 | M7-S3-005 |

---

## M8 — Multi-tenant Advanced UI (S4, 18 ED, 14 tasks)

| ID | Task | Owner (R) | Accountable | Est (ED) | Critical path |
|---|---|---|---|---|---|
| M8-S4-001 | Tier matrix in `packages.py` (Starter / Combo / Annual / Agency — features per tier) | Sumit (pricing) + billing-engineer | Sumit | 1 | **Yes** |
| M8-S4-002 | Feature flags per tier (env vars: `COMBO_PRODUCT`, `ADVANCED_TIER`, `ANNUAL_DISCOUNT`, `AGENCY_TIER`) | platform-engineer | Sumit | 1.5 | **Yes** |
| M8-S4-003 | Customer dashboard v3 — tier-aware sidebar + content-cards | frontend-engineer | frontend-engineer | 3 | **Yes** |
| M8-S4-004 | Admin "tier inspector" (owner-only, view as tenant) | frontend-engineer + ops-engineer | Sumit | 1.5 | No |
| M8-S4-005 | Combo upgrade flow (in-app, payment, immediate feature unlock) | billing-engineer + frontend-engineer | Sumit | 2 | **Yes** |
| M8-S4-006 | White-label prep — agency tenant model (sub-account isolation) | data-engineer + platform-engineer | Sumit | 2 | No (M9 critical-path) |
| M8-S4-007 | Owner-OS: coordination hub dashboard (existing; verify thin projection) | frontend-engineer | Sumit | 0.5 | No |
| M8-S4-008 | Live ops dashboard (P0 alert center, error-budget, deploy history) | frontend-engineer + sre-engineer | sre-engineer | 2 | No |
| M8-S4-009 | Voice AI console v2 (per-tenant DLT status, voice-call live monitor) | frontend-engineer + telephony-engineer | Sumit | 2 | **Yes** |
| M8-S4-010 | Billing portal — invoice history + plan change + cancel | billing-engineer + frontend-engineer | Sumit | 1 | **Yes** |
| M8-S4-011 | Compliance: SOC2 control mapping (read-only, M10 SOC2 prep) | compliance-engineer | Sumit | 1 | No (M10 prep) |
| M8-S4-012 | Risk: feature-flag misconfig exposes Premium to Starter | platform-engineer + Sumit | Sumit | 0 | (Risk-tracked) |
| M8-S4-013 | Risk: dashboard perf regression at 50 tenants | sre-engineer + frontend-engineer | sre-engineer | 0.5 | (Risk-tracked) |
| M8-S4-014 | First Combo upgrade validation (BLOCKING for M9 push) | Sumit | Sumit | 0.5 | M8-S4-005 |

---

## M9 — Annual contracts + agency plan (S5 + S6, 22 ED, 18 tasks)

### S5 — SKU packaging (11 ED, 9 tasks)

| ID | Task | Owner (R) | Accountable | Est (ED) |
|---|---|---|---|---|
| M9-S5-001 | Annual Starter SKU (`packages.py` ₹19,999/yr, ~16% discount) | Sumit + billing-engineer | Sumit | 1 |
| M9-S5-002 | Agency plan SKU (₹25,999/mo, white-label for 10 sub-accounts) | Sumit + billing-engineer | Sumit | 1 |
| M9-S5-003 | Razorpay/Stripe integration for annual billing (recurring + one-shot) | billing-engineer | Sumit | 2 |
| M9-S5-004 | Annual plan change UI (Starter-monthly → Annual-Starter, proration) | billing-engineer + frontend-engineer | Sumit | 2 |
| M9-S5-005 | Agency sub-account onboarding wizard | frontend-engineer + data-engineer | Sumit | 2 |
| M9-S5-006 | Agency white-label token provisioning (logo, domain, color) | platform-engineer | Sumit | 1 |
| M9-S5-007 | Annual contract template (T&C, DPDP consent, support SLA) | Sumit (legal) + compliance-engineer | Sumit | 1 |
| M9-S5-008 | Pricing page refresh (live in product + `landing/`) | frontend-engineer | sales-engineer | 1 |
| M9-S5-009 | Risk: Razorpay webhook race — mitigation: idempotency key + reconciliation | billing-engineer | Sumit | 0 |

### S6 — Close + retrospective (11 ED, 9 tasks)

| ID | Task | Owner (R) | Accountable | Est (ED) |
|---|---|---|---|---|
| M9-S6-001 | 50-logo milestone retrospective | Sumit | Sumit | 0.5 |
| M9-S6-002 | MRR ≥ ₹1.5L validation | Sumit | Sumit | 0.5 |
| M9-S6-003 | D7 retention ≥ 50% validation | data-engineer | Sumit | 0.5 |
| M9-S6-004 | Annual plan first-customer onboarding | Sumit (deal close) | Sumit | 1 |
| M9-S6-005 | Agency plan first-customer onboarding | Sumit (deal close) | Sumit | 1.5 |
| M9-S6-006 | M10 SOC2 Type 1 prep kickoff (read-only, vendor selection) | compliance-engineer | Sumit | 2 |
| M9-S6-007 | Team OS handoff: AI-staff self-tuning (objective-function auto-tune) | ml-engineer + platform-engineer | ml-engineer | 3 |
| M9-S6-008 | Charter renewal — M10–M13 scope (next 90 days) | Sumit | Sumit | 1 |
| M9-S6-009 | Risk: Annual subscription refund-claim dispute — mitigation: pro-rated refund SOP + support SLA | Sumit + billing-engineer | Sumit | 1 |

---

## Cross-cutting lanes (all sprints, 12 ED, 16 tasks)

| ID | Lane | Task | R | A | ED | Sprint |
|---|---|---|---|---|---|---|
| CC-001 | Security | SAST scan weekly (`bandit`, `pip-audit`) | security-engineer | sre-engineer | 0.5/week | All |
| CC-002 | Security | DAST smoke (`zap-baseline`) on staging | security-engineer | sre-engineer | 1 | All |
| CC-003 | Security | Dependency CVE weekly + auto-PR via Dependabot | sre-engineer | sre-engineer | 0.25/week | All |
| CC-004 | Observability | SLO dashboard (latency p95, error-rate, uptime) | sre-engineer | sre-engineer | 0.5 | All |
| CC-005 | Observability | Anomaly detector (call-out rate, payment-fail rate) | data-engineer + sre-engineer | sre-engineer | 1 | All |
| CC-006 | Billing | Billing-truth test in CI (BLOCKING) | billing-engineer | billing-engineer | 0.25/sprint | All |
| CC-007 | Runtime-data | Ratchet test in CI (BLOCKING) | platform-engineer | platform-engineer | 0.5/sprint | All |
| CC-008 | Deploy | Deploy hygiene (image retention, secret rotation) | sre-engineer | sre-engineer | 0.5/sprint | All |
| CC-009 | Backup | DB backup verify (daily restore-test) | sre-engineer | sre-engineer | 0.5/week | All |
| CC-010 | Backup | Redis snapshot retention policy | sre-engineer | sre-engineer | 0.25 | All |
| CC-011 | Compliance | DPDP audit log integrity check (HMAC chain) | compliance-engineer | sre-engineer | 1 | All |
| CC-012 | Compliance | Vobiz/Smartflo recording retention verify | compliance-engineer | compliance-engineer | 0.5 | All |
| CC-013 | Owner-gate | CHANGELOG + ADR review before push (Sumit) | Sumit | Sumit | 0.25/sprint | All |
| CC-014 | Owner-gate | Deploy packet (post-merge, pre-VPS) | Sumit | Sumit | 0.5/sprint | All |
| CC-015 | Owner-gate | Post-deploy smoke (5 min, 6 checks) | sre-engineer | Sumit | 0.25/sprint | All |
| CC-016 | Observability | Uptime + health-check auto-page (on-call = Sumit) | sre-engineer | sre-engineer | 0.25 | All |

---

## Critical-path summary

```
M6-S1-001 (DLT templates) → M6-S1-002 (Vobiz DID) → M6-S1-003 (voice arm)
   → M6-S1-005 (Outreach batch #1) → M6-S1-006 (Reply agent) → M6-S1-007 (Booking)
   → M6-S1-008 (Closing) → M6-S1-009 (UPI flow)
                                                                              ↓
M7-S3-001 (Health score) → M7-S3-002 (Churn detector) → M7-S3-003 (Proactive)
   → M7-S3-005 (Cohort report) → M7-S3-012 (D7 ≥ 50% validation GATE)
                                                                              ↓
M8-S4-001 (Tier matrix) → M8-S4-002 (Flags) → M8-S4-005 (Combo upgrade)
   → M8-S4-014 (First Combo validation GATE)
                                                                              ↓
M9-S5-001..003 (Annual + Razorpay) → M9-S5-004 (Annual change UI)
   → M9-S6-004 (First annual customer)
```

If any critical-path task slips > 1 day, charter amendment (CH-AMEND-NNN) required; risk register updated.

---

## Velocity tracking

Per-sprint velocity = sum(ED of tasks marked DONE within sprint). Target:
- S1: 14 ED (voice + outreach + first deal)
- S2: 14 ED (scale)
- S3: 14 ED (CS loop)
- S4: 18 ED (Advanced UI)
- S5: 11 ED (Annual)
- S6: 11 ED (close)

Total 90-day target = **82 ED** in-product + 12 ED cross-cutting = **94 ED**, matching top-of-document budget.

If velocity falls < 80% of target for 2 consecutive sprints → mid-charter review (Sumit + lead).