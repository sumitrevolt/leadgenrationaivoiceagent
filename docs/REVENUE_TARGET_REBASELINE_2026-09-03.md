# Revenue Target Re-baseline — 2026-09-03
**Owner decision (this session):** replace the ₹5,00,000 / 7-day goal with a defensible target; treat ₹5,00,000 as a 90-day milestone.
**Production authority (owner decision):** plan + local fixes only. No unattended production changes.

---

## 1. Verified starting state

| Metric | Value | Source |
|---|---|---|
| Lifetime collected revenue | **₹7,997.00** | `DAY_0_REVENUE_BASELINE.md` (corrected 2026-08-22) |
| Current MRR | **₹3,998.00** | 2 × Starter ₹1,999/mo |
| Paying customers | **2** (Jiya Makeover, Kamal) | Invoice ledger INV/0001, 0014, 0015 |
| ARPU | **₹1,999.00** | ₹3,998 / 2 |
| Outstanding UPI due | **₹0.00** (1 ambiguous row `upi_12` pending owner decision) | `DAY_0_REVENUE_BASELINE.md` |
| Prod health (checked 2026-09-03 08:48 IST) | **healthy**, `environment: production`, sha `036a4e4b`, uptime 5h 46m | `GET https://leadsgenai.in/health` |
| Ops endpoint auth | **HTTP 401** without token — admin gate working | `GET /api/ops/revenue-summary` |

**Caveat:** the lifetime / MRR figures above are dated **2026-08-22/23** — 11 days stale. The first action of the Day-1 war room is to re-pull live truth from the ledger before any plan is executed.

---

## 2. Why ₹5,00,000 in 7 days is not a target — it is a different business

Gap to close: ₹5,00,000 − ₹7,997 = **₹4,92,003 net-new, collected, in 7 days.**

At the current verified ARPU of ₹1,999, that requires **246 new paying customers in 7 days** — roughly **35 closes per day**.

Working backwards through a realistic funnel:

| Stage | Assumption | Required volume |
|---|---|---|
| Paid customers needed | — | 246 |
| Lead → paid (warm inbound, ₹2k Indian SMB SaaS, manual UPI) | 5% | ~4,920 qualified leads |
| Qualified leads needed per day | 4,920 / 7 | **~703 / day** |
| At 25% lead → qualified | — | **~2,800 new leads / day** |

Against that requirement, the live channel constraints are:

- Cold WhatsApp **OFF** (compliance).
- Email cap **25/day** (warmup).
- DND / TRAI gates and the consent ledger **must not be weakened**.
- Eligible trials in the system: **0** (verified 2026-08-23).
- Cold outbound voice is **DLT-gated**; the Jio Mobile DID is non-140 and therefore not legal for promotional calls.

**Conclusion:** the binding constraint is compliant channel capacity, not automation effort. ₹5L in 7 days cannot be reached without breaking a compliance gate — which is an explicit red line in `AGENTS.md` §5 and is not on the table.

---

## 3. Defensible target — 7-day sprint (2026-09-03 → 2026-09-10)

Adopts the sprint target already documented and evidence-based in `DAY_0_REVENUE_BASELINE.md`, rather than inventing new arithmetic.

| Tier | Net-new collected | Composition | Ending MRR |
|---|---|---|---|
| **Floor (commit)** | **₹9,995** | ~5 Starter-equivalents, or 1 Combo + 3 Starter | ~₹13,993 |
| **Base (plan)** | **₹16,000** | 2 Combo (₹5,999 × 2) + 2 Starter (₹1,999 × 2) + renewals | ~₹19,998 |
| **Stretch** | **₹25,000** | Base + 1 Voice Agent tier-1 (₹4,999) + 1 upsell | ~₹25,000+ |

**Governing metric:** verified **collected** cash only. No pipeline, no projections, no synthetic trials, no simulated payments — this is the existing truth rule and it stays.

### Where the money realistically comes from
1. **Hot Queue close-out (primary).** 42 warm leads were surfaced as of 2026-08-23; the 1-click UPI path is already deployed live on those cards (PR #430). This is the shortest path to cash and needs a fresh re-pull.
2. **Existing-customer upsell (highest probability).** Jiya and Kamal are both on Starter ₹1,999. A move to Combo/Advanced adds **+₹4,000 each**. Two conversations, no new acquisition cost.
3. **Renewals falling inside the window.** Kamal (last invoice Aug-03) is at renewal proximity.
4. **Reactivation of stalled conversations** already in the hot queue after a first reply.

---

## 4. ₹5,00,000 as a 90-day milestone — what it actually requires

| Metric | Value |
|---|---|
| Net-new collected required | ₹4,92,003 |
| New customers at current ARPU ₹1,999 | ~246 |
| New customers at blended ARPU ₹3,500 (with Combo mix) | ~140 |
| Sustained close rate needed (90 days, blended) | **~1.6 closes / day** |
| Qualified leads needed per day at 5% close | **~32 / day** |

**Implication:** this is a **channel-capacity build**, not a sprint. The 90-day plan must raise the compliant lead ceiling — email warmup past 25/day, transactional/service voice lanes (the Jio DID is legal there), programmatic SEO compounding, and GSC activation — then hold ~1.6 closes/day. The 7-day sprint's real job is to prove the close motion and surface the funnel's true conversion rate so the 90-day plan is built on measured data rather than assumption.

---

## 5. Operating rules confirmed this session

- **Production changes:** plan + local fixes only. Deploy remains owner-gated via `scripts/deploy_vps.sh`.
- **Compliance:** DND, TRAI windows, and the consent ledger are never disabled to hit a number.
- **Evidence:** every reported figure cites a file, endpoint, or log line. Nothing is reported as collected without ledger proof.
- **Recurring automations** (created 2026-09-03, window through 2026-09-10) now use the ₹9,995 floor / ₹16,000 base / ₹25,000 stretch ladder defined in §3.

---

## 6. Day-1 first actions

1. Re-pull live revenue truth (lifetime collected, MRR, active accounts) — the baseline in §1 is 11 days stale.
2. Re-pull the hot queue and rank the 42 warm leads by intent recency.
3. Draft and send the Jiya + Kamal Combo upsell (highest probability revenue in the window).
4. Resolve the `upi_12` ambiguous row (owner approve/reject) to clear the payment authorization gate.
5. Measure and record the actual lead → paid conversion rate, to parameterise the 90-day plan in §4.
