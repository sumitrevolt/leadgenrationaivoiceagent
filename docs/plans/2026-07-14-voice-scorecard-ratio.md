# Voice scorecard talk/listen repair

## Goal and risk

Remove ratio-only false positives and enforce the already-documented 22-word spoken
reply limit where live evidence still shows 24–30-word turns. High-risk voice-runtime
change, but no provider, outbound-call, consent, DND, disclosure, or billing gate changes.

## Root cause

The evaluator used word share alone. A four-turn exchange with one-sentence bot replies
and user inputs such as `haan` inevitably reports 78–91% bot share even when each bot
turn is concise. After repairing that, live evidence showed deterministic soft-no and
injection deflections still exceeded the system prompt's 22-word rule. A proposed
global `_clean()` reduction was rejected by red regression tests because it removed
load-bearing WhatsApp close-signal sentences; the safe fix stays template-scoped.

## Files and proof

- `tests/test_qa_checks.py`: red-first concise-bot/terse-user regression.
- `app/voice_agent/qa_checks.py`: require both excessive word share and an excessive
  average bot-turn length; preserve the existing 40-word monologue failure.
- `app/voice_agent/intent_softno.py`, `app/voice_agent/telecaller_brain.py`: shorten
  deterministic close/guardrail lines without changing the shared `_clean()` contract.
- `tests/test_intent_softno.py`, `tests/test_voice_injection_guard.py`,
  `tests/test_telecaller_brain.py`: enforce template budgets and preserve close-signal contracts.
- Proof: focused QA tests and a fresh strict live synthetic WebSocket scorecard.

Rollback: revert the voice-scorecard commit, rebuild app/workers, and re-run the strict
WebSocket scorecard; no service state or customer data repair is needed.
