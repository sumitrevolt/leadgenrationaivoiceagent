# PB-VOICE-CALLING — Voice Calling Playbook (P0)

- **Purpose**: Run compliant outbound calling that converts — without breaking TRAI/carrier rules.
- **Trigger**: auto-dial run (11:30 IST daily) / manual call / voice campaign.
- **Scope**: lead feed -> DND/consent check -> call -> outcome -> follow-up.
- **Prereqs**: DLT_APPROVED=1, VOICE_LAUNCH_KILL=0, PLATFORM_DIAL_DAILY=1, cap=100/run, concurrency=1.

## Strategy
1. Feed: qualified leads from Hot Queue/prospect store (niche=all).
2. Compliance spine BEFORE anything: DND fail-closed, phone-type gate, AI-disclosure at start, 10-19 IST window.
3. Dial with Swara (Gemini voice LLM primary, EdgeTTS hi-IN, Groq STT) — free stack only.
4. Outcome capture: interested -> owner hot queue; not interested -> suppress; callback -> schedule.
5. Post-call owner-armed WA send (WHATSAPP_AUTO_SEND + POST_CALL_WHATSAPP) if interested.

## Decision tree
```
Lead before dial
├─ DND/consent/opt-out?     -> BLOCK (fail-closed) RB-VOICE-006
├─ outside window?          -> wait (10-19 IST)
├─ call fails: busy/auth/bal -> per runbook class (RB-VOICE-00x)
└─ call connects            -> Swara conversation -> outcome -> follow-up rail
```

## Allowed actions
- Dial within caps/window, log states, train pause (>30 failures), provider failover.

## Prohibited actions
- Cold auto-calls without DLT; calling outside window; AI-disclosure removal; concurrency>1; paid providers.

## Escalation
- Sustained high failure -> pause + RB-VOICE-008 (AMBER gate).

## KPIs
- Connect rate, qualified-interested rate, calls-to-close, ₹ per connected call.

## Guardrails
- DND fail-closed (lookup fail = block); recording gate; learned IVR blocklist; circuit breaker.

## Linked runbooks
RB-VOICE-001..010 (trunk, busy, auth, balance, stuck, rejection, provider outage, failure rate, latency, webhook).

## Evidence requirements
- Per call: session id, state, duration, outcome, audio (90-day retention rule).

## Owner approval conditions
- Any change to DLT/window/cap/compliance spine; provider wallet recharge.
