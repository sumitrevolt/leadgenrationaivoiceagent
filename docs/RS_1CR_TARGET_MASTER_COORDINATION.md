# ₹1 Cr/Month Target — Master Coordination Document
**Date:** 2026-09-17  
**Status:** ACTIVE · 6-module execution plan  
**Authority:** PRD → ARCH → engineering tasks

---

## 0. The Honest Numbers

| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| **Monthly revenue** | ~₹2,000 (1 customer: Jiya) | ₹1,00,00,000 | **50,000×** |
| **Paid customers** | 1 | ~5,000 (at ₹1,999) | **5,000×** |
| **Weekly contacts** | ~875 | ~85,000 | **97×** |
| **Daily UPI confirmations** | ~0–5 | ~300+ | **60×** |
| **dev_workers rows** | 0 | >0 | **Execution proof missing** |

**Verdict:** ₹1 Cr/month is a **12-24 month horizon**, not a 30-day target. Two hard gates block revenue:
1. **DLT registration** — Voice product cold-outbound illegal without it
2. **Payment rail** — Manual UPI + owner bank-confirm caps at ~10-25 customers/day

---

## 1. Revenue Math (₹1 Cr/month decomposition)

### Product Mix (PRD §2b)
| Product | Share | ₹ value | Customers needed (at ARPU) |
|---------|-------|---------|---------------------------|
| AI Automated Marketing (Starter ₹1,999) | 62% | ₹62,00,000 | ~31,000 · ₹1,999/mo |
| AI Automated Marketing (Advanced ₹5,999) | — | part of 62% | — |
| AI Voice Calling Agent (₹4,999–₹19,999) | 33% | ₹33,00,000 | DLT-gated |
| Top-ups + annual prepay | 5% | ₹5,00,000 | Margin lever |

### Customer Count Scenarios
| Blend ARPU | Customers needed | Monthly growth (90d) |
|------------|------------------|---------------------|
| ₹1,999 (Starter) | **5,006** | ~55/day |
| ₹5,999 (Advanced) | **1,668** | ~19/day |
| ₹2,990 (mixed) | **3,345** | ~37/day |
| ₹19,999 (Voice Band C) | **501** | ~6/day |

**Reality check:** Voice is DLT-gated. Marketing is the volume engine. Mixed ARPU ₹2,990 → **3,345 customers** → **~37 paid/day**.

---

## 2. The 6 Execution Modules (ARCH §1)

### M1: Bot Workers & Agents Management
**Goal:** Prove agents are actually executing (dev_workers > 0 rows)

| Task | File | Status |
|------|------|--------|
| Fix `team.py:853` `cycle` fallback | `app/platform/team.py` | ❌ TODO |
| Create `dev_workers.py` (execution prover) | `app/platform/dev_workers.py` | ❌ TODO |
| Wire `DurableTaskStore.idempotency_key` as real truth | `app/platform/automation_orchestrator.py` | ❌ TODO |
| Generate `AGENT_REGISTRY.md` from `STAFF` (31 keys) | `scripts/gen_agent_registry.py` | ❌ TODO |
| Fix `_KNOWN_TOOLS` gap (openclaw/workbuddy/codex absent) | `app/platform/coordination_hub_auth.py` | ⚠️ Owner-gated |

**Owner action:** Approve enrollment for `openclaw/workbuddy/codex` in `_KNOWN_TOOLS`

### M2: Automation Optimization
**Goal:** Close 97× contact capacity gap (875/week → 85,000/week)

| Task | File | Status |
|------|------|--------|
| Create `capacity_ledger.py` (single source for channel caps) | `app/platform/capacity_ledger.py` | ❌ TODO |
| Emit per-channel capacity + blocked-by-compliance counters | `app/platform/auto_outreach.py` | ❌ TODO |
| Write `data/capacity_snapshot.json` (consumed by M5) | `data/capacity_snapshot.json` | ❌ TODO (runtime) |
| Add tests for 97× gap computation | `tests/test_capacity_ledger.py` | ❌ TODO |

**Critical constraint:** Compliance inviolate — promo window 09:00-19:00 IST, DND fail-CLOSED, cold WhatsApp OFF

### M3: Sales & Product Strategy
**Goal:** Owner-confirmation flow for UPI payments

| Task | File | Status |
|------|------|--------|
| Create `owner_upi_confirm.py` (pending UPI → owner confirm → invoice) | `app/billing/owner_upi_confirm.py` | ❌ TODO |
| Build `/app/revenue-kit` + `/app/inbox` one-click confirm surface | `app/api/owner_revenue_kit.py` | ❌ TODO |
| Annual-first default flag on checkout | `app/marketing/packages.py` | ❌ TODO |
| Tests: confirm→invoice in `data/invoices.jsonl` | `tests/test_owner_upi_confirm.py` | ❌ TODO |

