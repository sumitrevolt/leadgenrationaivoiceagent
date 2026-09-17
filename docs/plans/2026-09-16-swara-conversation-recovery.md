# Swara conversation recovery

Goal: restore responsive Smartflo inbound/outbound conversation without changing consent, disclosure, dial gates, billing or provider configuration.

Risk: high (live voice). Owner explicitly requested Swara repair; deployment/commit remains a separate repository gate. Rollback: revert only the reviewed Smartflo stream patch, preserving concurrent work. No production mutation in diagnosis.

Evidence: live systemd health production ab9b414e at 09:23Z; host checkout ad51142f (health label is not proof of loaded code). Sanitized 25-call sample: audio received, most sessions have no recognized user turns. Source: inline STT/reply blocks receive; Gemini/local STT imports do not exist. OmniRoute bulk timeouts may be post-call and are not attributed to spoken reply.

Ownership: primary agent edits app/telephony/smartflo_stream.py and tests/test_smartflo_conversation_recovery.py; adjusts existing callflow barge-in test to interrupt post-disclosure playback; isolates script-only no-dead-air tests from missing workstation credentials. Independent reviewer reads brain/provider paths and final diff only.

1. Red-first synthetic tests: paused speech/LLM work must not block receive/stop; utterance pauses retained; packet duration derived from bytes; empty STT advances fallback; real fallback helpers called; bounded failures; brain construction off event loop.
2. Implement one background turn per session, bounded audio accumulation and processing, cancellation on cleanup, truthful stage counters/timing, actual existing STT adapters. Preserve event protocol and compliance paths.
3. Verify new tests plus existing Smartflo callflow/audio/billing/disclosure suites, prod_check, secrets scan, diff check, voice scorecard (separate deployed vs local evidence). Fresh independent review.
4. Record exact results and remaining live release/call acceptance gate in progress and session handoff. No customer sends or test phone calls.

Wiring: existing Smartflo session serves both directions; no new routes, flags, scheduler jobs, providers or billing changes.
