---
name: integration-engineering
description: Add a new external integration (LLM/telephony/SMS/payment/CRM/storage/webhook/MCP) the LeadGen AI way — import-safe, flag-gated, INERT-without-creds, graceful fallback, secrets only in .env. Use when wiring a new API/provider/connector, "naya integration", "X service add karo", "provider wire karo", "API key se feature", "CRM sync", "webhook emit", or "connector banao".
---

# Integration Engineering (defensive · gated · inert-without-creds)

Codebase ka signature pattern: har external integration **import-safe + flag/cred-gated + graceful-degrade**. Bina creds = inert (crash nahi, feature silently skip). Yahi discipline 100+ integrations safe rakhe.

## The pattern
1. **Config** — `app/config.py` Settings me field (`x_api_key: str = ""`); env-name UPPER (`X_API_KEY`). Secret NEVER hardcode — sirf `.env` (gitignored).
2. **Handler module** — `app/integrations/` ya `app/marketing/`. Top-level import light; heavy deps **local import** inside functions.
3. **Inert guard**:
   ```python
   def _enabled(): return bool(settings.x_api_key) and _flag("X_ENABLED")
   async def send(...):
       if not _enabled(): return {"ok": False, "skipped": "X unconfigured"}
       try: ...; return {"ok": True, ...}
       except Exception as e: logger.warning("X: %s", e); return {"ok": False, "error": str(e)}
   ```
4. **Never-raise** — handler kabhi exception na phenke (caller defensive nahi hota).
5. **Multi-provider fallback** (jaise `free_ai.chat`) — primary→fallback chain + circuit-breaker (429 pe 60s cooldown).
6. **Gate risky** — auto-send/calling default OFF + loud warning (ban/DLT risk).

## Reference implementations (copy pattern, REBUILD nahi)
- LLM: `app/voice_agent/free_ai.py` (free multi-provider chain: Mistral mistral-small-latest PRIMARY → Groq llama-3.1-8b-instant → Cerebras gpt-oss-120b 429-prone → Gemini → SambaNova → OpenRouter + escalating circuit-breaker).
- Telephony: `app/telephony/vobiz_handler.py` (`base_url=None` if unconfigured; Vobiz = active provider, India-native SIP).
- SMS: `app/integrations/sms_dlt.py` (inert without `SMS_DLT_ENABLED`+BSP creds).
- WhatsApp: `app/marketing/whatsapp_campaign.py` (default 1-click links; auto-send gated).
- CRM: `app/integrations/zoho_crm.py` + `hubspot.py` (per-client/global creds, `CRM_SYNC` OFF).
- Outbound webhooks (HMAC): `app/integrations/webhooks_emitter.py` + `app/platform/customer_webhooks.py` (Svix-style signed, `CUSTOMER_WEBHOOKS`).
- LiteLLM per-key spend: `LITELLM_COSTS` flag. MCP-as-product: `/api/mcp-product/v1/*` (`MCP_PRODUCT`).
- Rate-limit dep: `app/api/ratelimit.py` (`rate_limit("name", N, sec)` Depends; Redis→in-memory fallback, FAIL-OPEN).

## Rules
- **Grep before building**: `grep '@router' app/api/*.py` — duplicate route prod ko **shadow** karta (FastAPI first-route-wins).
- Secrets sirf `.env`; exposed = rotate; VPS `.env` base64-over-ssh se likho (plain argv pe secret nahi).
- **Windows = source of truth**; verify `import app.main` + `prod_check.py`.

## Verify
Bina creds: feature inert, `import app.main` OK, prod_check PASS. Creds set → in-container smoke (real API 200). Test: import-safe + inert-path + happy-path (monkeypatch jsonl/env).
