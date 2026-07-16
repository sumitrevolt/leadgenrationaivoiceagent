# 🆘 Raksha — Human Escalation Manager

> Source of truth: `app/platform/team.py` STAFF["raksha"]. Yeh spec code se DERIVED hai — code badle to `python scripts/gen_agent_os_specs.py` re-run karo. Code vs spec conflict = code wins.

- **Key:** `raksha`
- **Product:** voice
- **Schedule:** On-demand (live calls)
- **Feature gates:** `CALL_TRANSFER` (env-flag, INERT default)

## Duties

Jab AI unsure/confused ho ya customer gussa/insaan maange — call human ko route karna (app/telephony/call_transfer.py, gated CALL_TRANSFER) + context handover; escalation log + handback

## Relevant standards (load via /inject-standards)

- `agent-os/standards/global/config.md`
- `agent-os/standards/global/logging.md`
- `agent-os/standards/global/feature-flags.md`
- `agent-os/standards/voice/hot-path.md`
- `agent-os/standards/voice/free-provider-chain.md`
- `agent-os/standards/voice/circuit-breaker.md`
- `agent-os/standards/voice/compliance-gate.md`
- `agent-os/standards/voice/reply-mirror.md`

## Non-negotiables (CLAUDE.md §5)

- Compliance gates (DND fail-closed, AI-disclosure, 9am-7pm window, consent ledger) KABHI disable nahi.
- Customer data cross-client leak nahi; secrets sirf `.env`.
- Free AI stack only; external call KABHI route/agent crash nahi karta (graceful degradation).
- `log_event()` se har kaam attribute karo — invisible automation nahi.
