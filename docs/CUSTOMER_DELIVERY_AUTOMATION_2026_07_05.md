# Customer Value-Delivery Automation — Council Decision + 20 Improvements

**Date:** 2026-07-05 · **Trigger:** first paying customer (jiya makeover, ₹1,999) got ZERO delivered value and was ghosted. LLM council (4 lenses: ops-excellence · product/CX · automation-reliability · growth/retention) → this finalized direction.

## The incident (root cause, evidence-confirmed)

The automation **generated** real value for jiya — LIVE mini-site (`/b/jiya-makeover-d79d`), content pack, brand kit, ~18 content items, SEO tracking — but **delivered none of it**. Onboarding sent a WhatsApp asking her to "describe your business" (because she had no website); she **replied**; her reply was **never captured** (`awaiting_kb_interview` still True, `business_info` empty) → she was **ghosted forever** with no retry, no fallback, no human alert. Content generated → queued → drained, never posted (no social connected). `subscription: None` (billing record inconsistency).

**The core defect:** the flow is a fragile single thread — *send ask → wait → capture reply* — and delivery of value **depends on the customer replying**. Any broken link (inbound webhook not firing, phone-format mismatch, not-active-at-reply, reply-agent race, capture throwing into a `logger.debug`) = **paying customer silently ghosted**, while the dashboard says "setup_done: True, onboarded ✓."

## 🏛️ CHAIRMAN DECISION (council converged, all 4 lenses)

**Payment is a promise with a clock. The instant money clears, deliver value FIRST — don't ask, don't wait — and don't stop until the customer has RECEIVED and ACKNOWLEDGED something usable. No paying customer may ever sit in a silent intermediate state.**

Four non-negotiable principles:
1. **Value-first, block on nothing.** On `paid`, immediately push the live mini-site link + sample content. The KB interview becomes *optional enrichment*, never a gate. (This alone collapses 4 of 5 silent-failure modes.)
2. **"Delivered" = received + acknowledged** (link opened / reply / go-live confirm) — NEVER a backend flag (`setup_done`, `queued`, `awaiting_*`).
3. **Per-customer delivery state machine + dead-man switch.** States `paid → assets_built → delivered → acknowledged`, idempotent, persisted, queryable. Paid-but-not-delivered past SLA → **hard alert to founder** (the andon cord that would have caught jiya on day one).
4. **Fail LOUD.** Every never-raise wrapper must fail-**record** to `dlq:failed_tasks` + alert — the bare `except → logger.debug` is exactly what swallowed jiya's reply. Silent loss is banned.

## 📋 The 20 improvements (billionaire-grade, prioritized)

### P0 — Delivery guarantee (fix the bug class; build first)
1. **Value-first delivery on `paid`** — `deliver_client_value(client)`: WhatsApp the live mini-site link + 3-5 ready-to-post pieces within minutes of UPI clearing, before any question. Interview = optional enrichment.
2. **Per-customer `delivery_state` machine** on the clients_store record (`paid→assets_built→delivered→acknowledged`) — single source of truth, idempotent compare-and-set, every transition timestamped.
3. **Dead-man reconciliation sweep** (registered in `automation_health.EXPECTED_GAP_MIN`): scans active paid customers in a non-terminal state past SLA → bounded auto-retry → escalate. Paid→not-delivered = **hard founder alert**; delivered→not-acknowledged = soft nudge only.
4. **Fail-loud capture** — `try_capture_onboarding_reply` + all delivery steps: on failure, record to `dlq:failed_tasks` + log WARNING (never silent `logger.debug`). Robust phone-match (already last-10; add +country-code + WA-JID normalization).
5. **Multi-channel fallback chain** — WA no-ack in T → SMS → email → founder-call task. Idempotent, dedup-keyed on `(customer, artifact)`.
6. **"Stuck right now" operator surface** — admin/office panel listing every paid customer not yet `delivered`/`acknowledged`, with one-click deliver + full context.

