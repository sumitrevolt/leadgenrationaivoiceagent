---
type: Policy
title: Tenant isolation
description: Customer data must never leak across clients — APIs, RAG, Postiz, logs.
tags: [security, dpdp, multi-tenant]
timestamp: 2026-07-17T00:00:00Z
resource: app/api/customer_auth.py
---

# Tenant isolation

1. Customer routes: `require_customer` JWT `sub` is the only tenant authority.
2. Qdrant: filter by `tenant_id` / namespace on every customer retrieve (fail-closed for customer scope).
3. Postiz: no global integration inheritance for customers (ADR-117).
4. Logs: no recipient PII in delivery logs (ADR-092 family).
5. OKF Git bundle: **no** passwords, API keys, WA tokens, private phones.

Related: [Knowledge stack](knowledge-stack.md).
