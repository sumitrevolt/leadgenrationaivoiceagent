# Risk Register — LeadGen AI (M6–M9)

> **Scoring:**
> - **P** (Probability) = 1 (rare) .. 5 (almost certain this sprint)
> - **I** (Impact) = 1 (cosmetic) .. 5 (revenue-blocking, customer-visible, irreversible)
> - **Score** = P × I, range 1–25
> - **Bucket:** ≥15 = 🔴 critical, 8–14 = 🟠 high, 4–7 = 🟡 medium, 1–3 = 🟢 low

## Summary

| Bucket | Count | Notes |
|---|---|---|
| 🔴 Critical (≥15) | 6 | All owner-mitigated; tracked weekly |
| 🟠 High (8–14) | 11 | Mitigated; tracked per-sprint |
| 🟡 Medium (4–7) | 14 | Documented; bi-weekly review |
| 🟢 Low (1–3) | 5 | Background |
| **Total tracked** | **36** | |

---

## R-VOICE-* (voice / DLT / Vobiz)

| ID | Risk | P | I | Score | Bucket | Root cause | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|---|---|---|
| R-VOICE-001 | DLT template registration slip > 2 weeks | 3 | 5 | 15 | 🔴 | Vobiz/DLT portal paperwork backlog; cross-vendor coordination | Submit 3 templates in S1 wk-1; follow up daily; backup: Smartflo-only fallback for DLT-pending templates | Sumit | OPEN (S1) |
| R-VOICE-002 | Voice quality below ELO threshold (M9 agency SLA breach) | 2 | 4 | 8 | 🟠 | GPT-Swara flagship under-trained for Hindi nagpur-style prosody | Continuous eval harness; ELO gate before M9 first-agency-customer | ml-engineer | OPEN |
| R-VOICE-003 | Vobiz DID exhaustion (Nagpur local numbers) | 2 | 3 | 6 | 🟡 | Single provider capacity | Stockpile 5+ DIDs in S1; auto-failover to Smartflo/SIP-trunk | telephony-engineer | OPEN |
| R-VOICE-004 | Call recording retention gap (DPDP / SOC2) | 3 | 4 | 12 | 🟠 | Manual cleanup vs auto | Recording lifecycle policy in S2; HMAC audit log | compliance-engineer | OPEN |
| R-VOICE-005 | Synthetic canary false-negative (looks green while Vobiz down) | 2 | 4 | 8 | 🟠 | Canary path diverges from prod | Real-call slice (1/day, real tenant) starting S3 | sre-engineer | OPEN |
| R-VOICE-006 | Voice kill-switch stuck ON (false-positive) | 2 | 3 | 6 | 🟡 | Env var override requires restart | Add runtime config + heartbeat in S2 | platform-engineer | OPEN |

## R-SALES-* (Sales OS / conversion)

| ID | Risk | P | I | Score | Bucket | Root cause | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|---|---|---|
| R-SALES-001 | First 5 deals slip to S3 | 4 | 5 | 20 | 🔴 | Manual founder time bottleneck; outreach quality variance | Pre-warm 50 leads S1 wk-1; close 5× wk-1 cadence; Sumit on-call for deal close | Sumit | OPEN |
| R-SALES-002 | Reply agent hallucination damages brand | 3 | 4 | 12 | 🟠 | LLM eval coverage < 100%; new templates | LLM-as-judge + human spot-check 20% sample | reply-engineer | OPEN |
| R-SALES-003 | WhatsApp WAHA queue overflow (> 100 pending) | 3 | 3 | 9 | 🟠 | Burst reply volume | Throttle 50/recipient/24h; auto-alert owner at > 60 | ops-engineer | OPEN |
| R-SALES-004 | Outreach lead-source dry-up (Legal sources cap) | 3 | 4 | 12 | 🟠 | Manual scraping limited; Google Maps Places API quota | Diversify: LinkedIn Sales Nav trial + referral seed in S2 | outreach-engineer | OPEN |
| R-SALES-005 | Combo upsell playbook ineffective (< 10% conversion) | 3 | 3 | 9 | 🟠 | Wrong signal for upsell timing | Trigger on usage threshold + NPS≥8; A/B 2 playbook variants S4 | sales-engineer | OPEN |

## R-CS-* (Customer success / retention)

