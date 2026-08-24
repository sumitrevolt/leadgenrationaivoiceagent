# 7-DAY REVENUE PLAN
**Date:** 2026-08-22  
**Objective:** Increase real collected revenue by 5× versus baseline (₹1,999 → ₹9,995) in 7 days using legitimate, measurable, production-safe automation.  
**Baseline:** See `DAY_0_REVENUE_BASELINE.md`  
**Blocking Rule:** Fix revenue blockers in rank order (see `REVENUE_BLOCKERS.md`). Never skip a higher-ranked blocker for a lower-ranked one.

---

## DAY 0 — TRUTH + REPAIR (Completed)
- [x] Baseline revenue established (`DAY_0_REVENUE_BASELINE.md`)
- [x] Infrastructure truth (prod SHA, containers, queues, health)
- [x] Hermes truth (no Desktop harness; infra handler only)
- [x] Bots truth (agent-os staff defined)
- [x] Providers healthy (5/5)
- [x] Pipeline inspected (prospects, invoices, marketing clients)
- [x] Top 10 revenue blockers ranked (`REVENUE_BLOCKERS.md`)
- [x] Repair P0 revenue path: Started with BLK-01 (Hot Queue owner bottleneck)

## DAY 1 — COMPLETE MONEY PATH
**Goal:** Prove end-to-end money path: lead → outreach → reply → conversation → offer → payment → onboarding.
**Actions:**
1. **Fix BLK-01 (Hot Queue owner bottleneck)**  
   - Modify `/app/inbox` to show 1-click UPI payment links for warm leads with positive replies.  
   - Ensure payment verification flow works (owner confirms UPI credit → instant workspace provisioning).  
   - Test with a synthetic warm lead (no real customer spam).  
2. **Verify BLK-02 (Trial-to-Paid Conversion Nudge)**  
   - Prepare automated trial expiration notice with UPI upgrade link (do not activate yet; wait for DAY 1 verification).  
3. **Verify BLK-03 (Single Customer Upsell Path)**  
   - Draft personalized ROI proposal for Jiya Makeover (Starter → Combo/Voice add-on).  
4. **Verify BLK-04 (GSC & pSEO Organic Inbound Dormant)**  
   - Confirm `GSC_ENABLEd=0` but credentials present; prepare to flip flag after DAY 1 verification.  
5. **Verify BLK-05 (Voice Post-Call Instant Offer Dispatch)**  
   - Check `POST_CALL_WHATSAPP` and `VOICE_CLOSE_WHATSAPP` flags; ensure templates exist.  
6. **Verify BLK-06 (High-Intent ICP Lead Filtering & Scoring)**  
   - Inspect current lead scoring implementation; ensure hot-lead surfacing works.  
7. **Verify BLK-07 (Automated Multi-Touch Stalled Lead Follow-ups)**  
   - Check `email_followup` scheduler for 48h/96h sequences.  
8. **Verify BLK-08 (Frictionless Manual UPI Onboarding Flow)**  
   - Confirm `UPI_AUTO_ACTIVATE=1` (scoped) and owner approval queue.  
9. **Verify BLK-09 (Own-Brand Video/Social Proof Automation)**  
   - Ensure `VIDEO_AD_CYCLE=1` and `DAILY_VIDEO_CLIENTS=*` are set.  
10. **Verify BLK-10 (Unified Admin Command Center Visibility)**  
    - Prepare Hermes Control Plane view in Admin dashboard (to be built after DAY 1).  

**Success Criteria for DAY 1:**  
- At least one warm lead from Hot Queue receives a 1-click UPI payment link.  
- Owner can confirm UPI credit and trigger instant workspace provisioning (no manual steps beyond UPI verification).  
- End-to-end money path tested with zero synthetic revenue (no fake payments).  
- All verification steps completed; no production changes made beyond BLK-01 fix.

## DAY 2 — LEAD QUALITY + CONVERSION
**Goal:** Improve ICP, scoring, personalization, offer, CTA, follow-up.
**Actions:**
1. **Activate BLK-04 (`GSC_ENABLED=1`)** after verifying credentials have read-only access to `sc-domain:leadsgenai.in`.  
2. **Refine lead scoring** (BLK-06) to prioritize high-ICP-fit, high-digital-gap, high-reachability leads.  
3. **Personalize outreach** using lead scores and ICP data (email/WhatsApp templates).  
4. **Test offer optimization** (BLK-19) for Starter vs. Combo vs. Voice tiers.  
5. **Improve follow-up sequences** (BLK-07) based on lead score and reply sentiment.  
6. **Begin trial-to-paid nudges** (BLK-02) for Sharma Solar and other trials.  
7. **Prepare upsell pitch** for Jiya Makeover (BLK-03).  

**Success Criteria for DAY 2:**  
- GSC rank tracking active and visible in admin dashboard.  
- Lead scoring system produces visible hot-lead surfacing in `/app/inbox`.  
- Outreach messages show personalization tokens (business name, niche, pain point).  
- At least one trial receives automated expiration notice with UPI upgrade link.

