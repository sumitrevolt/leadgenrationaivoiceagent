# â‚¹1 Cr/Month Target â€” Master Coordination Document
**Date:** 2026-09-17  
**Status:** ACTIVE Â· 6-module execution plan  
**Authority:** PRD â†’ ARCH â†’ engineering tasks

---

## 0. The Honest Numbers

| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| **Monthly revenue** | ~â‚¹2,000 (1 customer: Jiya) | â‚¹1,00,00,000 | **50,000Ã—** |
| **Paid customers** | 1 | ~5,000 (at â‚¹1,999) | **5,000Ã—** |
| **Weekly contacts** | ~875 | ~85,000 | **97Ã—** |
| **Daily UPI confirmations** | ~0â€“5 | ~300+ | **60Ã—** |
| **dev_workers rows** | 0 | >0 | **Execution proof missing** |

**Verdict:** â‚¹1 Cr/month is a **12-24 month horizon**, not a 30-day target. Two hard gates block revenue:
1. **DLT registration** â€” Voice product cold-outbound illegal without it
2. **Payment rail** â€” Manual UPI + owner bank-confirm caps at ~10-25 customers/day

---

## 1. Revenue Math (â‚¹1 Cr/month decomposition)

### Product Mix (PRD Â§2b)
| Product | Share | â‚¹ value | Customers needed (at ARPU) |
|---------|-------|---------|---------------------------|
| AI Automated Marketing (Starter â‚¹1,999) | 62% | â‚¹62,00,000 | ~31,000 Â· â‚¹1,999/mo |
| AI Automated Marketing (Advanced â‚¹5,999) | â€” | part of 62% | â€” |
| AI Voice Calling Agent (â‚¹4,999â€“â‚¹19,999) | 33% | â‚¹33,00,000 | DLT-gated |
| Top-ups + annual prepay | 5% | â‚¹5,00,000 | Margin lever |

### Customer Count Scenarios
| Blend ARPU | Customers needed | Monthly growth (90d) |
|------------|------------------|---------------------|
| â‚¹1,999 (Starter) | **5,006** | ~55/day |
| â‚¹5,999 (Advanced) | **1,668** | ~19/day |
| â‚¹2,990 (mixed) | **3,345** | ~37/day |
| â‚¹19,999 (Voice Band C) | **501** | ~6/day |

**Reality check:** Voice is DLT-gated. Marketing is the volume engine. Mixed ARPU â‚¹2,990 â†’ **3,345 customers** â†’ **~37 paid/day**.

---

## 2. The 6 Execution Modules (ARCH Â§1)

### M1: Bot Workers & Agents Management
**Goal:** Prove agents are actually executing (dev_workers > 0 rows)

| Task | File | Status |
|------|------|--------|
| Fix `team.py:853` `cycle` fallback | `app/platform/team.py` | âŒ TODO |
| Create `dev_workers.py` (execution prover) | `app/platform/dev_workers.py` | âŒ TODO |
| Wire `DurableTaskStore.idempotency_key` as real truth | `app/platform/automation_orchestrator.py` | âŒ TODO |
| Generate `AGENT_REGISTRY.md` from `STAFF` (31 keys) | `scripts/gen_agent_registry.py` | âŒ TODO |
| Fix `_KNOWN_TOOLS` gap (openclaw/workbuddy/codex absent) | `app/platform/coordination_hub_auth.py` | âš ï¸ Owner-gated |

**Owner action:** Approve enrollment for `openclaw/workbuddy/codex` in `_KNOWN_TOOLS`

### M2: Automation Optimization
**Goal:** Close 97Ã— contact capacity gap (875/week â†’ 85,000/week)

| Task | File | Status |
|------|------|--------|
| Create `capacity_ledger.py` (single source for channel caps) | `app/platform/capacity_ledger.py` | âŒ TODO |
| Emit per-channel capacity + blocked-by-compliance counters | `app/platform/auto_outreach.py` | âŒ TODO |
| Write `data/capacity_snapshot.json` (consumed by M5) | `data/capacity_snapshot.json` | âŒ TODO (runtime) |
| Add tests for 97Ã— gap computation | `tests/test_capacity_ledger.py` | âŒ TODO |

**Critical constraint:** Compliance inviolate â€” promo window 09:00-19:00 IST, DND fail-CLOSED, cold WhatsApp OFF