| ID | Risk | P | I | Score | Bucket | Root cause | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|---|---|---|
| R-CS-001 | D7 retention < 50% (blocks Combo upsell) | 4 | 5 | 20 | 🔴 | Onboarding completeness not measured; silent-churn pattern | Health score live S3 wk-2; proactive nudge 3-touch | cs-engineer | OPEN |
| R-CS-002 | Churn false-positive (unnecessarily churns happy customers) | 3 | 4 | 12 | 🟠 | Single-signal detector | 2-of-3 confirmation + owner review queue | data-engineer | OPEN |
| R-CS-003 | NPS noise (sample size small, statistical CI wide) | 4 | 2 | 8 | 🟠 | First 50 logos = small N | Bootstrap CI; bi-weekly; report as "early signal" until N>30 | data-engineer | OPEN |
| R-CS-004 | Testimonial capture friction (NPS≥9 path abandoned) | 2 | 2 | 4 | 🟡 | Manual step | 1-click in-app + auto-template | frontend-engineer | OPEN |
| R-CS-005 | Reactivation playbook harassment (D7-D14 silent → 3-touch) | 2 | 3 | 6 | 🟡 | 3-touch over-tuned | Cap at 3 touches/14d; pause if reply-rate < 2% | cs-engineer | OPEN |

## R-UI-* (Multi-tenant UI / tier gating)

| ID | Risk | P | I | Score | Bucket | Root cause | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|---|---|---|
| R-UI-001 | Feature-flag misconfig exposes Premium to Starter | 2 | 5 | 10 | 🟠 | Env var typo / wrong tier in matrix | Two-eye review on `packages.py`; feature-flag tests in CI | platform-engineer | OPEN |
| R-UI-002 | Dashboard perf regression at 50 tenants | 3 | 4 | 12 | 🟠 | Query N+1 / no pagination | p95 latency budget < 800ms; auto-page on regression | frontend-engineer + sre-engineer | OPEN |
| R-UI-003 | Tier matrix price race (SKU added mid-sprint) | 2 | 3 | 6 | 🟡 | `packages.py` change + cache stale | Pricing-truth test BLOCKING in CI | billing-engineer | OPEN |
| R-UI-004 | White-label agency tenant data leak | 1 | 5 | 5 | 🟡 | Sub-account boundary bug | Tenant-scope middleware + integration test on every commit | platform-engineer | OPEN (M9) |

## R-PBILL-* (billing / payments)

| ID | Risk | P | I | Score | Bucket | Root cause | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|---|---|---|
| R-PBILL-001 | Razorpay webhook race / duplicate charge | 2 | 5 | 10 | 🟠 | Async idempotency gap | Idempotency key + reconciliation cron | billing-engineer | OPEN (M9) |
| R-PBILL-002 | Annual subscription refund-claim dispute | 3 | 3 | 9 | 🟠 | 7-day cooling-off edge case | Pro-rated refund SOP; clear T&C at purchase | Sumit + billing-engineer | OPEN |
| R-PBILL-003 | UPI payment verify false-positive (manual claim of ₹1,999) | 2 | 4 | 8 | 🟠 | Manual SMS-UPI fallback path | Strict Razorpay verification; UPI auto-verify | billing-engineer | OPEN |
| R-PBILL-004 | Plan-change proration wrong (annual upgrade mid-cycle) | 3 | 3 | 9 | 🟠 | Edge cases around mid-cycle | Unit tests on proration engine; spot-check 1 real case | billing-engineer | OPEN |

## R-COMPLY-* (compliance / DPDP / SOC2 prep)

| ID | Risk | P | I | Score | Bucket | Root cause | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|---|---|---|
| R-COMPLY-001 | DPDP purge incomplete (customer deletion leaves 8 datasets) | 2 | 5 | 10 | 🟠 | Manual multi-step purge | Audit log + 8-step integration test; pre-delete dry-run | compliance-engineer | OPEN |
| R-COMPLY-002 | Consent capture gap (voice / marketing without explicit) | 2 | 4 | 8 | 🟠 | Onboarding flow assumptions | Consent re-capture at each touchpoint; T&C review S2 | compliance-engineer | OPEN |
| R-COMPLY-003 | Audit log tampering (HMAC chain break) | 1 | 5 | 5 | 🟡 | Storage compromise | Append-only HMAC chain + offline archive | compliance-engineer | OPEN |
| R-COMPLY-004 | Recording retention misconfig (kept > 90d) | 3 | 3 | 9 | 🟠 | Storage budget vs legal hold | Auto-cleanup + legal-hold exception workflow | compliance-engineer | OPEN |

## R-INFRA-* (infra / observability / capacity)

