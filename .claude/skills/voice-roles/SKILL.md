---
name: voice-roles
description: Swara telecaller, Ananya appointment booker, Riya receptionist — voice role wiring, prompts, test-call flow, and API. Use when adding voice personas, booking/reception agents, or voice_role parameters.
---
# Voice Roles (Product 2)

**Source:** `app/voice_agent/voice_roles.py` · API `GET /api/voice/agents`

| Role ID | Agent | Flow alias | Direction | Goal |
|---------|-------|------------|-----------|------|
| `telecaller` | Swara | `qualify` | outbound | qualify + pitch |
| `booking_agent` | Ananya | `booking`, `appointment` | outbound | slot book |
| `receptionist` | Riya | `reception`, `inbound` | inbound | front-desk help |

## Wiring touch-points

- `TelecallerBrain(voice_role=...)` — prompt + opener
- `vobiz_stream` / `phone_stream` — `customParameters.voice_role` or `flow`
- `web_call.py` — session `flow` · UI `/app/test-call` dropdown
- `team.py` STAFF: `swara`, `ananya`, `riya`

## Test (free)

Web-call WS:
```json
{"type":"start","niche":"hospital_appointments","flow":"booking","client_name":"City Clinic"}
{"type":"start","niche":"dental_implants","flow":"reception","client_name":"Smile Dental"}
```

Phone: `voice_role=booking_agent` in stream customParameters.

## Booking tools

`function_calling.py`: `book_appointment`, `check_availability` — booking + reception roles get tool hint in prompt.

## Don't

- Marketing Advanced voice = **feature**, alag product nahi (ADR-009)
- Swara outbound sales script reception pe mat lagao — role alag prompt hai

Tune: `voice-agent-kb` + `test-agent` + `web-call-triage`

## Enterprise gate (persona config → live calls)
Operating loop — Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). **Change-risk tier: High-risk** — yeh personas reference nahi, LIVE outbound/inbound calls pe chalti hain (TelecallerBrain prompt + `vobiz_stream`/`phone_stream` `voice_role` param), isliye prompt/role change = telephony-grade.

**Compliance (fail-CLOSED — har role me intact):** har persona greeting me AI-disclosure ("ek AI assistant", TRAI) baked rahe; outbound roles (Swara/Ananya) TRAI 9am–7pm + DND fail-CLOSED + consent-ledger se bound (`compliance.py`) — role-prompt edit inko bypass na kare. Riya inbound = looser gate par disclosure phir bhi.

**Evidence (done):** role wiring change ke baad FREE web-call WS test (upar JSON) — opener + tools + disclosure correct + `python scripts/agent_tester.py` clean. Cross-path: naya role = TelecallerBrain + `vobiz_stream`/`phone_stream` + `web_call.py` + `team.py` STAFF sab me wire (ek miss = adhoora).