### M3: Sales & Product Strategy
**Goal:** Owner-confirmation flow for UPI payments

| Task | File | Status |
|------|------|--------|
| Create `owner_upi_confirm.py` (pending UPI â†’ owner confirm â†’ invoice) | `app/billing/owner_upi_confirm.py` | âŒ TODO |
| Build `/app/revenue-kit` + `/app/inbox` one-click confirm surface | `app/api/owner_revenue_kit.py` | âŒ TODO |
| Annual-first default flag on checkout | `app/marketing/packages.py` | âŒ TODO |
| Tests: confirmâ†’invoice in `data/invoices.jsonl` | `tests/test_owner_upi_confirm.py` | âŒ TODO |

**Non-negotiable:** No payment gateway. Manual UPI only. Owner is sole confirmer.

### M4: Telegram Setup (PARTIALLY COMPLETE)
**Goal:** End-to-end owner notification feed

| Task | File | Status |
|------|------|--------|
| âœ… Create 10 chats (2 channels + 8 supergroups) | â€” | âœ… DONE (2026-09-13) |
| âœ… Create 3 coordination chats (workers, agents, admin) | â€” | â¸ï¸ **PENDING: needs phone number** |
| âœ… Add bot as admin to Marketing-Community | â€” | âœ… DONE |
| âŒ Add bot as admin to remaining 9 chats | â€” | â¸ï¸ **PENDING: manual or Telethon** |
| âœ… Create `owner_notify.py` (L1 egress) | `app/utils/owner_notify.py` | âœ… DONE (2026-09-16) |
| âŒ Run `telegram_setup.py --apply` (descriptions/topics/pins) | `scripts/telegram_setup.py` | â¸ï¸ **PENDING: needs bot as admin** |
| âŒ Verify egress: `send_owner('Test', severity='P0', evidence='verify')` | â€” | â¸ï¸ **PENDING** |

**Owner action required:** Provide phone number (+91XXXXXXXXXX) for Telethon auth, OR manually create 3 chats + add bot as admin

### M5: Performance Tracking
**Goal:** Verified vs claimed metrics separation

| Task | File | Status |
|------|------|--------|
| Create `KpiRecord` schema with `verified: bool` + `evidence` | `app/platform/kpi_ledger.py` | âŒ TODO |
| Force `workforce` source â†’ `UNVERIFIED` label | `app/utils/owner_feed.py` | âœ… DONE (already enforced) |
| Wire existing dashboards (`/app/bot-command-center`, Prometheus/Grafana) | â€” | âœ… EXIST |
| Document router gotcha: `Depends(...)` = `route.dependant.dependencies` | `docs/architecture/` | âŒ TODO |

**Critical:** `data/workforce_live_status.json` claims are **NOT trustworthy** â€” `FORCE_UNVERIFIED` already enforced

### M6: Production VVS & Deployment
**Goal:** Deployment stability + no false successes

| Task | File | Status |
|------|------|--------|
| âœ… `deploy_vps.sh` = single deploy authority | `scripts/deploy_vps.sh` | âœ… DONE |
| âœ… False success guard (no `docker compose up -d app`) | `tests/test_no_app_container_drift.py` | âœ… DONE |
| âŒ Add log rotation (`RotatingFileHandler`) | `app/utils/logger.py` | âš ï¸ Gap: plain `FileHandler` = disk blowup risk |
| âœ… Deploy proof: `/health.version == deployed sha` + skew check | `scripts/deploy_vps.sh` | âœ… DONE |

---

## 3. Current State vs Target Timeline

### Phase 0: Unblock (Days 0-7) â€” THIS WEEK
**Exit:** â‰¥2 paying Marketing customers (Jiya + 1)

| Check | Status |
|-------|--------|
| Owner authenticated `/app/inbox` 15-30 min/day | â¸ï¸ **OWNER ACTION** |
| UPI Bind/Re-Approve flow tested | â¸ï¸ **OWNER ACTION** |
| Bank credit confirmation working | â¸ï¸ **OWNER ACTION** |
| M1: Fix `team.py:853` cycle fallback | âŒ Not started |
| M4: Create 3 missing Telegram chats | â¸ï¸ **OWNER ACTION (phone number)** |

### Phase 1: System for 1-3 paid/day (Days 8-30)
**Exit:** â‰¥1 paid/day sustained 7 days; onboarding fail rate <10%