## DAY 3 — CHANNEL SCALE
**Goal:** Scale only proven safe channels (WhatsApp, email, voice) after verifying conversion economics.
**Actions:**
1. **Scale WhatsApp outreach** (if `WHATSAPP_AUTO_SEND` safe and compliant) after verifying suppression lists and opt-outs work.  
2. **Scale email outreach** warmup to increase daily send cap (maintain <25/day until warmup complete).  
3. **Scale voice calls** only if `PLATFORM_DIAL_DAILY=1` and `VOICE_LAUNCH_KILL=0` show consistent conversion; respect daily cap.  
4. **Monitor channel-specific CAC and payback period** via revenue attribution.  
5. **Do not scale** any channel that shows negative economics or compliance risk.  

**Success Criteria for DAY 3:**  
- At least one channel (WhatsApp, email, or voice) shows increased volume with stable or improved conversion rate.  
- No compliance violations (DND, opt-out, spam reports).  
- Revenue attribution shows positive ROI from scaled channel.

## DAY 4 — CONVERSION OPTIMIZATION
**Goal:** Analyze actual drop-offs in funnel and run controlled A/B tests.
**Actions:**
1. **Analyze funnel metrics** from `REVENUE_BLOCKERS.md` and `DAY_0_REVENUE_BASELINE.md`:  
   - Lead → Qualified  
   - Qualified → Contacted  
   - Contacted → Reply  
   - Reply → Opportunity  
   - Opportunity → Paid  
2. **Identify biggest drop-off** and design a controlled change (e.g., CTA wording, offer timing, follow-up delay).  
3. **Run A/B test** using existing feature flag infrastructure (or create a temporary flag).  
4. **Measure impact** on conversion rate and revenue per lead.  
5. **Iterate** until no further easy wins found.  

**Success Criteria for DAY 4:**  
- Funnel metrics show improvement in at least one stage.  
- A/B test results documented and winning variant identified.  
- No degradation in other funnel stages.

## DAY 5 — REACTIVATION + UPSELL
**Goal:** Target prior leads, stalled conversations, warm prospects, existing customers.
**Actions:**
1. **Reactivate prior leads** (non-trial, inactive) with new offer sequence (email/WhatsApp).  
2. **Resume stalled conversations** in Hot Queue that went cold after first reply.  
3. **Upsell existing customers** (starting with Jiya Makeover) to higher tiers or add-ons.  
4. **Referral program** activation for happy customers (if not already live).  
5. **Revenue attribution** to track reactivation and upsell revenue separately.  

**Success Criteria for DAY 5:**  
- At least one prior lead or stalled conversation moves to paid.  
- At least one existing customer upgrades or buys add-on.  
- Reactivation and upsell revenue tracked in daily revenue digest.

## DAY 6 — SCALE WINNERS
**Goal:** Increase volume only in segments producing verified positive economics.
**Actions:**
1. **Review DAY 4 and DAY 5 results** to identify winning segments (ICP, channel, offer, etc.).  
2. **Increase volume** in those segments (e.g., more leads from winning ICP, more calls in winning time window).  
3. **Maintain safety checks**: compliance gates, budget caps, kill switches.  
4. **Monitor for saturation** and diminishing returns; pause scaling if ROI drops.  
5. **Document scaling decisions** in `AUTOMATION_MATRIX.md`.  

**Success Criteria for DAY 6:**  
- Revenue growth accelerates in winning segments.  
- No increase in compliance violations or customer complaints.  
- CAC stays stable or decreases in scaled segments.

## DAY 7 — CLOSE + COLLECT
**Goal:** Prioritize hot leads, open offers, pending payments, onboarding blockers, renewal/upsell opportunities.
**Actions:**
1. **Hot leads:** Follow up with leads that have shown high intent (multiple website visits, demo requests).  
2. **Open offers:** Send reminders for proposals/offers sent but not yet accepted.  
3. **Pending payments:** Verify UPI credits for any payments in progress; provision workspaces instantly.  
4. **Onboarding blockers:** Fix any issues preventing new customers from realizing first value (e.g., missing brand assets, misconfigured channels).  
5. **Renewal/upsell:** Approach customers nearing end of first month for renewal or upsell.  
6. **Final revenue push:** Ensure all possible revenue-generating actions are taken before day end.  

**Success Criteria for DAY 7:**  
- Daily revenue digest shows progress toward 5× target.  
- No critical blockers remain unattended.  
- System left in a stable, automated state for continued operation post-7 days.

---

## Execution Principles
- **Production evidence > assumptions > chat claims.** Never fake numbers.  
- **One fix, zero regressions.** Use targeted regression tests before/after changes.  
- **Owner-gated actions:** Manual UPI confirmation, legal commitments, irreversible actions require explicit owner approval.  
- **Safety first:** Compliance gates (DND, TRAI, consent) never disabled.  
- **Measure everything:** Track leads, outreach, replies, conversions, revenue, CAC.  
- **Iterate daily:** Each day ends with verification and plan adjustment for next day.  

**Final KPI (Day 7 end):** Actual collected revenue (verified via `data/invoices.jsonl` and VPS DB).  

---  
**Next Immediate Action:** Begin DAY 1 work by inspecting and fixing BLK-01 (Hot Queue owner bottleneck) in `/app/inbox`.