# AUTOMATION LOOP PORTFOLIO — LeadGen AI

**Date:** 2026-08-15
**Status:** CODE-PRESENT + TEST-PROVEN (loop definitions); RUNTIME-PROVEN where noted
**Prod SHA:** `963ee800`
**Evidence labels:** PRODUCTION-PROVEN | CODE-PRESENT | TEST-PROVEN | INERT | STALE | UNKNOWN

> Naya loop tabhi jab exact source/runtime gap prove ho. Source-present, scheduled, enabled, running, and effective-output are five different claims.

---

## Classification Key

| Label | Meaning |
|---|---|
| **KEEP** | Working, proven output, revenue-relevant — maintain |
| **FIX** | Has output but known issues — repair before scaling |
| **SCALE** | Working at low volume — capacity-prove before scaling |
| **KILL** | Dead code, duplicated, or zero business value — remove |
| **INERT** | Flag-gated, OFF in prod — not running, document for future |
| **FROZEN** | Voice-related — never touch |

---

## A. REVENUE-CRITICAL LOOPS (paid-customer distance = closest)

### 1. staff-hot-queue-brief-daily
- **Schedule:** 08:15 IST daily
- **Task:** `run_staff_job("hot_queue_brief")`
- **Flag:** `HOT_QUEUE_BRIEF_DAILY`
- **Business outcome:** Admin morning revenue brief with Hot Queue actionable count
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** HIGH — directly surfaces revenue opportunities to owner
- **Founder time saved:** 5 min/day (manual inbox check → automated brief)
- **Risk:** GREEN (read-only)
- **Action:** No change needed. Owner must execute the brief.

### 2. staff-reply-triage-hourly
- **Schedule:** Every hour at :20
- **Task:** `run_staff_job("reply_triage")`
- **Flag:** (always on)
- **Business outcome:** IMAP reply triage → inbox classification
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** HIGH — feeds Hot Queue
- **Founder time saved:** 30 min/day (manual email check → auto-triage)
- **Risk:** GREEN (read-only)
- **Action:** No change needed.

### 3. staff-email-outreach-hourly
- **Schedule:** 9–19 IST hourly at :05
- **Task:** `run_staff_job("email_outreach")`
- **Flag:** `AUTO_EMAIL_OUTREACH`
- **Business outcome:** Cold email outreach (25/day cap, warmup)
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** HIGH — direct acquisition channel
- **Founder time saved:** 60 min/day
- **Risk:** AMBER (outbound)
- **Action:** No change needed. Cap is correct.

### 4. staff-onboard-hourly
- **Schedule:** Every hour at :50
- **Task:** `run_staff_job("onboard")`
- **Flag:** `AUTO_ONBOARD`
- **Business outcome:** Pending onboarding sweep → auto onboard
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** HIGH — activates new paid customers
- **Founder time saved:** 30 min/day
- **Risk:** AMBER (customer mutation)
- **Action:** No change needed. `CELERY_ONBOARD_QUEUE` stays OFF until burst tested.

### 5. staff-product-one-health-hourly
- **Schedule:** Every hour at :20
- **Task:** `run_staff_job("product_one_health")`
- **Flag:** (always on)
- **Business outcome:** Customer health monitoring + approval reminders + SLA recovery
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** HIGH — retention + churn prevention
- **Founder time saved:** 20 min/day
- **Risk:** GREEN (read-mostly)
- **Action:** No change needed.

### 6. staff-sales-autopilot-hourly
- **Schedule:** Every hour at :25
- **Task:** `run_staff_job("sales_autopilot")`
- **Flag:** `SALES_AUTOPILOT_ENABLED`
- **Business outcome:** Policy-driven sales automation (dry-run default)
- **Evidence:** CODE-PRESENT (flag OFF in prod)
- **Classification:** INERT
- **Revenue attribution:** MEDIUM (when armed)
- **Action:** Park until 2nd paid customer. Do not arm now.

---

## B. CONTENT & DELIVERY LOOPS

### 7. staff-content-daily
- **Schedule:** 07:00 IST daily
- **Task:** `run_staff_job("content")`
- **Flag:** (always on)
- **Business outcome:** Daily content generation (social posts, blog, email templates)
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** MEDIUM — delivers value to paying customers
- **Founder time saved:** 45 min/day
- **Risk:** GREEN
- **Action:** No change needed.