| Task | Owner action |
|------|-------------|
| GSC creds â†’ flag flip (`GSC_ENABLED=1`) | Owner: DNS TXT verify |
| Paid ads (Meta/Google) â†’ `/audit` with UTMs | Owner: approve budget |
| Hot Queue SLA + optional second closer | Owner: hire/training |
| M1: `dev_workers.py` execution prover | Engineering |
| M2: `capacity_ledger.py` | Engineering |
| M3: `owner_upi_confirm.py` | Engineering |

### Phase 2: Toward ~10 paid/day (Days 31-60)
**Exit:** Peak week â‰¥5-10 paid/day; month-1 churn <5%

| Task | Owner action |
|------|-------------|
| Multi-closer coverage inside TRAI window | Owner: hire 2-3 telecallers |
| Referral kit push (`/app/affiliates`) | Engineering |
| Pricing/`/start` CRO | Engineering |
| M5: `kpi_ledger.py` verified metrics | Engineering |
| M6: Log rotation fix | Engineering |

### Phase 3: Capacity design for 50/day (Days 61-90)
**Exit:** Written capacity plan + staging/dry-run of 50 simulated onboardings

| Task | Owner action |
|------|-------------|
| Lock CAC vs 1-month gross margin | Owner: approve ad spend |
| Sales factory roster + queue routing | Owner: hire 5-10 sales |
| Onboarding factory (parallel Celery) | Engineering |
| Billing ops: batch UPI confirm | Owner: hire collections desk |
| Kill criteria: CAC > 1 mo GM â†’ pause ads | Engineering |

### Phase 4: Scale to â‚¹1 Cr/month (Months 4-12)
**Exit:** 3,345+ customers; â‚¹1 Cr/month MRR

| Condition | Status |
|-----------|--------|
| DLT registration complete | â¸ï¸ **OWNER PAPERWORK** |
| Verified payment rail (or owner-run collections desk) | â¸ï¸ **OWNER DECISION** |
| 20-50 human telecallers | â¸ï¸ **OWNER HIRING** |
| Paid ads budget (â‚¹X/month) | â¸ï¸ **OWNER BUDGET** |
| Automation: 85,000 contacts/week capacity | Engineering (M2) |

---

## 4. Owner Decisions Required (BLOCKERS)

| # | Decision | Impact | Urgency |
|---|----------|--------|---------|
| **D1** | Provide phone number for Telegram Telethon auth | Unlocks M4 (Telegram coordination grid) | **HIGH** |
| **D2** | Authenticate `/app/inbox` 15-30 min/day | Unlocks 2nd paid customer (Phase 0 exit) | **HIGH** |
| **D3** | DLT registration for Voice product cold-outbound | Unlocks 33% of â‚¹1 Cr revenue | **MEDIUM** |
| **D4** | Paid ads budget (Meta/Google) | Closes 97Ã— contact capacity gap | **MEDIUM** |
| **D5** | Human telecaller hiring (20-50) | Required for â‚¹1 Cr volume | **LOW** (Phase 3+) |
| **D6** | Collections desk for UPI confirmation | Required for 300+ payments/day | **LOW** (Phase 3+) |
| **D7** | Approve `openclaw/workbuddy/codex` enrollment | Unlocks M1 agent coordination | **LOW** |

---

## 5. Engineering Tasks (No Owner Action Required)

### P0: Execution Proof (M1)
- [ ] Fix `team.py:853` `cycle` fallback â†’ trust real events only
- [ ] Create `dev_workers.py` with DB-backed idempotency
- [ ] Wire `DurableTaskStore.idempotency_key` as canonical truth
- [ ] Generate `AGENT_REGISTRY.md` from `STAFF` (31 keys)
- [ ] Tests: `test_dev_workers_execution_proof.py`

### P1: Capacity Ledger (M2)
- [ ] Create `capacity_ledger.py` (channel caps + gap computation)
- [ ] Emit per-channel capacity counters in `auto_outreach.py`
- [ ] Write `data/capacity_snapshot.json`
- [ ] Tests: `test_capacity_ledger.py` (97Ã— gap verified)

### P2: Owner UPI Confirm (M3)
- [ ] Create `owner_upi_confirm.py` (pending â†’ confirm â†’ invoice)
- [ ] Build `/app/revenue-kit` surface
- [ ] Annual-first default flag
- [ ] Tests: `test_owner_upi_confirm.py`

