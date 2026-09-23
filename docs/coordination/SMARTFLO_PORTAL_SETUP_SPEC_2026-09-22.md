# SmartFlo Portal Setup Spec — Owner-Authorize Run

**Date:** 2026-09-22
**Worktree:** `feat/smartflo-acceptance-framework` @ `9ff68df5`
**Portal URL:** `https://cloudphone.tatateleservices.com/manage-did-numbers`
**API endpoint:** `https://api-smartflo.tatateleservices.com/v1/click_to_call_support`
**Auth:** Bearer token (TATA_SMARTFLO_API_TOKEN) + Click-to-Call API Key (TATA_SMARTFLO_API_KEY)
**Bearer header becomes MANDATORY after 30 Sep 2026** (per `tata_smartflo_handler.py:27`)

> **Boundary:** This spec is for the OWNER to execute in the browser. Browser
> control is NOT authorized in this MiniMax session + SmartFlo credentials must
> be handled only through the owner's authorized private interface. Per
> directive §10: "Production deploy, destructive cleanup, credential rotation
> aur customer-facing actions apne existing approval aur verification gates ke
> andar rahenge."

---

## 1. Pre-flight (verify with me first)

Before touching the portal, run the local pre-flight script (additive — does
NOT touch the portal):

```bash
cd "C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent"
C:\Users\Ratanshila\.local\bin\python3.exe scripts/smartflo_channel_verify.py --mode preflight
```

Expected output:
- Current `TATA_SMARTFLO_API_TOKEN` set? (fingerprint only — NO value)
- Current `TATA_SMARTFLO_API_KEY` set? (fingerprint only)
- Current `SMARTFLO_VOICE_STREAM_ENABLED` value (should be 0 today → expected)
- Current `tata_channel_1..5` status from `tata_tele_config.py` (channel 1 = active; 2-5 = pending)
- DID placeholders (currently `+9180698797XX`) — flag as placeholder

**What we have today:** 1 LIVE channel + 4 pending. Code-side config is wired;
portal-side config is the unknown.

---

## 2. Portal-side checklist (5 channels × 6 items each = 30 actions)

For each of the 5 channels in the portal, the owner must:

| # | Action | Per-channel value | Notes |
|---|---|---|---|
| 2.1 | Verify the DID number is assigned | real number from portal (not placeholder) | Today's placeholders: `+918069879701..705` |
| 2.2 | Verify the C2C API Key is generated | one API key per channel OR one shared key with 5 DIDs | per `tata_smartflo_handler.py:90-92` |
| 2.3 | Copy the API Key + Bearer token to local `.env` via key_manager (NOT committed) | `TATA_SMARTFLO_API_TOKEN` + `TATA_SMARTFLO_API_KEY` + `TATA_SMARTFLO_DID` | key_manager vault: `/opt/leadgen/secrets/keys.json` |
| 2.4 | Configure the Voice Bot destination to Swara (NOT human/extension) | WebSocket URL: `wss://leadsgenai.in/api/telephony/vobiz/stream/{stream_token}` | see `smartflo_stream.py` for token validation |
| 2.5 | Configure the status callback webhook | `https://leadsgenai.in/api/webhooks/smartflo` | see `smartflo_webhooks.py` |
| 2.6 | Enable call recording | toggle ON | needed for post-call webhook audio + transcript |

### 2.1–2.3 — DID + API Key
- Login to `https://cloudphone.tatateleservices.com`
- Click **Manage DID Numbers** (left nav)
- For each of the 5 DIDs:
  - Confirm the number matches the planned assignment (channel 1 = `+918069879701` etc — REPLACE placeholders with real numbers)
  - Generate / copy the C2C API key
  - Copy the Bearer token (Settings → API)
- Save tokens to key_manager (NOT `.env` file in repo):
  - Slot A: `TATA_SMARTFLO_API_TOKEN`
  - Slot B: `TATA_SMARTFLO_API_KEY`
  - Slot C: `TATA_SMARTFLO_DID` (channel 1 first)
- Repeat for channels 2–5 (separate slots D, etc., OR one shared token with 5 DIDs)

### 2.4 — Voice Bot destination
- Per SmartFlo portal: each DID needs a **destination** when called
- The destination MUST be the Voice Bot endpoint (Swara), NOT a human agent or extension
- WebSocket URL format: `wss://leadsgenai.in/api/telephony/vobiz/stream/{stream_token}`
- The `stream_token` is generated per-call by `app/telephony/stream_token.py:generate_stream_token()`

### 2.5 — Status webhook
- Per `smartflo_webhooks.py`: portal must POST call-status events to `https://leadsgenai.in/api/webhooks/smartflo`
- Events expected: call_initiated, call_answered, call_completed, recording_ready, dtmf_received
- Webhook secret: `SMARTFLO_WEBHOOK_SECRET` (set in portal + env)

### 2.6 — Recording enablement
- Without recording enabled, post-call hooks (`post_call_hooks.py`) cannot deliver audio
- Recording retention: 90 days (DPDP Act 2023)

---

## 3. Code-side actions (MiniMax can do, NOT destructive)

After portal setup, MiniMax will:

### 3.1 Update `tata_tele_config.py` channel numbers
- Replace placeholders `+9180698797{i:02d}` with real DID numbers
- Status: `tata_channel_1..5` all `active`
- ADDS file: `docs/coordination/SMARTFLO_PORTAL_CHANNEL_MAP_2026-09-22.md` with real DIDs