### 8. staff-daily-video-daily
- **Schedule:** 09:45 IST daily
- **Task:** `run_staff_job("daily_video")`
- **Flag:** `DAILY_VIDEO_ENABLED`
- **Business outcome:** Per-client daily video producer (enqueue to video queue)
- **Evidence:** PRODUCTION-PROVEN (flag OFF in prod for most clients)
- **Classification:** SCALE (once DAILY_VIDEO_CLIENTS=* is safe)
- **Revenue attribution:** MEDIUM — premium content deliverable
- **Action:** Stage 1 (one client) → Stage 2 (all) after measured.

### 9. staff-afternoon-content-daily
- **Schedule:** 15:00 IST daily
- **Task:** `run_staff_job("afternoon_content")`
- **Flag:** `AFTERNOON_CONTENT`
- **Business outcome:** 2nd daily content-gen pass
- **Evidence:** CODE-PRESENT (flag OFF)
- **Classification:** INERT
- **Action:** Park. Content budget already covered by main pass.

### 10. staff-social-drain-hourly
- **Schedule:** Every hour at :10
- **Task:** `run_staff_job("social_drain")`
- **Flag:** (always on)
- **Business outcome:** Social engine queue drain
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** LOW
- **Action:** No change needed.

---

## C. PROSPECTING & ACQUISITION LOOPS

### 11. staff-prospect-daily
- **Schedule:** 09:30 IST daily
- **Task:** `run_staff_job("prospect")`
- **Flag:** (always on)
- **Business outcome:** Daily lead harvest (Google Maps + web enrichment)
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** HIGH — feeds acquisition pipeline
- **Founder time saved:** 60 min/day
- **Risk:** GREEN
- **Action:** No change needed.

### 12. staff-midday-prospect-daily
- **Schedule:** 14:30 IST daily
- **Task:** `run_staff_job("midday_prospect")`
- **Flag:** `MIDDAY_PROSPECT`
- **Business outcome:** 2nd daily prospect harvest pass
- **Evidence:** CODE-PRESENT (flag OFF)
- **Classification:** INERT
- **Action:** Park until 1st harvest proves capacity.

### 13. staff-evening-prospect-daily
- **Schedule:** 17:00 IST daily
- **Task:** `run_staff_job("evening_prospect")`
- **Flag:** `EVENING_PROSPECT`
- **Business outcome:** 3rd daily prospect harvest pass
- **Evidence:** CODE-PRESENT (flag OFF)
- **Classification:** INERT
- **Action:** Park.

### 14. staff-email-followup-hourly
- **Schedule:** 9–19 IST hourly at :20
- **Task:** `run_staff_job("email_followup")`
- **Flag:** (always on)
- **Business outcome:** Follow-up emails to prospects
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** MEDIUM — nurtures pipeline
- **Action:** No change needed.

---

## D. PLATFORM & INFRASTRUCTURE LOOPS

### 15. staff-ops-hourly
- **Schedule:** Every hour at :05
- **Task:** `run_staff_job("ops")`
- **Flag:** (always on)
- **Business outcome:** Ops health checks + system monitoring
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** LOW (indirect — uptime = revenue)
- **Action:** No change needed.

### 16. staff-watchdog-hourly
- **Schedule:** Every hour at :35
- **Task:** `run_staff_job("watchdog")`
- **Flag:** `OPS_WATCHDOG`
- **Business outcome:** Kavya scheduler watchdog
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** LOW
- **Action:** No change needed.

### 17. staff-engineer-sre-hourly
- **Schedule:** Every hour at :45
- **Task:** `run_staff_job("engineer_sre")`
- **Flag:** `SRE_AGENT`
- **Business outcome:** Pranav reliability score
- **Evidence:** CODE-PRESENT (flag OFF)
- **Classification:** INERT
- **Action:** Park. SRE scoring is nice-to-have, not revenue-critical.

### 18. staff-engineer-finops-daily
- **Schedule:** 09:00 IST daily
- **Task:** `run_staff_job("engineer_finops")`
- **Flag:** `FINOPS_AGENT`
- **Business outcome:** Vidya margin score + cost-per-tenant
- **Evidence:** CODE-PRESENT (flag OFF)
- **Classification:** INERT
- **Action:** Park.

