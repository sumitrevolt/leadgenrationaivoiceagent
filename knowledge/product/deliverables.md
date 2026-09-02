---
type: Runbook
title: Customer deliverables rules
description: What counts as delivered vs pending for Marketing starter — honesty gates.
tags: [delivery, product-one, approvals]
timestamp: 2026-07-17T00:00:00Z
resource: app/marketing/product_one_delivery.py
---

# Customer deliverables rules

- Live stage comes from Product One computation / delivery ledger — not stale `delivery_state` fields alone.
- Approvals backlog is real work; `CONTENT_APPROVAL_AUTO` = auto-**submit**, not auto-approve.
- Social publish requires **per-customer** Postiz integration IDs (ADR-117) — never corporate global fallback.
- Hands-free publish needs `SOCIAL_PREFS_HONOR=1` + customer `approval_mode=auto` + owned channels + `SOCIAL_ENGINE`.
- WhatsApp auto-send stays OFF (ban-safety); 1-click human send only.
- `gbp_suggestions` is **done** only after scored audit JSON (`data/gbp_audits/{cid}.json`) OR gbp content OR manual mark — a GBP URL alone is `in_progress`, not done.

Related: [Starter plan](starter-plan.md), [Tenant isolation](../architecture/tenant-isolation.md).