### 3.2 Enable `SMARTFLO_VOICE_STREAM_ENABLED=1` (currently 0)
- Edit `app/api/telephony_smartflo.py` deployment env or docker-compose env
- OR set in VPS `.env` via deploy_vps.sh
- Gate 1 of `smartflo_acceptance.py` will flip from FAIL → PASS

### 3.3 Run acceptance test on channel 1
- Owner provides test number
- VPS SSH stable
- `python -m app.voice.smartflo_acceptance --to <test-number>`
- Gates 0-3 PASS automatically; gates 4-11 fill in as the call progresses

### 3.4 Gradual rollout (after channel 1 passes)
- Test 2 simultaneous channels
- Test all 5 simultaneous channels
- Per directive: "Validate one channel first, then two simultaneous channels, then the authorized five-channel capacity."

---

## 4. What MiniMax CANNOT do (owner gate)

| Action | Why | Owner required |
|---|---|---|
| Browser login to SmartFlo portal | Browser control NOT authorized in this session | Yes — manual browser session |
| Generate / rotate Bearer token | Credential rotation gated (per directive §10) | Yes — portal Settings → API |
| Set WebSocket destination per channel | Portal-only config | Yes — portal Settings → Voice Bot |
| Authorize test number | Customer-facing call (TRAI compliance gate) | Yes — must be owner's number or explicit written consent |
| Provide UPI test credit | Payment-rail gated | Yes — needs bank credit |
| Provision TYPESAFE_API_KEY | Credential rotation gated | Yes — key_manager slot allocation |
| Enable SMARTFLO_VOICE_STREAM_ENABLED | Deploy-time env change | Yes — VPS .env via deploy_vps.sh |
| Production deploy | Deploy gated to `scripts/deploy_vps.sh` | Yes — explicit owner trigger |

---

## 5. Failure modes the owner might encounter

| Portal error | Code-side response |
|---|---|
| 401 Unauthorized | Token expired → rotate via portal Settings → API |
| 403 Forbidden | API key revoked → regenerate per-channel C2C key |
| 404 webhook not found | Webhook URL not configured → portal Settings → Call Events |
| 500 gateway error | Retry with exponential backoff (built into `TataSmartfloClient`) |
| DID assigned but Voice Bot not set | Calls fail with "destination unreachable" → configure per §2.4 |
| Recording toggle off | Post-call hooks fire without audio → enable per §2.6 |

---

## 6. Acceptance criteria (Wave 7 §7 directive)

Per directive:
> "Complete one authorized real bidirectional Swara conversation before
> expanding to five-channel production operation."

Gates per `app/voice/smartflo_acceptance.py`:
- **Gate 0** `credentials_present` — env + key_manager fingerprint check
- **Gate 1** `stream_enabled` — `SMARTFLO_VOICE_STREAM_ENABLED=1`
- **Gate 2** `vps_reachable` — TCP probe to 72.61.245.204:22 within 4s
- **Gate 3** `test_number_authorized` — owner-provided `--to <number>`
- **Gates 4-11** (REMOTE STUBS — to be filled by operator-trusted VPS session):
  4. `smartflo_call_accepted` — C2C API returns 200 OR inbound call answered
  5. `websocket_opened` — `smartflo_stream.handle` connects via `stream_token`
  6. `swara_greeting_played` — TTS outbound completes
  7. `caller_speech_recognized` — STT returns non-empty text
  8. `swara_response_contextual` — LLM reply within deadline
  9. `multi_turn_no_dead_air` — no gap > 2s between turns
  10. `interruption_barge_in` — caller speaks over TTS, bot yields
  11. `call_ended_with_outcome` — STOP event + transcript + CDR + CRM update

**Acceptance to "operational" status:** All 12 gates PASS with real evidence
on at least 1 channel. Channels 2-5 can be activated only after channel 1
passes all 12 gates.

---

## 7. Summary — what MiniMax has done vs what owner must do

### MiniMax (already done)
- ✅ 5-channel config scaffold (`tata_tele_config.py`)
- ✅ Provider = TATA_SMARTFLO, Vobiz REMOVED 2026-09-15
- ✅ Bearer-token auth wired (`tata_smartflo_handler.py`)
- ✅ Webhook handler ready (`smartflo_webhooks.py`)
- ✅ WebSocket stream ready (`smartflo_stream.py`)
- ✅ 12-gate acceptance framework (`smartflo_acceptance.py`)
- ✅ SmartFlo owner command (`/smartflo` in Telegram — Wave 7 §2)
- ✅ Config-validation script (`scripts/smartflo_channel_verify.py`)

### Owner (must do
1. Login to `https://cloudphone.tatateleservices.com/manage-did-numbers`
2. For each of 5 DIDs: confirm number, get API key, configure Voice Bot destination + webhook
3. Save tokens to key_manager (NOT repo `.env`)
4. Authorize test number + provide VPS SSH access
5. Set `SMARTFLO_VOICE_STREAM_ENABLED=1` (when ready)
6. Run acceptance test: `python -m app.voice.smartflo_acceptance --to <number>`

### MiniMax (will do after owner completes above)
- Update `tata_tele_config.py` with real DIDs (replaces placeholders)
- Mark channels 2-5 status = `active` (was `pending`)
- Deploy env change via `scripts/deploy_vps.sh`
- Run 1→2→5 channel rollout with per-channel acceptance
- Update memory/decisions.md with the channel map ADR

---

🐦 pelican