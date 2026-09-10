# Tata Smartflo — demo-account live test runbook (2026-09-07)

Demo account (`TATA DEMO 29…`, portal https://cloudphone.tatateleservices.com) is valid **2 days → expires ~2026-09-09**.
Goal: ONE real phone call where Smartflo streams audio to `wss://leadsgenai.in/api/telephony/smartflo/stream` and Swara answers.

## What already exists in code (merged PR #457, 2026-09-04)

| Piece | Where | Notes |
|---|---|---|
| Dynamic endpoint resolver | `POST /api/telephony/smartflo/endpoint` → `{"success":true,"wss_url":...}` | 2 s deadline (Smartflo-enforced) |
| Bidirectional WS | `WS /api/telephony/smartflo/stream` (`app/api/telephony_smartflo.py` → `app/telephony/smartflo_stream.py`) | mulaw 8 kHz ⇄ PCM16 16 kHz; gated by `SMARTFLO_VOICE_STREAM_ENABLED` (INERT default) |
| Click-to-Call (outbound test) | `POST /api/telephony/smartflo/test-call` (admin) → `TataSmartfloClient.place_call` | needs `TATA_SMARTFLO_API_TOKEN` + `TATA_SMARTFLO_API_KEY` |
| Webhook receiver | `POST /api/webhooks/tata-smartflo` | CDR/status; best-effort |
| Trunk registration | `app/telephony/trunks.py` (`TATA_SMARTFLO_ENABLED=1` + creds) | weight 50, cps 2 |
| Admin status | `GET /api/telephony/smartflo/status` | STT/TTS/audioop capability snapshot |

2026-09-07 fixes (pre-demo, this worktree, `tests/test_smartflo_stream.py::TestDemoReadinessRegressions`, 75 green):
Groq STT now uploads a real WAV (was raw PCM → 400 every utterance) · playback runs as a background task so barge-in actually works · `start` accepts camelCase **and** snake_case · start-frame **key-set** is logged (no PII) so a protocol mismatch is visible in one log line · default greeting says "AI assistant" (§5 disclosure).

## 2026-09-10 hardening (Vobiz parity — end-to-end pass)

Four real defects were found and fixed. Evidence labels are honest; nothing here is claimed
PRODUCTION-PROVEN because no live Smartflo call has happened yet.

| # | Defect | Fix | Evidence |
|---|---|---|---|
| 1 | **`telephony_service.py:83` latent `AttributeError`.** Handler construction was `if self.provider in ("vobiz", "sip")` — `tata_smartflo` fell through, so `self._handler` stayed `None` and the tata branch (~line 217) would crash on first use. | Added `"tata_smartflo"` to the tuple. | CODE-PRESENT |
| 2 | **`TataSmartfloClient.place_call` had ZERO compliance gates**, and `POST /api/telephony/smartflo/test-call` called it directly. A dial could bypass `dial_gate` / `ComplianceGate` / `admin_kill_engaged()` entirely. | Pre-flight added at the top of `place_call` (`enforce_compliance: bool = True`) AND at the `/test-call` call site (`_smartflo_dial_block_reason`). Fail-closed: every block/error returns `{"status_code": 0, "body": {"error": "compliance_blocked: <reason>"}}` and never POSTs. Mirrors `vobiz_handler.py:91/:116`. | CODE-PRESENT |
| 3 | **Silent revenue leak.** `smartflo_webhooks.py::_meter_call` called `meter_call_completion(client_id=…, call_duration_s=…, metadata={…})`, but the real signature (`app/telephony/post_call_hooks.py:47-54`) is `meter_call_completion(call_id, *, client_id="", client_name="", duration_seconds, campaign_id=None)`. `call_id` is a REQUIRED positional and `call_duration_s`/`metadata` do not exist → **every** call raised `TypeError`, swallowed at `logger.debug`. **No Smartflo minute was ever billed.** | Corrected call + `logger.warning` (never `debug`) on failure + loud warning when `custom_identifier` carries no billable identity. | **TEST-PROVEN** — 124 Smartflo tests green; new regression asserts `call_id` actually arrives at the meter. |
| 4 | `app/config.py` had **zero** `tata_smartflo_*` typed settings (trunks/readiness read raw `os.environ`). | 11 additive typed settings (token, key, did, enabled, voice_stream_enabled, weight, cps_limit, max_concurrent, webhook_secret, ws_secret, ws_require_secret). | CODE-PRESENT |

**Test command that proves #3** (the repo `.venv` is mandatory — managed python 3.13 lacks sqlalchemy):
```
cd "C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent"
CODEBUDDY_SAFE_DELETE_ENABLED=0 VOICE_LAUNCH_KILL=0 ./.venv/Scripts/python.exe -m pytest \
  tests/test_smartflo_webhook_payload.py tests/test_smartflo_e2e.py tests/test_smartflo_test_call.py \
  tests/test_smartflo_stream.py tests/test_smartflo_audio_conversion.py tests/test_swara_smartflo_callflow.py -q
# 2026-09-10: 124 passed
```
`VOICE_LAUNCH_KILL=0` is required because the kill switch is fail-closed and
`data/voice_launch_kill.json` does not exist locally.

### Why the tests had not caught #3
`tests/test_smartflo_e2e.py` and `tests/test_smartflo_webhook_payload.py` monkeypatched
`meter_call_completion` with fakes matching the **buggy** signature, so the fakes accepted the
wrong kwargs and the production `TypeError` never surfaced. The fakes were updated to the real
signature — the 3 resulting failures were correct enforcement, not a regression.

### Invariant adopted (owner-approved 2026-09-10)
Compliance guards were being attached to **call sites** rather than the **dial capability**, so
every new call site is a new chance to forget them. Recorded in full at
`docs/architecture/24X7_ARCHITECTURE_RECORD.md` §12 — *TELEPHONY PROVIDER DIAL INVARIANT*:
one fail-closed choke point; provider clients accept a dial ticket, not a bare number; billing
identity mandatory; no second dial path. **Never make an ungated provider a failover target.**

## UNVERIFIED until the first live call (do not claim these work)

1. Exact Smartflo WS event schema (`streamSid` vs `stream_sid`, `mediaFormat`, whether it expects our `connected`/`start` acks). → read the `start schema` log line after call #1.
2. Dynamic-endpoint response field name (`wss_url`) and whether the demo tenant has Voice Bot / streaming enabled at all (Tata usually enables it per account).
3. Click-to-Call "second leg" landing on the voice bot — the `api_key` destination must be the Voice Bot / streaming flow, not an agent extension.
4. Whether Tata requires our VPS IP `72.61.245.204` in **Settings → IP Pool Whitelisting** for API calls (menu exists in the demo portal — add it up front).

## Portal side (owner, in browser) — collect 4 things

1. **IP Pool Whitelisting** → add `72.61.245.204` (VPS). Cheap, avoids a silent 401/403 on the C2C API.
2. **API token** — Smartflo issues a Bearer token via the auth/login API (`POST https://api-smartflo.tatateleservices.com/v1/auth/login`, body `{"email":..,"password":..}` → `access_token`) or from the portal API section. → `TATA_SMARTFLO_API_TOKEN`
3. **Click-to-Call Support API key** (portal → API key section; destination = the voice-bot flow) → `TATA_SMARTFLO_API_KEY`
4. **DID** bundled with the demo (10 digits, no +91) → `TATA_SMARTFLO_DID`
5. **Voice Bot / audio-streaming config** (docs: "bi-directional audio streaming integration document"): set either
   - Static WSS: `wss://leadsgenai.in/api/telephony/smartflo/stream`, or
   - Dynamic endpoint: `POST https://leadsgenai.in/api/telephony/smartflo/endpoint` mapping `$callId,$fromNumber,$toNumber` into the JSON body.
   Then route the demo DID's inbound flow → that Voice Bot node.
6. **Webhook** (optional for call #1): `POST https://leadsgenai.in/api/webhooks/tata-smartflo`.

## VPS side (owner, via SSH — agent sandbox has NO network to VPS)

```bash
ssh -i ~/.ssh/id_rsa root@72.61.245.204
cd /opt/leadgen && git fetch origin && bash scripts/smartflo_vps_check.sh     # read-only probe; paste output back
```
Decision tree from the probe: `WS → 404` = Smartflo code not live → deploy (`setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &`, needs `APP_VERSION=<sha>`; then `/health.version == sha`).
`WS → 403` = code live, flag OFF → append to `.env` (owner-only; values never in chat/repo):
```
TATA_SMARTFLO_API_TOKEN=…
TATA_SMARTFLO_API_KEY=…
TATA_SMARTFLO_DID=…
TATA_SMARTFLO_ENABLED=1
SMARTFLO_VOICE_STREAM_ENABLED=1
SMARTFLO_DEFAULT_NICHE=general
```
then recreate ONLY the app service with the running image tag:
`APP_VERSION=$(docker compose -f docker-compose.vps.yml ps --format '{{.Image}}' app | sed 's/.*://') docker compose -f docker-compose.vps.yml up -d --no-deps --force-recreate app`
Re-run the probe → `WS → 101` = ARMED.

## Test sequence (call #1 = inbound is simplest; no DLT question for inbound)

1. Owner dials the demo DID from own mobile → Smartflo → Voice Bot → our WSS. Expect Swara greeting within ~2 s.
2. Watch: `docker compose -f docker-compose.vps.yml logs -f app | grep smartflo-stream` → `WS open` → `start schema …` → `user: …` → `bot: …`.
3. Speak over the bot → expect `clear` event + bot stops (barge-in).
4. Press `9` → opt-out path + hangup (consent ledger write, `source=smartflo_dtmf_press9`).
5. Outbound (only if inbound works): `POST /api/telephony/smartflo/test-call {"to":"98xxxxxxxx"}` with admin JWT → `placed:true`, `ref_id` → phone rings → bridged to bot. Call window 10–19 IST; own number only.
6. Evidence to capture: the `start schema` line, one transcript file `data/call_transcripts/smartflo_*.json`, webhook hit (if configured), `/api/telephony/smartflo/status`.
7. **Call-id identity (added 2026-09-10, blocks paid traffic).** Capture the media `start` frame's
   `callSid` and the status webhook's call id from the SAME call and confirm they are identical.
   If they are not, `finalize_stream_session` (stream path) and `_meter_call` (webhook) use different
   `call_meter:{...}` dedupe keys and the call is billed twice. Capture:
   `docker compose -f docker-compose.vps.yml logs -f app | grep -E "smartflo-stream|\[smartflo-webhook\]"`

## Rollback
`SMARTFLO_VOICE_STREAM_ENABLED=0` + `TATA_SMARTFLO_ENABLED=0` → recreate app. Vobiz path untouched (separate router/handler).

## 2026-09-10 (second pass) — live-stream P0s

The first pass above covered transport, outbound compliance and webhook billing. A line-by-line
parity read of `app/telephony/smartflo_stream.py` (937 lines) against `app/telephony/vobiz_stream.py`
then surfaced three **P0s on the live media path** — all three are now fixed.

| # | Defect | Why it mattered | Fix |
|---|---|---|---|
| P0-1 | **press-9 opt-out was dead code.** `smartflo_stream.py:427-439` imported `from app.telephony.consent_ledger import ConsentAction, persist_opt_out`. Neither symbol exists — that module exports only `record_opt_out` (`consent_ledger.py:421`). The `ImportError` was swallowed by `except Exception: pass`, so pressing 9 **never wrote to the consent ledger**. The kwargs were also wrong (`action=`/`source=` vs `reason=`/`channel=`). | TCCCPR opt-out failure, completely silent. Fail-OPEN compliance gate. | New `_persist_opt_out()` mirroring `vobiz_stream.py:1431-1445`, correct `record_opt_out` kwargs, ERROR-logged on failure (never silent), phone logged last-4-digits only. |
| P0-2 | **No AI disclosure / permission ask.** The file imported `app.voice_agent.niche_scripts` nowhere; the opener was a hardcoded inline string in `_maybe_greet`. `check_missing_ai_disclosure` never called. Vobiz routes its opener through `ensure_permission_ask(ensure_ai_disclosure(...))` (`vobiz_stream.py:2520/2523`). | Disclosure could drift out of sync with the rest of the platform. | `_opening_line_raw()` + `_maybe_greet()` now call the SAME shared helpers. Mandatory, no skip flag. |
| P0-3 | **No end-of-call qualification/billing.** Only `_cleanup` existed; no `_auto_qualify` (vobiz has one at `vobiz_stream.py:3541`, called from `:3362`). The pre-existing metering block also swallowed every failure with `except Exception: pass`. | Unqualified calls, and billing failures invisible. | `_cleanup` now calls `finalize_stream_session` (`post_call_hooks.py:751-831`) — transcript + meter + qualify in one entry point. Failures now ERROR-logged with a fallback meter. |

### Double-metering contract (do not break)
`finalize_stream_session` meters internally via `meter_call_completion(call_id=...)`, deduped on
`call_meter:{call_id}`. Billing identity is `self.call_sid` (from the Smartflo media `start` frame's
`callSid`, `smartflo_stream.py:370`) falling back to `self.stream_sid` — the **same** expression the
old standalone block used, so billed identity is unchanged. The standalone block was removed, so
there is exactly ONE in-process meter. The status webhook meters the same way and shares the dedupe
key **only if the provider call id matches**.

> **UNVERIFIED — needs a live capture.** Whether `start.callSid` is byte-identical to the webhook's
> `call_id` (`call_id` / `callId` / `uuid` / `id`) cannot be proven from code. If they differ, the
> webhook and the stream path bill the **same call twice** — and that hazard predates this change.
> Resolve by capturing one real call's `start` frame and webhook body side by side before enabling
> paid Smartflo traffic. See "UNVERIFIED until the first live call" #7 below.

#### Partial mitigation shipped (2026-09-10)

The two paths resolve their id **independently**, and the stream's set was much narrower than the
webhook's — so most mis-spellings silently fell back to `stream_sid` and guaranteed a second bill.

| Path | Before | After |
|---|---|---|
| Status webhook (`smartflo_webhooks.py:183`) | `_pick(data, "call_id","callId","callid","uuid","id")` | unchanged |
| Media stream (`smartflo_stream`) | `start.get("callSid") or start.get("call_sid")` — **only 2 spellings** | `_extract_call_id(data, start)` over `("callSid","call_sid","callId","call_id","callid","uuid","id")`, searched in `start` then the whole frame |

Three things now hold:
1. **Convergence** — both paths accept the same key set, so any spelling Smartflo sends resolves to
   the same id on both sides and `call_meter:{...}` dedupes correctly.
2. **Observability** — if the start frame carries NO call id at all, `_cleanup()` logs
   `[smartflo-stream] NO provider call id on the start frame … billed TWICE` at WARNING before it
   meters. The very first live call will say so out loud.
3. **Lock-in** — `tests/test_smartflo_billing_identity.py` parses the webhook's actual source and
   asserts *every key the webhook accepts, the stream must also accept*. Add a spelling to one side
   and forget the other → the test fails.

Still deliberately **not** done: refusing to meter when no provider call id is present. Never billing
is the worse failure (that was the original bug), so we bill and warn rather than silently drop.

### Also fixed: `app/config.py` env-alias hazard (P1)
The additive typed Smartflo mirrors were named `tata_smartflo_*`, but three of the real switches
have **no** `TATA_` prefix — live readers use `SMARTFLO_VOICE_STREAM_ENABLED`
(`app/api/telephony_smartflo.py:121`), `SMARTFLO_WS_SECRET` (`:133`) and `SMARTFLO_WS_REQUIRE_SECRET`
(`:134`). Under pydantic-settings a `tata_smartflo_*` field binds to an env var nobody sets, so any
future `settings.<field>` reader would read the default and silently keep the provider **INERT even
with the switch armed** — a "configured but dead" state. Fixed with
`validation_alias=AliasChoices(REAL_NAME, TATA_NAME)`; locked by
`tests/test_smartflo_config_alias.py`.

### Test-isolation lesson (2026-09-10) — read before adding stream tests

Fixing P0-1 **broke an unrelated test**, and the reason is worth remembering:

`tests/test_smartflo_stream.py:382-397` (`TestDTMF::test_dtmf_9_triggers_cleanup`) used
`lead_phone="919876543210"` and patched nothing. While `_persist_opt_out` was dead code that was
harmless; the moment it started really working, the test began writing a **real opt-out** to the
gitignored runtime file `data/consent_ledger.jsonl`. `+919876543210` then became permanently opted out,
and `tests/test_telephony_upgrades.py::test_compliance_fails_closed_on_unverified_dnd` started failing
with `reasons == ['opted_out']` instead of `['dnd_lookup_failed']`.

Two things were wrong, and both are now fixed:
1. **Tests wrote to real runtime files.** `finalize_stream_session` (added under P0-3) also writes, and
   142 of 144 rows in `data/interactions.jsonl` turned out to be `source:"stream_session"` test
   artifacts. `tests/_stream_runtime_isolation.py` now installs an autouse in-memory recorder for
   `consent_ledger.record_opt_out` and `post_call_hooks.finalize_stream_session` across
   `test_smartflo_stream.py` and `test_swara_smartflo_callflow.py`, with a
   `real_finalize_stream_session` marker to opt back in. Note `record_opt_out` writes **three** files
   (`consent_ledger.jsonl`, `voice_suppression.jsonl`, `wa_suppression.jsonl`) — the two suppression
   files are why purging only the ledger was not enough.
2. **The wrong instinct would have been to quiet the gate.** The compliance fix stayed; the tests were
   isolated instead. Never disable `_persist_opt_out` or `finalize_stream_session` to make a suite green.

Purge recipe if it happens again (all are gitignored runtime data; back up first):
```
grep -v 'stream_session' data/interactions.jsonl > /tmp/i.jsonl && cp /tmp/i.jsonl data/interactions.jsonl
: > data/consent_ledger.jsonl; : > data/voice_suppression.jsonl; : > data/wa_suppression.jsonl
```

## Known gaps (backlog — still open)

**Compliance-ish, arm before paid traffic**
- HMAC not enforced (`SMARTFLO_WS_REQUIRE_SECRET=0`).
- `start.callSid` vs webhook `call_id` identity unproven → possible double billing (see above).
- Metering dedupe is fail-open: `seen_before` falls back to memory if Redis dies.

### Also closed (2026-09-10, second continuation pass)

| # | Defect | Fix |
|---|---|---|
| 10 | **Analytics mislabel.** `finalize_stream_session` called `persist_call_log(provider="phone")` hardcoded → a Smartflo call was indistinguishable from any other stream session in the `call_logs` table, and the dashboard could never break it out. Vobiz passes `provider="vobiz"` (`vobiz_stream.py:3374`). | Added a `provider` parameter (default `"phone"` → existing callers unchanged); `smartflo_stream` passes `"tata_smartflo"`. |
| 11 | **No customer `call_completed` webhook.** Vobiz emits `outbound_webhooks.emit("call_completed", …)` from its own cleanup (`vobiz_stream.py:3327`); this helper did not, so a Smartflo call never reached a customer's subscribed endpoint — silently, inside a swallowed `except`. | `finalize_stream_session` now emits it with `source="tata_smartflo_stream"`, and an emit failure logs at WARNING instead of vanishing. Safe because this helper has exactly one caller in-tree (`smartflo_stream`). |

Note: `persist_call_log` was listed as an open backlog item earlier — that was **wrong**. It was
already covered transitively by the P0-3 `finalize_stream_session` fix. Corrected here.

**Parity, not blocking**
- STT+LLM still run inline in the receive loop (only playback is async).
- No conditional routing, no campaign A/B, no sentiment persistence, no `serve_agent` on this path.
- `AUTO_QUALIFY_CALLS` defaults to `"0"` → qualification is wired but inert until enabled.
- No live-call test with real credentials yet.