| ID | Risk | P | I | Score | Bucket | Root cause | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|---|---|---|
| R-INFRA-001 | VPS CPU saturation at 50 tenants | 3 | 4 | 12 | 🟠 | No horizontal scale, single VPS | Auto-scale to 2× VPS at > 70% CPU; pre-empt S3 | sre-engineer | OPEN |
| R-INFRA-002 | DB disk full (runaway JSONL) | 3 | 4 | 12 | 🟠 | Runtime-data debt grows | Disk-alert at 70%; quarterly cleanup of UNDECLARED findings | sre-engineer | OPEN |
| R-INFRA-003 | Redis cache eviction storm | 2 | 3 | 6 | 🟡 | Memory pressure | LRU tuning; cache size ceiling | sre-engineer | OPEN |
| R-INFRA-004 | Celery worker crash loop (memory leak) | 2 | 3 | 6 | 🟡 | Long-running tasks | Worker restart policy + circuit breaker | infra-doctor | OPEN |
| R-INFRA-005 | LLM API rate-limit (Groq + GPT) | 3 | 3 | 9 | 🟠 | Burst usage | 2-provider failover (Groq ↔ GPT) + queue replay | ml-engineer | OPEN |
| R-INFRA-006 | GHCR image retention exhausted | 2 | 2 | 4 | 🟡 | Image growth | 14-day retention policy in deploy workflow | sre-engineer | OPEN |

## R-PROCESS-* (governance / process)

| ID | Risk | P | I | Score | Bucket | Root cause | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|---|---|---|
| R-PROCESS-001 | Owner-gating queue backlog (Sumit > 5 actions/day) | 3 | 3 | 9 | 🟠 | 24/7 autonomous agents | Owner 2×30min/day; defer non-urgent to weekly review | Sumit | OPEN |
| R-PROCESS-002 | Charter scope creep mid-sprint | 3 | 3 | 9 | 🟠 | Sales pressure | CH-AMEND gate; charter-OK required for any > 1 day task | Sumit | OPEN |
| R-PROCESS-003 | Subagent context drift (lost in long context) | 4 | 2 | 8 | 🟠 | Context window limits | Sub-task isolation; `taskId` checkpoints | lead | OPEN |
| R-PROCESS-004 | Knowledge loss on agent restart | 2 | 3 | 6 | 🟡 | Ephemeral worker context | Daily log + MEMORY.md sync; cloud memory retrieval | lead | OPEN |

## R-SEC-* (security)

| ID | Risk | P | I | Score | Bucket | Root cause | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|---|---|---|
| R-SEC-001 | Public-API key leak (env var in GH) | 1 | 5 | 5 | 🟡 | Git history | gh-secret-scanning + secret-rotation runbook | security-engineer | OPEN |
| R-SEC-002 | Tenant isolation breach (cross-tenant data) | 2 | 5 | 10 | 🟠 | ORM raw SQL or middleware bypass | Per-request tenant-scope assertion; integration test | security-engineer + platform-engineer | OPEN |
| R-SEC-003 | Dependency CVE (critical, no auto-patch) | 3 | 4 | 12 | 🟠 | Dependabot rate-limit + manual review | Weekly CVE sweep; emergency patch SLA 24h | sre-engineer | OPEN |
| R-SEC-004 | IDOR on `/admin/remove-customer` | 1 | 5 | 5 | 🟡 | Owner-only endpoint | Two-eye confirmation; audit-log on every call | platform-engineer | OPEN |

---

## Mitigation strategies (universal pattern)

1. **Detect**: monitoring + canary + synthetic + alert (P0 in < 5 min)
2. **Mitigate**: rollback OR feature-flag-off OR manual stop-gap (< 15 min)
3. **Recover**: full RCA within 24h, fix-and-test within 72h, ADR within 1 sprint
4. **Prevent**: regression test + runbook + on-call rotation; verified monthly

---

## Contingency playbooks

### CP-01: DLT clearance slip
Voice stays OFF for new tenants. Conversion continues on Starter-only path. Combo upgrade deferred. Daily check on DLT portal. Backup vendor: Smartflo direct.

### CP-02: VPS outage > 1h
- T+0: auto-page Sumit
- T+5: GHCR image + Hostinger snapshot restore on standby VPS
- T+30: DNS failover to backup VPS (pre-warmed, no traffic)
- T+60: full RCA + customer comm

### CP-03: Single paying customer churns in first 30 days
- Sumit personally within 4h
- 7-day post-mortem: why, what could we have caught
- Pattern-check across other 49 customers (silent-churn signal)

### CP-04: Major model outage (GPT-Swara + Groq both down)
- Rule-based fallback for voice (TTS pre-recorded script)
- WhatsApp text-only via WAHA
- Voice kill-switch auto-arm
- Wait for provider recovery

### CP-05: Budget overrun > 130% by mid-sprint
- Freeze non-critical work
- Sumit reviews cost; identifies waste
- Charter amendment with cost-cut plan

---

## Risk review cadence

- **Daily**: ops-engineer scans `R-VOICE-*`, `R-INFRA-*`, `R-PBILL-*` (auto-detected signals)
- **Weekly**: lead + Sumit review all 🔴 and any new 🟠
- **Per-sprint**: full review; update status OPEN→MITIGATED→CLOSED
- **Quarterly**: re-score, archive CLOSED, retire noise