### P3: Telegram Egress (M4)
- [ ] â¸ï¸ **BLOCKED: Owner phone number for Telethon auth**
- [ ] After chats created: run `telegram_setup.py --apply`
- [ ] Verify egress: `send_owner('Test', severity='P0', evidence='verify')`

### P4: Verified KPIs (M5)
- [ ] Create `kpi_ledger.py` with `verified: bool` + `evidence`
- [ ] Document router gotcha (`Depends(...)` â†’ `route.dependant.dependencies`)
- [ ] Wire existing dashboards (Prometheus/Grafana)

### P5: Log Rotation (M6)
- [ ] Add `RotatingFileHandler` to `app/utils/logger.py`
- [ ] Configure size/time rotation (avoid disk blowup)

---

## 6. Evidence Labels (Always Apply)

| Label | Meaning |
|-------|---------|
| `PRODUCTION-PROVEN` | Verified live in prod (ledger, /health, smoke) |
| `CODE-PRESENT` | Code exists, not yet tested in prod |
| `TEST-PROVEN` | Tests green, not yet in prod |
| `UNKNOWN` | Unverified, need to probe |
| `STALE` | Was true, no longer valid |
| `PARTIAL` | Partially true (some paths work, some don't) |
| `LOCAL-ONLY` | Works locally, untested on VPS |

**Rule:** A claim with no label = claim nobody acts on.

---

## 7. Key Files Reference

| File | Purpose |
|------|---------|
| `deliverables/software-company/crore-strategy-PRD-2026-09-16.md` | Product requirements (Xu/PM) |
| `deliverables/software-company/crore-strategy-ARCH-2026-09-16.md` | System design (Gao/Architect) |
| `docs/architecture/EVENT_CONTRACTS.md` | Shared event schema (TaskRecord, FeedEvent, DevWorkerRecord) |
| `docs/gtm/HOT_QUEUE_BLITZ_CHECKLIST.md` | Phase 0 exit criteria |
| `docs/gtm/PRODUCT1_50_PAID_DAY_90D.md` | 50 paid/day capacity plan |
| `docs/gtm/CAPACITY_50_DAY.md` | Backend capacity proof (50 simulated onboardings) |
| `config/telegram/setup_spec.yaml` | 13-entity Telegram grid spec |
| `scripts/telegram_setup.py` | Bot-API bootstrap (descriptions/topics/pins) |
| `scripts/telegram_create_chats.py` | Userbot chat creation (Path B) |
| `app/utils/owner_notify.py` | L1 egress (severity routing, dedupe, rate-limit) |
| `app/utils/owner_feed.py` | Event store (14KB, TEST-PROVEN) |
| `app/platform/team.py` | 31-agent registry (STAFF) |
| `app/platform/automation_orchestrator.py` | Task orchestration (DurableTaskStore) |
| `app/billing/gst_invoice.py` | Invoice ledger (stats() line 489) |
| `app/marketing/packages.py` | Pricing (â‚¹1,999/â‚¹5,999) |
| `app/marketing/voice_packages.py` | Voice pricing (â‚¹4,999/â‚¹9,999/â‚¹19,999) |

---

## 8. Next Immediate Actions

### Today (Owner):
1. **Provide phone number** for Telegram setup (unlocks M4)
2. **Authenticate `/app/inbox`** 15-30 min (unlocks Phase 0)
3. **Check UPI pending payments** â†’ Bind + Approve + bank confirm

### This Week (Engineering):
1. **M1:** Fix `team.py:853` cycle fallback (5 min)
2. **M6:** Add log rotation to `logger.py` (15 min)
3. **M1:** Create `dev_workers.py` stub (1 hour)

### This Month:
1. **M3:** Build `owner_upi_confirm.py` + `/app/revenue-kit`
2. **M2:** Create `capacity_ledger.py`
3. **M5:** Create `kpi_ledger.py`

---

**Bottom line:** â‚¹1 Cr/month is a **12-24 month program**, not a sprint. Current verified baseline = **â‚¹5,997 collected FY 2026-27**, 1 paying customer. The architecture is designed. The code paths exist. What's missing is **execution proof** (M1) + **owner capacity** (D1-D7).

ðŸ¦ pelican

