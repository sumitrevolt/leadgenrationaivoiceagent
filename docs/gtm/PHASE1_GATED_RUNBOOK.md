# Phase 1 gated runbook (after 2nd paid Marketing customer)

Do **not** execute this until [HOT_QUEUE_BLITZ_CHECKLIST.md](HOT_QUEUE_BLITZ_CHECKLIST.md)
Phase 0 exit is ticked: Jiya + 1 new ₹1,999/mo + one inbox→start→paid loop.

Scoreboard: admin "Aaj naye paid" (`paid_today` / `activations_today`).

## T13 Ads budget (OWNER ₹)

- Meta/Google → `/audit` or `/start` with UTMs.
- Daily spend cap + kill switch **outside** the product. No auto-spend button in-app.
- Pause if CAC > 1-month GM.

## T14 GSC

- Creds first. Then separate owner gate `GSC_ENABLED`.
- Code already INERT (`app/integrations/gsc.py`). Do not arm without creds.

## T15 Postiz own-brand

- Confirm weekly cadence on existing connected channels.
- No new social stack. Customer-page Advanced Access is a different (external) track.

## T16 Second closer

- Optional extra hours inside TRAI window. WhatsApp stays 1-click human.
- FREEBUFF Hot Queue connector stays parked unless a real funnel step fails.

## T17 Onboard fail-rate

- Measure `setup_done` vs real KB seed for the 2nd paid tenant.
- Retry `onboard_client` only if that tenant is actually stuck. Do not rewrite the wizard.

## T18 Referral

- Use existing `/app/affiliates` + `POST /api/growth/affiliate/kit`. No new engine.

## T19 `/start` CRO

- One CTA. Manual UPI rail unchanged. Copy/layout only after Phase 0 exit.

## T20 / T34 / T42

- Infra note: [CAPACITY_50_DAY.md](CAPACITY_50_DAY.md).
- UPI batch / dual-approver UI still `owner_confirmed_upi`. No Stripe/Razorpay.

## Never-arm

Cold WhatsApp auto-send · `HARNESS_SESSION_EVENTS` · GSC without creds ·
`COORDINATION_HUB_ENABLED` as a control plane / 32nd STAFF · Swara/voice edits.
Live already has `DUNNING_ENGINE=1` / hub=1 / `UPI_AUTO_ACTIVATE=1` — **observe, do not flip** from this runbook.
