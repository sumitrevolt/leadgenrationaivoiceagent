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

2026-09-09 official VOICE Streaming contract check: Smartflo sends `connected` → `start` → `media` → `stop` (and `dtmf`/provider `mark`) to the endpoint; the endpoint sends only bot `media`, `mark`, and `clear` back. The endpoint must not echo `connected` or `start`. Bot media is µ-law/8000 base64 and each payload must be at least 160 bytes or a 160-byte multiple.

## UNVERIFIED until the first live call (do not claim these work)

1. Live Smartflo WS event delivery and audio proof → read the `start schema` log line and capture `media_frames`, `caller_rms_max`, and a transcript after call #1. The event direction and packet contract are now confirmed from the official VOICE Streaming documents.
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

## Rollback
`SMARTFLO_VOICE_STREAM_ENABLED=0` + `TATA_SMARTFLO_ENABLED=0` → recreate app. Vobiz path untouched (separate router/handler).

## Known gaps after demo (backlog)
Smartflo-path AI qualification/rewards (no `_auto_qualify` on this path yet — vobiz has it) · STT+LLM still run inline in the receive loop (only playback is async) · no HMAC enforced (`SMARTFLO_WS_REQUIRE_SECRET=0`) — fine for demo, arm before customer traffic.
