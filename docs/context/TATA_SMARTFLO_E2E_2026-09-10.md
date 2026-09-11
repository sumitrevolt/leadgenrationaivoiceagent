# Tata Tele SmartFlo — end-to-end Vobiz parity · handoff (2026-09-10)

**Ask:** *"smart flow setup karna hai jaise vobiz ke liye kiya tha same tata tele smart flow se
karna hai abhi tumhe end to end setup"*

**Result:** SmartFlo ab Vobiz ke barabar hai compliance, billing, provider-routing aur end-of-call
processing me. **269 tests green.** Ek silent revenue leak, ek TCCCPR fail-open, aur ek
double-billing hazard (partially) — teeno band.

Evidence labels are honest: **TEST-PROVEN** = suite green; **CODE-PRESENT** = written + compiles,
not live-exercised; **UNVERIFIED** = needs a live call.

---

## 1. Defects found and closed

| # | Defect | Sev | Evidence |
|---|---|---|---|
| 1 | `telephony_service.py:83` — `tata_smartflo` missing from handler construction → `_handler = None` → latent `AttributeError` on first use. | P1 | CODE-PRESENT |
| 2 | `TataSmartfloClient.place_call` had **zero compliance gates**; `POST /test-call` called it directly. A dial could bypass `dial_gate` / `ComplianceGate` / `admin_kill_engaged()`. | **P0** | CODE-PRESENT |
| 3 | **Silent revenue leak.** `smartflo_webhooks._meter_call` called `meter_call_completion(client_id=…, call_duration_s=…, metadata=…)` vs real signature `meter_call_completion(call_id, *, client_id, client_name, duration_seconds, campaign_id)`. `call_id` is REQUIRED positional → `TypeError` every call, swallowed at `logger.debug`. **No SmartFlo minute was ever billed.** | **P0** | **TEST-PROVEN** |
| 4 | **press-9 opt-out was dead code.** Imported `ConsentAction` / `persist_opt_out` — neither exists in `consent_ledger.py` (only `record_opt_out`, line 421). `ImportError` swallowed by `except Exception: pass` → TCCCPR **fail-open**. | **P0** | **TEST-PROVEN** |
| 5 | No AI disclosure on the opener — hardcoded inline string, drifted from the platform helper. | **P0** | **TEST-PROVEN** |
| 6 | No end-of-call qualification/billing (no `_auto_qualify` equivalent). Old metering block swallowed all failures. | P0 | **TEST-PROVEN** |
| 7 | `call_manager.py` — `TelephonyProvider` had only `VOBIZ` and forced vobiz, so `DEFAULT_TELEPHONY=tata_smartflo` **silently dialed Vobiz**. `admin_ops` `PROVIDER_CREDS` always reported Vobiz creds. | P1 | **TEST-PROVEN** |
| 8 | `app/config.py` — typed mirrors named `tata_smartflo_*`, but the real switches are `SMARTFLO_VOICE_STREAM_ENABLED` / `SMARTFLO_WS_SECRET` / `SMARTFLO_WS_REQUIRE_SECRET`. A future `settings.<field>` reader would keep the provider **INERT with the switch armed**. | P1 | **TEST-PROVEN** |
| 9 | **Double-billing hazard.** Stream resolved the call id from only `start.callSid`/`call_sid` (2 spellings); the webhook accepts 5 (`call_id`,`callId`,`callid`,`uuid`,`id`) at `smartflo_webhooks.py:183`. Different id → different `call_meter:{…}` key → **one call billed twice**. | **P0** | **TEST-PROVEN** (mitigated) |
| 10 | **Analytics mislabel.** `persist_call_log(provider="phone")` hardcoded → Smartflo calls indistinguishable in the `call_logs` table; dashboard could never break them out (Vobiz passes `"vobiz"`). | P2 | **TEST-PROVEN** |
| 11 | **No customer `call_completed` webhook.** Vobiz emits it (`vobiz_stream.py:3327`); the stream helper did not → Smartflo calls never reached a customer's subscribed endpoint, silently. | P1 | **TEST-PROVEN** |

> Correction: `persist_call_log` was listed as an open backlog item in the first handoff. That was
> **wrong** — it was already covered transitively by the P0-3 `finalize_stream_session` fix. Defect 10
> above is the narrower, real problem (the row existed but was mislabelled `provider="phone"`).

## 2. Files changed

**Production**
- `app/telephony/telephony_service.py` — handler construction includes `tata_smartflo`
- `app/telephony/tata_smartflo_handler.py` — fail-closed compliance pre-flight in `place_call`
- `app/api/telephony_smartflo.py` — `_smartflo_dial_block_reason` gate on `/test-call`
- `app/telephony/smartflo_webhooks.py` — `_meter_call` billing fix (revenue)
- `app/telephony/smartflo_stream.py` — `_persist_opt_out`, `_opening_line_raw`/`_maybe_greet`
  disclosure, `_cleanup` → `finalize_stream_session`
