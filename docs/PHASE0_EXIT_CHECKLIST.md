# Phase 0 Exit Checklist — Get 2nd Paying Customer

**Goal:** Exit Phase 0 by getting 2nd paying Marketing subscriber
**Target:** Jiya Makeover = 1st customer, need 2nd within 7 days
**Revenue impact:** ₹2,000 → ₹4,000/month (2× growth)

---

## Current State

| Metric | Value |
|--------|-------|
| Paid customers | 1 (Jiya Makeover) |
| Monthly revenue | ~₹2,000 |
| Target | ₹1,00,00,000/month |
| Gap | 50,000× |
| Phase | Phase 0 (not exited) |

---

## Owner Actions (15-30 min/day)

### Daily Routine

**Morning (10 min):**
1. Login to https://leadsgenai.in/app/inbox
2. Check **Hot Queue** — interested leads
3. Respond to inquiries (personalized, not templated)
4. Mark as "contacted" in system

**Afternoon (10 min):**
1. Check **Pending UPI Payments**
2. Bind new payments → Approve → Generate invoice
3. Confirm bank credit → Activate subscription
4. Send welcome email + onboarding

**Evening (10 min):**
1. Review **Revenue Dashboard**
2. Check **Campaign Performance**
3. Update **Lead Source Tracking**

---

## Conversion Funnel

```
Website Visit → Audit Request → Demo → Inquiry → UPI Payment → Bind → Approve → Invoice → Active Customer
    1000          100           50      20       10         5       3        2         1
     1%           5%           40%     40%      50%        60%     60%      100%      100%
```

**Current:** 1 customer from ~20 inquiries
**Target:** 3-5 customers/week → ₹6,000-15,000/week → ₹25,000-60,000/month

---

## UPI Payment Flow (Critical Path)

### Step 1: Customer Pays
- Customer sends UPI payment to `leadsgenai@ybl` (or your VPA)
- Transaction ID captured in system
- Status: `pending_confirmation`

### Step 2: Owner Binds Payment
- Go to `/app/inbox` → **Pending Payments**
- Click **Bind** → Enter transaction ID
- System matches payment to inquiry
- Status: `bound`

### Step 3: Owner Approves
- Click **Approve** → Confirm amount matches
- System generates invoice (INV/2026-27/XXXX)
- Status: `approved`

### Step 4: Bank Credit Check
- Check bank statement / UPI app
- Verify credit received
- Status: `confirmed`

### Step 5: Activate Subscription
- System auto-activates Marketing product
- Send welcome email + onboarding
- Add to `marketing_clients.jsonl`
- Status: `active`

---

## Success Metrics

### Daily
- [ ] Check inbox (15 min)
- [ ] Respond to all inquiries (< 1 hour)
- [ ] Process pending UPI payments

### Weekly
- [ ] 2+ new inquiries from Hot Queue
- [ ] 1+ new paid customer
- [ ] ₹4,000+ weekly revenue

### Monthly
- [ ] 10+ paid customers
- [ ] ₹20,000+ monthly revenue
- [ ] Exit Phase 0

---

## Common Issues & Fixes

### Issue: Payment not matching inquiry
**Fix:** Check UPI transaction ID, verify amount, manually link in DB

### Issue: Customer says payment sent but not received
**Fix:** Check bank statement, wait 24h, contact customer for screenshot

### Issue: Invoice not generating
**Fix:** Check `GSTIN` env var, verify `invoices.jsonl` writable

### Issue: Subscription not activating
**Fix:** Check `subscription.activate()` called, verify Redis state

---

## Scripts & Tools

### Check Pending Payments
```bash
python -c "from app.billing.owner_upi_confirm import get_confirm; c = get_confirm(); print(c.get_summary())"
```

### List Hot Queue
```bash
curl https://leadsgenai.in/app/inbox
```

### Check Revenue
```bash
curl https://leadsgenai.in/api/admin/dashboard | jq '.revenue'
```

---

## Next Steps

1. **Today:** Login to `/app/inbox`, check Hot Queue
2. **This week:** Respond to all inquiries, process 1 UPI payment
3. **Next week:** Get 2nd paying customer, exit Phase 0
4. **Month 1:** Reach 10 customers, ₹20k/month
5. **Month 3:** Reach 50 customers, ₹1L/month
6. **Month 6:** Reach 200 customers, ₹4L/month
7. **Month 12:** Reach 800 customers, ₹1Cr/month

---

**Questions?** Check [`docs/gtm/HOT_QUEUE_BLITZ_CHECKLIST.md`](docs/gtm/HOT_QUEUE_BLITZ_CHECKLIST.md)