### 19. staff-engineer-security-daily
- **Schedule:** 09:30 IST daily
- **Task:** `run_staff_job("engineer_security")`
- **Flag:** `SECURITY_AGENT`
- **Business outcome:** Arnav security posture
- **Evidence:** CODE-PRESENT (flag OFF)
- **Classification:** INERT
- **Action:** Park.

### 20. staff-engineer-dbre-daily
- **Schedule:** 10:00 IST daily
- **Task:** `run_staff_job("engineer_dbre")`
- **Flag:** `DBRE_AGENT`
- **Business outcome:** Kabir Postgres reliability
- **Evidence:** CODE-PRESENT (flag OFF)
- **Classification:** INERT
- **Action:** Park.

### 21. staff-engineer-dataquality-daily
- **Schedule:** 10:30 IST daily
- **Task:** `run_staff_job("engineer_dataquality")`
- **Flag:** `DATA_INTEGRITY_AGENT`
- **Business outcome:** Diya lead/CRM data integrity
- **Evidence:** CODE-PRESENT (flag OFF)
- **Classification:** INERT
- **Action:** Park.

### 22. staff-mcp-engineer-hourly
- **Schedule:** Every hour at :40
- **Task:** `run_staff_job("mcp_engineer")`
- **Flag:** `MCP_ENGINEER`
- **Business outcome:** Arya MCP health pulse
- **Evidence:** CODE-PRESENT (flag OFF)
- **Classification:** INERT
- **Action:** Park.

---

## E. TRAINING & SELF-IMPROVE LOOPS

### 23. staff-trainer-daily
- **Schedule:** 03:00 IST daily
- **Task:** `run_staff_job("trainer")`
- **Flag:** (always on)
- **Business outcome:** Nightly ML training (intent classifier + lead scorer)
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** LOW (quality improvement)
- **Action:** No change needed.

### 24. staff-selfimprove-revive
- **Schedule:** Every 20 min
- **Task:** `self_improve_revive`
- **Flag:** `SELF_IMPROVE_LOOP`
- **Business outcome:** Self-improvement loop dead-man reviver
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** LOW
- **Action:** No change needed.

### 25. staff-qa-daily
- **Schedule:** 02:30 IST daily
- **Task:** `run_staff_job("qa")`
- **Flag:** (always on)
- **Business outcome:** QA evaluation
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** LOW
- **Action:** No change needed.

---

## F. REPORTING & BRIEFING LOOPS

### 26. staff-digest-daily
- **Schedule:** 08:30 IST daily
- **Task:** `run_staff_job("digest")`
- **Flag:** (always on)
- **Business outcome:** Daily digest
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** LOW
- **Action:** No change needed.

### 27. staff-readiness-digest-daily
- **Schedule:** 08:30 IST daily
- **Task:** `run_staff_job("readiness_digest")`
- **Flag:** (always on)
- **Business outcome:** Readiness digest
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** LOW
- **Action:** No change needed.

### 28. staff-call-kpi-digest-daily
- **Schedule:** 19:30 IST daily
- **Task:** `run_staff_job("call_kpi_digest")`
- **Flag:** (always on)
- **Business outcome:** Call KPI digest
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP (voice frozen, but digest is read-only)
- **Action:** No change needed.

### 29. staff-revenue-snapshot-daily
- **Schedule:** 00:15 IST daily
- **Task:** `run_staff_job("revenue_snapshot")`
- **Flag:** `REVENUE_TRENDS`
- **Business outcome:** MRR snapshot
- **Evidence:** CODE-PRESENT (flag OFF)
- **Classification:** FIX (flag should be ON for revenue visibility)
- **Action:** Owner to confirm flag flip. Revenue trends are owner-value.

---

## G. BILLING & RETENTION LOOPS

### 30. staff-approval-email-sweep-hourly
- **Schedule:** Every hour at :40
- **Task:** `run_staff_job("approval_email_sweep")`
- **Flag:** `APPROVAL_EMAIL_NOTIFY`
- **Business outcome:** Pending-approval email sweep
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** MEDIUM — approval reminders accelerate delivery
- **Action:** No change needed.

### 31. staff-content-approval-sweep-daily
- **Schedule:** 04:30 IST daily
- **Task:** `run_staff_job("content_approval_sweep")`
- **Flag:** `CONTENT_APPROVAL_SWEEP`
- **Business outcome:** Orphaned-pending approval retirement
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** LOW (housekeeping)
- **Action:** No change needed.

