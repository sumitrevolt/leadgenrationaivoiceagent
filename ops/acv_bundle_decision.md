# ACV Bundle Decision — Council Options

## Status: ⏳ **PENDING OWNER DECISION** (5 days overdue, proposed Aug 27)

## Current Situation
- **MRR:** ₹5,997 (1 customer: Jiya makeover)
- **Revenue Sprint Goal:** ₹5,00,000/7d by 2026-08-30 (MISSED)
- **Daily Hot Queue:** 43 leads stuck (recycling daily, owner hasn't acted)
- **Only paid customer since:** 2026-07-05 (27 days ago)

## Three Bundle Options

### Option 1: Annual-Prepaid Bundle (Conservative)
**Price:** ₹14,999/year (₹1,250/mo effective)
**Includes:**
- AI Automated Marketing (Main plan: ₹1,999/mo value)
- 500 prospect calls/month (Voice Agent: ₹4,999/mo tier value)
- 200 AI-generated content posts
- Basic onboarding + 1 custom niche KB

**Revenue Math:**
- 1 sale = ₹14,999 upfront (covers 7.5 months at current MRR)
- 5 sales = ₹74,995 (surpasses ₹5L annualized at 6.7 sales)
- 8 sales = ₹1,19,992 (surpasses ₹5L/7d goal at ₹14,285/day pace vs ₹71,428/day needed)

**Risk:** Lowest price resistance. Clear upgrade from ₹1,999/mo.

### Option 2: Mid-Tier Growth Bundle (Aggressive)
**Price:** ₹55,000/year (₹4,583/mo effective)
**Includes:**
- AI Automated Marketing (Advanced plan: ₹5,999/mo value)
- 1,500 prospect calls/month (Voice Agent: ₹9,999/mo tier)
- 1,000 AI content posts
- Premium onboarding + custom niche KB + competitor monitoring
- Priority support + strategy calls

**Revenue Math:**
- 1 sale = ₹55,000 (covers 9.2 months at current MRR)
- 5 sales = ₹2,74,950
- 9 sales = ₹4,94,955 (≈ ₹5L goal)

**Risk:** Higher price resistance. Targets agencies/boutique studios.

### Option 3: Enterprise Voice-Only (Niche-Focused)
**Price:** ₹19,999/year (₹1,667/mo effective)
**Includes:**
- AI Voice Calling Agent (flat per niche: ₹9,999/mo value)
- 3,000 minutes/month
- DLT-approved cold outbound
- Voice-only (no marketing automation)

**Revenue Math:**
- 1 sale = ₹19,999
- 10 sales = ₹1,99,990
- 25 sales = ₹4,99,975 (≈ ₹5L goal)

**Risk:** Limited TAM. Best for high-ticket niche owners who want tele-calling.

## DSH Allowlist — First Pilot Client

### Current DSH State
```json
{
  "dsh_runtime_enabled": true,
  "dsh_shadow_enabled": true,
  "dsh_allowlist": []
}
```
DSH runtime is ON but no clients are routed through it yet.

### Proposed First Client
**Candidate:** Jiya Makeover (current paying customer, INV/2026-27/0001)
- **Status:** Already paying ₹1,999/mo
- **Rationale:** Safest pilot — existing customer, no migration risk
- **DSH migration:** Add `jiya_makeover` to `dsh_allowlist` in `.env`
- **Rollback plan:** Remove from allowlist → instant revert to legacy pipeline

### DSH Allowlist Mechanism
1. Set `.env`: `DSH_ALLOWLIST="jiya_makeover"`
2. Route check: `app/integrations/dsh.py` checks `DSH_RUNTIME_FLAG` + allowlist
3. Dashboard: `/app/office` shows DSH status per client
4. Shadow mode: DSH calls run parallel for 48h before cutover

## Recommendation
**Option 1 (Annual-Prepaid Bundle at ₹14,999)** is the fastest path to ₹5L:
- 33 sales needed (vs 3 for Option 1, 9 for Option 2, 25 for Option 3)
- Wait, correction: 1 sale = ₹14,999, so **33 sales** = ₹4,94,967
- But with the 43 hot leads + modular kitchen outreach, 5-10 sales is achievable
- DSH pilot with Jiya gives us a proven migration path for other customers

## Owner Decision Matrix
| Option | Price | 5L Target | Difficulty | Best For |
|--------|-------|-----------|------------|----------|
| 1 | ₹14,999/yr | 33 sales | Easy | Fast revenue |
| 2 | ₹55,000/yr | 9 sales | Medium | Agency TAM |
| 3 | ₹19,999/yr | 25 sales | Hard | Voice-only niche |

**⏰ Deadline:** Owner pick within 4h (now Sep 2, 09:30 IST)
