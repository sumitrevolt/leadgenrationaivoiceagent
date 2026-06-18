---
name: churn-prevention
description: Save-offer / cancel-flow / failed-payment playbooks for LeadGen AI retention engines — dunning.py (D0/3/7/14), client_health.py (red/yellow/green), lifecycle_nurture.py, usage_alerts.py. Use jab "customer cancel kar raha", "churn", "payment fail", "save offer", "win-back", "retention", "client chhod raha" ya in engines ke email-drafts/copy upgrade karne ho.
---

# Churn Prevention (LeadGen AI)

Engines BANE hue hain — yeh skill batati hai unke drafts/offers KAUNSI playbook follow karein. Naya engine mat banao; copy aur offer-logic in files me upgrade karo:
- **Involuntary (payment fail)**: `app/billing/dunning.py` `_TOUCHES` D0/3/7 recovery + D14 win-back, pre-dunning renewal reminder (`RENEWAL_REMINDER_DAYS=5`), `mark_recovered` auto-close. Gated `DUNNING_ENGINE=1` (default OFF — off = case+draft RECORD hota, auto-send nahi). Har touch me manual UPI (`UPI_VPA`) pay instruction (Razorpay gateway removed).
- **Risk detect**: `app/platform/client_health.py` 0-100 → red/yellow/green + Hinglish retention action (alerts `CLIENT_HEALTH_ALERTS=1`).
- **Early-tenure**: `app/marketing/lifecycle_nurture.py` D0/2/5/7/12 trial→paid. **Upsell-moment**: `app/billing/usage_alerts.py` 80%/100% minutes.

## Playbook: reason → offer (Hinglish save-offers)
| Signal/Reason | Primary offer | Fallback |
|---|---|---|
| "Mehenga lag raha" | **Downgrade Starter ₹1,199** — "plan right-size karo, sab data safe" | 25% off 2 mahine |
| "Use nahi ho raha" / yellow health | **Concierge call** — "10-min me setup theek karte hain" + content pack redo | Pause 1 mahina |
| Seasonal/band dhandha | **Pause 1 mahina** (max 2 — lamba pause wapas nahi aata) | Starter downgrade |
| "Result nahi dikha" | ROI recap (leads_30d, posts, calls from client data) + free month-1 report | Founder call |
| Renewal-time hichkichahat | **Annual switch** — "2 mahine FREE, daam lock" | — |
| Business closed | Gracefully jaane do, win-back list me — offer push ❌ |  |

## Rules (distilled)
1. **Offer reason se match karo** — blanket discount "use nahi ho raha" wale ko nahi bachata; usse concierge/onboarding bachata hai.
2. **Discount ≤30%, ≤3 mahine, ₹ amount bolo** ("₹625/mo bachao" > "25% off"). Deep discount = cancel-and-return training.
3. **Dunning tone**: blame nahi ("payment nahi gaya" not "aapne nahi diya"), plain-text, direct UPI pay-instruction, batao kya rukega (posts/calls/reports). D14 win-back = warm, no guilt.
4. **Best save = cancel se PEHLE**: red health = same-day personal touch (Sumit ko alert jata hai); yellow = proactive "sab theek?" + quick win. Endowment dikhao — unka data/posts/reviews jo jama hua.
5. **Dark patterns ❌**: cancel easy rahe, guilt-trip copy nahi. "Saved" customer jo 30 din me phir gaya = saved nahi tha — `dunning_runs.jsonl`/health trend se verify.

## Verification
Draft change → `pytest tests/test_revenue_automation.py` green · flags check (`/api/growth/infra/flags`) · live recovery: `GET /api/growth/revenue/dunning` cases + weekly `revenue_digest` me recovered count.

Adapted from coreyhaines31/marketingskills (via VoltAgent/awesome-agent-skills)
