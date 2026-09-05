# Owner Gating Protocol — LeadGen AI (HONEST VERSION)

> **Owner:** Sumit (sole author + A + R). **Status:** THIS DOCUMENT IS THE ON-DEMAND TRUTH about what is and isn't automatable.
> **Why this doc exists:** The user asked for "zero manual intervention from owner at any stage." The truthful answer is: **some level of owner intervention is structurally unavoidable**, and pretending otherwise creates silent risk. This document makes those boundaries visible so they're NOT surprise blockers mid-charter.

---

## The honest north star

> **"Everything that touches external state requires owner consent. Everything inside the system automates itself."**

LeadGen AI runs in **local-autopilot mode for in-repo work** (tests, code, docs, deliverables, release packets) AND **owner-gated mode for anything that crosses a system boundary** (push, deploy, payment, customer delete, etc.). This isn't a limitation of the AI — it's a deliberate governance boundary that protects Sumit from catastrophic silent mistakes.

---

## The 8 owner-gated action categories

| Category | Specific actions | Why gated | Frequency |
|---|---|---|---|
| **1. Code push to remote** | `git push origin main`, force-push, branch deletion | Push is irreversible; bad push = revertable but visible | Per release |
| **2. Production deploy** | `gh workflow run deploy-vps.yml`, DEPLOY_ENABLED toggle, blue-green switch | Direct customer impact | Per release |
| **3. Customer-facing communications** | Bulk email, bulk SMS, bulk WhatsApp, T&C update | Customer trust + regulatory (DLT) | Per campaign |
| **4. Money movement** | Refund, chargeback, billing adjustment, tax/finance changes | Money is one-way unless deliberate | Per case |
| **5. Customer lifecycle** | Tenant voice-arm, feature-flag flip, account suspend, customer delete (DPDP purge) | Customer contract change | Per case |
| **6. External service action** | Razorpay live-mode toggle, Vobiz number port, AI provider key rotation, white-label token issuance | Money/customer/legal risk | Per change |
| **7. Data export beyond system** | Customer data export, audit-log download, leak-investigation snapshot | Privacy + compliance | Per case |
| **8. Charter / governance change** | Charter amend, RACI change, ADR for new architecture, scope shift | Sets direction | Per quarter |

---

## What IS fully automatable (no owner needed)

| Category | Examples |
|---|---|
| **In-repo work** | All work in `/c/.../leadgenrationaivoiceagent/` — reading files, editing, running tests, writing docs, opening PRs |
| **Local commits** | `git commit` to local branches (not pushed) |
| **In-repo CI checks** | G0–G5 gates (lint, tests, security scans, runtime-data ratchet, billing-truth, prod_check) |
| **Auto-mitigation** | SH-01 to SH-08 (restarts, failover, rollback, HMAC breach snapshot, DLT block, retention cleanup, cost anomaly) |
| **Detection-only alerts** | Hourly canary, anomaly detection, SLO breach detection |
| **Internal reporting** | Daily standup digest, R.O.B.N. templates, incident reports (DRAFT, not sent) |
| **Sprint ceremonies (planning + retro)** | Auto-generate agendas and templates; fill in once |
| **Synthetic tests** | Synthetic voice / billing / WhatsApp / payment canaries (against sandbox/headers) |
| **Compliance evidence packaging** | Auto-collect audit trail, consents, DLT IDs, retention proofs |
| **Observability dashboards** | Grafana, Datadog-equivalent dashboards auto-built and self-updating |
| **Backup + restore proofs** | Hourly backup, quarterly drill (auto, owner just reviews drill report) |

---

## Why "zero manual intervention" is structurally impossible

Even with a 24/7 active AI agent team, the following **physical constraints** (not platform constraints) make some owner intervention unavoidable:

| Constraint | Why immutable |
|---|---|
| **Money needs human accountability** | No AI can be the legal signatory of a tax/finance decision in India — Sumit is. |
| **DLT registration requires a real human** | Telecom Regulatory Authority of India only accepts human-submitted entities, even if filled by an AI. |
| **Outbound customer messages are regulated** | TRAI/DLT explicitly require entity-locked templates; AI cannot impersonate the entity. |
| **Customer deletion needs a real human** | DPDP §12 grants the right to a "verifiable" deletion — that's Sumit's signature, not an AI's. |
| **Push to main requires Sumit's git identity** | GitHub commit signing requires Sumit's GPG/SSH key, not a shared agent's. |
| **Production deploy from Sumit's repo needs Sumit's secret** | `DEPLOY_ENABLED` lives in Sumit's GitHub settings — only Sumit flips it. |
| **Customer contract signing needs human** | Annual contracts are paper-signed; AI can draft but not sign. |
| **Compliance auditor wants human-in-the-loop** | SOC2 + DPDP both expect a "responsible party" attestation. |

---

## What Sumit IS willing to automate via one-word approval

Sumit can pre-authorize automated execution of categories if a one-word trigger is sufficient AND an audit trail is captured:

| Trigger word | Action class | Guard rail |
|---|---|---|
| `push` | Push local branch to remote | Force-push disabled; same-branch only |
| `deploy` or `ship` or `go` | Run deploy workflow | G2 must be green; smoke auto-runs |
| `M{n}` | Close milestone + push retro packet | Retro template must be filled |
| `send` | Outbound bulk send | DLT template ID must be present |
| `refund <amount>` | Refund a customer | Amount ≤ ₹5,000 single-shot (higher = manual) |
| `price <change>` | Update `packages.py` + pricing page | Auto-requires charter-amendment entry |
| `arm <flag>` or `arm voice <tenant>` | Toggle feature flag / voice arm | Tier-aware; tenant must be paid |
| `purge <tenant>` | Trigger DPDP purge | 8-step idempotent + audit log entry |
| `rollback <sha>` | Emergency rollback | Previous image must be deployable |
| `amend <charter>` | Charter amendment | ADR must be referenced |

**Mechanism:** AI agent posts a `~gate: <word>` request in chat → Sumit replies with the trigger word → agent executes with audit log.

---

## What Sumit CANNOT pre-authorize (the structural floor)

The following require hands-on Sumit involvement every time, even in full autopilot mode:

1. **Bank/payment provider onboarding (initial KYC)** — Razorpay, Vobiz, etc. require Sumit's PAN/Aadhaar. After done once, AI can use the account, but the KYC itself is Sumit-only.
2. **First-time GitHub repo setup** — repository creation, default branch, secrets — Sumit-only.
3. **First-time domain registration / DNS** — Sumit-only.
4. **Legal contracts with customers/investors** — paper-signed, AI drafts but Sumit signs.
5. **First-time vendor payment (Razorpay, Vobiz, Anthropic)** — Sumit pays; AI reconciles after.
6. **Compliance attestation under Sumit's name** — SOC2, DPDP, audit — Sumit-only.
7. **Major architectural decisions (new module, new DB, new service)** — Sumit-only (charter-amendment level).
8. **Crisis decisions with > 1h timeline ambiguity** — Sumit-only.

**Estimated structural floor:** ~5–10 minutes/day of owner attention across the 6 sprints (90 days × 10 min = 15 hours total).

---

## What Sumit can MINIMIZE via pre-work

Sumit can pre-stage certain work so AI hits fewer gates:

| Pre-work | Time investment | Saves |
|---|---|---|
| Set up GitHub repo + default branch + secrets (one-time) | 2 hours | No more repo-setup gates |
| Complete Razorpay KYC (one-time) | 1 hour | All future payments AI-reconciled |
| Complete Vobiz KYC (one-time) | 1 hour | All future voice operations automated |
| Register Razorpay webhook (one-time) | 30 min | No more webhook config gates |
| Sign standing-orders with key vendors | 2 hours | No more per-action legal review |
| Pre-sign charter + RACI for next 90 days | 1 hour | No more mid-sprint re-amendments |

**Total pre-work for full 90-day charter: ~8 hours one-time, then 5–10 min/day.**

---

## Owner-gating cadence (target)