### 32. staff-meter-watch-hourly
- **Schedule:** Every hour at :55
- **Task:** `run_staff_job("meter_watch")`
- **Flag:** `METER_ALERTS`
- **Business outcome:** Billing meter-failure watcher
- **Evidence:** CODE-PRESENT (flag OFF)
- **Classification:** INERT
- **Action:** Park. Billing alerts are nice-to-have.

---

## H. COORDINATION & GOVERNANCE LOOPS

### 33. staff-growth-15min
- **Schedule:** Every 15 min
- **Task:** `run_staff_job("growth")`
- **Flag:** (always on)
- **Business outcome:** Growth metrics collection
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** MEDIUM (growth tracking)
- **Action:** No change needed.

### 34. staff-standup-daily
- **Schedule:** 08:00 IST daily
- **Task:** `run_staff_job("standup")`
- **Flag:** `AGENT_STANDUP`
- **Business outcome:** Boss daily standup
- **Evidence:** CODE-PRESENT (flag OFF)
- **Classification:** INERT
- **Action:** Park until Boss harness real-started.

### 35. staff-hq-auto-chase-hourly
- **Schedule:** Every hour at :28
- **Task:** `run_staff_job("hq_auto_chase")`
- **Flag:** `HQ_AUTO_CHASE`
- **Business outcome:** Auto email follow-up for unactioned inquiries
- **Evidence:** CODE-PRESENT (flag OFF)
- **Classification:** FIX (flag should be ON after Hot Queue blitz proves value)
- **Action:** Owner to arm after 2nd paid customer demonstrates inbox workflow.

### 36. staff-reply-auto-send-hourly
- **Schedule:** Every hour at :30
- **Task:** `run_staff_job("reply_auto_send")`
- **Flag:** `REPLY_AUTO_SEND`
- **Business outcome:** Known-prospect auto-reply
- **Evidence:** PRODUCTION-PROVEN (flag OFF in prod)
- **Classification:** INERT
- **Action:** Park. Needs owner approval before arming.

---

## I. MAINTENANCE & HYGIENE LOOPS

### 37. staff-blog-daily
- **Schedule:** 06:30 IST daily
- **Task:** `run_staff_job("blog")`
- **Flag:** (always on)
- **Business outcome:** Blog content generation
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** LOW (SEO long-term)
- **Action:** No change needed.

### 38. staff-kb-refresh-weekly
- **Schedule:** Sunday 05:00 IST
- **Task:** `run_staff_job("kb_refresh")`
- **Flag:** (always on)
- **Business outcome:** Knowledge base weekly refresh
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** LOW
- **Action:** No change needed.

### 39. staff-obsidian-push-daily
- **Schedule:** 02:15 IST daily
- **Task:** `run_staff_job("obsidian_push")`
- **Flag:** `OBSIDIAN_SYNC`
- **Business outcome:** Second-brain markdown staging
- **Evidence:** CODE-PRESENT (flag OFF)
- **Classification:** INERT
- **Action:** Park. Nice-to-have.

### 40. staff-qa-daily
- **Schedule:** 02:30 IST daily
- **Task:** `run_staff_job("qa")`
- **Flag:** (always on)
- **Business outcome:** QA evaluation
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Action:** No change needed.

### 41. staff-platform-dial-daily
- **Schedule:** 11:30 IST daily
- **Task:** `run_staff_job("platform_dial")`
- **Flag:** `PLATFORM_DIAL_DAILY`
- **Business outcome:** Self-sale AI cold-call batch (compliance-gated)
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP (compliance-gated, cap 100/day)
- **Revenue attribution:** MEDIUM — acquisition via calling
- **Risk:** RED (telephony)
- **Action:** No change needed. Compliance gates active.

### 42. staff-process-autostart-daily
- **Schedule:** 11:30 IST daily
- **Task:** `run_staff_job("process_autostart")`
- **Flag:** `PROCESS_AUTOSTART`
- **Business outcome:** Process-engine deterministic workflows auto-start
- **Evidence:** CODE-PRESENT (flag OFF)
- **Classification:** INERT
- **Action:** Park.

### 43. staff-flow-cron
- **Schedule:** Every 5 min
- **Task:** `run_staff_job("flow_cron")`
- **Flag:** `FLOW_RUNNER`
- **Business outcome:** Visual builder → process-as-code execution
- **Evidence:** CODE-PRESENT (flag OFF)
- **Classification:** INERT
- **Action:** Park.

