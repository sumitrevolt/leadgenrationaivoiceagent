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

## Enterprise gate
Operating loop chalao — Discover → Contract → Execute → Self-review → Evidence (`fable-operating-manual`). Integration almost-always **High-risk** (secret + external provider + aksar outbound side-effect) → §9 ka pura automation bar + named rollback + `self-code-review`/`security-review`. Pure read-only LLM/storage connector = Standard.

**Gates (provider/connector domain — relevant pick):**
- **Safety / inert-without-creds (signature gate):** `_enabled()` = creds + flag dono; bina = `{"ok": False, "skipped": ...}`, crash nahi. Auto-send/auto-call/auto-post default OFF + loud warning. Secrets sirf `.env` (gitignored); exposed = rotate; VPS `.env` base64-over-ssh (plain argv pe secret nahi) — `scripts\check_secrets.py` gate.
- **Idempotency / dedupe** (send/call/bill/post/CRM-write trigger karne wale integrations pe MANDATORY): idempotency-key/dedupe → duplicate email/call/charge/CRM-row na ho (webhook emitter HMAC + delivery-id pattern dekho).
- **Reliability** (provider/network work): per-call timeout + bounded retry + never-raise wrapper; background path fail → DLQ `dlq:failed_tasks`. Provider down ≠ caller crash.
- **Cost/quota fallback:** free-stack multi-provider chain + circuit-breaker (429/quota → escalating cooldown, success pe reset) — pattern `free_ai.py`. Soft-paid/credit provider (NVIDIA NIM) chain me deep rakho.
- **Compliance fail-CLOSED — SIRF outbound channels pe** (telephony/SMS/WhatsApp/call): TRAI 9am–7pm window · DND scrub (lookup-fail = BLOCK) · AI-disclosure-at-start · DPDP consent/retention · 140-series. CRM/storage/LLM connector pe yeh lagu NAHI — mat lagao.
- **Observability + rollback (named):** event/log + flag in `growth.py AUTOMATION_FLAGS` → visible at `/api/growth/infra/flags`. Rollback = **flag OFF** (instant inert) → `import app.main` clean → no recreate needed (gated path dead).

**Evidence (done):** bina creds inert + `import app.main` OK + `.venv\Scripts\python.exe scripts\prod_check.py` PASS + `scripts\check_secrets.py` clean + `.venv\Scripts\python.exe -m pytest tests\test_<integration>.py -q` (import-safe + inert-path + happy-path monkeypatched + 1 failure-path + idempotency assert). Creds set → in-container real-API 200 smoke.