- `app/telephony/call_manager.py` — `TATA_SMARTFLO` enum member + `_build_handler()`
- `app/api/admin_ops.py` — `_provider_creds_ok()`, `PROVIDER_CREDS`, `TATA_SMARTFLO_CREDS`
- `app/config.py` — `AliasChoices` env-alias fix
- `app/telephony/smartflo_stream.py` — `_CALL_ID_KEYS` + `_extract_call_id()` (billing identity
  convergence) and a WARNING when the start frame carries no provider call id

**Tests (new)** `tests/test_smartflo_config_alias.py`, `tests/test_call_manager_provider_routing.py`,
`tests/test_smartflo_billing_identity.py`, `tests/_stream_runtime_isolation.py`
**Tests (updated)** `test_smartflo_stream.py`, `test_smartflo_webhook_payload.py`,
`test_smartflo_e2e.py`, `test_swara_smartflo_callflow.py`, `test_cross_path_telephony.py`
**Docs** `docs/integrations/TATA_SMARTFLO_SETUP.md`, `docs/architecture/24X7_ARCHITECTURE_RECORD.md` §12

## 3. Verification

```
CODEBUDDY_SAFE_DELETE_ENABLED=0 VOICE_LAUNCH_KILL=0 ./.venv/Scripts/python.exe -m pytest \
  tests/test_smartflo_stream.py tests/test_smartflo_webhook_payload.py tests/test_smartflo_e2e.py \
  tests/test_smartflo_test_call.py tests/test_smartflo_audio_conversion.py \
  tests/test_swara_smartflo_callflow.py tests/test_smartflo_config_alias.py \
  tests/test_call_manager_provider_routing.py tests/test_telephony_upgrades.py \
  tests/test_consent_ledger.py tests/test_consent_reconsent_cooloff.py \
  tests/test_smartflo_billing_identity.py tests/test_cross_path_telephony.py \
  tests/test_voice_close_consent_bridge.py tests/test_dev_worker_registry.py \
  tests/test_omniroute_combo_health.py -q
# 2026-09-10 → 269 passed, EXIT=0
```

Runtime-data isolation re-proven each run (before → after): `interactions.jsonl` 5→5,
`consent_ledger.jsonl` 0→0, `voice_suppression.jsonl` 0→0, `wa_suppression.jsonl` 0→0.

## 4. Test-pollution regression (and the lesson)

Fixing defect #4 made previously-inert tests write **real** gitignored runtime data. One polluted
opt-out row for `+919876543210` broke
`test_telephony_upgrades.py::test_compliance_fails_closed_on_unverified_dnd`
(`reasons == ['opted_out']` instead of `['dnd_lookup_failed']`).

- `record_opt_out` writes **three** files — purging only `consent_ledger.jsonl` is not enough.
- `vobiz_stream.py:3345` calls `app.platform.interaction_log.record` **directly**, bypassing
  `finalize_stream_session`; `test_cross_path_telephony.py::test_vobiz_cleanup_meters_once` patched
  only the meter, leaking 1 real row per run.
- Fix = structural autouse isolation (`tests/_stream_runtime_isolation.py`), not per-test patching.
- **The compliance gate was never weakened to make a suite green.** That instinct is an ABORT.

## 5. BLOCKED — needs owner

1. **`start.callSid` vs webhook `call_id` identity is UNVERIFIED.** Mitigated, not closed: both paths
   now accept the same key set, and a missing provider call id produces a WARNING before metering, so
   the first live call will reveal it. But the actual byte-identity of the two ids can only be proven
   by one live capture. Blocks paid SmartFlo traffic. (Deliberately NOT done: refusing to meter when
   no provider call id is present — never billing is the worse failure.)
2. Arming: `TATA_SMARTFLO_ENABLED=1`, `SMARTFLO_VOICE_STREAM_ENABLED=1`, HMAC
   (`SMARTFLO_WS_REQUIRE_SECRET=1`), `AUTO_QUALIFY_CALLS=1` — **owner-gated, not flipped**.
3. **No commit / push / deploy was performed** (standing rule). 8 files staged-clean and ready for
   review; note Alembic 026 + 027 must still commit together from the earlier phase.

## 6. Parity backlog (not blocking)

`persist_call_log` analytics row · `outbound_webhooks.emit("call_completed")` · conditional routing ·
campaign A/B · sentiment persistence · `serve_agent` · STT+LLM still inline in the receive loop ·
metering dedupe is fail-open if Redis dies.
