# E2E Test Plan — LeadGenAI Pipeline

> **Purpose:** Map every stage of the LeadGen pipeline to the **real existing test** that covers it, so you can answer "is the full pipeline tested?" without re-reading 220 test files.
> **This is an INDEX over the real suite (`tests/`, ~220 files) — NOT a new test framework.** Run with `scripts\run_tests.bat` → read `pytest_run.log`.
> **Last verified:** 2026-06-27.

---

## How to run

```bash
scripts\run_tests.bat                          # full suite → pytest_run.log (read the log)
pytest tests/test_pipeline_automation.py -q    # targeted stage
pytest tests/e2e/ -q                            # scenario-level E2E
```
> Full `pytest tests/` can hang on the `team_pulse` area — prefer targeted suites per the deploy SOP.

---

## Pipeline stage → covering test (real files)

| # | Pipeline stage | Module(s) | Covering test(s) |
|---|---|---|---|
| 1 | **Lead scrape / harvest** | `lead_scraper/`, `platform/lead_harvester.py` | `tests/test_lead_harvester.py` |
| 2 | **Pipeline automation (scrape→score→queue)** | `agents/`, `platform/` | `tests/test_pipeline_automation.py` |
| 3 | **Email outreach + backlog** | `platform/outreach`, `integrations/email_sender.py` | `tests/test_auto_outreach.py` · `test_outreach_backlog.py` · `test_outreach_audit_led.py` |
| 4 | **Inbound inquiry → client lead** | `api/public_site.py`, `inquiry_hooks` | `tests/test_customer_onboard.py` · `test_customer_portal.py` |
| 5 | **Customer portal + marketing tools** | `api/customer*`, `marketing/` | `test_customer_portal.py` · `test_customer_marketing_tools.py` · `test_customer_studio.py` |
| 6 | **Flows / automations (per-client)** | `flow_runner`, `flow_compiler` | `test_flow_run_e2e.py` · `test_flow_compiler_customer_safe.py` · `test_customer_flows_api.py` |
| 7 | **Voice call → STT/LLM/TTS → CRM** | `voice_agent/`, `telephony/vobiz_stream.py` | `test_voice_agent.py` · `test_voice_fixes.py` · `test_phase3_voice.py` · `test_parity_voiceai.py` |
| 8 | **Voice quality / latency / roles** | `voice_agent/` | `test_voice_llm_race.py` · `test_voice_metrics.py` · `test_voice_opener_cache.py` · `test_voice_roles.py` · `test_voice_tools.py` |
| 9 | **Billing — auth/IDOR** | `billing/`, `api/customer` | `test_billing_auth_idor.py` |
| 10 | **Billing — idempotency** | `billing/usage.py`, `lead_usage.py` | `test_billing_idempotency.py` |
| 11 | **Billing — pricing truth (CI gate)** | `marketing/packages.py` | `test_billing_truth_2026.py` |
| 12 | **Payments — webhooks** | `billing/`, Stripe | `test_payment_webhooks.py` |
| 13 | **Customer webhooks (Svix-style HMAC)** | `customer_webhooks` | `test_customer_webhooks.py` · `test_customer_webhooks_flow_tail.py` · `test_outbound_webhook_emit.py` · `test_webhook_rotate_retry.py` |
| 14 | **Customer 2FA (TOTP)** | `api/customer` | `test_customer_totp.py` |
| 15 | **Tenant / billing phase-3** | `middleware/tenant.py`, `billing/` | `test_phase3_billing_tenant.py` |
| 16 | **Scenario-level E2E (playbook)** | full stack | `tests/e2e/test_playbook_scenarios.py` |

---

## Gaps / notes

- **Voice cold-calling end-to-end** is NOT testable live until DLT + Vobiz recharge unlock (external blocker). Until then, voice paths are covered by the unit/integration tests above + `scripts/agent_tester.py` (free scorecard) on the FREE web-call path (`/app/test-call`).
- WhatsApp / social auto-send are intentionally OFF (ban-safe) — covered as draft-only, no live-send test.
- For a **wiring** (not behaviour) check, the static gates in `PRODUCTION_CHECKLIST.md` §A are the fast E2E-equivalent (0 gaps = every frontend handler hits a real API, every flag is read, every job is dispatchable).

---

**Related:** `PRODUCTION_CHECKLIST.md` (deploy gates) · `WORKFLOW_MAPS.md` (visual pipeline) · `docs/ADR-2026-06-25-Batch2-Testing-E2E.md` (E2E testing ADR).
