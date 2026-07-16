# 🧑‍💼 Boss — Manager (Supervisor)

> Source of truth: `app/platform/team.py` STAFF["manager"]. Yeh spec code se DERIVED hai — code badle to `python scripts/gen_agent_os_specs.py` re-run karo. Code vs spec conflict = code wins.

- **Key:** `manager`
- **Product:** platform
- **Schedule:** On-demand (har /api/agents/run pe)

## Duties

Kaam baantna — data/leads agents ko route karna (LangGraph), team coordination

## Relevant standards (load via /inject-standards)

- `agent-os/standards/global/config.md`
- `agent-os/standards/global/logging.md`
- `agent-os/standards/global/feature-flags.md`
- `agent-os/standards/backend/api-routers.md`
- `agent-os/standards/backend/auth.md`
- `agent-os/standards/backend/error-handling.md`
- `agent-os/standards/backend/lazy-imports.md`
- `agent-os/standards/backend/pydantic-models.md`

## Non-negotiables (CLAUDE.md §5)

- Compliance gates (DND fail-closed, AI-disclosure, 9am-7pm window, consent ledger) KABHI disable nahi.
- Customer data cross-client leak nahi; secrets sirf `.env`.
- Free AI stack only; external call KABHI route/agent crash nahi karta (graceful degradation).
- `log_event()` se har kaam attribute karo — invisible automation nahi.
