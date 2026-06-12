---
name: pipeline-hygiene
description: Weekly funnel-data safai — junk deals, stale "ready" prospects, classifier drift, bulk-sender leaks. Use jab pipeline score kharab aaye, deals suspicious lagen, ya har hafte ek baar routine sweep ke liye.
---

# Pipeline Hygiene (weekly sweep)

> 2026-06-12 review se born: score 31/100 — 464 "ready" stuck, 2 deals dono JUNK (PayU/Instamojo newsletters se reply_agent ne deals bana diye the). Guards ab code me hain; yeh sweep unhe VERIFY karta hai + naye leak pakadta hai.

## Sweep checklist (15 min, har Monday)
1. **Deals real hain?** `GET /api/growth/sales/deals` — har deal ka source prospect KNOWN hai? Unknown-sender deal = `_is_bulk_sender()` guard leak — sender pattern guard me add karo.
2. **Reply classifier drift**: reply triage stats — "other" bucket > 50% = classifier ya inbox noise problem. Sample 5 "other" replies padho: bulk/newsletter hain to guard; genuine hain to intent prompt tune (llm-error-analysis skill).
3. **Staleness**: prospects `created_at`/`updated_at` (ab store me hain) — "ready" 14+ din untouched = stale. Action: dialer-sprint list me daalo YA cadence re-enroll YA dead mark. "Ready" pile ko GROW mat hone do.
4. **Dunning/lifecycle stores**: `GET /api/growth/revenue/dunning` + `/revenue/lifecycle` — zombie cases (resolved par open)? Manual close.
5. **Channel attribution sanity**: `GET /api/growth/experiments` — outcomes credit sahi channels ko ja raha? UTM-less inbound spike = attribution gap.
6. **Re-score**: `POST /api/growth/leads/rescore` sweep ke baad — fresh data pe scores.

## Junk-source patterns (guard registry)
Newsletters/transactional senders jo LEAD NAHI hain: payment gateways (PayU/Instamojo/Razorpay notifications), no-reply@, marketing digests. Naya junk mile → `_is_bulk_sender()` me pattern + yahan note.

## Output
Har sweep ka 3-line summary SESSION_LOG me: deals checked / stale count / naya guard (agar koi). Pipeline score re-run karke delta note karo. Score 3 hafte improve na ho = funnel-level problem (growth_optimizer analysis dekho), data-safai ka nahi.
