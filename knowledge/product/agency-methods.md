---
type: ProductMap
title: AI agency methods vs LeadGen starter
description: 12 common AI-agency marketing methods mapped to ₹1,999 starter — what ships vs what we refuse to over-promise.
tags: [gtm, starter, honesty, marketing]
timestamp: 2026-07-17T00:00:00Z
resource: app/marketing/packages.py
---

# AI agency methods → LeadGen ₹1,999 starter

Full agency retainers sell paid-ads management, deep SEO, and influencer ops.
Starter focuses on **content, local presence, reputation, lead capture, CRM, follow-up drafts, monthly report** — commercially safer at ₹1,999.

| # | Method | Starter reality |
|---|--------|-----------------|
| 1 | Content marketing | Daily AI posts/posters/festival creatives + Studio tools (LIVE) |
| 2 | Paid advertising | Ads **copy / budget suggestion drafts only** — no Meta/Google spend management |
| 3 | Lead generation | Forms, mini-site, audit funnels, Maps prospecting (platform); customer lead widget |
| 4 | Automated follow-up | WhatsApp/email **drafts** + reminders; bulk WA auto-send OFF (ban-safe) |
| 5 | Social media management | Queue + approval + Postiz when customer owns channels; comment/DM = light/tools |
| 6 | Local SEO / GBP | **Scored GBP audit (0–100)** in Reports + tips/text Studio tools |
| 7 | SEO / conversion | Schema, FAQ, service-city pages, chatbots — not full SEO retainer |
| 8 | Email marketing | Newsletter outline + sequences drafts — not ESP agency ops |
| 9 | Influencer / UGC | **UGC request kit** only — no influencer outreach/management |
| 10 | Reputation | Review kit, reply drafts, bad-review rescue |
| 11 | AI chatbots | Website widget FAQ + lead capture |
| 12 | Analytics | Monthly report + delivery KPIs (posts/leads/GBP score/approvals) — no fake ROAS |

## Starter operating loop

Audit → content → lead capture → CRM → follow-up drafts → approval/publish → monthly report → optimize.

## Code truth

- Features list: `app/marketing/packages.py`
- Deliverables: `app/marketing/product_one_delivery.py` (GBP done = scored audit OR gbp content OR manual — **not** mere GBP URL)
- GBP API: `GET/POST /api/customer/gbp/questions|score`
- Report metrics: `app/marketing/client_report.collect_delivery`

Related: [Starter plan](starter-plan.md), [Deliverables](deliverables.md).
