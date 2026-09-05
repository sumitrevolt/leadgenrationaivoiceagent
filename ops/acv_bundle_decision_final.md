# ACV Bundle Decision — Council Options (Final)

## Status: ⏳ **OWNER DECISION REQUIRED** (5 days overdue, proposed Aug 27)

## Current Situation
- **MRR:** ₹5,997 (1 customer: Jiya makeover, INV/2026-27/0001)
- **Revenue Sprint Goal:** ₹5,00,000/7d by 2026-08-30 (MISSED)
- **Daily Hot Queue:** 43 leads recycling daily (owner hasn't clicked "Done")
- **Only paid customer since:** 2026-07-05 (27 days ago)
- **Email Outreach:** 4039 emails → <2% reply rate (reflexion Aug 29)

## Three Bundle Options (Revenue Math)

### Option 1: Annual-Prepaid Marketing Bundle (RECOMMENDED)
**Price:** ₹14,999/year (₹1,250/mo effective)
**Includes:**
- AI Marketing Automation (Starter: ₹1,999/mo value)
- 500 prospect calls/month (Voice callback feature)
- 200 AI-generated content posts
- Basic onboarding + 1 custom niche KB

**Revenue Math:**
- 1 sale = ₹14,999 upfront (covers 7.5 months at current MRR)
- **5 sales = ₹74,995** — immediate cash flow
- **33 sales = ₹4,94,967** (≈ ₹5L target)
- With 43 hot leads + modular kitchen pilot → 5-10 sales achievable

**Risk:** Lowest price resistance. Clear upgrade from ₹1,999/mo.

### Option 2: Mid-Tier Growth Bundle
**Price:** ₹55,000/year (₹4,583/mo effective)
**Includes:**
- AI Marketing Automation (Advanced: ₹5,999/mo value)
- 1,500 prospect calls/month (Voice Agent: ₹9,999/mo tier)
- 1,000 AI content posts
- Premium onboarding + custom niche KB + competitor monitoring
- Priority support + strategy calls

**Revenue Math:**
- 1 sale = ₹55,000
- 9 sales = ₹4,94,955 (≈ ₹5L target)

**Risk:** Higher price resistance. Targets agencies/boutique studios.

### Option 3: Enterprise Voice-Only (Niche-Focused)
**Price:** ₹19,999/year (₹1,667/mo effective)
**Includes:**
- AI Voice Calling Agent Standalone (Band B: ₹9,999/mo value)
- 3,000 minutes/month
- DLT-approved cold outbound
- Voice-only (no marketing automation)

**Revenue Math:**
- 1 sale = ₹19,999
- 25 sales = ₹4,99,975 (≈ ₹5L target)

**Risk:** Limited TAM. Best for high-ticket niche owners who want tele-calling.

## Decision Matrix

| Option | Price | 5L Target | Difficulty | Best For |
|--------|-------|-----------|------------|----------|
| **1** | **₹14,999/yr** | **33 sales** | **Easy** | **Fast revenue** |
| 2 | ₹55,000/yr | 9 sales | Medium | Agency TAM |
| 3 | ₹19,999/yr | 25 sales | Hard | Voice-only niche |

## DSH Allowlist — First Pilot Client

### Current DSH State (prod .env)
```bash
DSH_RUNTIME_ENABLED=1
DSH_SHADOW_ENABLED=1
DSH_ALLOWLIST_CSV=""
```

DSH runtime is ON but no clients are routed through it yet.

### Proposed First Client: Jiya Makeover
- **Status:** Current paying customer (₹1,999/mo, INV/2026-27/0001)
- **Rationale:** Safest pilot — existing customer, no migration risk
- **Mechanism:** Add to `DSH_ALLOWLIST_CSV` in .env
- **Rollback:** Remove from allowlist → instant revert to legacy pipeline

### DSH Allowlist Mechanism
1. Set `.env`: `DSH_ALLOWLIST_CSV="jiya_makeover"`
2. Route check: `app/integrations/dsh.py` checks `DSH_RUNTIME_FLAG` + allowlist
3. Shadow mode: DSH runs parallel for 48h before cutover
4. Dashboard: `/app/office` shows DSH status per client

## Recommendation
**Option 1 (Annual-Prepaid Bundle at ₹14,999)** + **DSH allowlist = jiya_makeover**

This is the fastest path:
- Revenue: 5-10 sales from 43 hot leads = ₹75K-₹150K immediate
- DSH pilot with Jiya proves migration path for other customers
- Modular kitchen pilot (Loop A) compounds lead flow

## Action Required (Owner)
1. **Pick Option 1/2/3** — I'll create the package in `packages.py`
2. **Confirm Jiya as DSH pilot** — I'll add to `.env` and deploy
3. **Click "Done" on today's 43 hot leads** — ntfy push has the button

**⏰ Decision needed now** — the 43 leads are waiting.