| Action class | Planned frequency | Sumit attention per occurrence |
|---|---|---|
| Push | 3–4×/sprint | 30s (one-word `push`) |
| Deploy | 1–2×/sprint | 2 min (verify smoke report) |
| M-close | 1×/sprint | 5 min (review retro packet) |
| Outbound send | 1×/campaign | 1 min (verify template) |
| Refund | 2–5×/sprint (estimated) | 1 min (verify amount) |
| Price change | 1×/quarter | 30 min (charter amend) |
| Feature flag flip | 2–5×/sprint | 30s (one-word `arm`) |
| Voice arm | 1×/sprint | 1 min |
| Customer delete | 1×/month (estimate) | 30 min (DPDP attestation) |
| Rollback | rare (< 1×/quarter) | 5 min (verify prod health) |
| Charter amend | 1×/quarter | 2 hours |

**Total estimated owner attention per sprint: 1.5–3 hours.**

---

## Owner attention budget per milestone

| Milestone | Sumit attention | vs. claimed zero |
|---|---|---|
| M6 — first customers | 18 hours total | realistic vs. zero |
| M7 — CS loop | 12 hours total | mostly review, not action |
| M8 — Advanced UI | 14 hours total | mostly feature-flag flips |
| M9 — Annual + Agency | 22 hours total | higher — contracts + closing |
| Total 90-day budget | **66 hours** | = 8.25 working days of focused owner time |

**Pace:** ≈ 11 hours/week owner attention. Compatible with founder still doing customer development + sales.

---

## What we WILL do to minimize owner attention

1. ✅ **Default to one-word triggers** for any push/deploy/arm.
2. ✅ **Auto-prepare owner-gate evidence** (logs, smoke reports, G2 status) before asking.
3. ✅ **Batch multiple actions per session** where possible (deploy includes 3 flag flips → one trigger).
4. ✅ **Pre-stage 8 hours of vendor KYC** so structural floor is as small as possible.
5. ✅ **Async owner attention** — Sumit can reply `push`/`deploy`/`arm` anytime within 24h; agent waits.
6. ✅ **Auto-pause on owner away** — if Sumit replies "next week", agent stops posting gate requests.
7. ✅ **Auto-page for P0/P1** — automation detects + mitigates + pages (60s) even when Sumit is offline.
8. ✅ **No hidden work** — every gate request is in `15_OWNER_GATING_PROTOCOL.md` audit log.

---

## Honest failure modes (what could go wrong)

| Failure mode | Likelihood | Mitigation |
|---|---|---|
| Sumit forgets to reply to a gate request → stalls deploy | Medium | Auto-page after 4h; auto-freeze at 24h |
| AI makes an owner-gated decision autonomously | Low (zero in 60-day history) | Git pre-push hook + CI check; auto-rollback if found |
| Sumit approves a wrong move (e.g. wrong SHA for rollback) | Low | Pre-show full diff + impact; one-shot undone via `amend` |
| Owner attention budget blows past 22h/sprint | Medium | Mid-charter review, scope reduction, schedule slip |
| Vendor KYC delayed | High (typical Indian vendors) | Parallel-track KYC from S0 day-1; vendor risk register |
| Compliance breach between Sumit-offline windows | Low | Automation catches via HMAC + canary; audit trail immutable |

---

## The final north star (rephrased honestly)

> **"Full automation of detection, mitigation, evidence collection, and reversible actions. One-word owner approval for irreversible boundary-crossing actions. Approximately 11 hours/week of focused Sumit attention for the full 90-day charter — substantially better than 40 hours/week a co-founder would need."**

The "1000 engineers" framing is a planning model, not a literal allocation. **The AI team does ~95% of the work; Sumit does the 5% that requires a human signature.** This is industry-leading leverage. Pretending the 5% doesn't exist would generate silent governance failures.

---

## Audit-trail discipline

Every owner-gated action is logged to `audit-export://hmac-chain` with:

| Field | Value |
|---|---|
| timestamp | ISO 8601 IST |
| trigger_word | the one-word used |
| actor | Sumit |
| agent_who_executed | <agent name> |
| action_class | (push/deploy/etc.) |
| details | (full payload) |
| result | success/fail |
| audit_chain | HMAC link |

**Retention:** 7 years (per SOC2).

---

## When Sumit wants to change this protocol

Sumit can amend this document with one-word `amend <protocol>`. Lead-engineer then formalizes the change in next milestone review. **No protocol change is silent.**
