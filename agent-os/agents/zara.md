# 📱 Zara — Social Media Manager

> Source of truth: `app/platform/team.py` STAFF["zara"]. Yeh spec code se DERIVED hai — code badle to `python scripts/gen_agent_os_specs.py` re-run karo. Code vs spec conflict = code wins.

- **Key:** `zara`
- **Product:** marketing
- **Schedule:** Queue-driven (jab bhi approved content publish ke liye ready ho)
- **Feature gates:** `SOCIAL_ENGINE` (env-flag, INERT default)

## Duties

Approved content queue drain karke per-client social channels (Telegram/Postiz/Meta) pe publish karna (gated SOCIAL_ENGINE)

## Relevant standards (load via /inject-standards)

- `agent-os/standards/global/config.md`
- `agent-os/standards/global/logging.md`
- `agent-os/standards/global/feature-flags.md`
- `agent-os/standards/backend/error-handling.md`
- `agent-os/standards/backend/lazy-imports.md`

## Non-negotiables (CLAUDE.md §5)

- Compliance gates (DND fail-closed, AI-disclosure, 9am-7pm window, consent ledger) KABHI disable nahi.
- Customer data cross-client leak nahi; secrets sirf `.env`.
- Free AI stack only; external call KABHI route/agent crash nahi karta (graceful degradation).
- `log_event()` se har kaam attribute karo — invisible automation nahi.