**Non-negotiable:** No payment gateway. Manual UPI only. Owner is sole confirmer.

### M4: Telegram Setup (PARTIALLY COMPLETE)
**Goal:** End-to-end owner notification feed

| Task | File | Status |
|------|------|--------|
| ✅ Create 10 chats (2 channels + 8 supergroups) | — | ✅ DONE (2026-09-13) |
| ✅ Create 3 coordination chats (workers, agents, admin) | — | ⏸️ **PENDING: needs phone number** |
| ✅ Add bot as admin to Marketing-Community | — | ✅ DONE |
| ❌ Add bot as admin to remaining 9 chats | — | ⏸️ **PENDING: manual or Telethon** |
| ✅ Create `owner_notify.py` (L1 egress) | `app/utils/owner_notify.py` | ✅ DONE (2026-09-16) |
| ❌ Run `telegram_setup.py --apply` (descriptions/topics/pins) | `scripts/telegram_setup.py` | ⏸️ **PENDING: needs bot as admin** |
| ❌ Verify egress: `send_owner('Test', severity='P0', evidence='verify')` | — | ⏸️ **PENDING** |

**Owner action required:** Provide phone number (+91XXXXXXXXXX) for Telethon auth, OR manually create 3 chats + add bot as admin

### M5: Performance Tracking
**Goal:** Verified vs claimed metrics separation

| Task | File | Status |
|------|------|--------|
| Create `KpiRecord` schema with `verified: bool` + `evidence` | `app/platform/kpi_ledger.py` | ❌ TODO |
| Force `workforce` source → `UNVERIFIED` label | `app/utils/owner_feed.py` | ✅ DONE (already enforced) |
| Wire existing dashboards (`/app/bot-command-center`, Prometheus/Grafana) | — | ✅ EXIST |
| Document router gotcha: `Depends(...)` = `route.dependant.dependencies` | `docs/architecture/` | ❌ TODO |

**Critical:** `data/workforce_live_status.json` claims are **NOT trustworthy** — `FORCE_UNVERIFIED` already enforced

### M6: Production VVS & Deployment
**Goal:** Deployment stability + no false successes

| Task | File | Status |
|------|------|--------|
| ✅ `deploy_vps.sh` = single deploy authority | `scripts/deploy_vps.sh` | ✅ DONE |
| ✅ False success guard (no `docker compose up -d app`) | `tests/test_no_app_container_drift.py` | ✅ DONE |
| ❌ Add log rotation (`RotatingFileHandler`) | `app/utils/logger.py` | ⚠️ Gap: plain `FileHandler` = disk blowup risk |
| ✅ Deploy proof: `/health.version == deployed sha` + skew check | `scripts/deploy_vps.sh` | ✅ DONE |

---

## 3. Current State vs Target Timeline

### Phase 0: Unblock (Days 0-7) — THIS WEEK
**Exit:** ≥2 paying Marketing customers (Jiya + 1)

| Check | Status |
|-------|--------|
| Owner authenticated `/app/inbox` 15-30 min/day | ⏸️ **OWNER ACTION** |
| UPI Bind/Re-Approve flow tested | ⏸️ **OWNER ACTION** |
| Bank credit confirmation working | ⏸️ **OWNER ACTION** |
| M1: Fix `team.py:853` cycle fallback | ❌ Not started |
| M4: Create 3 missing Telegram chats | ⏸️ **OWNER ACTION (phone number)** |

### Phase 1: System for 1-3 paid/day (Days 8-30)
**Exit:** ≥1 paid/day sustained 7 days; onboarding fail rate <10%

| Task | Owner action |
|------|-------------|
| GSC creds → flag flip (`GSC_ENABLED=1`) | Owner: DNS TXT verify |
| Paid ads (Meta/Google) → `/audit` with UTMs | Owner: approve budget |
| Hot Queue SLA + optional second closer | Owner: hire/training |
| M1: `dev_workers.py` execution prover | Engineering |
| M2: `capacity_ledger.py` | Engineering |
| M3: `owner_upi_confirm.py` | Engineering |

### Phase 2: Toward ~10 paid/day (Days 31-60)
**Exit:** Peak week ≥5-10 paid/day; month-1 churn <5%

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
| Kill criteria: CAC > 1 mo GM → pause ads | Engineering |

### Phase 4: Scale to ₹1 Cr/month (Months 4-12)
**Exit:** 3,345+ customers; ₹1 Cr/month MRR

