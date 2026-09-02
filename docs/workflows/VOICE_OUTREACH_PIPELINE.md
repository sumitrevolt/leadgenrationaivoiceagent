# Voice Outreach Pipeline — Production Contract

**Workflow ID:** `voice.outreach` · **Version:** 1 · **Owner:** Swara (Telecaller) + Tara (Voice Infra Ops)
**Trigger:** campaign / inbound / callback → `telephony/call_manager.py` / `vobiz_stream.py`
**Status:** code-certified; **commercially blocked** (Vobiz recharge + DID + DLT — user paperwork).

## State machine
```
QUEUED → DIALING → ANSWERED → IN_CALL → QUALIFIED → METERED → DOWNSTREAM_APPLIED  [terminal]
   │        │          │          │
   │        │          │          └─► HANGUP/AMD/VOICEMAIL ─► METERED (terminal)
   └────────┴──────────┴──────────────────────────────────► BLOCKED (DND/window/consent, terminal)
```
- **Compliance gates (never bypass):** DND **fail-closed** (`dnd_lookup_failed`=BLOCK), calling-window
  9am–7pm, AI-disclosure at greeting, 140-series/DLT for cold calls.

## Step → module map (real code)
| Step | Module | Idempotency |
|---|---|---|
| Dial | `telephony/vobiz_handler.VobizClient.place_call` | call id |
| Stream/STT/LLM/TTS | `telephony/vobiz_stream.py` (Groq STT · Gemini-voice · EdgeTTS) | session token |
| Qualify | `voice_agent/call_qualifier.py` (post-call AI) | call id |
| Meter | `telephony/post_call_hooks.meter_call_completion` | call id (idempotent) |
| Downstream | `post_call_hooks.apply_qualified_downstream` (CRM/sales/cadence) | call id |

## Validation & reliability
Distributed call-state (Redis, in-memory fallback). AMD → voicemail-drop/hangup.
Bounded awaits + THINK watchdog (dead-air guard). Cross-path parity guarded by
`scripts/cross_path_audit.py` (vobiz_stream `_cleanup` == call_manager parity).

## Events
`call.completed` (`billing/usage.py`) · `call.report.ready`.

## Metrics & alerts
`agent_events` · `llm_metrics` · Arjun QA scorecard (double/repeat/slow/long) · Tara hourly readiness · ntfy.

## Test matrix (E2E)
happy call · DND-block · window-block · provider failure (STT=0 fallback) · AMD/voicemail ·
qualify path · meter idempotency · downstream apply · barge/backchannel. Coverage:
`test_vobiz.py`, `test_voice_agent.py`, `test_cross_path_telephony.py`, `test_consent_ledger.py`, `test_ai_disclosure.py`.

## Runbook
[Provider Outage](../runbooks/RUNBOOK_PROVIDER_OUTAGE.md) · [Duplicate Outreach](../runbooks/RUNBOOK_DUPLICATE_OUTREACH.md).