### P1 — Value-first delivery experience (the ₹1,999 "worth it" moment)
7. **Deliver in first 5 minutes** — UPI clears → instant WA welcome with live mini-site link + sample posts.
8. **Flip onboarding ASK→DELIVER-first** — auto-build starter site/posts from business name + niche (+ Google Maps data); interview only "make it even better."
9. **Zero-friction mobile hub** (no login/OTP) — mini-site preview + every post with one-tap "Share to Instagram / WhatsApp Status."
10. **Mini-site drives visible outcomes** — prominent Call/WhatsApp-me button ringing HER phone → countable enquiries she attributes to the ₹1,999.
11. **Day-0 delivery-confirmation loop** — WA read-receipt; not confirmed in ~2h → SMS + email fallback → founder alert.
12. **Weekly "your marketing is working" WA digest** — 5 fresh tap-to-post pieces + tiny numbers (site views, enquiries).
13. **60-second voice-note walkthrough** at handover (Swara TTS) — "yeh aapki site hai, aise use karein" — human warmth, no reading.
14. **Fix `subscription: None`** — activation must create a consistent subscription record; reconcile existing active-but-subscription-less clients.

### P2 — Activation → retention → referral loop (growth engine)
15. **Define "activated"** = mini-site live + first content posted + customer confirmed she can see it — instrument this event; it's the real North-Star, not payment.
16. **First-inbound alert** — mini-site form/callback → ping customer AND founder on her first real lead ("someone contacted you via your new site") = the true aha + retention anchor.
17. **Peak-moment testimonial capture** — at go-live, collect a WA testimonial + before/after screenshot → auto 1-page case study.
18. **Unlock the 338 warm leads** — attach the jiya case study to the AI-drafted replies sitting in the Hot Queue (see outreach diagnosis).
19. **Local referral loop** — one-tap "share my site" + "refer a shop owner → both get ₹500 off / 1 free month" (local owners cluster in WhatsApp groups).
20. **Monthly ROI receipt** — plain-language WA voice-note report (visitors / calls / leads this month) — makes ROI legible = stops month-1 churn on a low-ticket plan.

## Biggest risk if ignored (council unanimous)
A paying customer who silently got nothing churns, disputes (Razorpay chargeback), and warns every other local shop in the tight WhatsApp-group word-of-mouth network — poisoning the exact 0→1 distribution the low-ACV model depends on. And you never find out, because the system proudly reports "onboarded ✓" over silent failure.

## Build order
P0 items 1-4 first (delivery guarantee + fail-loud) — this is the buildable fix that stops the bug class. Then P1 experience, then P2 growth loop. Customer-facing auto-send is flag-gated (`AUTO_DELIVER_VALUE`, default OFF) + founder-alert first, so delivery is reviewed before it goes live to real customers.

## ✅ FINAL STATUS (2026-07-05, all shipped/accounted)

| # | Item | Status |
|---|------|--------|
| 1-6 | P0 delivery guarantee (value-first, state machine, dead-man, fail-loud, stuck-surface) | ✅ built + deployed |
| 7-9 | value-first delivery / deliver-on-activation | ✅ built (wired into UPI activate) |
| 10 | mini-site call/WhatsApp button | ✅ already existed (verified) |
| 11 | delivery→acknowledged loop | ✅ built (inbound reply = ack) |
| 12 | weekly value digest | ✅ built (honest metrics, 6d) |
| 13 | voice-note walkthrough | ⏸ DEFERRED — needs WAHA audio/media-send capability (not verified); lowest value, higher complexity. Text delivery already walks the customer through. |
| 14 | subscription reconcile | ✅ non-bug (plan resolves = starter) |
| 15 | "activated" event | ✅ `is_activated` = acknowledged |
| 16 | first-inbound alert | ✅ already existed (CLIENT_HOT_LEAD_ALERT) |
| 17 | testimonial capture | ✅ built (gated AUTO_TESTIMONIAL, default OFF) |
| 18 | case study → 338 leads | ✅ generator built (honest, real assets); attach step = founder action |
| 19 | referral loop | ✅ built (config-driven REFERRAL_REWARD; no unilateral offer) |
| 20 | monthly ROI receipt + view tracking | ✅ built (real mini-site view tracking + 28d honest receipt) |

**Flags:** `AUTO_DELIVER_VALUE=1` ON (delivery + weekly + monthly live). `AUTO_TESTIMONIAL`, `REFERRAL_REWARD` = opt-in (default OFF/unset) so no customer testimonial-ask or financial offer fires until the founder sets them.
**Delivered:** jiya makeover + trending tattoos (value delivered, tracked). Dead-man ensures no future paid customer is silently ghosted.