| Condition | Status |
|-----------|--------|
| DLT registration complete | ⏸️ **OWNER PAPERWORK** |
| Verified payment rail (or owner-run collections desk) | ⏸️ **OWNER DECISION** |
| 20-50 human telecallers | ⏸️ **OWNER HIRING** |
| Paid ads budget (₹X/month) | ⏸️ **OWNER BUDGET** |
| Automation: 85,000 contacts/week capacity | Engineering (M2) |

---

## 4. Owner Decisions Required (BLOCKERS)

| # | Decision | Impact | Urgency |
|---|----------|--------|---------|
| **D1** | Provide phone number for Telegram Telethon auth | Unlocks M4 (Telegram coordination grid) | **HIGH** |
| **D2** | Authenticate `/app/inbox` 15-30 min/day | Unlocks 2nd paid customer (Phase 0 exit) | **HIGH** |
| **D3** | DLT registration for Voice product cold-outbound | Unlocks 33% of ₹1 Cr revenue | **MEDIUM** |
| **D4** | Paid ads budget (Meta/Google) | Closes 97× contact capacity gap | **MEDIUM** |
| **D5** | Human telecaller hiring (20-50) | Required for ₹1 Cr volume | **LOW** (Phase 3+) |
| **D6** | Collections desk for UPI confirmation | Required for 300+ payments/day | **LOW** (Phase 3+) |
| **D7** | Approve `openclaw/workbuddy/codex` enrollment | Unlocks M1 agent coordination | **LOW** |

---

## 5. Engineering Tasks (No Owner Action Required)

### P0: Execution Proof (M1)
- [ ] Fix `team.py:853` `cycle` fallback → trust real events only
- [ ] Create `dev_workers.py` with DB-backed idempotency
- [ ] Wire `DurableTaskStore.idempotency_key` as canonical truth
- [ ] Generate `AGENT_REGISTRY.md` from `STAFF` (31 keys)
- [ ] Tests: `test_dev_workers_execution_proof.py`

### P1: Capacity Ledger (M2)
- [ ] Create `capacity_ledger.py` (channel caps + gap computation)
- [ ] Emit per-channel capacity counters in `auto_outreach.py`
- [ ] Write `data/capacity_snapshot.json`
- [ ] Tests: `test_capacity_ledger.py` (97× gap verified)

### P2: Owner UPI Confirm (M3)
- [ ] Create `owner_upi_confirm.py` (pending → confirm → invoice)
- [ ] Build `/app/revenue-kit` surface
- [ ] Annual-first default flag
- [ ] Tests: `test_owner_upi_confirm.py`

### P3: Telegram Egress (M4)
- [ ] ⏸️ **BLOCKED: Owner phone number for Telethon auth**
- [ ] After chats created: run `telegram_setup.py --apply`
- [ ] Verify egress: `send_owner('Test', severity='P0', evidence='verify')`

### P4: Verified KPIs (M5)
- [ ] Create `kpi_ledger.py` with `verified: bool` + `evidence`
- [ ] Document router gotcha (`Depends(...)` → `route.dependant.dependencies`)
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
| `scripts/telethon_create_groups.py` | Userbot chat creation (Path B) |
| `app/utils/owner_notify.py` | L1 egress (severity routing, dedupe, rate-limit) |
| `app/utils/owner_feed.py` | Event store (14KB, TEST-PROVEN) |
| `app/platform/team.py` | 31-agent registry (STAFF) |
| `app/platform/automation_orchestrator.py` | Task orchestration (DurableTaskStore) |
| `app/billing/gst_invoice.py` | Invoice ledger (stats() line 489) |
| `app/marketing/packages.py` | Pricing (₹1,999/₹5,999) |
| `app/marketing/voice_packages.py` | Voice pricing (₹4,999/₹9,999/₹19,999) |

---

## 8. Next Immediate Actions

### Today (Owner):
1. **Provide phone number** for Telegram setup (unlocks M4)
2. **Authenticate `/app/inbox`** 15-30 min (unlocks Phase 0)
3. **Check UPI pending payments** → Bind + Approve + bank confirm

### This Week (Engineering):
1. **M1:** Fix `team.py:853` cycle fallback (5 min)
2. **M6:** Add log rotation to `logger.py` (15 min)
3. **M1:** Create `dev_workers.py` stub (1 hour)

### This Month:
1. **M3:** Build `owner_upi_confirm.py` + `/app/revenue-kit`
2. **M2:** Create `capacity_ledger.py`
3. **M5:** Create `kpi_ledger.py`

---

**Bottom line:** ₹1 Cr/month is a **12-24 month program**, not a sprint. Current verified baseline = **₹5,997 collected FY 2026-27**, 1 paying customer. The architecture is designed. The code paths exist. What's missing is **execution proof** (M1) + **owner capacity** (D1-D7).

🐦 pelican
