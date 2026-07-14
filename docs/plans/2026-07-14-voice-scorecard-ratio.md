# Voice scorecard talk/listen repair

## Goal and risk

Remove a strict-scorecard false positive for concise replies to intentionally terse
scripted users while preserving detection of genuine long monologues. Tooling-only,
standard risk; no live prompt, call flow, provider, telephony, or compliance gate changes.

## Root cause

The evaluator used word share alone. A four-turn exchange with one-sentence bot replies
and user inputs such as `haan` inevitably reports 78–91% bot share even when each bot
turn is concise. The existing bad fixture proves a different failure: 40-word bot turns.

## Files and proof

- `tests/test_qa_checks.py`: red-first concise-bot/terse-user regression.
- `app/voice_agent/qa_checks.py`: require both excessive word share and an excessive
  average bot-turn length; preserve the existing 40-word monologue failure.
- Proof: focused QA tests and a fresh strict live synthetic WebSocket scorecard.

Rollback: revert these two files; no service state or customer data repair is needed.