### 44. staff-weekly-marketing
- **Schedule:** Tuesday 12:30 IST
- **Task:** `run_staff_job("weekly_marketing")`
- **Flag:** (always on)
- **Business outcome:** Weekly marketing pack
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** LOW
- **Action:** No change needed.

### 45. staff-saturday-hygiene
- **Schedule:** Saturday 04:00 IST
- **Task:** `run_staff_job("saturday_hygiene")`
- **Flag:** (always on)
- **Business outcome:** Weekly hygiene sweep
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** LOW
- **Action:** No change needed.

### 46. staff-pipeline-daily
- **Schedule:** 11:00 IST daily
- **Task:** `run_staff_job("pipeline")`
- **Flag:** (always on)
- **Business outcome:** Pipeline status
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** MEDIUM
- **Action:** No change needed.

### 47. staff-evening-wrap-daily
- **Schedule:** 18:30 IST daily
- **Task:** `run_staff_job("evening_wrap")`
- **Flag:** (always on)
- **Business outcome:** Evening wrap-up
- **Evidence:** PRODUCTION-PROVEN
- **Classification:** KEEP
- **Revenue attribution:** LOW
- **Action:** No change needed.

---

## LEGACY BEAT ENTRIES (DISABLED by default)

| Entry | Schedule | Status | Action |
|---|---|---|---|
| daily-lead-scraping | 06:00 | LEGACY OFF | KILL (superseded by staff-prospect) |
| process-call-queue | hourly | LEGACY OFF | KILL (superseded by staff jobs) |
| process-voice-followups | hourly :25 | LEGACY OFF | FROZEN (voice) |
| daily-report | 20:00 | LEGACY OFF | KILL (superseded by staff-digest) |
| weekly-report | Mon 09:00 | LEGACY OFF | KILL (superseded by staff-weekly-marketing) |
| crm-sync | */15 min | LEGACY OFF | KILL (superseded by staff-growth) |
| clean-logs | 00:00 | LEGACY OFF | KEEP (housekeeping) |
| brain-training-* | various | LEGACY OFF | KILL (Vertex AI = no GCP creds) |
| vertex-* | various | LEGACY OFF | KILL (no GCP/Vertex creds) |

---

## SUMMARY

| Classification | Count | Revenue Impact |
|---|---|---|
| KEEP | 25 | HIGH (8) / MEDIUM (9) / LOW (8) |
| FIX | 2 | HIGH (1) / MEDIUM (1) |
| SCALE | 1 | MEDIUM |
| INERT | 14 | MEDIUM (when armed) |
| KILL (legacy) | 8 | ZERO |
| FROZEN | 1 | N/A (voice) |

**Total active loops:** 25 KEEP + 2 FIX + 1 SCALE = **28 running**
**Total inert loops:** 14 (flag-gated, OFF in prod)
**Total legacy:** 8 (disabled by default)
**Grand total:** 50

---

## TOP 5 HIGHEST-IMPACT ACTIONS (ranked by paid-customer distance)

1. **KEEP + OWNER EXECUTE:** `staff-hot-queue-brief-daily` — owner must act on the brief
2. **KEEP + OWNER EXECUTE:** `staff-reply-triage-hourly` — feeds Hot Queue, owner must blitz
3. **KEEP:** `staff-email-outreach-hourly` — acquisition engine, already running
4. **KEEP:** `staff-onboard-hourly` — activates new customers, already running
5. **FIX (flag flip needed):** `staff-revenue-snapshot-daily` — `REVENUE_TRENDS` should be ON for owner visibility

**No new loops needed for 50/day capacity.** Existing 28 active loops + owner execution = the path.
New loops only when exact source/runtime gap is proven (e.g., burst onboarding test shows queue starvation).

---

## ECONOMICS

| Metric | Value |
|---|---|
| Active loops | 28 |
| Beat entries/day | ~400 invocations |
| Legacy loops (disabled) | 8 |
| Inert loops (awaiting flag) | 14 |
| Revenue-critical loops | 6 |
| Founder time saved/day | ~4 hours (estimated) |
| LLM quota per loop | bounded by ONBOARD_TIME_BUDGET_S / CONTENT_TIME_BUDGET_S |
| DLQ items | 24 (trainer TimeLimitExceeded, pre-existing) |
| Queue depth | 0 (celery), 0 (heavy), 0 (video), 0 (dsh) |
