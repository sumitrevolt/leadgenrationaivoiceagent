---
type: Policy
title: Pricing rules
description: Single-source pricing discipline for LeadGen AI.
tags: [billing, packages, gst]
timestamp: 2026-07-17T00:00:00Z
resource: app/marketing/packages.py
---

# Pricing rules

1. **`packages.py` is the single source** for public plan shapes; sync via `subscription._sync_plans_from_packages`.
2. Pricing change = `packages.py` + `tests/test_billing_truth_2026.py` together.
3. Growth ₹2,999 = LEGACY hidden — use `get_public_packages()`.
4. GST only when `GST_GSTIN` set; invoices Rule-46 sequential `INV/YYYY-YY/NNNN`.
5. Do not invent “Hands-Free always live” claims — draft/approval gates apply (ADR-116).

Live amounts and feature bullets: read code, not this file, when they disagree.
