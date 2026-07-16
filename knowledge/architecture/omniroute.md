---
type: Architecture
title: OmniRoute
description: Local-dev LLM gateway adapter — INERT on VPS unless flags ON.
tags: [omniroute, llm, free-stack]
timestamp: 2026-07-17T00:00:00Z
resource: app/platform/omniroute_client.py
---

# OmniRoute

- Local WSL gateway only by default; VPS flags OFF.
- Routes use free combo / auto-aliases (`leadgen-free-first` + fallbacks) — free-tokens mandate.
- Provider label for combo IDs = `combo` (or resolved `provider/model`), not a fake provider name.
- Fail-open: gateway miss → existing `free_ai` chain continues.
- Never send raw customer PII — `mask_customer_data` + `validate_no_secrets` before network.
